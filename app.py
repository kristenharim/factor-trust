"""
Factor Trust — Streamlit frontend over the validated engine.

engine.py is the source of numerical truth and is untouched by this file: this
script only wires widgets to its three functions (simulate / sweep_n /
from_spectrum) and draws what they return.

Walkthrough: 14-Lab/working/factor-trust — Streamlit rebuild walkthrough.md
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

import engine

# ------------------------------------------------------------------ page + theme
st.set_page_config(page_title="Factor Trust", layout="wide")

st.markdown("""
<style>
  #MainMenu, footer, [data-testid="stDecoration"],
  [data-testid="stToolbar"], [data-testid="stAppDeployButton"] { display: none; }
  .block-container { padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1400px; }
  [data-testid="stMetricValue"] { font-size: 1.9rem; font-variant-numeric: tabular-nums; }
  [data-testid="stMetricLabel"] { text-transform: uppercase; letter-spacing: .08em; font-size: .7rem; opacity: .65; }
  [data-testid="stSidebar"] { border-right: 1px solid #30363d; }
  table, .stDataFrame { font-variant-numeric: tabular-nums; }
  h1 { font-size: 1.35rem !important; font-weight: 600; letter-spacing: -.01em; }
  h2, h3 { font-size: 1rem !important; text-transform: uppercase; letter-spacing: .06em; opacity: .8; }
</style>
""", unsafe_allow_html=True)

st.title("Factor Trust — how much should you trust your PCA factors?")

FACTOR_COLORS = ["#8ec0f5", "#34b38a", "#d9a53f", "#a793ec"]
DEFAULT_VOLS = [16.0, 8.0, 6.0, 5.0]      # paper Table 1, annualized %
DEFAULT_PREVS = [1.25, 1.0, 1.0, 1.0]     # paper G_B diagonal

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    mode = st.radio("Input mode", ["Model calibration", "Sample spectrum"])
    n = int(st.number_input("observations n", min_value=8, max_value=504, value=63))
    p = int(st.number_input("assets p", min_value=20, max_value=100_000, value=3000, step=100))
    k = int(st.number_input("factors k", min_value=1, max_value=4, value=3))
    dist = st.selectbox("factor return distribution", ["Student-t (6 df)", "Normal"])
    reps = int(st.select_slider("simulations", options=[200, 400, 1000, 2000], value=400))

    if mode == "Model calibration":
        vols = [st.number_input(f"factor {j+1} vol %", value=DEFAULT_VOLS[j],
                                min_value=0.1, step=0.5) for j in range(k)]
        prevs = [st.number_input(f"factor {j+1} prevalence", value=DEFAULT_PREVS[j],
                                 min_value=0.05, step=0.05) for j in range(k)]
        idio = st.number_input("idiosyncratic vol %", value=40.0, min_value=1.0, step=1.0)
    else:
        eig_text = st.text_area(
            "paste ALL n eigenvalues of your sample covariance (comma/space separated)",
            height=120,
            placeholder="0.034, 0.0088, 0.006, 0.0026, 0.0025, 0.0024, 0.0023, 0.0027")
        st.caption("Used as a **spectrum-matched plug-in scenario**: implied SNRⱼ = θⱼ/ℓ − 1 "
                   "calibrates the simulation. θ and ℓ carry sampling noise, so this is a "
                   "scenario, not an inversion.")

dist_key = "t" if dist.startswith("Student") else "normal"

# ------------------------------------------------------------------ inputs -> engine args
if mode == "Model calibration":
    a = [(v / 100) ** 2 * c for v, c in zip(vols, prevs)]
    d2 = (idio / 100) ** 2
    spectrum = None
else:
    try:
        eigs = [float(x) for x in eig_text.replace(",", " ").split()]
    except ValueError:
        st.error("Could not parse those eigenvalues — numbers separated by commas or spaces only.")
        st.stop()
    try:
        spectrum = engine.from_spectrum(eigs, n, k)
    except ValueError as e:
        st.error(str(e))
        st.stop()
    a, d2 = spectrum["a"], spectrum["d2"]


# ------------------------------------------------------------------ cached engine calls
@st.cache_data(show_spinner="simulating…")
def run_sim(p, n, k, a, d2, dist, reps):
    return engine.simulate(p, n, k, list(a), d2, dist, 6, reps)


@st.cache_data(show_spinner="sweeping…")
def run_sweep(p, k, a, d2, dist, reps=250):
    return engine.sweep_n(p, [21, 42, 63, 126, 189, 252, 378, 504], k, list(a), d2, dist, 6, reps)


r = run_sim(p, n, k, tuple(a), float(d2), dist_key, reps)

q = lambda pct, j: r["quantiles"][str(pct)][j]
floor_of = lambda j: spectrum["floor_measured"][j] if spectrum else r["floor_plugin_median"][j]
snr_of = lambda j: spectrum["snr"][j] if spectrum else r["snr"][j]

# ------------------------------------------------------------------ KPI cards
cols = st.columns(k)
for j in range(k):
    with cols[j]:
        st.metric(f"Factor {j+1}", f"< {q(0.9, j):.0f}° @ 90%")
        st.caption(f"median {q(0.5, j):.1f}° · floor {floor_of(j):.1f}° · "
                   f"SNR {snr_of(j):.1f} · swap {r['swap_rate'][j]*100:.1f}%")

# ------------------------------------------------------------------ fan chart
fig = go.Figure()
for j in range(k):
    y = k - j
    for lo, hi, width, color in [(0.025, 0.975, 8, "#1f3350"),
                                 (0.10, 0.90, 16, "#2b4f7e"),
                                 (0.25, 0.75, 24, "#3f76b8")]:
        fig.add_shape(type="line", x0=q(lo, j), x1=q(hi, j), y0=y, y1=y,
                      line=dict(color=color, width=width))
    fig.add_shape(type="line", x0=r["floor_asymptotic"][j], x1=r["floor_asymptotic"][j],
                  y0=y - 0.25, y1=y + 0.25, line=dict(color="#77808d", width=1.6, dash="dash"))
    fig.add_shape(type="line", x0=floor_of(j), x1=floor_of(j), y0=y - 0.25, y1=y + 0.25,
                  line=dict(color="#e8703a", width=3))
    fig.add_trace(go.Scatter(
        x=[q(0.5, j)], y=[y], mode="markers",
        marker=dict(color="#9ecbf7", size=9, line=dict(color="#0d1117", width=2)),
        hovertemplate=(f"<b>Factor {j+1}</b><br>median %{{x:.1f}}°<br>"
                       f"50% band {q(0.25, j):.1f}–{q(0.75, j):.1f}°<br>"
                       f"80% band {q(0.10, j):.1f}–{q(0.90, j):.1f}°<br>"
                       f"95% band {q(0.025, j):.1f}–{q(0.975, j):.1f}°<br>"
                       f"floor {floor_of(j):.1f}°<extra></extra>")))
    fig.add_annotation(xref="paper", x=0, y=y, text=f"Factor {j+1}", showarrow=False,
                       xanchor="right", xshift=-10,
                       font=dict(color=FACTOR_COLORS[j], size=13))

fig.update_xaxes(range=[0, 90], title="angle between estimated and true factor direction (°)",
                 gridcolor="#21262d", zeroline=False)
fig.update_yaxes(showticklabels=False, range=[0.4, k + 0.6],
                 gridcolor="rgba(0,0,0,0)", zeroline=False)
fig.update_layout(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="monospace", size=12),
    margin=dict(l=90, r=10, t=30, b=10),
    height=90 * k + 90,
    showlegend=False,
)
st.plotly_chart(fig, width="stretch")

st.caption(
    "Orange tick = observable floor "
    + ("(measured from YOUR eigenvalues). " if spectrum
       else "(median plug-in asymptotic floor, simulated). ")
    + "Dashed gray = asymptotic formula. Blue bands = 50/80/95% simulated outcomes under your "
    "stated assumptions — a conditional Monte Carlo distribution, **not a confidence interval**. "
    "The gap between the floor and the bands is the in-subspace rotation term, which is provably "
    "not estimable from data alone."
)

# ------------------------------------------------------------------ quantile table + export
df = pd.DataFrame([{
    "factor": f"Factor {j+1}",
    "floor°": round(floor_of(j), 1),
    "asym°": round(r["floor_asymptotic"][j], 1),
    "q50°": round(q(0.5, j), 1),
    "q80°": round(q(0.8, j), 1),
    "q90°": round(q(0.9, j), 1),
    "q95°": round(q(0.95, j), 1),
    "swap_rate": r["swap_rate"][j],
} for j in range(k)])

st.dataframe(df, hide_index=True, width="stretch")

c1, c2, _ = st.columns([1, 1, 4])
with c1:
    st.download_button("Download CSV", df.to_csv(index=False), file_name="factor-trust.csv")
with c2:
    st.download_button("Download JSON", pd.Series(r).to_json(), file_name="factor-trust.json")

# ------------------------------------------------------------------ required-history sweep
st.subheader("Required history")
target = int(st.number_input("target: q90 error ≤ (degrees)", min_value=1, max_value=89, value=20))

if st.button("Run sweep"):
    sw = run_sweep(p, k, tuple(a), float(d2), dist_key)

    sweep_fig = go.Figure()
    for j in range(k):
        sweep_fig.add_trace(go.Scatter(
            x=sw["n"], y=[row[j] for row in sw["q90"]],
            mode="lines+markers", name=f"Factor {j+1}",
            line=dict(color=FACTOR_COLORS[j], width=2),
            hovertemplate=f"Factor {j+1} · n=%{{x}}<br>q90 %{{y:.1f}}°<extra></extra>"))
    sweep_fig.add_hline(y=target, line_dash="dash", line_color="#e05d5d",
                        annotation_text=f"target {target}°",
                        annotation_font=dict(color="#e05d5d"))
    sweep_fig.update_xaxes(title="observations n (days)", gridcolor="#21262d", zeroline=False)
    sweep_fig.update_yaxes(title="q90 error (°)", range=[0, 90], gridcolor="#21262d", zeroline=False)
    sweep_fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="monospace", size=12),
        margin=dict(l=10, r=10, t=30, b=10),
        height=340,
        legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(sweep_fig, width="stretch")

    for j in range(k):
        hit = next((nn for nn, row in zip(sw["n"], sw["q90"]) if row[j] <= target), None)
        floor_j = sw["floor"][-1][j]
        if hit:
            st.write(f"**Factor {j+1}:** reaches target at n ≥ {hit}")
        elif floor_j > target:
            st.write(f"**Factor {j+1}:** ⚠️ unreachable at any n — the observable floor "
                     f"({floor_j:.1f}°) already exceeds your target")
        else:
            st.write(f"**Factor {j+1}:** not reached within the tested range (n ≤ {sw['n'][-1]})")

# ------------------------------------------------------------------ validation footer
if mode == "Model calibration" and p == 3000 and n == 63 and k == 3 and dist_key == "t":
    st.caption(
        "Cross-checked against the reference engine at this exact calibration (n=63, p=3000, k=3, "
        "Student-t): reference q50/q90 = 16.7°/19.8° (factor 1), 34.9°/46.4° (factor 2), "
        "44.1°/51.6° (factor 3). This run: "
        + ", ".join(f"{q(0.5, j):.1f}°/{q(0.9, j):.1f}°" for j in range(k)) + "."
    )
