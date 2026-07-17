"""Default calibration, sweep grid, and the precomputed default sweep.

Why this file exists: the required-history sweep eigendecomposes an n x n matrix
per path and the grid runs to n=252, so it costs O(n^3) x reps x 6 points. That
is ~1s on a laptop and ~7 MINUTES on Streamlit's free tier, which measured
100-300x slower. Nearly every visitor clicks that button on the paper defaults,
which never change - so the answer is precomputed here, once, and committed.

The precomputed path is also the *more* accurate one: fidelity is free when you
pay for it offline, so the cache runs at 1000 paths per point where the live
path can only afford 200.

Only the discrete inputs are precomputed (k = 1..4 at the paper calibration).
Vols, prevalence, idio and p are continuous, so a custom calibration always
falls through to the live path - correct, just slow, and the app says so.

Deliberately free of streamlit so it can be imported by the builder without
booting the app. Rebuild after touching SWEEP_GRID, the defaults, or
engine.simulate:

    python3 calibration.py
"""
import json
from pathlib import Path

import engine

# paper Table 1 (annualized %) and the G_B diagonal; provenance in the app's
# methodology register. Illustrative, not fitted to any current book.
DEFAULT_VOLS = [16.0, 8.0, 6.0, 5.0]
DEFAULT_PREVS = [1.25, 1.0, 1.0, 1.0]
DEFAULT_IDIO = 40.0
DEFAULT_P = 3000
DEFAULT_K = 3
DEFAULT_DIST = "t"
MAX_K = 4

# 1mo ... 1y of daily data. Stops at 252 by decision, not by cost: the model
# holds loadings fixed for the whole window, so reading further would answer
# "how much history do I need?" using its least credible assumption.
SWEEP_GRID = [21, 42, 63, 126, 189, 252]
LIVE_REPS = 200      # what a custom calibration can afford on a shared vCPU
CACHED_REPS = 1000   # precomputed, so precision costs nothing at run time

CACHE_PATH = Path(__file__).resolve().parent / "sweep_default.json"


def engine_args(vols, prevs, idio):
    """UI units (annualized %) -> engine units. One definition, imported by both
    the app and the builder, so they cannot drift into a silent cache miss."""
    a = [(v / 100) ** 2 * c for v, c in zip(vols, prevs)]
    return a, (idio / 100) ** 2


def key(p, k, a, d2, dist):
    """Identity of a sweep. Rounded because these come from float widget math.
    n is absent on purpose: the sweep varies n itself, so the sidebar's n never
    invalidates the cache."""
    return [p, k, [round(float(x), 12) for x in a], round(float(d2), 12),
            dist, list(SWEEP_GRID)]


def load(p, k, a, d2, dist):
    """The precomputed sweep for this calibration, or None to compute it live."""
    if not CACHE_PATH.exists():
        return None
    want = key(p, k, a, d2, dist)
    for entry in json.loads(CACHE_PATH.read_text())["entries"]:
        if entry["key"] == want:
            return entry["sweep"]
    return None


def _build():
    entries = []
    for k in range(1, MAX_K + 1):
        a, d2 = engine_args(DEFAULT_VOLS[:k], DEFAULT_PREVS[:k], DEFAULT_IDIO)
        print(f"k={k}:")
        sweep = engine.sweep_n(
            DEFAULT_P, SWEEP_GRID, k, a, d2, DEFAULT_DIST, 6, CACHED_REPS,
            on_point=lambda done, total, n: print(f"  n={n:<4} ({done}/{total})"))
        entries.append({"key": key(DEFAULT_P, k, a, d2, DEFAULT_DIST), "sweep": sweep})

    CACHE_PATH.write_text(json.dumps(
        {"reps": CACHED_REPS, "grid": SWEEP_GRID, "entries": entries}, indent=1))

    # every precomputed entry must load back, or the app silently pays 7 minutes
    for k in range(1, MAX_K + 1):
        a, d2 = engine_args(DEFAULT_VOLS[:k], DEFAULT_PREVS[:k], DEFAULT_IDIO)
        assert load(DEFAULT_P, k, a, d2, DEFAULT_DIST) is not None, f"k={k} does not load back"
    print(f"wrote {CACHE_PATH.name}: {CACHED_REPS} paths x {len(SWEEP_GRID)} points "
          f"x k=1..{MAX_K}  ({CACHE_PATH.stat().st_size / 1024:.1f} kB)")


if __name__ == "__main__":
    _build()
