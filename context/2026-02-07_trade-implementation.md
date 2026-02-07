# Inter-Regional Primary Energy Trade — Implementation Log

**Date**: 2026-02-07
**Branch**: `cht/proj/phase-1`
**Commits**: `d7774f8d5` (trade module), `334f6f2bb` (deflator fix)

## What Was Done

Implemented Phase 1 inter-regional primary energy trade for coal, oil, and gas.

### New Files
| File | Purpose |
|---|---|
| `scripts/export_fos_curves.R` | Extracts `L111.RsrcCurves_EJ_R_Ffos` from `PREBUILT_DATA.rda` → CSV |
| `ghim/data/external/energy/fos_curves_R32.csv` | 832 rows, R32-level fossil supply curves (1975$/GJ) |
| `ghim/data/trade_cal.py` | R32→country (GDP-share downscale)→R10 pipeline, transport costs |
| `ghim/energy/trade.py` | `GlobalMarket`, `TradeModule`, `TradeResult` — market clearing |
| `ghim/tests/test_trade.py` | 26 tests (unit + integration) |

### Modified Files
| File | Change |
|---|---|
| `ghim/config.py` | Added `TRADED_FUELS`, `TRADE_PRICE_TOL/MAX_ITER/FLOOR/CEILING`, `GCAM3_TO_2020_DEFLATOR` |
| `ghim/energy/supply.py` | Added `production_at_price()` method and `max_annual_production` field to `ResourceSupply` |
| `ghim/solver/recursive.py` | Added `trade_prices` param to `solve_period()`, `compute_primary_fuel_demand()` helper, `_solve_regions_for_period()`, restructured `run_model()` with trade clearing loop, trade fields on `PeriodResult` |
| `ghim/output/reporting.py` | Added trade columns (world prices, net exports, domestic production) |
| `ghim/run.py` | Added `--no-trade` CLI flag |
| `CLAUDE.md` | Updated architecture, commands, module structure |

## Architecture

### Data Pipeline
```
PREBUILT_DATA.rda
  → Rscript scripts/export_fos_curves.R
  → fos_curves_R32.csv (832 rows, costs in 1975$/GJ)
  → trade_cal.py: R32→country (GDP-share)→R10, deflate 1975$→2020$
  → build_regional_supplies(): region→fuel→ResourceSupply
```

### Market Clearing (per period)
```
1. compute_primary_fuel_demand() per region (single-pass estimate)
2. TradeModule.solve_trade() → GlobalMarket.clear_market() per fuel
   - Collect all grade costs across regions
   - Find cheapest grade cost where total capacity >= total demand
   - Fine-tune via bisection if intermediate grades exist
   - Scale production proportionally when capacity > demand
3. solve_period() per region with delivered prices (world + transport)
```

### Key Design Decisions
- **Step-function supply curves**: Grade-cost search (not pure bisection) to handle discrete jumps
- **max_annual_production**: 3x base-year production cap per region/fuel (prevents stock=flow confusion)
- **Single-pass demand**: Trade demands estimated once, not iterated with solver (known limitation)
- **Proportional scaling**: When supply capacity > demand at marginal price, regions produce proportionally
- **Floating-point eps**: `production_at_price()` uses eps=1e-6 for grade cost comparison

## GDP Deflator
- **Source**: BEA GDP Implicit Price Deflator, FRED series A191RD3A086NBEA
- **In-repo**: `input/gcamdata/R/pipeline-helpers.R:346-359` (hardcoded array, 1929-2023)
- **Value**: 105.381 / 27.800 = **3.79** (1975$ → 2020$)
- **Initial error**: Had 3.56 (corresponds to ~2016-2017, not 2020). Fixed in `334f6f2bb`.

## Test Results
- **114 tests passing** (88 existing + 26 new trade tests)
- Sanity checks verified:
  - Middle East is net oil exporter
  - Eurasia exports oil and gas
  - North America exports gas
  - Global net exports sum to ~0 per fuel at base year
  - World prices in range $1-50/GJ

## Known Limitations
- **Single-pass demand estimation**: `compute_primary_fuel_demand()` runs once before trade clearing; actual demands in `solve_period()` may differ due to price changes. Could iterate.
- **No depletion tracking in trade**: `cumulative_extracted` on trade supply curves is not updated period-to-period (resource depletion not modeled yet).
- **Transport costs are fixed**: No distance-based or congestion-based transport cost dynamics.
- **Future phases**: Electricity interconnection, refined products trade, hydrogen trade.
