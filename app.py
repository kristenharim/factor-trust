"""
Factor Trust — Streamlit frontend over the validated engine.

engine.py is the source of numerical truth and is untouched by this file: this
script only wires widgets to its three functions (simulate / sweep_n /
from_spectrum) and draws what they return.

Walkthrough: 14-Lab/working/factor-trust — Streamlit rebuild walkthrough.md
"""
import hashlib
import math
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

import calibration
import engine

# st.cache_data keys on a function's args and its own body — NOT on engine.py.
# Edit the engine and a warm cache serves the old payload: here that surfaced as
# a KeyError, but a change to the *math* with the same keys would silently serve
# stale numbers that still look authoritative, which for this tool is the worst
# failure available. Tie the cache key to the engine's actual bytes.
ENGINE_FINGERPRINT = hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()[:12]

# ------------------------------------------------------------------ page + theme
st.set_page_config(page_title="factor-trust", layout="wide")

# Most of the look lives in .streamlit/config.toml (mono font, square corners,
# hairline borders). This only covers what the theme system can't reach.
st.markdown("""
<style>
  #MainMenu, footer, [data-testid="stDecoration"],
  [data-testid="stToolbar"], [data-testid="stAppDeployButton"] { display: none; }
  /* stHeader is a 48.75px opaque bar at z-index 999990: it paints over the top of
     the page, so content must clear it and it must not show as a band. */
  [data-testid="stHeader"] { background: transparent; }
  .block-container { padding-top: 4rem; padding-bottom: 4rem; max-width: 1180px; }

  /* type-in fields, not spinner widgets */
  [data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] { display: none; }
  [data-testid="stSidebar"] label p { font-size: .78rem; opacity: .7; letter-spacing: .04em; }
  [data-testid="stSidebar"] .block-container { padding-top: 1rem; }

  /* section rules: LABEL ───────────── */
  .rule { display: flex; align-items: center; gap: .7rem; margin: 1.9rem 0 .7rem;
          font-size: .68rem; text-transform: uppercase; letter-spacing: .14em; opacity: .45; }
  .rule::after { content: ""; flex: 1; height: 1px; background: #222a33; }

  /* header */
  .hdr { display: flex; align-items: baseline; gap: .8rem; }
  .hdr b { font-size: 1.05rem; font-weight: 700; letter-spacing: -.01em; color: #e6edf3; }
  .hdr span { font-size: .75rem; opacity: .45; }
  .spec { margin: .45rem 0 .2rem; padding: .35rem 0; font-size: .74rem; opacity: .5;
          border-top: 1px solid #222a33; border-bottom: 1px solid #222a33; }
  .spec i { font-style: normal; color: #e6edf3; opacity: .85; }

  /* headline: one line, not three cards */
  .verdict { display: flex; align-items: baseline; gap: 1.6rem; flex-wrap: wrap;
             margin: 1.1rem 0 .2rem; }
  .verdict .lbl { font-size: .68rem; text-transform: uppercase; letter-spacing: .12em; opacity: .45; }
  .verdict .v { font-size: 1.5rem; font-weight: 500; font-variant-numeric: tabular-nums; }
  .verdict .v u { text-decoration: none; font-size: .7rem; opacity: .5; margin-right: .35rem; }

  /* table reads as fixed-width tool output */
  [data-testid="stTable"] table { border-collapse: collapse; }
  [data-testid="stTable"] thead th { text-transform: uppercase; font-size: .66rem; font-weight: 500;
                                     letter-spacing: .1em; opacity: .5; text-align: right;
                                     border-bottom: 1px solid #2c3641; padding: .3rem .7rem; }
  [data-testid="stTable"] td { text-align: right; font-variant-numeric: tabular-nums;
                               padding: .28rem .7rem; border-bottom: 1px solid #161c23; }
  [data-testid="stTable"] tbody th { text-align: left; opacity: .75; font-weight: 400;
                                     padding: .28rem .7rem; border-bottom: 1px solid #161c23; }

  /* max-width in rem, not ch: ch scales with this element's own small font-size,
     which collapsed the column to ~427px. */
  .note { font-size: .8rem; line-height: 1.55; opacity: .6; max-width: 54rem; }
  .note b { color: #b6bfc9; font-weight: 500; opacity: .9; }
  .note i { font-style: italic; opacity: .85; }

  /* methodology prose: reference material, not a landing page — default h4 and
     body sizes shout next to the .68rem section rules */
  [data-testid="stExpander"] summary { font-size: .78rem; }
  [data-testid="stExpander"] h4 { font-size: .7rem !important; text-transform: uppercase;
                                  letter-spacing: .12em; opacity: .55; font-weight: 500;
                                  margin: 1.8rem 0 .6rem; }
  [data-testid="stExpander"] p, [data-testid="stExpander"] li { font-size: .8rem;
                                  line-height: 1.55; max-width: 54rem; }
  [data-testid="stExpander"] td, [data-testid="stExpander"] th { font-size: .74rem;
                                  line-height: 1.45; }

  /* chart legend: swatches shaped like the marks they stand for */
  .sw { display: inline-block; vertical-align: middle; margin: 0 .35rem 0 0; }
  .sw.tick { width: 2px; height: 11px; background: #d98a3a; }
  .sw.dot { width: 0; height: 11px; border-left: 2px dotted #6b7683; }
  .sw.band { width: 15px; height: 8px; background: #38465a; }
</style>
""", unsafe_allow_html=True)

FACTOR_COLORS = ["#5b91c9", "#4a9d6a", "#d98a3a", "#9d84cc"]
BAND_COLORS = ["#1c242e", "#28323e", "#38465a"]   # 95 / 80 / 50 %
REPO = "https://github.com/kristenharim/factor-trust"

# Calibration defaults, the sweep grid and the precomputed sweep all live in
# calibration.py, which imports no streamlit so the cache builder can share them.
DEFAULT_VOLS = calibration.DEFAULT_VOLS    # paper Table 1, annualized %
DEFAULT_PREVS = calibration.DEFAULT_PREVS  # paper G_B diagonal
SWEEP_GRID = calibration.SWEEP_GRID
SWEEP_REPS = calibration.LIVE_REPS


def resid_var_pct(angle_deg):
    """Fraction of the factor's directional variance a book neutralized on the
    ESTIMATED direction still carries: sin² of the angle to the true one."""
    return math.sin(math.radians(angle_deg)) ** 2 * 100


def rule(label):
    st.markdown(f'<div class="rule">{label}</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown('<div class="rule">input</div>', unsafe_allow_html=True)
    mode = st.radio("mode", ["model calibration", "sample spectrum"], label_visibility="collapsed")
    n = int(st.number_input("n · observations", min_value=8, max_value=504, value=63))
    p = int(st.number_input("p · assets", min_value=20, max_value=100_000, value=3000, step=100))
    k = int(st.number_input("k · factors", min_value=1, max_value=4, value=3))
    dist = st.selectbox("factor return distribution", ["Student-t (6 df)", "Normal"])
    reps = int(st.select_slider("simulations", options=[200, 400, 1000, 2000], value=400))

    if mode == "model calibration":
        st.markdown('<div class="rule">calibration</div>', unsafe_allow_html=True)
        vols = [st.number_input(f"f{j+1} vol %", value=DEFAULT_VOLS[j],
                                min_value=0.1, step=0.5) for j in range(k)]
        prevs = [st.number_input(f"f{j+1} prevalence", value=DEFAULT_PREVS[j],
                                 min_value=0.05, step=0.05) for j in range(k)]
        idio = st.number_input("idiosyncratic vol %", value=40.0, min_value=1.0, step=1.0)
    else:
        st.markdown('<div class="rule">spectrum</div>', unsafe_allow_html=True)
        eig_text = st.text_area(
            "all n eigenvalues of your sample covariance",
            height=120,
            placeholder="0.034, 0.0088, 0.006, 0.0026, 0.0025, 0.0024, 0.0023, 0.0027")
        st.caption("Spectrum-matched plug-in scenario: implied SNRⱼ = θⱼ/ℓ − 1 calibrates the "
                   "simulation. θ and ℓ carry sampling noise, so this is a scenario, not an "
                   "inversion.")

dist_key = "t" if dist.startswith("Student") else "normal"

# ------------------------------------------------------------------ inputs -> engine args
if mode == "model calibration":
    # via calibration so the app and the cache builder derive a/d2 identically —
    # any drift here would silently miss the cache and cost minutes
    a, d2 = calibration.engine_args(vols, prevs, idio)
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
def run_sim(p, n, k, a, d2, dist, reps, engine_fp):
    return engine.simulate(p, n, k, list(a), d2, dist, 6, reps)


@st.cache_data(show_spinner=False)
def run_sweep(p, k, a, d2, dist, engine_fp, reps=SWEEP_REPS):
    """Precomputed for the paper calibration, live for anything else.

    Live is the slow path by a wide margin: eigendecomposition is O(n^3), so the
    n=252 point alone costs ~60x the n=63 one, and the free tier runs ~100-300x
    slower than a laptop. Progress-reported for exactly that reason."""
    cached, _ = calibration.load(p, k, list(a), d2, dist)
    if cached is not None:
        return cached
    bar = st.progress(0.0, "sweeping…")
    sw = engine.sweep_n(
        p, SWEEP_GRID, k, list(a), d2, dist, 6, reps,
        on_point=lambda done, total, n: bar.progress(done / total, f"sweeping… n={n}"))
    bar.empty()
    return sw


r = run_sim(p, n, k, tuple(a), float(d2), dist_key, reps, ENGINE_FINGERPRINT)

q = lambda pct, j: r["quantiles"][str(pct)][j]
floor_of = lambda j: spectrum["floor_measured"][j] if spectrum else r["floor_plugin_median"][j]
snr_of = lambda j: spectrum["snr"][j] if spectrum else r["snr"][j]
sub_q = lambda lab, pct: r["subspace"][lab]["quantiles"][str(pct)]

# A label is only a label if the estimator can hold onto it. Above this much
# mutual confusion the named directions are not identified and only their span
# is: at an exact tie PCA cannot separate two factors at all (any rotation
# within the plane is an equally valid eigenbasis), and the per-factor angle
# degrades to ~random while the span stays sharp.
TIE_TOL = 0.05


def tied_runs(confusion, k):
    """Adjacent factors the estimator confuses with each other, merged into runs.

    Adjacent only: eigenvalue ranking can only confuse neighbours."""
    # max, not sum: a swap puts h_j on b_j+1 AND h_j+1 on b_j on the SAME path,
    # so adding the two directions double-counts the paths that swapped.
    mutual = [max(confusion[j][j + 1], confusion[j + 1][j]) for j in range(k - 1)]
    runs = []
    for j, m in enumerate(mutual):
        if m <= TIE_TOL:
            continue
        if runs and runs[-1][-1] == j:
            runs[-1] = runs[-1] + (j + 1,)
        else:
            runs.append((j, j + 1))
    return runs, mutual


ties, mutual_conf = tied_runs(r["confusion"], k)
tied_idx = {j for g in ties for j in g}


def headline_entries():
    """Per factor, except that a tied run speaks once, as its span. Printing
    'f2 44°' next to 'f3 50°' for two factors the estimator swaps 1 path in 15
    is a bare scalar dressed as a measurement."""
    out, j = [], 0
    while j < k:
        run = next((g for g in ties if g[0] == j), None)
        if run:
            lab = engine.group_label(run)
            out.append((f"{lab} span", sub_q(lab, 0.9), FACTOR_COLORS[run[0]]))
            j = run[-1] + 1
        elif j in tied_idx:
            j += 1
        else:
            out.append((f"f{j+1}", q(0.9, j), FACTOR_COLORS[j]))
            j += 1
    return out

# ------------------------------------------------------------------ header + spec echo
st.markdown(
    '<div class="hdr"><b>factor-trust</b>'
    '<span>angle error of PCA factors under your calibration</span></div>'
    f'<div class="spec">n=<i>{n}</i> &nbsp; p=<i>{p}</i> &nbsp; k=<i>{k}</i> &nbsp; '
    f'dist=<i>{dist_key}</i> &nbsp; reps=<i>{reps}</i> &nbsp; seed=<i>{r["seed"]}</i> &nbsp; '
    f'src=<i>{"spectrum" if spectrum else "model"}</i></div>',
    unsafe_allow_html=True)

# ------------------------------------------------------------------ headline
st.markdown(
    '<div class="verdict"><span class="lbl">90% of runs<br>land within</span>'
    + "".join(f'<span class="v" style="color:{color}"><u>{lab}</u>{val:.0f}°</span>'
              for lab, val, color in headline_entries())
    + "</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ fan chart
rule("[1] error distribution")

fig = go.Figure()
for j in range(k):
    y = k - j
    for (lo, hi), width, color in zip([(0.025, 0.975), (0.10, 0.90), (0.25, 0.75)],
                                      [7, 15, 23], BAND_COLORS):
        fig.add_shape(type="line", x0=q(lo, j), x1=q(hi, j), y0=y, y1=y,
                      line=dict(color=color, width=width))
    fig.add_shape(type="line", x0=r["floor_asymptotic"][j], x1=r["floor_asymptotic"][j],
                  y0=y - 0.28, y1=y + 0.28, line=dict(color="#6b7683", width=1, dash="dot"))
    fig.add_shape(type="line", x0=floor_of(j), x1=floor_of(j), y0=y - 0.28, y1=y + 0.28,
                  line=dict(color="#d98a3a", width=2))
    fig.add_trace(go.Scatter(
        x=[q(0.5, j)], y=[y], mode="markers",
        marker=dict(color=FACTOR_COLORS[j], size=8, symbol="line-ns",
                    line=dict(color=FACTOR_COLORS[j], width=2.5)),
        hovertemplate=(f"<b>f{j+1}</b><br>median %{{x:.1f}}°<br>"
                       f"50% band {q(0.25, j):.1f}–{q(0.75, j):.1f}°<br>"
                       f"80% band {q(0.10, j):.1f}–{q(0.90, j):.1f}°<br>"
                       f"95% band {q(0.025, j):.1f}–{q(0.975, j):.1f}°<br>"
                       f"floor {floor_of(j):.1f}°<extra></extra>")))
    fig.add_annotation(xref="paper", x=0, y=y, text=f"f{j+1}", showarrow=False,
                       xanchor="right", xshift=-8,
                       font=dict(color=FACTOR_COLORS[j], size=12))

fig.update_xaxes(range=[0, 90], dtick=15, title="angle between estimated and true direction (°)",
                 title_font=dict(size=11), gridcolor="#161c23", zeroline=False,
                 ticks="outside", ticklen=4, tickcolor="#2c3641", showline=True,
                 linecolor="#2c3641", tickfont=dict(size=11))
fig.update_yaxes(showticklabels=False, range=[0.45, k + 0.55],
                 gridcolor="rgba(0,0,0,0)", zeroline=False)
fig.update_layout(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="JetBrains Mono, monospace", size=12, color="#b6bfc9"),
    margin=dict(l=48, r=8, t=8, b=8),
    height=62 * k + 80,
    showlegend=False,
)
st.plotly_chart(fig, width="stretch")

st.markdown(
    '<div class="note">'
    '<span class="sw tick"></span>observable floor '
    + ("(measured from your eigenvalues)" if spectrum else "(median plug-in, simulated)")
    + '&nbsp;&nbsp;&nbsp; <span class="sw dot"></span>asymptotic formula'
      '&nbsp;&nbsp;&nbsp; <span class="sw band"></span>50/80/95% of simulated runs'
      "<br>Bands are a conditional Monte Carlo distribution under your stated assumptions, "
    "<b>not a confidence interval</b>. The gap between floor and bands is the in-subspace "
    "rotation term, which is provably not estimable from data alone."
    "</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ quantile table + export
rule("[2] readout")

df = pd.DataFrame([{
    "factor": f"f{j+1}",
    "snr": round(snr_of(j), 1),
    "floor°": round(floor_of(j), 1),
    "asym°": round(r["floor_asymptotic"][j], 1),
    "q50°": round(q(0.5, j), 1),
    "q80°": round(q(0.8, j), 1),
    "q90°": round(q(0.9, j), 1),
    "q95°": round(q(0.95, j), 1),
    "resid%@q90": round(resid_var_pct(q(0.9, j)), 0),
    "swap%": round(r["swap_rate"][j] * 100, 1),
} for j in range(k)])

# :g strips pandas' trailing zeros (12.6000 -> 12.6); df itself stays numeric for export
st.table(df.set_index("factor").map(lambda v: f"{v:g}"))

# The tie warning sits directly under the rows it disqualifies, not below the
# consequence text — a reader who stops at the table must still see it.
for run in ties:
    lab = engine.group_label(run)
    names = " and ".join(f"f{j+1}" for j in run)
    worst = max(q(0.9, j) for j in run)
    pair_conf = max(mutual_conf[j] for j in range(run[0], run[-1])) * 100
    st.markdown(
        f'<div class="note" style="margin:.5rem 0 0">'
        f'<b style="color:#d98a3a">[tied] {names} are not separately identified.</b> '
        f'The estimator swaps their labels on <b>{pair_conf:.1f}%</b> of paths, '
        f'so the rows above describe directions it cannot reliably tell apart — at an exact '
        f'tie those per-factor angles degrade toward a random direction while still printing '
        f'as if they were measurements. What survives is their {len(run)}-D span, known to '
        f'<b>{sub_q(lab, 0.9):.1f}°</b> at q90 against <b>{worst:.1f}°</b> for the worst '
        f'named direction in it. <b>Hedge the span, not the named direction.</b>'
        "</div>", unsafe_allow_html=True)

st.markdown(
    '<div class="note">'
    + "<br>".join(
        f'<span style="color:{FACTOR_COLORS[j]}">f{j+1}</span> &nbsp; at q90 = '
        f'<b>{q(0.9, j):.1f}°</b>, a book neutralized on the <i>estimated</i> f{j+1} '
        f'direction still carries <b>≈{resid_var_pct(q(0.9, j)):.0f}%</b> of f{j+1} '
        "directional variance." + (" <b>Not usable alone — see [tied] above.</b>"
                                   if j in tied_idx else "") for j in range(k))
    + "".join(
        f'<br><span style="color:{FACTOR_COLORS[g[0]]}">{engine.group_label(g)}</span> &nbsp; '
        f'at q90 = <b>{sub_q(engine.group_label(g), 0.9):.1f}°</b>, a book neutralized on the '
        f'estimated <i>span</i> still carries <b>≈{resid_var_pct(sub_q(engine.group_label(g), 0.9)):.0f}%</b> '
        "of the worst-case in-span factor variance." for g in ties)
    + "<br><br>Residual variance fraction = sin² of the angle, under an "
      "<b>idealized projection</b>: exact orthogonal neutralization on the estimated "
      "direction, no costs, no error in the hedge ratio itself. It is a restatement of "
      "the same conditional scenario in variance units, <b>not an independent "
      "measurement</b> — and deliberately not basis points, which would require your "
      "actual holdings and covariance."
    "</div>", unsafe_allow_html=True)

c1, c2, _ = st.columns([1, 1, 5])
with c1:
    st.download_button("export csv", df.to_csv(index=False),
                       file_name="factor-trust.csv", width="stretch")
with c2:
    st.download_button("export json", pd.Series(r).to_json(),
                       file_name="factor-trust.json", width="stretch")

# ------------------------------------------------------------------ required-history sweep
rule("[3] required history")

# Checked before the click so the cost is stated up front, not discovered after
# four minutes of staring at a progress bar.
_, sweep_state = calibration.load(p, k, list(a), float(d2), dist_key)
sweep_precomputed = sweep_state == "hit"

s0, s1, s2, _ = st.columns([1.2, 1.3, 1, 2.5])
with s0:
    # Nobody's mandate is written in degrees. Same target, stated as the
    # consequence it actually governs: resid = sin²(angle), so angle = asin√resid.
    target_unit = st.selectbox("target stated as", ["max residual variance %", "q90 angle °"])
with s1:
    if target_unit.startswith("max residual"):
        max_resid = st.number_input("q90 residual variance ≤ (%)", min_value=1, max_value=99,
                                    value=20)
        target = math.degrees(math.asin(math.sqrt(max_resid / 100)))
    else:
        target = float(st.number_input("target q90 (°)", min_value=1, max_value=89, value=20))
with s2:
    st.markdown('<div style="height:1.75rem"></div>', unsafe_allow_html=True)
    go_sweep = st.button("run sweep", width="stretch")

if target_unit.startswith("max residual"):
    st.markdown(
        f'<div class="note" style="margin:-.2rem 0 .4rem">Retaining no more than '
        f'<b>{max_resid}%</b> of a factor\'s directional variance after neutralizing on the '
        f'estimated direction means <b>q90 ≤ {target:.1f}°</b> — the same target, in the '
        "unit the mandate is actually written in."
        "</div>", unsafe_allow_html=True)

if sweep_state == "custom":
    st.markdown(
        '<div class="note" style="margin:-.2rem 0 .4rem"><b>Custom calibration.</b> '
        "Only the paper defaults are precomputed, so this one runs live: six "
        "eigendecomposition sweeps on a shared vCPU, which takes <b>several minutes</b> "
        "in the browser. It will report progress per grid point."
        "</div>", unsafe_allow_html=True)
elif sweep_state == "stale":
    st.markdown(
        '<div class="note" style="margin:-.2rem 0 .4rem">'
        '<b style="color:#d98a3a">Precomputed sweep is stale.</b> '
        "It was built by a different engine than the one that produced the fan above, so "
        "serving it would put two disagreeing results on one page. Falling through to the "
        "live path (several minutes). Rebuild with <b>python3 calibration.py</b>."
        "</div>", unsafe_allow_html=True)

if go_sweep:
    sw = run_sweep(p, k, tuple(a), float(d2), dist_key, ENGINE_FINGERPRINT)

    sweep_fig = go.Figure()
    for j in range(k):
        sweep_fig.add_trace(go.Scatter(
            x=sw["n"], y=[row[j] for row in sw["q90"]],
            mode="lines+markers", name=f"f{j+1}",
            line=dict(color=FACTOR_COLORS[j], width=1.6),
            marker=dict(size=5, symbol="square"),
            hovertemplate=f"f{j+1} · n=%{{x}}<br>q90 %{{y:.1f}}°<extra></extra>"))
    sweep_fig.add_hline(y=target, line_dash="dot", line_width=1, line_color="#d98a3a",
                        annotation_text=f"target {target:.4g}°", annotation_position="top right",
                        annotation_font=dict(color="#d98a3a", size=11))
    sweep_fig.update_xaxes(title="observations n (days)", title_font=dict(size=11),
                           gridcolor="#161c23", zeroline=False, ticks="outside", ticklen=4,
                           tickcolor="#2c3641", showline=True, linecolor="#2c3641",
                           tickfont=dict(size=11))
    sweep_fig.update_yaxes(title="q90 error (°)", title_font=dict(size=11), range=[0, 90],
                           dtick=30, gridcolor="#161c23", zeroline=False, ticks="outside",
                           ticklen=4, tickcolor="#2c3641", showline=True, linecolor="#2c3641",
                           tickfont=dict(size=11))
    sweep_fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="JetBrains Mono, monospace", size=12, color="#b6bfc9"),
        margin=dict(l=8, r=8, t=28, b=8),
        height=300,
        legend=dict(orientation="h", y=1.16, x=0, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=11)),
    )
    st.plotly_chart(sweep_fig, width="stretch")

    lines = []
    for j in range(k):
        hit = next((nn for nn, row in zip(sw["n"], sw["q90"]) if row[j] <= target), None)
        floor_j = sw["floor"][-1][j]
        if hit:
            lines.append(f'<span style="color:{FACTOR_COLORS[j]}">f{j+1}</span> '
                         f'&nbsp;[ ok ]&nbsp; target met at n ≥ <b>{hit}</b>')
        elif floor_j > target:
            # Loudest element by design (playbook): it's the one output no persona
            # attacked. NOT "unreachable at any n" — the floor arcsin√(δ²/(nλ+δ²))
            # shrinks toward 0 as n grows, so that would be a false claim in the one
            # place the tool is trusted most. What actually blocks it is stationarity.
            lines.append(f'<span style="color:{FACTOR_COLORS[j]}">f{j+1}</span> '
                         f'&nbsp;<b style="color:#d98a3a; opacity:1">[fail]&nbsp; out of reach '
                         f'on a credible window</b> — even the observable floor at n = '
                         f'{sw["n"][-1]} ({floor_j:.1f}°) exceeds your {target:.4g}° target. '
                         f'The floor keeps falling with n, so this is reachable only with more '
                         f'history than fixed loadings can credibly cover.')
        else:
            lines.append(f'<span style="color:{FACTOR_COLORS[j]}">f{j+1}</span> '
                         f'&nbsp;[ -- ]&nbsp; not reached by n = {sw["n"][-1]} — more history '
                         f'only helps if loadings hold still that long')
    st.markdown('<div class="note" style="opacity:.75">' + "<br>".join(lines) + "</div>",
                unsafe_allow_html=True)
    st.markdown(
        f'<div class="note" style="margin-top:.7rem">The sweep stops at n = {SWEEP_GRID[-1]} '
        "(one year) by choice, not by cost. The model holds loadings <b>fixed for the whole "
        "window</b>, so sweeping to two or three years would answer “how much history do I need?” "
        "using the assumption least likely to survive that long — the curve would keep dropping "
        "and quietly promise precision that stationarity cannot deliver. Read a target unmet by "
        f"n = {SWEEP_GRID[-1]} as a statement about <b>how long you can believe your own factor "
        "model</b>, not as a request for more data."
        + (f"<br>Precomputed offline at {calibration.CACHED_REPS} paths per point, so this "
           "curve is steadier than the fan above it."
           if sweep_precomputed else
           f"<br>Computed live at {SWEEP_REPS} paths per point (lighter than the main fan), so "
           "treat a crossing as a threshold, not a precise n.")
        + "</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ methodology
rule("[4] methodology & assumptions")

with st.expander("What this computes, what it assumes, and where it is wrong"):
    st.markdown(f"""
**What it is.** A conditional simulator of PCA factor-direction error. Given (n, p, k), per-factor
signal strengths and a factor-return distribution, it Monte-Carlos the finite-p error sin²∠(hⱼ, bⱼ)
per factor, reports it in degrees as 50/80/95% bands, and marks the observable floor ℓ/θⱼ separately.

**What it is not.**
- **Not an estimator of total error from data alone.** The rotation component is provably not
  estimable (Gurdogan–Shkolnik impossibility). The fan is *simulated under assumptions*.
- **Not a confidence interval.** The bands are a conditional predictive distribution under an
  assumed data-generating process. No amount of simulation fidelity changes this.
- Not investment advice, and not a production risk tool.

The two visual classes differ **in kind**: the orange floor tick is measured (or would be, from your
eigenvalues); the blue fan is simulated. The gap between them is the non-identifiable rotation term.

#### Tied factors: when a label stops being a label

PCA orders factors by sample eigenvalue. When two eigenvalues are close, that ordering is not
stable: the estimator hands you two directions but cannot reliably say which is which. At an *exact*
tie it is not a precision problem but an identification one — any rotation within the shared plane is
an equally valid eigenbasis, so the per-factor angle degrades toward a random direction while still
printing as a number. In simulation, two strong but exactly-tied factors report ≈85° per-factor (no
information) while their 2-D span is known to ≈27°.

So when the estimator swaps two labels on more than 5% of paths, this app stops leading with their
named directions and reports their **span** instead: the largest principal angle between the true and
estimated subspaces, i.e. arccos of the smallest singular value of Bᵀ H. That quantity is invariant
to eigenvector sign *and* to label swaps — the exact two ambiguities that corrupt the per-factor
numbers — which is why it survives a tie when they do not. The per-factor rows stay visible, marked,
because they are still what the estimator returned; they just cannot carry a hedge on their own.

The `swap%` column is the raw trigger. Its floor is not reported: the per-factor floor ℓ/θⱼ is a
per-direction quantity, and a defensible *subspace* floor needs the paper's Corollary 2 rather than a
number invented here.

#### What is exact, what is asymptotic, what is simulated

| quantity | status |
|---|---|
| sin²∠(hⱼ, bⱼ) per path | **exact finite-p draw** — no asymptotic shortcut |
| floor tick, spectrum mode | exact arithmetic on your eigenvalues (its own sampling noise is **not** shown) |
| floor tick, model mode | median of the simulated plug-in ℓ/θⱼ — an asymptotic floor, not a pathwise finite-p bound |
| gray asymptotic tick | closed-form limit arcsin√(δ²/(nλⱼ+δ²)), reference only |
| fan quantiles | empirical quantiles of simulated paths, with Monte Carlo noise |

Per path: Y = U·diag(√(pλ))·Φ + Z. The n×n dual Gram is simulated exactly without ever forming a
p-dimensional array (Wishart via Bartlett when p−k ≥ n, direct Gaussian block otherwise), so cost is
O(n³) and independent of p. Factors are matched by eigenvalue rank — the honest choice, since a
practitioner cannot detect a swap either, but it fattens weak-factor tails. The `swap%` column
reports how often it happened.

#### Assumptions register

| assumption | plausible violation | effect on the fan |
|---|---|---|
| random orthonormal true loadings | real sector/style structure | **largest external-validity gap**; direction configuration-dependent |
| loadings fixed across time | drift / regime change | live markets add error the fan omits → **fan optimistic** |
| iid observations | vol clustering, autocorrelation | effective n < nominal n → **fan optimistic** |
| Gaussian idiosyncratic noise | fat-tailed specific returns | **untested hypothesis**, not a proven-safe step |
| correct factor count k | ambiguous factor count in real markets | conflated factors; bias direction unclear |
| prevalence enters as diag(G_B) | correlated loadings | vol²·prev is valid **only** when Σ_f and G_B share a diagonal basis |

Two of the three "fan optimistic" rows are unmitigated. **The true error is more likely above these
bands than below them.**

#### Validation status

Cross-checked against a full p-dimensional reference engine (agreement <0.5° at p=500 and p=3000)
and against the paper's Figure 1; floors reproduce the closed form; simulated totals sit above the
floor as the theorem requires. The footer re-runs the reference check live on the paper calibration.

**External validity is not established.** The true loading direction is latent, so "realized
rotation" cannot be observed directly on real equity panels; cross-window sample rotation also
contains genuine loading drift and is not the fan's target. Every number here is therefore
internally consistent and externally unproven. Monte Carlo noise on the displayed quantiles is a
run-to-run heuristic, not a derived interval.

**Defaults** are the paper's illustrative calibration (US equity, Bayraktar et al. 2014), not fitted
to any current book.

[Source and full methodology register]({REPO})
""")

# ------------------------------------------------------------------ validation footer
if mode == "model calibration" and p == 3000 and n == 63 and k == 3 and dist_key == "t":
    rule("[5] validation")
    st.markdown(
        '<div class="note">Cross-checked against the reference engine at this exact calibration '
        "(n=63, p=3000, k=3, Student-t).<br>reference q50/q90 &nbsp; 16.7°/19.8° · 34.9°/46.4° · "
        "44.1°/51.6°<br>this run &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; "
        + " · ".join(f"{q(0.5, j):.1f}°/{q(0.9, j):.1f}°" for j in range(k))
        + "</div>", unsafe_allow_html=True)

st.markdown(
    f'<div class="note" style="margin-top:2.5rem; padding-top:.8rem; '
    f'border-top:1px solid #222a33">Prototype, not group-reviewed. '
    f'Engine, methodology and assumption register: <a href="{REPO}">{REPO.split("//")[1]}</a>'
    "</div>", unsafe_allow_html=True)
