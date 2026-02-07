# Fix GDP Soaring at 2020→2025 Transition

**Date**: 2026-02-07
**Branch**: `cht/proj/phase-1`

## Problem

Asia-Pacific Developed GDP jumped from 5,637 B$ (2020) to 9,157 B$ (2025) — a 62% surge vs SSP's expected ~9% growth. Occurred with and without trade.

**Root cause**: `klem.py:118` — forward TFP calibration read `self.capital_stock` which had just been reset to K(2000)=5,056 on line 115, instead of K(BASE_YEAR)=19,536. This produced inflated TFP for all future years (TFP jumped from 13.24 at 2020 to 20.29 at 2025).

**Secondary issue**: Trade-cleared prices far below observed (oil $2.07 vs $6.76/GJ), causing unrealistic fuel price discontinuity at 2020→2025.

## Changes Made

### 1. Primary fix — `ghim/econ/klem.py:118`
```python
# BEFORE (buggy):
k_ref = self.capital_stock  # ← K(2000) after line 115 reset

# AFTER (fixed):
k_ref = k_hist[BASE_YEAR]  # K(BASE_YEAR) = K(2020)
```

### 2. Trade transition config — `ghim/config.py`
Added `TRADE_TRANSITION_YEARS: int = 20` — linearly blends observed→trade-cleared world prices over 20 years (w=0.25 at 2025, 0.50 at 2030, 0.75 at 2035, 1.0 at 2040+).

### 3. Trade price blending — `ghim/solver/recursive.py`
After projection-period trade iteration converges, blends world prices:
- `blended = (1-w) * observed + w * cleared`
- Blends on world prices (not delivered) so transport costs aren't double-counted
- Recomputes delivered prices from blended world prices

### 4. Regression test — `ghim/tests/test_klem.py`
`test_future_tfp_uses_base_year_k()` — verifies TFP(2025)/TFP(2020) < 1.5.

## Test Results
- **115 tests passing** (114 original + 1 new regression test)

## Remaining Work / Next Steps
- Visually verify GDP trajectory is smooth (run model + check output)
- Known issues still open:
  - **HIGH**: Zero population → arbitrary TFP fallback (`klem.py:85-86`)
  - **MEDIUM**: Price iteration non-convergence is silent (`recursive.py:239`)
  - **MEDIUM**: `PREF_DECAY_RATE` defined but never wired in (`config.py:62`)
  - **MEDIUM**: `LABOR_FORCE_PARTICIPATION` global not regional (`config.py:32`)
  - Default energy data is approximate IEA 2020 values, not from actual IEA database
  - Late-period (2130+) oscillation persists when resources deplete through major grade boundaries
