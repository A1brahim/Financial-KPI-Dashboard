from __future__ import annotations
import yfinance as yf, pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RAW, PROC = DATA_DIR / "raw", DATA_DIR / "processed"
RAW.mkdir(parents=True, exist_ok=True); PROC.mkdir(parents=True, exist_ok=True)

def _pick(df, names):
    """Return the first matching line item by any of the candidate names (case-insensitive)."""
    if df is None or df.empty:
        return None
    idx_map = {str(i).strip().lower(): i for i in df.index}
    for n in names:
        key = n.strip().lower()
        if key in idx_map:
            return df.loc[idx_map[key]]
    # also try relaxed contains match (handles small naming drifts)
    for key_low, real_idx in idx_map.items():
        if any(n.strip().lower() in key_low for n in names):
            return df.loc[real_idx]
    return None

def fetch(ticker: str):
    t = yf.Ticker(ticker)
    fin, bal, cfs = t.financials, t.balance_sheet, t.cashflow
    if fin is not None and not fin.empty: fin.to_csv(RAW / f"{ticker}_financials.csv")
    if bal is not None and not bal.empty: bal.to_csv(RAW / f"{ticker}_balance_sheet.csv")
    if cfs is not None and not cfs.empty: cfs.to_csv(RAW / f"{ticker}_cashflow.csv")
    return fin, bal

def compute_kpis(ticker: str) -> pd.DataFrame:
    fin, bal = fetch(ticker)
    if fin is None or fin.empty or bal is None or bal.empty:
        raise ValueError("Missing statements from yfinance for this ticker.")

    # ---- pick line items with broader fallbacks ----
    revenue        = _pick(fin, [
        "Total Revenue","Revenue","Sales","Operating Revenue"
    ])
    gross_profit   = _pick(fin, [
        "Gross Profit","Gross Income"
    ])
    operating_inc  = _pick(fin, [
        "Operating Income","EBIT","Earnings Before Interest and Taxes","Operating Profit"
    ])
    net_income     = _pick(fin, [
        "Net Income","Net Income Common Stockholders","Net Income From Continuing Operations","Profit Attributable To Owners"
    ])

    # Equity labels vary a lot across tickers/feeds
    equity         = _pick(bal, [
        "Total Stockholder Equity","Total Shareholder Equity","Total Equity",
        "Stockholders' Equity","Shareholders' Equity",
        "Total Equity Gross Minority Interest","Total Equity Net Minority Interest"
    ])

    # Debt fallbacks
    total_debt     = _pick(bal, [
        "Total Debt","Short Long Term Debt Total","Total Interest Bearing Debt",
        "Short Term Debt","Long Term Debt"
    ])

    # ---- build tidy frame ----
    df = pd.DataFrame({
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": operating_inc,
        "net_income": net_income,
        "total_equity": equity,
        "total_debt": total_debt,
    }).T.T
    df.index.name = "period_end"
    df = df.sort_index().astype("float64")

    # ---- core KPIs ----
    df["gross_margin_pct"]      = df["gross_profit"] / df["revenue"]
    df["operating_margin_pct"]  = df["operating_income"] / df["revenue"]
    df["net_margin_pct"]        = df["net_income"] / df["revenue"]

    # Use average equity for ROE when available; guard div-by-zero/NaN
    avg_equity = (df["total_equity"].shift(1) + df["total_equity"]) / 2
    df["roe_pct"] = df["net_income"] / avg_equity
    df.loc[(avg_equity == 0) | (avg_equity.isna()), "roe_pct"] = pd.NA

    # Leverage with guard
    df["debt_to_equity"] = df["total_debt"] / df["total_equity"]
    df.loc[(df["total_equity"] == 0) | (df["total_equity"].isna()), "debt_to_equity"] = pd.NA

    # Growth
    df["revenue_yoy"]    = df["revenue"].pct_change()
    df["net_income_yoy"] = df["net_income"].pct_change()

    out = PROC / f"{ticker}_kpis.csv"
    df.to_csv(out)
    return df

if __name__ == "__main__":
    print(compute_kpis("ULVR.L").tail(3)[["revenue","net_income","net_margin_pct","roe_pct","debt_to_equity"]])