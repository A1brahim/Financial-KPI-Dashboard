import streamlit as st
import pandas as pd
from pathlib import Path
from pipeline import compute_kpis

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
CATS = {
    "Consumer & Staples": {
        "Unilever (ULVR.L)": "ULVR.L",
        "Tesco (TSCO.L)": "TSCO.L",
        "Diageo (DGE.L)": "DGE.L",
        "Reckitt (RKT.L)": "RKT.L",
    },
    "Energy & Materials": {
        "Shell (SHEL.L)": "SHEL.L",
        "BP (BP.L)": "BP.L",
        "Rio Tinto (RIO.L)": "RIO.L",
    },
    "Healthcare": {
        "AstraZeneca (AZN.L)": "AZN.L",
        "GSK (GSK.L)": "GSK.L",
    },
    "Financials": {
        "Barclays (BARC.L)": "BARC.L",
        "HSBC (HSBA.L)": "HSBA.L",
        "Lloyds (LLOY.L)": "LLOY.L",
    },
    "Industrials/Utilities/Telecoms": {
        "BAE Systems (BA.L)": "BA.L",
        "RELX (REL.L)": "REL.L",
        "National Grid (NG.L)": "NG.L",
        "SSE (SSE.L)": "SSE.L",
        "Vodafone (VOD.L)": "VOD.L",
        "BT Group (BT-A.L)": "BT-A.L",
    },
}

# Flatten for functions that still expect a simple dict
UK = {name: tkr for group in CATS.values() for name, tkr in group.items()}

st.set_page_config(page_title="UK Financial KPI Dashboard", layout="wide")
st.title("🇬🇧 UK Financial KPI Dashboard")

# --- Helpers ---
@st.cache_data(show_spinner=False)
def load_kpis(tkr: str) -> pd.DataFrame:
    """Load processed KPIs from CSV if present; otherwise compute & save."""
    csv = DATA / f"{tkr}_kpis.csv"
    if csv.exists():
        df = pd.read_csv(csv, index_col=0, parse_dates=True)
    else:
        df = compute_kpis(tkr)
    # Ensure chronological order and consistent dtypes
    df = df.sort_index()
    return df


def fmt_big(x: float) -> str:
    try:
        val = float(x)
    except Exception:
        return "—"
    for unit in ["", "K", "M", "B", "T"]:
        if abs(val) < 1000.0:
            return f"{val:,.0f}{unit}"
        val /= 1000.0
    return f"{val:,.0f}T"

# --- Controls ---
# Category & company selectors
category = st.selectbox("Category", list(CATS.keys()), key="select_category")
options_in_cat = list(CATS[category].keys())
label = st.selectbox("Pick a company", options_in_cat, key="select_company")
ticker = CATS[category][label]

# Optional: force recompute (useful after code changes)
colr1, colr2 = st.columns([1,3])
with colr1:
    refresh = st.button("Refresh data", key="btn_refresh")

if refresh:
    # Recompute & overwrite the CSV, then clear cache
    _ = compute_kpis(ticker)
    load_kpis.clear()

df = load_kpis(ticker)
latest = df.iloc[-1]

# Friendly notice if ROE is missing
if pd.isna(latest.get("roe_pct", None)):
    st.info("ROE unavailable for the latest period (equity not found or zero). Try another ticker or open the Debug panel below.")

# --- KPI Cards ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Revenue (latest)", fmt_big(latest.get("revenue", float("nan"))))
c2.metric("Net Income (latest)", fmt_big(latest.get("net_income", float("nan"))))
net_margin_pct = latest.get("net_margin_pct", float("nan"))
roe_pct = latest.get("roe_pct", float("nan"))
c3.metric("Net Margin", f"{net_margin_pct*100:,.1f}%" if pd.notna(net_margin_pct) else "—")
c4.metric("ROE", f"{roe_pct*100:,.1f}%" if pd.notna(roe_pct) else "—")

# --- Charts ---
st.subheader("Profitability Trend")
cols_profit = [c for c in ["revenue", "net_income"] if c in df.columns]
if cols_profit:
    st.line_chart(df[cols_profit])
else:
    st.write("No profitability columns available to plot.")

st.subheader("Margins")
cols_margins = [c for c in ["gross_margin_pct", "operating_margin_pct", "net_margin_pct"] if c in df.columns]
if cols_margins:
    show_sector_avg_m = st.checkbox("Show sector average lines", value=True, key="avg_margins")
    plot_df_m = df[cols_margins].copy()
    if show_sector_avg_m:
        # Build sector average for the selected category over the same metrics
        peer_tickers = [CATS[category][n] for n in options_in_cat]
        peer_frames = []
        for tkr in peer_tickers:
            try:
                dfi = load_kpis(tkr)
                peer_frames.append(dfi[cols_margins])
            except Exception:
                pass
        if peer_frames:
            # Concatenate and compute mean across companies for each metric
            stacked = pd.concat([f.add_suffix(f"__{i}") for i, f in enumerate(peer_frames)], axis=1)
            for c in cols_margins:
                plot_df_m[f"{c} (sector avg)"] = stacked.filter(like=c).mean(axis=1)
    st.line_chart(plot_df_m)
else:
    st.write("No margin columns available to plot.")


st.subheader("Leverage")
if "debt_to_equity" in df.columns:
    show_sector_avg_l = st.checkbox("Show sector average line", value=True, key="avg_leverage")
    plot_df_l = df[["debt_to_equity"]].rename(columns={"debt_to_equity": "Debt/Equity"}).copy()
    if show_sector_avg_l:
        peer_tickers = [CATS[category][n] for n in options_in_cat]
        peer_frames = []
        for tkr in peer_tickers:
            try:
                dfi = load_kpis(tkr)
                if "debt_to_equity" in dfi.columns:
                    peer_frames.append(dfi[["debt_to_equity"]].rename(columns={"debt_to_equity": f"Debt/Equity__{tkr}"}))
            except Exception:
                pass
        if peer_frames:
            stacked = pd.concat(peer_frames, axis=1)
            plot_df_l["Debt/Equity (sector avg)"] = stacked.mean(axis=1)
    st.line_chart(plot_df_l)
else:
    st.write("Debt/Equity not available.")

# --- Peer comparison ---
st.subheader("Peer comparison (pick 1–3 companies)")
colp1, colp2 = st.columns([2,1])
with colp1:
    cross_cats = st.checkbox("Compare across all categories", value=False, key="chk_crosscats")

if cross_cats:
    peer_options = list(UK.keys())
else:
    peer_options = options_in_cat

choices = st.multiselect("Companies", peer_options, default=[label], key="ms_peers")

if choices:
    # Build a latest-metrics table
    rows = []
    for name in choices:
        tkr = UK[name]
        df_i = load_kpis(tkr)
        last = df_i.iloc[-1]
        rows.append({
            "Company": name,
            "Ticker": tkr,
            "Revenue": last.get("revenue", float("nan")),
            "Net Income": last.get("net_income", float("nan")),
            "Net Margin %": (last.get("net_margin_pct", float("nan")) or float("nan")) * 100,
            "ROE %": (last.get("roe_pct", float("nan")) or float("nan")) * 100,
            "Debt/Equity": last.get("debt_to_equity", float("nan")),
        })
    comp = pd.DataFrame(rows).set_index("Company")

    # --- Heatmap of latest KPIs ---
    st.subheader("Heatmap — latest KPIs")
    comp_num = comp.copy()
    metrics = ["Net Margin %", "ROE %", "Debt/Equity"]
    # Keep only the metrics that exist
    metrics = [m for m in metrics if m in comp_num.columns]
    if metrics and not comp_num.empty:
        normalize = st.checkbox("Normalize per metric (z-score)", value=True)
        plot_df_h = comp_num[metrics].copy()
        # z-score by column if requested
        if normalize:
            plot_df_h = (plot_df_h - plot_df_h.mean()) / plot_df_h.std(ddof=0)
        try:
            import plotly.express as px
            fig = px.imshow(
                plot_df_h,
                x=metrics,
                y=plot_df_h.index,
                text_auto=".1f",
                aspect="auto",
                origin="lower",
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            # Fallback: show the numeric table if plotly is unavailable
            st.dataframe(plot_df_h)
    else:
        st.write("No comparable metrics available for heatmap.")

    # Show table with formatted large numbers
    st.dataframe(
        comp.assign(
            **{
                "Revenue": comp["Revenue"].apply(fmt_big),
                "Net Income": comp["Net Income"].apply(fmt_big),
                "Net Margin %": comp["Net Margin %"].map(lambda x: f"{x:,.1f}%" if pd.notna(x) else "—"),
                "ROE %": comp["ROE %"].map(lambda x: f"{x:,.1f}%" if pd.notna(x) else "—"),
                "Debt/Equity": comp["Debt/Equity"].map(lambda x: f"{x:,.2f}" if pd.notna(x) else "—"),
            }
        )
    )

    # Simple bar charts for ROE and Net Margin
    st.write("")
    st.caption("Bars show latest available values")
    cols = st.columns(2)
    with cols[0]:
        if comp["ROE %"].notna().any():
            st.bar_chart(comp["ROE %"])  # already in %, numeric
        else:
            st.write("ROE not available for selected companies.")
    with cols[1]:
        if comp["Net Margin %"].notna().any():
            st.bar_chart(comp["Net Margin %"])  # already in %, numeric
        else:
            st.write("Net margin not available for selected companies.")

    # Download button for raw comparison data
    csv_bytes = comp.to_csv().encode("utf-8")
    st.download_button(
        label="Download comparison CSV",
        data=csv_bytes,
        file_name="kpi_comparison_latest.csv",
        mime="text/csv",
    )

# --- Debug panel ---
with st.expander("Debug: show available line items"):
    import yfinance as yf
    t = yf.Ticker(ticker)
    fin = t.financials
    bal = t.balance_sheet
    st.write("**Income statement index (first 20):**")
    if fin is not None and not fin.empty:
        st.write(list(map(str, fin.index[:20])))
    else:
        st.write("No income statement returned.")

    st.write("**Balance sheet index (first 30):**")
    if bal is not None and not bal.empty:
        st.write(list(map(str, bal.index[:30])))
    else:
        st.write("No balance sheet returned.")