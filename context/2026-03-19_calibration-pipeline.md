# Research Note — 2026-03-19: Calibration Pipeline Overhaul

## Session Summary

Full calibration pipeline restructuring for H2, district heat, demand carrier shares, and electricity generation mix.

## What Was Done

### 1. H2/DH Production Calibration (COMPLETED)
- Added `heat_production`, `h2_production` to CalibrationDataset
- Derived from demand-side FE aggregates (Σ sector_total × carrier_share)
- `_generation_target` mechanism: 0.0% deviation all periods

### 2. Demand Carrier Share Calibration (COMPLETED)
- **Industry**: Added "heat" EndUseTech to EU subsector
- **Buildings**: Added "heat" to `_other_techs()`
- **Subsector-adjusted shares**: `_subsector_adjusted_shares()` for EU/FS split
- **Efficiency correction**: FE→service share conversion (`tech_shares × effs`)
- **Inline preference recalibration**: in `model.F()` every solver iteration using cached `_target_svc_shares`

### 3. sector_pref_weight (COMPLETED)
- Replaces `_demand_scale` (exogenous multiplier) with price-channel mechanism
- `w = P × (ratio^(1/γ) − 1)` — analytically solved
- Sector total demand adjusts via price elasticity, not fudge factor
- `_demand_scale` removed from `demand_envelope()`

### 4. Buildings Independent Subsector Demands (COMPLETED)
- Each subsector (res/com × heating/cooling/other) has own demand envelope
- Per-subsector income elasticity + HDD/CDD climate scaling
- `calibrate_subsector_demands()` back-calculates base_demand from GCAM targets
- Subsector fractions now endogenous (income-driven mix shift)

### 5. Industry Income Elasticity Fix (COMPLETED)
- Was: `approx_demand = base_demand × GDP_ratio` → circular, premature satiation for developing countries
- Now: `_last_demand_ej` from previous period (inter-period carry-forward)
- Fully endogenous, recursive-dynamic structure

### 6. Transport price_index Override (COMPLETED)
- `_TransportSubsector.price_index()` now uses `lcot()` ($/km) instead of `levelized_cost()` (mixed units)

### 7. Agriculture Calibration (COMPLETED)
- Enabled via `_SECTOR_AR6_NAME["AgricultureSector"] = "agriculture"`

### 8. Electricity R32 Init (COMPLETED)
- Replaced R10 `DEFAULT_ELEC_SHARES` with GCAM R32 base year shares
- Falls back to GCAM-v8.2 SSP2-Ref if no calibrator
- South Korea nuclear: -14.2pp → -0.8pp

### 9. Profit Shutdown (COMPLETED)
- Added to VintageTracker/PipelineAwareVintageTracker
- GCAM A23 params: median_shutdown_point=-0.1, steepness=6
- pref_weight flows through to shutdown via unit conversion (pf × k/β)
- FOM included in variable cost (not sunk — real ongoing cost)
- All techs get profit shutdown (including renewables for consistency)

### 10. Electricity Inline Recalibration (COMPLETED)
- `_target_tech_shares` cached from `_apply_calibration`
- Recalibrated at current LCOE in `model.F()` step 4pre

## Current Calibration Results (2025-2100)

| Metric | Result |
|--------|--------|
| GDP | 0.0% all periods |
| Industry | 0% all periods |
| Buildings | 0-1% |
| Transport | 0% |
| Agriculture | -3→0% |
| FE Total | +0.1% |
| Electricity/H2/DH production | 0.0% |
| Carrier gaps | ±2.7 EJ stable |
| Elec tech mix | coal +2-6pp, solar -2-8pp (vintage inertia) |

## Remaining Issues

### Electricity Tech Mix Gap (coal +4pp, solar -8pp at 2050)
- Root cause: vintage inertia — coal profitable (cheap fuel), solar/wind underinvested
- Profit shutdown helps but coal var_cost (11.2 $/GJ with FOM) < market_price (13)
- FOM just added to var_cost — awaiting test results
- Possible further fix: resource constraints for hydro/wind/solar (external model linkage)

### Resource Constraints (Phase 2+ / External Linkage)
- Hydro: no max generation cap → overinvested (+4pp)
- Solar/Wind: no land/grid constraint
- This motivates linkage with water/land-use models (design point, not bug)

### Legacy Code Cleanup Needed
- `AR6Calibrator`: should be removed, replaced by `Calibrator`
- `DEFAULT_ELEC_SHARES`, `DEFAULT_ELEC_TOTAL_EJ`: R10-based, dead code
- `is_native_r32` checks: always True with GCAM, simplify
- `R32_TO_R10` mapping: only needed for trade (separate concern)
- Calibrator naming: should be parameterized by (model, scenario), not hardcoded "GCAM"

## Files Modified This Session

| File | Changes |
|------|---------|
| `ghim/calibration.py` | heat/h2 fields + getter methods |
| `ghim/data/gcam_cal.py` | heat/h2 production from FE aggregates |
| `ghim/build.py` | Major: R32 init, subsector adjustment, pref_weight, inline recal, agriculture, buildings subsector demands, inter-period demand carry-forward |
| `ghim/model.py` | Inline recalibration for demand + electricity sectors |
| `ghim/sectors/abc.py` | sector_pref_weight, removed _demand_scale |
| `ghim/sectors/buildings.py` | Independent subsector demands, calibrate_subsector_demands |
| `ghim/sectors/industry.py` | Heat tech, _last_demand_ej, income elasticity fix |
| `ghim/sectors/transport.py` | price_index lcot override |
| `ghim/sectors/district_heat.py` | total_production_ej param |
| `ghim/sectors/electricity.py` | R32 init, profit shutdown params, FOM in var_cost |
| `ghim/core/vintage.py` | profit_shutdown_factor, profit_shutdown_params, initialize_single_vintage |
| `ghim/tests/test_sectors.py` | EU tech count 7→8 |

## Commits (cht/proj/phase-1)

1. `5bbe9cf` - H2/heat/demand carrier matching
2. `a4095ce` - Buildings independent subsector demands
3. `31b0e69` - Industry income elasticity fix (GCAM target ref)
4. `b3e6cca` - Endogenous industry elasticity (inter-period carry-forward)
5. `da62d74` - Profit shutdown for electricity vintage
6. `0b0cc06` - Profit shutdown unit conversion fix + single-vintage option
7. `6d2c523` - R32 GCAM elec shares for vintage init + slides
8. (pending) - FOM in variable cost for profit shutdown

## Next Steps When Resuming

### Refactor (높은 우선순위)
1. **AR6 완전 삭제** — AR6Calibrator class, ar6_cal.py, is_native_r32 분기, R5 매핑 전부 제거
2. **Calibration 인터페이스 재설계** (유저 확정):
   ```
   calibrate = True (default)
     ├── dataset 없음 → GCAM-v8.2 / SSP2-Ref / 1975-2100 / run_end=2100
     ├── dataset 있음 + model_name/scenario 없음 → 유저에게 되물음 (error)
     └── dataset 있음 + model_name/scenario 있음 → 해당 데이터로 calibration
         ├── cal_start, cal_end: 데이터셋에서 자동 결정 (유저 override 가능)
         └── run_end: default = cal_end (유저가 2150 등으로 연장 가능)
   calibrate = False
     └── 이전에 저장된 calibrated params 로드해서 바로 solve
   ```
3. **Calibrated params 저장/로드**: pref_factors, sector_pref_weight, _target_svc_shares, vintage state 등을 파일로 저장 → 재활용
4. **DEFAULT_ELEC_SHARES 등 R10 legacy dict 삭제** — GCAM fallback으로 대체 완료
5. R10은 trade module에서만 사용 → 유지

### 모형 개선
6. **Buildings subsector 독립 수요함수** (gcamdata A44 파라미터) — Phase 1 scope
7. Hydro 자원 제약 (max generation cap)
