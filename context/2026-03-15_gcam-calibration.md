# GCAM Calibration Session — 2026-03-15

## What was built

### New files
- **`ghim/data/gcam_cal.py`** — GCAM parquet → GHIM variable mapping, vectorized (~2.5s load)
  - 22 years (1975-2100), 32 R32 regions
  - GCAM 1990$ → 2010$ (×1.5114 BEA deflator)
  - Fuel mapping (18→7), elec tech mapping (20→14), sector classifier, buildings subsector classifier
  - `_build_fe_aggregates()`: cached vectorized FE aggregation with `ghim_subsector` column
  - `load_gcam_calibration()` → `CalibrationDataset`

- **`ghim/calibration.py`** additions:
  - `CalibrationDataset` dataclass (targets-only container, R32 resolution)
    - Fields: gdp, population, capital_stock, factor_shares, elec_shares, fe_total, fe_carrier_shares, sector_totals, sector_carrier_shares, subsector_totals, subsector_carrier_shares, elec_generation
  - `Calibrator` class (general-purpose, `native_r32=True`) — same interface as `AR6Calibrator`
  - `AR6Calibrator` updated: `native_r32=False`, `model_name` property

- **`ghim/tests/test_gcam_calibrator.py`** — 45 tests

- **`ghim/output/calibration_validation.py`** — validation plots script

### Modified files
- **`ghim/build.py`**:
  - `calibrator_type` param on `build_oop_model()` and `oop_run_model()`
  - GCAM GDP (MER, 2010$) used when `calibrator_type="gcam"` (SSP PPP 2005$ for AR6)
  - `_apply_ar6_calibration` → `_apply_calibration` (handles both AR6/GCAM)
  - `_apply_subsector_calibration()` — buildings subsector-level calibration
  - Subsector-level carrier share recalibration in `_apply_calibration` for buildings
  - GDP diagnostic uses `model.ssp_gdp_target` instead of SSP dataframe

- **`ghim/run.py`**: `--calibrator {ar6, gcam}` CLI flag

- **`ghim/sectors/buildings.py`**:
  - All EndUseTech efficiencies set to 1.0 (preference factors absorb cost/efficiency)
  - Coal added to `_other_techs()` (for China/India cooking/water heating)

- **`ghim/sectors/transport.py`**:
  - `_TransportSubsector.calibrate()` override — uses `lcot()` ($/km) not `levelized_cost()` ($/GJ)
  - Fixed 16% transport FE deviation bug (cost space mismatch)

### Presentation
- `present/slim-19-mar-2026/slides.tex`:
  - Page 23: static Model Overview (white bg, no title)
  - Calibration Validation section (8 slides): pipeline, GDP, FE sector, FE carrier, elec gen, elec mix, solver/timing

## Calibration results (493 tests passing)

| Item | Deviation |
|------|-----------|
| GDP (endogenous, 32 regions, 2025-2100) | **0.00%** |
| Industry FE (base year, all regions) | **0.0%** |
| Buildings FE (base year, all regions) | **0.0%** |
| Buildings subsectors (6 services × all regions) | **0.0%** |
| Transport FE (base year, all regions) | **+0.1%** |
| Buildings carrier shares (base year) | **±0.1pp** (USA/EU/India 0.0pp) |
| Global FE trajectory (2025→2100) | **+1.3% → +2.5%** |
| Worst-case regional FE deviation | **<4%** |

## Electricity generation calibration — COMPLETED

### Problem & fix
- GCAM gen = FE demand + T&D losses + own-use (ratio 1.09-1.63× by region)
- Fix: `_apply_calibration` sets `sector._generation_target` from GCAM data
- `model.F()` uses `_generation_target` instead of FE demand as `demand_ej`
- `elec_generation` field added to `CalibrationDataset`, populated in `load_gcam_calibration()`
- Result: **0.00% deviation**, all 32 regions, 2025-2100

## Key design decisions made
- **GDP unit**: Calibrator-specific (GCAM=MER 2010$, AR6=PPP 2005$). TFP recalibrates to match.
- **PPP/MER**: GCAM has both; ratio is fixed over time in GCAM. MER chosen for internal consistency with energy prices and trade.
- **Buildings efficiency**: All techs set to 1.0 — preference factors absorb physical COP/efficiency. This gives near-perfect carrier share reproduction.
- **Transport calibrate()**: Must use lcot() ($/km) not levelized_cost() ($/GJ) to match compute_shares().
- **CalibrationDataset**: Targets-only container. Input data (costs, learning rates) stays in model config. Future extension: user-provided InputDataset.

## Timing
- Data loading: 3.5s
- TFP calibration (4 passes × 26 periods): 36s
- Forward solve (26 periods × 1.9s/period): 50s
- Total: ~90s (single-thread Python)
