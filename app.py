"""
Factor Trust: Streamlit frontend over the validated engine.

engine.py is the source of numerical truth and is untouched by this file: this
script only wires widgets to its three functions (simulate / sweep_n /
from_spectrum) and draws what they return.

Walkthrough: 14-Lab/working/factor-trust — Streamlit rebuild walkthrough.md
"""
import hashlib
import json
import math
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

import calibration
import engine
import reporting

# st.cache_data keys on a function's args and its own body, NOT on engine.py.
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
  /* Hide the chrome piece by piece, NOT the whole toolbar: stToolbar also
     contains stExpandSidebarButton, the only control that reopens a collapsed
     sidebar. Hiding the parent made collapsing the sidebar a one-way door that
     only a page reload undid. */
  #MainMenu, footer, [data-testid="stDecoration"],
  [data-testid="stAppDeployButton"] { display: none; }
  [data-testid="stToolbar"] { background: transparent; }
  /* stHeader is a 48.75px opaque bar at z-index 999990: it paints over the top of
     the page, so content must clear it and it must not show as a band. */
  [data-testid="stHeader"] { background: transparent; }
  .block-container { padding-top: 4rem; padding-bottom: 4rem; max-width: 1180px; }

  /* type-in fields, not spinner widgets: p and n are four-digit numbers nobody
     wants to click up to. k is the exception — it is a single digit with a range
     of 8, so hiding its steppers left no visible way to change it at all and the
     cap read as lower than it is. */
  [data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] { display: none; }
  .st-key-k_factors [data-testid="stNumberInputStepUp"],
  .st-key-k_factors [data-testid="stNumberInputStepDown"] { display: flex; }
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

FACTOR_COLORS = ["#5b91c9", "#4a9d6a", "#d98a3a", "#9d84cc",
                 "#4fa3a0", "#c07ba0", "#8a9b4f", "#b8794f"]
# desaturated to sit with the rest of the palette; red is the only new hue and it
# is reserved for "do not read this row as a named direction"
STATE_COLORS = {"usable": "#4a9d6a", "caution": "#d98a3a",
                "unusable": "#c96a6a", "unstable": "#c96a6a"}
BAND_COLORS = ["#1c242e", "#28323e", "#38465a"]   # 95 / 80 / 50 %
REPO = "https://github.com/kristenharim/factor-trust"

# Calibration defaults, the sweep grid and the precomputed sweep all live in
# calibration.py, which imports no streamlit so the cache builder can share them.
DEFAULT_VOLS = calibration.DEFAULT_VOLS    # paper Table 1, annualized %
DEFAULT_PREVS = calibration.DEFAULT_PREVS  # paper G_B diagonal
SWEEP_GRID = calibration.SWEEP_GRID
SWEEP_REPS = calibration.LIVE_REPS
SWEEP_FINGERPRINT = calibration.cache_fingerprint()


# moved to reporting.py so the wording helpers that share it are unit-tested
resid_var_pct = reporting.resid_var_pct


def rule(label):
    st.markdown(f'<div class="rule">{label}</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown('<div class="rule">input</div>', unsafe_allow_html=True)
    mode = st.radio("mode", ["model calibration", "sample spectrum"], label_visibility="collapsed")
    n = int(st.number_input("n · observations", min_value=8, max_value=504, value=63))
    p = int(st.number_input("p · assets", min_value=20, max_value=100_000, value=3000, step=100))
    # The cap used to be 4 because the label assignment brute-forced all k!
    # permutations per path. That is now Hungarian when scipy is present, so the
    # binding constraint is readability rather than cost. Past 5 or 6 statistical
    # factors the weak ones sit near the noise floor and swap labels constantly,
    # which the scorecard will tell you.
    # n > k is an engine precondition, so the cap has to track n or the app can
    # be driven into a state that stops with an error (n=8 with k=8).
    k_ceiling = max(1, min(calibration.MAX_K, len(FACTOR_COLORS), n - 1))
    k = int(st.number_input("k · factors", min_value=1,
                            max_value=k_ceiling, value=min(3, k_ceiling),
                            key="k_factors",
                            help=f"Up to {k_ceiling} here (the engine needs n > k). "
                                 "Past 4 the defaults are extrapolated, and past 5 or 6 the weak "
                                 "factors swap labels so often that the scorecard stops naming "
                                 "them."))
    dist = st.selectbox("factor return distribution", ["Student-t (6 df)", "Normal"])
    reps = int(st.select_slider("simulations", options=[200, 400, 1000, 2000], value=400))
    tie_cutoff_pct = st.number_input(
        "tie cutoff · swap %", min_value=1.0, max_value=25.0, value=5.0, step=1.0,
        help="Display policy, not a statistical test: above this label-swap rate the app "
             "leads with the span instead of the named rows. At 400 paths a rate near 5% "
             "carries ≈±2pt of Monte Carlo noise — the readout shows the interval.")
    # Usability is a property of the USE, not of the angle: 17° is fine for
    # neutralizing broad market exposure and useless for attributing PnL to
    # factor 3. So the bands are the reader's to set and the scorecard says what
    # the number costs rather than pronouncing the factor good or bad.
    band_green = float(st.number_input(
        "usable below · q90 °", min_value=1.0, max_value=89.0, value=10.0, step=1.0,
        key="band_green",
        help="Your call, not a theorem threshold. Set it from what you do with the "
             "direction: tight for attribution, loose for broad neutralization."))
    # min_value tracks the green band so the widget can never display a value the
    # scorecard is not using. Both inputs carry explicit keys: without them the
    # widget identity is derived from its parameters, so moving the green band
    # would re-key the amber one and drop whatever the reader had typed there.
    band_amber = float(st.number_input(
        "caution below · q90 °", min_value=band_green + 1.0, max_value=90.0,
        value=max(25.0, band_green + 1.0), step=1.0, key="band_amber",
        help="Above this the scorecard calls the factor unusable. A direction picked "
             "at random scores 90°, which is the scale everything here is read against."))

    if mode == "model calibration":
        st.markdown('<div class="rule">calibration</div>', unsafe_allow_html=True)
        vols = [st.number_input(f"f{j+1} vol %", value=DEFAULT_VOLS[j],
                                min_value=0.1, step=0.5) for j in range(k)]
        prevs = [st.number_input(f"f{j+1} prevalence", value=DEFAULT_PREVS[j],
                                 min_value=0.05, step=0.05) for j in range(k)]
        idio = st.number_input("idiosyncratic vol %", value=40.0, min_value=1.0, step=1.0)
    else:
        st.markdown('<div class="rule">spectrum</div>', unsafe_allow_html=True)
        spectrum_entry = st.radio(
            "spectrum entry",
            ["complete spectrum", "top k + bulk summary"],
            help="The bulk mean must use every non-factor eigenvalue, not a selected tail.")
        if spectrum_entry == "complete spectrum":
            eig_text = st.text_area(
                f"exactly n={n} positive eigenvalues",
                height=120,
                placeholder="Paste the complete spectrum, in any order")
            bulk_mean_input = None
            bulk_count_input = None
        else:
            eig_text = st.text_area(
                f"exactly k={k} top eigenvalues",
                height=90,
                placeholder="0.034, 0.0088, 0.006")
            bulk_mean_input = st.number_input(
                "bulk mean ℓ · mean of every remaining eigenvalue",
                min_value=1e-12, value=0.0025, format="%.8f")
            bulk_count_input = int(st.number_input(
                "eigenvalues included in ℓ", min_value=1, max_value=max(1, n - k),
                value=max(1, n - k), step=1))
        st.caption("Eigenvalues of the sample covariance matrix (not correlation). "
                   "Spectrum-matched plug-in scenario: implied SNRⱼ = θⱼ/ℓ − 1 calibrates the "
                   "simulation. θ and ℓ carry sampling noise, so this is a scenario, not an "
                   "inversion. n must be the effective spectral dimension used by the PCA.")

dist_key = "t" if dist.startswith("Student") else "normal"

# ------------------------------------------------------------------ inputs -> engine args
if mode == "model calibration":
    # via calibration so the app and the cache builder derive a/d2 identically.
    # Any drift here would silently miss the cache and cost minutes
    a, d2 = calibration.engine_args(vols, prevs, idio)
    spectrum = None
    spectrum_input = None
else:
    try:
        eigs = [float(x) for x in eig_text.replace(",", " ").split()]
    except ValueError:
        st.error("Could not parse those eigenvalues — numbers separated by commas or spaces only.")
        st.stop()
    try:
        spectrum = engine.from_spectrum(
            eigs, n, k, bulk_mean=bulk_mean_input, bulk_count=bulk_count_input)
    except ValueError as e:
        st.error(str(e))
        st.stop()
    a, d2 = spectrum["a"], spectrum["d2"]
    spectrum_input = {
        "entry_mode": spectrum_entry,
        "supplied_eigenvalues": eigs,
        "bulk_mean_supplied": bulk_mean_input,
        "bulk_count_supplied": bulk_count_input,
    }

try:
    engine.validate_calibration(p, n, k, a, d2, reps)
except ValueError as e:
    st.error(str(e))
    st.stop()


# ------------------------------------------------------------------ cached engine calls
@st.cache_data(show_spinner="simulating…")
def run_sim(p, n, k, a, d2, dist, reps, engine_fp):
    # paths come back too: the histogram and the distribution-swap panel both need
    # the raw draws, and asking for them here is free next to re-running the sim
    return engine.simulate(p, n, k, list(a), d2, dist, 6, reps, return_paths=True)


@st.cache_data(show_spinner="simulating the other distribution…")
def run_alt_dist(p, n, k, a, d2, dist, reps, engine_fp):
    """Same calibration, opposite factor-return law. Everything else identical,
    so the difference between the two fans is attributable to that one choice."""
    other = "normal" if dist == "t" else "t"
    return engine.simulate(p, n, k, list(a), d2, other, 6, reps, return_paths=True), other


@st.cache_data(show_spinner=False)
def run_sweep(p, k, a, d2, dist, engine_fp, cache_fp, reps=SWEEP_REPS):
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

# Display cutoff, NOT a theorem-derived threshold: above this much mutual
# confusion the tool leads with the span instead of the named rows. The proved
# statement is only about the *exact* tie (any rotation within the plane is an
# equally valid eigenbasis, so the directions are formally unidentified and only
# the span invariant); a finite swap rate is an approach to that limit, not the
# limit. Whether any given % is a principled cutoff is an open question for the
# group (README §8). It is user-adjustable in the sidebar precisely so it reads
# as a policy knob, not a result.
TIE_TOL = tie_cutoff_pct / 100
ties, mutual_conf = reporting.tied_runs(r["confusion"], k, TIE_TOL)
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

# Check prevalence as well as vol: the strength is vol²×prevalence, so leaving
# either one at its invented default still means an invented default.
if mode == "model calibration" and k > calibration.PAPER_K and (
        vols[calibration.PAPER_K:] == DEFAULT_VOLS[calibration.PAPER_K:k]
        or prevs[calibration.PAPER_K:] == DEFAULT_PREVS[calibration.PAPER_K:k]):
    st.warning(
        f"Factors {calibration.PAPER_K + 1}–{k} are running on **extrapolated defaults**. The "
        "paper's illustrative table stops at "
        f"{calibration.PAPER_K}; the strengths above that are a decaying continuation chosen "
        "only to keep vol²×prevalence ordered, and they are not sourced from anywhere. Put your "
        "own numbers in the sidebar before reading anything into those rows.")

if p < 10 * n:
    st.warning(
        f"High-dimensional scope warning: p/n = {p/n:.1f}. The floor result is a p → ∞, "
        "fixed-n statement; 10× is a conservative UI guardrail, not a theorem threshold. "
        "The finite-p simulation still runs, but do not present the asymptotic tick as settled.")

# ------------------------------------------------------------------ headline
# A bare "44°" has no scale attached and a reader supplies the wrong one: 44 is
# less than 90, 90 sounds like a maximum, so 44 reads as "half wrong, fine". The
# anchor is what fixes it. Two directions drawn at random in R^p are almost
# exactly orthogonal, so 90° is not the worst case on some arbitrary scale, it is
# what guessing scores. Every angle on this page is read against that.
# Name only a factor whose name means something. Headlining "f8 is 73° off" when
# f8 swaps labels on half the runs attaches a precise number to a direction the
# estimator cannot reliably identify, which is the exact failure the tie logic
# exists to prevent. Fall back to the worst STABLE factor, and if none is stable
# say nothing beyond f1 and let the scorecard carry it.
stable = [j for j in reporting.stable_factor_indices(k, ties) if j != 0]
worst_j = max(stable, key=lambda j: q(0.5, j)) if stable else 0
st.markdown(
    f'<div style="font-size:1.35rem;line-height:1.5;margin:.2rem 0 .1rem">'
    f'Your <b style="color:{FACTOR_COLORS[0]}">f1</b> direction is typically '
    f'<b>{q(0.5, 0):.0f}° off</b> the true one.'
    + (f' <b style="color:{FACTOR_COLORS[worst_j]}">f{worst_j+1}</b> is '
       f'<b>{q(0.5, worst_j):.0f}° off</b>.' if worst_j != 0 else '')
    + f'</div><div class="note" style="margin:0 0 .5rem">A direction picked at random would be '
      f'{reporting.RANDOM_BASELINE_DEG:.0f}° off, so that is the scale to read these against.'
      f'</div>',
    unsafe_allow_html=True)

st.markdown(
    '<div class="verdict"><span class="lbl">90% of runs<br>land within</span>'
    + "".join(f'<span class="v" style="color:{color}"><u>{lab}</u>{val:.0f}°</span>'
              for lab, val, color in headline_entries())
    + "</div>"
    # The headline travels in screenshots; the conditionality must travel with it.
    '<div class="note" style="margin:.15rem 0 0">of <i>simulated</i> runs under the '
    'calibration above — a conditional Monte Carlo statement, not real-market confidence. '
    'If these calibration numbers were estimated from the same returns you would PCA, '
    'treat every figure on this page as optimistic (see [3]).</div>',
    unsafe_allow_html=True)

# ------------------------------------------------------------------ scorecard
# One row per factor, in words, against the reader's own bands. This is the part
# that travels into a slide, so it carries the consequence ("a hedge on it clears
# 92% of the exposure") rather than the statistic that implies it.
rows = []
for j in range(k):
    state, sentence = reporting.verdict(q(0.9, j), r["swap_rate"][j],
                                        band_green, band_amber, TIE_TOL)
    colour = STATE_COLORS[state]
    rows.append(
        f'<div style="display:flex;gap:.9rem;align-items:baseline;padding:.42rem .7rem;'
        f'border-left:2px solid {colour};background:#141a21;margin-bottom:3px">'
        f'<span style="color:{colour};min-width:5.4rem">f{j+1} &nbsp;{q(0.5, j):.0f}°'
        f'<span style="opacity:.6;font-size:.78rem"> / {q(0.9, j):.0f}° at q90</span></span>'
        f'<span style="color:#b6bfc9;font-size:.86rem">{sentence}</span></div>')
st.markdown("".join(rows), unsafe_allow_html=True)
st.caption(f"First angle is the median run, second is the 90th percentile. Bands "
           f"({band_green:g}° / {band_amber:g}°) are yours, set in the sidebar — usability "
           f"depends on what the direction is for, not on the angle alone.")

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
    "<b>not a confidence interval</b>. Excess total error above the floor is influenced by "
    "in-subspace rotation under the model; the visible distance in degrees is not an additive "
    "decomposition of the theorem."
    "</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- shape of the fan
# The bands above give five numbers per factor. The shape is a different fact: a
# long right tail means the median understates what a bad run looks like, and no
# quantile shows that on its own. Free to draw, the paths are already in hand.
paths = r["paths"]["angle"]
hfig = go.Figure()
for j in range(k):
    hfig.add_trace(go.Histogram(
        x=[row[j] for row in paths], name=f"f{j+1}", nbinsx=60, opacity=0.55,
        marker=dict(color=FACTOR_COLORS[j], line=dict(width=0)),
        hovertemplate=f"<b>f{j+1}</b><br>%{{x:.0f}}°<br>%{{y}} runs<extra></extra>"))
    hfig.add_vline(x=q(0.9, j), line=dict(color=FACTOR_COLORS[j], width=1, dash="dot"),
                   opacity=.8)
hfig.add_vline(x=reporting.RANDOM_BASELINE_DEG, line=dict(color="#6b7683", width=1),
               annotation_text="a random direction", annotation_position="top left",
               annotation_font=dict(size=10, color="#6b7683"))
hfig.update_xaxes(range=[0, 92], dtick=15, title="angle between estimated and true direction (°)",
                  title_font=dict(size=11), gridcolor="#161c23", showline=True,
                  linecolor="#2c3641", tickfont=dict(size=11))
hfig.update_yaxes(title="simulated runs", title_font=dict(size=11), gridcolor="#161c23",
                  tickfont=dict(size=11))
hfig.update_layout(template="plotly_dark", barmode="overlay", height=270,
                   paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                   font=dict(family="JetBrains Mono, monospace", size=12, color="#b6bfc9"),
                   margin=dict(l=48, r=8, t=8, b=8),
                   legend=dict(orientation="h", y=1.08, x=0, font=dict(size=11)))
st.plotly_chart(hfig, width="stretch")
st.markdown(
    '<div class="note">Every simulated run, not a summary of them. Dotted lines are each '
    'factor&#39;s q90. Angles stay in degrees on purpose: rescaling to 0–1 would throw away the '
    'only reference point a reader has, which is that <b>a direction picked at random lands at '
    '90°</b>. A long right tail means the median is a poor description of a bad run.'
    "</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- distribution swap
# How much of the answer rests on a choice nobody can verify from data. This is a
# fragility measure, not another error measure: same calibration, same seed, one
# assumption changed.
if st.button("how much of this depends on the return distribution?", width="content"):
    alt, other = run_alt_dist(p, n, k, tuple(a), float(d2), dist_key, reps, ENGINE_FINGERPRINT)
    focus = max(range(k), key=lambda j: q(0.5, j))       # the weakest factor is the fragile one
    label = {"t": "Student-t (6 df)", "normal": "Normal"}
    dfig = go.Figure()
    for res, key, colour in ((r, dist_key, FACTOR_COLORS[0]), (alt, other, "#d98a3a")):
        dfig.add_trace(go.Histogram(
            x=[row[focus] for row in res["paths"]["angle"]], nbinsx=60, opacity=0.55,
            name=label[key], marker=dict(color=colour, line=dict(width=0)),
            hovertemplate=f"{label[key]}<br>%{{x:.0f}}°<extra></extra>"))
        dfig.add_vline(x=res["quantiles"]["0.9"][focus],
                       line=dict(color=colour, width=1, dash="dot"), opacity=.85)
    dfig.update_xaxes(range=[0, 92], dtick=15, title=f"f{focus+1} angle (°)",
                      title_font=dict(size=11), gridcolor="#161c23", showline=True,
                      linecolor="#2c3641", tickfont=dict(size=11))
    dfig.update_yaxes(title="simulated runs", title_font=dict(size=11),
                      gridcolor="#161c23", tickfont=dict(size=11))
    dfig.update_layout(template="plotly_dark", barmode="overlay", height=260,
                       paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                       font=dict(family="JetBrains Mono, monospace", size=12, color="#b6bfc9"),
                       margin=dict(l=48, r=8, t=8, b=8),
                       legend=dict(orientation="h", y=1.1, x=0, font=dict(size=11)))
    st.plotly_chart(dfig, width="stretch")
    here_q90, there_q90 = q(0.9, focus), alt["quantiles"]["0.9"][focus]
    shift = abs(here_q90 - there_q90)
    rel = shift / max(here_q90, 1e-9) * 100
    # A bare "1.7°" invites the reader to assume it is large, because they have
    # nothing to compare it to. State the reading. This cuts both ways: the same
    # sentence has to be willing to call the tool fragile when it is.
    read = ("so at this calibration the headline numbers are <b>not</b> very sensitive to that "
            "choice" if rel < 10 else
            "so a large share of the headline number is riding on that choice")
    st.markdown(
        f'<div class="note">Same p, n, k and calibration; only the factor-return law changes. '
        f'f{focus+1} at q90 goes from <b>{here_q90:.1f}°</b> under {label[dist_key]} to '
        f'<b>{there_q90:.1f}°</b> under {label[other]}, a shift of '
        f'<b>{shift:.1f}°</b> ({rel:.0f}% of the angle), {read}. That gap is not error, '
        f'it is <b>how much of '
        'your answer rests on a distributional assumption you cannot check from the returns '
        'themselves</b>. The floor formula is derived under Gaussian noise and is not '
        're-derived for heavy tails, so on the Student-t side the fan moves and the asymptotic '
        'tick does not.'
        "</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ quantile table + export
rule("[2] readout")

swap_ci = [reporting.wilson95(r["swap_rate"][j], reps) for j in range(k)]
df = pd.DataFrame([{
    "factor": f"f{j+1}",
    "snr": round(snr_of(j), 1),
    "floor°": round(floor_of(j), 1),
    "asym°": round(r["floor_asymptotic"][j], 1),
    # model-side by construction: rho comes from the simulated factor draw. In
    # spectrum mode floor° switches to your eigenvalues but this column cannot,
    # so it is dropped there rather than sitting next to a measured number
    # looking like one.
    **({} if spectrum else {"path°": round(r["floor_pathwise_median"][j], 1)}),
    "q50°": round(q(0.5, j), 1),
    "q80°": round(q(0.8, j), 1),
    "q90°": round(q(0.9, j), 1),
    "q90lo°": round(r["q90_mc95"]["lower"][j], 1),
    "q90hi°": round(r["q90_mc95"]["upper"][j], 1),
    "q95°": round(q(0.95, j), 1),
    "resid%@q90": round(resid_var_pct(q(0.9, j)), 0),
    "swap%": round(r["swap_rate"][j] * 100, 1),
    "swaplo%": round(swap_ci[j][0] * 100, 1),
    "swaphi%": round(swap_ci[j][1] * 100, 1),
} for j in range(k)])

# :g strips pandas' trailing zeros (12.6000 -> 12.6); df itself stays numeric for export
st.table(df.set_index("factor").map(lambda v: f"{v:g}"))
st.caption("q90lo/q90hi = a 95% bootstrap interval, swaplo/swaphi = a 95% Wilson interval — "
           "both for Monte Carlo estimation noise only, not uncertainty about whether the "
           "simulator describes real markets. A tie verdict decided by less than the swap "
           "interval is noise; raise the simulation count before trusting it.")
if not spectrum:
    st.caption("asym° evaluates the floor at the population strength vol²×prevalence, which is a "
               "second (n → ∞) limit on top of the p → ∞ one, and reads optimistic for the weaker "
               "factors at small n. path° evaluates the same formula at each path's realized ρⱼ "
               "and is the theorem's own floor conditional on F. Assembled pathwise, floor + "
               f"rotation lands on the simulated median: predicted "
               f"{'/'.join(f'{v:.1f}' for v in r['total_predicted_median'])}° against measured "
               f"{'/'.join(f'{q(0.5, j):.1f}' for j in range(k))}°, where the same assembly at "
               f"population strength gives "
               f"{'/'.join(f'{v:.1f}' for v in r['total_predicted_pop_median'])}°.")

# The tie warning sits directly under the rows it disqualifies, not below the
# consequence text: a reader who stops at the table must still see it.
for run in ties:
    lab = engine.group_label(run)
    names = " and ".join(f"f{j+1}" for j in run)
    worst = max(q(0.9, j) for j in run)
    pair_conf = max(mutual_conf[j] for j in range(run[0], run[-1]))
    conf_lo, conf_hi = reporting.wilson95(pair_conf, reps)
    pair_conf *= 100
    st.markdown(
        f'<div class="note" style="margin:.5rem 0 0">'
        f'<b style="color:#d98a3a">[tied] {names} are hard to tell apart here.</b> '
        f'The estimator swaps their labels on <b>{pair_conf:.1f}%</b> '
        f'(95% MC interval {conf_lo * 100:.1f}–{conf_hi * 100:.1f}%) of simulated paths, so the '
        f'individual rows above are unreliable as <i>named</i> directions. (In the limiting case '
        f'of an <i>exact</i> eigenvalue tie they would be formally unidentified — any rotation '
        f'within their plane is an equally valid eigenbasis — and only their span invariant; a '
        f'swap rate this size is an approach to that limit, not the limit itself.) Their '
        f'{len(run)}-D span is the part that stays put in simulation: '
        f'<b>{sub_q(lab, 0.9):.1f}°</b> at q90 against <b>{worst:.1f}°</b> for the worst named '
        f'direction in it. The {tie_cutoff_pct:g}% switch is a display heuristic (adjustable in '
        f'the sidebar) and no span-level floor or required-history target is claimed — see '
        f'[5] methodology.'
        "</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- confusion heatmap
# The swap% column collapses this matrix to its off-diagonal total. Drawn in full
# it says WHICH factor a label leaks into, which the scalar cannot: a 6% swap rate
# spread over two neighbours is a different problem from 6% into one of them.
# Columns sum to 1 by construction (each is "where did h_j's best match land"),
# so it is a set of distributions and is not symmetric. Reading it the other way
# round is the mistake to avoid.
if k > 1:
    conf_m = r["confusion"]
    hm = go.Figure(go.Heatmap(
        z=[[conf_m[i][j] * 100 for j in range(k)] for i in range(k)],
        x=[f"h{j+1} (estimated)" for j in range(k)],
        y=[f"b{i+1} (true)" for i in range(k)],
        text=[[f"{conf_m[i][j] * 100:.1f}%" for j in range(k)] for i in range(k)],
        texttemplate="%{text}", textfont=dict(size=12),
        colorscale=[[0, "#141a21"], [0.5, "#8a5a2a"], [1, "#5b91c9"]],
        zmin=0, zmax=100, showscale=False,
        # phrased estimated-first because the columns are the distributions; the
        # row reading is the one the note below tells the reader not to take
        hovertemplate="estimated %{x} matched to true %{y}"
                      "<br>%{z:.1f}% of that column&#39;s runs<extra></extra>"))
    hm.update_layout(template="plotly_dark", height=90 + 52 * k,
                     paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                     font=dict(family="JetBrains Mono, monospace", size=11, color="#b6bfc9"),
                     margin=dict(l=110, r=8, t=8, b=8))
    hm.update_yaxes(autorange="reversed")
    st.plotly_chart(hm, width="stretch")
    st.markdown(
        '<div class="note">Where each estimated direction&#39;s best match actually landed, over '
        'all simulated runs. <b>Each column is a distribution and sums to 100%</b>, so the matrix '
        'is deliberately not symmetric — read it column by column, never as a similarity table. '
        'The diagonal is how often the estimator recovered the factor it was aiming at; the '
        'off-diagonal mass in a column is exactly that factor&#39;s swap%, broken out by where '
        'the label went. Matching uses the true directions, which no practitioner has.'
        "</div>", unsafe_allow_html=True)

st.markdown(
    '<div class="note">'
    + "<br>".join(
        f'<span style="color:{FACTOR_COLORS[j]}">f{j+1}</span> &nbsp; at q90 = '
        f'<b>{q(0.9, j):.1f}°</b>, a book neutralized on the <i>estimated</i> f{j+1} '
        f'direction still carries <b>≈{resid_var_pct(q(0.9, j)):.0f}%</b> of f{j+1} '
        "directional variance." + (" <b>Unreliable alone — see [tied] above.</b>"
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

factor_exports = []
for j, row in enumerate(df.to_dict(orient="records")):
    group = next((engine.group_label(g) for g in ties if j in g), None)
    factor_exports.append({
        **row,
        "named_reliable": j not in tied_idx,
        "tie_group": group,
        "q90_mc95_method": r["q90_mc95"]["method"],
    })
subspace_exports = [{
    "name": engine.group_label(g),
    "metric": "largest principal angle",
    "q50°": sub_q(engine.group_label(g), 0.5),
    "q90°": sub_q(engine.group_label(g), 0.9),
    "floor°": None,
    "required_history": None,
    "claim_status": "conditional simulation; no theorem-backed floor or target",
} for g in ties]
export_payload = reporting.build_export_payload(
    engine_fingerprint=ENGINE_FINGERPRINT,
    inputs={
        "n": n, "p": p, "k": k, "distribution": dist_key, "dof": 6,
        "simulation_paths": reps, "seed": r["seed"],
        "source": "spectrum" if spectrum else "model",
        "ordered_strengths": list(a), "idiosyncratic_variance": float(d2),
    },
    factors=factor_exports,
    subspaces=subspace_exports,
    tie_groups=[engine.group_label(g) for g in ties],
    spectrum=({**spectrum_input, **spectrum} if spectrum else None),
    assumptions=[
        "conditional latent-factor simulation",
        "fixed loadings", "iid observations", "Gaussian idiosyncratic noise",
        "random orthonormal loadings", "correct k",
    ])
export_df = pd.DataFrame(reporting.export_rows(export_payload))

c1, c2, _ = st.columns([1, 1, 5])
with c1:
    st.download_button("export csv", export_df.to_csv(index=False),
                       file_name="factor-trust.csv", width="stretch")
with c2:
    st.download_button("export json", json.dumps(export_payload, indent=2),
                       file_name="factor-trust.json", width="stretch")

# ------------------------------------------------------------------ calibration sensitivity
rule("[3] calibration sensitivity")

if mode == "model calibration":
    st.markdown(
        '<div class="note" style="margin:0 0 .5rem">Every number above is conditional on the '
        'sidebar calibration — inputs which, in practice, are <b>estimated from the same '
        'returns you would PCA</b>, a circularity this tool cannot break for you. This panel '
        'measures how far the headline moves when those inputs are wrong by a stated amount: '
        'each scenario scales all factor vols, all prevalences, or the idiosyncratic vol '
        'up or down together, re-simulates, and reports the envelope.</div>',
        unsafe_allow_html=True)
    sc0, sc1, _ = st.columns([1.2, 1, 3])
    with sc0:
        sens_pct = st.selectbox("input perturbation", ["±10%", "±15%", "±20%"], index=1)
    with sc1:
        st.markdown('<div style="height:1.75rem"></div>', unsafe_allow_html=True)
        go_sens = st.button("run sensitivity", width="stretch")

    if go_sens:
        delta = float(sens_pct.strip("±%")) / 100
        # 6 extra simulations: cap the panel at 400 paths so a 2000-path main run
        # doesn't turn one click into six of them.
        sens_reps = min(reps, 400)
        scenarios = []
        for label, sv, sp_, si in [
                (f"vols +{sens_pct[1:]}", 1 + delta, 1.0, 1.0),
                (f"vols −{sens_pct[1:]}", 1 - delta, 1.0, 1.0),
                (f"prevalence +{sens_pct[1:]}", 1.0, 1 + delta, 1.0),
                (f"prevalence −{sens_pct[1:]}", 1.0, 1 - delta, 1.0),
                (f"idio +{sens_pct[1:]}", 1.0, 1.0, 1 + delta),
                (f"idio −{sens_pct[1:]}", 1.0, 1.0, 1 - delta)]:
            a_s, d2_s = calibration.engine_args(
                [v * sv for v in vols], [c * sp_ for c in prevs], idio * si)
            r_s = run_sim(p, n, k, tuple(a_s), float(d2_s), dist_key, sens_reps,
                          ENGINE_FINGERPRINT)
            ties_s, _ = reporting.tied_runs(r_s["confusion"], k, TIE_TOL)
            scenarios.append((label, r_s, ties_s))

        base = run_sim(p, n, k, tuple(a), float(d2), dist_key, sens_reps, ENGINE_FINGERPRINT)
        sens_df = pd.DataFrame([{
            "factor": f"f{j+1}",
            "q90°": round(base["quantiles"]["0.9"][j], 1),
            "q90 min°": round(min(r_s["quantiles"]["0.9"][j] for _, r_s, _ in scenarios), 1),
            "q90 max°": round(max(r_s["quantiles"]["0.9"][j] for _, r_s, _ in scenarios), 1),
            "floor°": round(base["floor_asymptotic"][j], 1),
            "floor min°": round(min(r_s["floor_asymptotic"][j] for _, r_s, _ in scenarios), 1),
            "floor max°": round(max(r_s["floor_asymptotic"][j] for _, r_s, _ in scenarios), 1),
        } for j in range(k)])
        st.table(sens_df.set_index("factor").map(lambda v: f"{v:g}"))

        base_ties, _ = reporting.tied_runs(base["confusion"], k, TIE_TOL)
        flips = [lab for lab, _, ties_s in scenarios if ties_s != base_ties]
        if flips:
            st.markdown(
                '<div class="note"><b style="color:#d98a3a">The tie verdict itself moves</b> '
                f'under: {", ".join(flips)}. Which factors count as reliably named is not '
                'robust to this much calibration error — read the named rows accordingly.'
                "</div>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="note" style="margin-top:.5rem">Envelope across 6 one-at-a-time '
            f'scenarios at {sens_reps} paths each (min/max of the scenario values; the '
            f'columns at that base are the same-path baseline). One-at-a-time scaling is a '
            f'first-order probe, not a joint error model — real calibration errors are '
            f'correlated and can move the envelope further.</div>',
            unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="note">Available in model-calibration mode. In spectrum mode the inputs '
        'are your measured eigenvalues; their sampling noise is a different object than a '
        'calibration scaling and is not yet quantified here (see [5] methodology).</div>',
        unsafe_allow_html=True)

# ------------------------------------------------------------------ required-history sweep
rule("[4] required history — a model-implied scenario")

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
    sw = run_sweep(
        p, k, tuple(a), float(d2), dist_key, ENGINE_FINGERPRINT, SWEEP_FINGERPRINT)

    sweep_fig = go.Figure()
    stable_factors = reporting.stable_factor_indices(k, ties)
    for j in stable_factors:
        q90_y = [row[j] for row in sw["q90"]]
        q90_lo = [row["lower"][j] for row in sw["q90_mc95"]]
        q90_hi = [row["upper"][j] for row in sw["q90_mc95"]]
        sweep_fig.add_trace(go.Scatter(
            x=sw["n"], y=q90_y,
            mode="lines+markers", name=f"f{j+1}",
            line=dict(color=FACTOR_COLORS[j], width=1.6),
            marker=dict(size=5, symbol="square"),
            error_y=dict(type="data", symmetric=False,
                         array=[hi - y for hi, y in zip(q90_hi, q90_y)],
                         arrayminus=[y - lo for y, lo in zip(q90_y, q90_lo)],
                         color=FACTOR_COLORS[j], thickness=0.8, width=2),
            hovertemplate=(f"f{j+1} · n=%{{x}}<br>q90 %{{y:.1f}}°"
                           "<br>MC 95% interval shown by bars<extra></extra>")))
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
    if stable_factors:
        st.plotly_chart(sweep_fig, width="stretch")

    lines = []
    for j in stable_factors:
        points = list(zip(sw["n"], sw["q90"], sw["q90_mc95"]))
        confirmed = next(((nn, row, ci) for nn, row, ci in points
                          if ci["upper"][j] <= target), None)
        point_hit = next(((nn, row, ci) for nn, row, ci in points
                          if row[j] <= target), None)
        floor_j = sw["floor"][-1][j]
        if confirmed:
            hit, _, ci = confirmed
            lines.append(f'<span style="color:{FACTOR_COLORS[j]}">f{j+1}</span> '
                         f'&nbsp;[ ok ]&nbsp; target met at n ≥ <b>{hit}</b> after accounting for '
                         f'Monte Carlo q90 uncertainty (95% upper endpoint {ci["upper"][j]:.1f}°).')
        elif point_hit:
            hit, row, ci = point_hit
            lines.append(f'<span style="color:{FACTOR_COLORS[j]}">f{j+1}</span> '
                         f'&nbsp;[borderline]&nbsp; point estimate crosses at n = <b>{hit}</b>, but '
                         f'the 95% Monte Carlo interval ({ci["lower"][j]:.1f}–'
                         f'{ci["upper"][j]:.1f}°) still crosses the target.')
        elif floor_j > target:
            lines.append(f'<span style="color:{FACTOR_COLORS[j]}">f{j+1}</span> '
                         f'&nbsp;<b style="color:#d98a3a; opacity:1">[conditional fail]&nbsp; not '
                         f'supported on a credible window</b> — the limiting floor reference at n = '
                         f'{sw["n"][-1]} ({floor_j:.1f}°) exceeds your {target:.4g}° target. '
                         f'The floor keeps falling with n, so this is reachable only with more '
                         f'history than fixed loadings can credibly cover. This is a scenario '
                         f'conclusion, not a finite-p pathwise impossibility claim.')
        else:
            lines.append(f'<span style="color:{FACTOR_COLORS[j]}">f{j+1}</span> '
                         f'&nbsp;[ -- ]&nbsp; not reached by n = {sw["n"][-1]} — more history '
                         f'only helps if loadings hold still that long')
    for group in ties:
        names = engine.group_label(group)
        lines.append(
            f'<span style="color:{FACTOR_COLORS[group[0]]}">{names}</span> '
            '&nbsp;[withheld]&nbsp; named-factor history decisions are suppressed because the '
            'labels are unstable; no span-level history target has been derived.')
    st.markdown('<div class="note" style="opacity:.75">' + "<br>".join(lines) + "</div>",
                unsafe_allow_html=True)
    st.markdown(
        f'<div class="note" style="margin-top:.7rem">This is a <b>model-implied scenario</b>, '
        "not a data requirement: the sweep holds this exact calibration fixed while n varies, "
        "so it answers “at what n does the <i>simulated</i> q90 cross the target, if the "
        "calibration is right and stays right.” It is not a guarantee that collecting that much "
        "history achieves the target — and if the calibration was itself estimated from a "
        "window of length n, the whole curve inherits that circularity. "
        f"The sweep stops at n = {SWEEP_GRID[-1]} "
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

# ------------------------------------------------------------------ the other budget: p
# Sits inside [4] on purpose. Both questions are "how do I buy a better estimate",
# and the honest answer is that one of the two currencies does not spend: n moves
# the curve, p does not. Cheap to run because the dual-Gram construction is
# O(n^3) and independent of p, so every point on this grid costs what the main
# fan costs, unlike the n sweep where the last point dominates.
P_GRID = [100, 300, 1000, 3000, 10_000, 30_000, 100_000]


@st.cache_data(show_spinner=False)
def run_p_sweep(n, k, a, d2, dist, engine_fp, reps=SWEEP_REPS):
    bar = st.progress(0.0, "sweeping assets…")
    sw = engine.sweep_p(
        P_GRID, n, k, list(a), d2, dist, 6, reps,
        on_point=lambda done, total, pp: bar.progress(done / total, f"sweeping… p={pp:,}"),
        keep_paths=25)
    bar.empty()
    return sw


st.markdown('<div style="height:.9rem"></div>', unsafe_allow_html=True)
if st.button("and would more assets help?", width="content"):
    psw = run_p_sweep(n, k, tuple(a), float(d2), dist_key, ENGINE_FINGERPRINT)
    pfig = go.Figure()
    for j in range(k):
        # Individual runs as points, never joined: each grid point is its own
        # simulate() call and the Wishart block consumes a different number of
        # variates at each p, so there is no path that continues across the axis.
        # A line here would draw a continuity the simulation does not have.
        pfig.add_trace(go.Scatter(
            x=[pp for pp in P_GRID for _ in psw["paths"][0]],
            y=[row[j] for pt in psw["paths"] for row in pt], mode="markers",
            marker=dict(color=FACTOR_COLORS[j], size=3, opacity=0.18), showlegend=False,
            hoverinfo="skip"))
        pfig.add_trace(go.Scatter(
            x=P_GRID + P_GRID[::-1],
            y=[row[j] for row in psw["q90"]] + [row[j] for row in psw["q10"][::-1]],
            fill="toself", fillcolor=FACTOR_COLORS[j], opacity=0.10, mode="none",
            showlegend=False, hoverinfo="skip"))
        pfig.add_trace(go.Scatter(
            x=P_GRID, y=[row[j] for row in psw["q50"]], mode="lines+markers",
            line=dict(color=FACTOR_COLORS[j], width=2), marker=dict(size=5),
            name=f"f{j+1}",
            hovertemplate=f"<b>f{j+1}</b><br>p=%{{x:,}}<br>median %{{y:.1f}}°<extra></extra>"))
        pfig.add_hline(y=psw["floor"][j], line=dict(color=FACTOR_COLORS[j], width=1, dash="dash"),
                       opacity=.35)
        # The curves do NOT settle on the floor: the floor is one of the two terms
        # in the theorem and the rotation term does not vanish in p, only in n.
        # Drawing the assembled limit as well is the difference between a panel
        # that shows the result and one that misstates it.
        pfig.add_trace(go.Scatter(
            x=P_GRID, y=[row[j] for row in psw["limit"]], mode="lines",
            line=dict(color=FACTOR_COLORS[j], width=1.4, dash="longdash"),
            opacity=.85, showlegend=False, hoverinfo="skip"))
    pfig.add_vline(x=p, line=dict(color="#6b7683", width=1, dash="dot"),
                   annotation_text="your p", annotation_font=dict(size=11, color="#6b7683"))
    # dtick=1 on a log axis is one tick per decade; the default adds 2x and 5x
    # minor labels that just clutter a seven-point grid
    pfig.update_xaxes(type="log", dtick=1, title="assets p (log scale), n held fixed",
                      title_font=dict(size=11), gridcolor="#161c23", showline=True,
                      linecolor="#2c3641", tickfont=dict(size=11))
    pfig.update_yaxes(range=[0, 90], dtick=15, title="angle (°)", title_font=dict(size=11),
                      gridcolor="#161c23", tickfont=dict(size=11))
    pfig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                       plot_bgcolor="rgba(0,0,0,0)", height=330,
                       font=dict(family="JetBrains Mono, monospace", size=12, color="#b6bfc9"),
                       margin=dict(l=48, r=8, t=8, b=8),
                       legend=dict(orientation="h", y=-0.28, font=dict(size=11)))
    st.plotly_chart(pfig, width="stretch")
    # Measured from where the reader actually stands, not from the left edge of
    # the grid. The small-p end is still climbing out of the pre-asymptotic
    # regime, so quoting p=100 -> p=100,000 would report a large drop and read as
    # evidence AGAINST the panel's own point. The decision on the table is
    # "should I expand the universe I already have", so that is the comparison.
    here = next((i for i, pp in enumerate(P_GRID) if pp >= p), len(P_GRID) - 1)
    from_p = P_GRID[here]
    first, last = psw["q50"][here], psw["q50"][-1]
    # Quote the grid point actually measured, not the user's p, or at p=500 the
    # sentence claims a number it read off the p=1000 row. at_top compares p to
    # the grid top rather than the index, since `here` saturates at the last
    # index for anything above 30,000 and would claim "nothing left to buy" at
    # p=50,000 with a 2x expansion still on the grid.
    at_top = p >= P_GRID[-1]
    span = (f'Your p = {p:,} is at or past the top of the grid, so there is nothing left to '
            f'buy here. Across the flat stretch from p = {P_GRID[-3]:,} the median moves by '
            if at_top else
            f'From p = {from_p:,} (the nearest grid point at or above your {p:,}) to '
            f'p = {P_GRID[-1]:,}, {P_GRID[-1] / from_p:.0f}× the universe, the median moves by ')
    ref = psw["q50"][-3] if at_top else first
    crn_note = (
        'Every grid point shares one seed and the whole grid stays in one Wishart branch, so '
        'this is a <b>common-random-numbers</b> sweep: the factor draw is held fixed across p '
        'and only the noise block is redrawn, which strips sampling wobble out of the '
        'comparison. The points stay unjoined because coupled is not the same as identical.'
        if psw["crn"] else
        f'<b>Not</b> a common-random-numbers sweep at this n: the smallest grid point '
        f'(p = {P_GRID[0]:,}) has p−k &lt; n = {n}, which sends it down a different noise branch '
        'and desynchronizes the draw from the larger p. Treat the points as independent runs.')
    st.markdown(
        '<div class="note">Solid is the median run, the shaded band is q10–q90, the long-dashed '
        'line is the theorem&#39;s limit (floor + rotation), the faint dashed line below it is '
        'the floor alone, and the points are 25 individual runs per grid point. '
        + crn_note + " "
        + span
        + ", ".join(f'<b>{ref[j] - last[j]:+.1f}°</b> on f{j+1}' for j in range(k))
        + ". <b>The curves settle onto the limit line, not onto the floor.</b> The floor is only "
          "one of the theorem&#39;s two terms; the in-subspace rotation is a finite-<i>n</i> "
          "effect and does not vanish as p grows, so the gap you can see between the two dashed "
          "lines is rotation error that no amount of assets removes. Both are p → ∞ statements "
          "at fixed n, which is why adding assets buys nothing here. What moves them is more "
          "history (the sweep above) or a stronger factor."
          "<br>The left of the grid is still climbing out of the pre-asymptotic regime, so "
          "the drop visible there is the asymptotics arriving, <b>not</b> a return on adding "
          "assets. Read the flat right-hand stretch, which is where any real universe sits."
          "</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ methodology
rule("[5] methodology & assumptions")

with st.expander("What this computes, what it assumes, and where it is wrong"):
    st.markdown(f"""
**What it is.** A conditional simulator of PCA factor-direction error. Given (n, p, k), per-factor
signal strengths and a factor-return distribution, it Monte-Carlos the finite-p error sin²∠(hⱼ, bⱼ)
per factor, reports it in degrees as 50/80/95% bands, and marks the observable floor ℓ/θⱼ separately.
PCA here means eigenvectors of the sample **covariance** matrix (not the correlation matrix), and the
"true direction" bⱼ is the corresponding population eigenvector of Σ — if your shop runs PCA on
correlations, the two problems differ by a per-asset rescaling and these numbers do not transfer.

**What it is not.**
- **Not an estimator of total error from data alone.** The rotation component is provably not
  estimable (Gurdogan–Shkolnik impossibility). The fan is *simulated under assumptions*.
- **Not a confidence interval.** The bands are a conditional predictive distribution under an
  assumed data-generating process. No amount of simulation fidelity changes this.
- Not investment advice, and not a production risk tool.

The two visual classes differ **in kind**: the orange floor tick is measured (or would be, from your
eigenvalues); the blue fan is simulated. Excess error above the floor is influenced by the
non-identifiable rotation term, but their visual separation in degrees is not the theorem's additive
second term (the decomposition is additive on the sin² scale).

#### Tied factors: when a label stops being a label

PCA orders factors by sample eigenvalue. When two eigenvalues are close, that ordering is not
stable: the estimator hands you two directions but cannot reliably say which is which. At an *exact*
tie it is not a precision problem but an identification one — any rotation within the shared plane is
an equally valid eigenbasis, so the per-factor angle degrades toward a random direction while still
printing as a number. In simulation, two strong but exactly-tied factors report ≈85° per-factor (no
information) while their 2-D span is known to ≈27°.

So when the estimator swaps two labels on more than {tie_cutoff_pct:g}% of paths — **an arbitrary
display cutoff, adjustable in the sidebar, not a theorem-derived threshold** — this app stops leading
with their named directions and reports their
**span** instead: the largest principal angle between the true and estimated subspaces, i.e. arccos of
the smallest singular value of Bᵀ H. That quantity is invariant to eigenvector sign *and* to label
swaps — the exact two ambiguities that corrupt the per-factor numbers — which is why it survives a tie
when they do not. The per-factor rows stay visible, marked, because they are still what the estimator
returned; at this swap rate they are unreliable as individually named directions.

**Claim boundary.** *Established:* at an exact tie only the joint span is invariant, and the largest
principal angle is what this engine simulates (checked against rotations of known size). *Not
established:* that the paper's Corollary 2 supplies a floor for *this* statistic (a bound on a sum of
subspace losses is not automatically a bound on the maximum principal angle), that 5% is a principled
switch, or that the required-history "unreachable" logic extends to a span. The app therefore reports
**no subspace floor, no span-level target test, and no theorem-derived threshold** — subspace mode is
a conditional diagnostic and a limitation flag, not a new theorem-backed output. Resolving the
theory-to-statistic mapping with the group is what those numbers would need first; until then, they
remain future work.

#### What is exact, what is asymptotic, what is simulated

| quantity | status |
|---|---|
| sin²∠(hⱼ, bⱼ) per path | **exact finite-p draw** — no asymptotic shortcut |
| floor tick, spectrum mode | exact arithmetic on your eigenvalues (its own sampling noise is **not** shown) |
| floor tick, model mode | median of the simulated plug-in ℓ/θⱼ — an asymptotic floor, not a pathwise finite-p bound |
| gray asymptotic tick (`asym°`) | closed-form limit arcsin√(δ²/(nλⱼ+δ²)) in the **p → ∞, n fixed** regime, derived under the model's own assumptions (in particular Gaussian idiosyncratic noise). Selecting Student-t factor returns changes the simulated fan only — **the formula is not re-derived for heavy tails**, which is why it is a reference tick and not a bound. Evaluated at the *population* strength λ = vol²×prevalence, a second (n → ∞) limit on top of the p → ∞ one |
| pathwise floor (`path°`) | the same formula at each path's *realized* ρⱼ (the eigenvalues of D̂ = C^½(FᵀF/n)C^½), then medianed. The theorem conditions on F, so ρⱼ is random and this is the floor it names; `asym°` silently substitutes its n → ∞ limit. They separate at small n because D̂'s eigenvalues spread, and **`asym°` is the optimistic one for the weaker factors** |
| fan quantiles | empirical quantiles of simulated paths; q90 includes a 95% bootstrap interval for Monte Carlo estimation noise |

Per path: Y = U·diag(√(pλ))·Φ + Z. The n×n dual Gram is simulated exactly without ever forming a
p-dimensional array (Wishart via Bartlett when p−k ≥ n, direct Gaussian block otherwise), so cost is
O(n³) and independent of p. Estimated and true directions are matched by the one-to-one permutation
that maximizes total absolute overlap. The `swap%` column reports how often that assignment differs
from the population-strength rank label. **That matching uses the true directions** — information no
practitioner has on real data, where you would name factors by economic interpretation and could
mislabel without knowing. Simulated named-factor accuracy is therefore optimistic in a way the fan
cannot show.

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

**Decomposition check.** The engine assembles the theorem pathwise — floor + (1−floor)·sin²∠(ŵⱼ, eⱼ)
at each path's own ρⱼ — and the median of that lands on the separately simulated median total. At the
default calibration the two agree to **0.0–0.34°**, against **0.48–3.28°** for the same assembly at
the population strength λ. Both sides are built per path and medianed once, so the substitution is
the only difference being measured. That checks equation (5) *inside* the simulator rather than one
implementation against another, and it is asserted in the engine self-check so it cannot rot. It is
one calibration: the gap widens as n falls and D̂'s eigenvalues spread, and that has not been swept.

**The asset sweep uses common random numbers, conditionally.** Every point on the p grid shares one
seed, but that only couples the draws when the whole grid stays in one Wishart branch (smallest
p−k ≥ n). The grid starts at p=100 and n goes to 504, so above roughly n=96 the small-p points take
the direct Gaussian branch and the stream desynchronizes. The panel reads the engine's flag and says
which case you are in rather than asserting one.

**That sweep converges on the theorem's limit, not on the floor.** The floor is one of two terms;
the in-subspace rotation is a finite-n effect and does not shrink as p grows. At default settings and
p=100,000 the medians are [16.90, 34.62, 43.95]° against a floor of [15.73, 32.21, 40.03]° and an
assembled limit of [16.91, 34.56, 43.93]°. Both lines are drawn, so the visible gap between them is
rotation error rather than something a bigger universe would close.

**External validity is not established.** The true loading direction is latent, so "realized
rotation" cannot be observed directly on real equity panels; cross-window sample rotation also
contains genuine loading drift and is not the fan's target. Every number here is therefore
internally consistent and externally unproven. The displayed q90 Monte Carlo interval quantifies only
numerical estimation noise from a finite number of simulated paths; it does not establish external
validity or quantify sampling noise in the spectrum-derived floor.

**Defaults** are the paper's illustrative calibration (US equity, Bayraktar et al. 2014), not fitted
to any current book.

[Source and full methodology register]({REPO})
""")

# ------------------------------------------------------------------ validation footer
if mode == "model calibration" and p == 3000 and n == 63 and k == 3 and dist_key == "t":
    rule("[6] validation")
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
