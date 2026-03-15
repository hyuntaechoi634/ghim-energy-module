# Research Note — 2026-03-19: Calibration Pipeline Overhaul

## Session Summary (2 sessions, 2026-03-16)

Full calibration pipeline restructuring: H2/DH/carrier shares, electricity tech mix,
AR6 removal, post-cal projection, solver optimization, buildings demand curves.

## Session 1: Calibration Accuracy

### Completed
1. **H2/DH production calibration** — 0.0% deviation all periods
2. **Demand carrier shares** — Industry heat tech, buildings heat, efficiency correction
3. **sector_pref_weight** — replaces _demand_scale (price-channel mechanism)
4. **Buildings independent subsector demands** — per-subsector income elasticity
5. **Industry endogenous income elasticity** — inter-period demand carry-forward
6. **Profit shutdown** — GCAM A23 params, FOM in var_cost, pref_weight flows through
7. **R32 GCAM elec shares** — vintage initialization (South Korea nuclear -14pp→-0.8pp)
8. **Vintage back-calculation** — new = (target×demand - surviving)/gap → ±1pp tech mix
9. **Inline preference recalibration** — in model.F() every solver iteration
10. **Tests**: 300s→9s (lru_cache on load_gcam_calibration)

## Session 2: Architecture + Post-cal

### Completed
11. **AR6 완전 삭제** — AR6Calibrator, ar6_cal.py, is_native_r32 분기 전부 제거 (-1077줄)
12. **CalibrationConfig** — calibrate/model_name/scenario/cal_start/cal_end/run_end/post_cal_mode
13. **T&D loss rate** — replaces _generation_target (demand × (1/(1-td_loss)))
14. **Post-cal HOLD/DECAY** — 2100-2150 projection, exogenous GDP 해제
15. **TFP trend extrapolation** — post-cal에서 마지막 성장률 외삽 (GDP 313→641T$)
16. **calibration_year fix** — preference decay가 inline recal 후 적용되는 버그
17. **Industry oscillation damping** — _last_demand_ej damped update (0.7×new + 0.3×old)
18. **Anderson solver** — 325-dim full state vector (구현됨, DampedSolver가 더 빠름)
19. **DampedSolver 최적화** — FE_RECAL 3→2, 78s→51s
20. **Non-parametric demand curves** — buildings subsector GDP/cap→demand/cap lookup
21. **sector_pref_weight → subsector 전달** — buildings override 수정 (Bld +27%→-4%)
22. **CalibratedParams save/load** — pickle (~1.6MB)
23. **Calibration pass bounded** — cal_end까지만 (post-cal TFP 감소 방지)

## Current Calibration Results

### Calibration (2025-2100)
| Metric | Result |
|--------|--------|
| GDP | 0.0% all periods |
| Industry | ±1% |
| Buildings | ±4% (2025) → ±1% (2050+) |
| Transport | 0% |
| FE Total | ±0.3% |
| Elec generation | +1-2% (T&D loss based) |
| Elec tech mix | ±1pp |
| Carrier gaps | ±2.7 EJ |

### Post-cal (2100-2150, HOLD mode)
| Metric | 2100 | 2150 | Trend |
|--------|------|------|-------|
| GDP | 313T$ | 641T$ | +1.5%/yr |
| GDP/cap | 31.7k | 69.7k | +2.0%/yr |
| Population | 9.88B | 9.19B | -0.7%/yr |
| FE | 724 EJ | 681-744 EJ | Industry oscillation |
| Elec share | 36.4% | 36-38% | Stable |
| Coal (elec) | 24% | ~7% | Natural retirement |
| Solar (elec) | 25% | ~48% | Learning + new investment |

### Performance
- Run time: 50s (26 periods, DampedSolver)
- Tests: 491 pass, 9s
- Save/load: 1.6MB pickle

## Architecture Decisions Made

1. **_generation_target 제거** → T&D loss rate (demand-driven, not quantity-forced)
2. **_demand_scale 제거** → sector_pref_weight (price-channel)
3. **calibrate_subsector_demands 유지** — 상수 α 부족 (Gompertz 미반영), demand curves 보완
4. **Vintage back-calculation** — target_shares = effective target (not new-investment share)
5. **Profit shutdown** — FOM in var_cost, pref_weight flows through (pf × k/β unit conversion)
6. **Post-cal mode**: HOLD (default) > DECAY (unstable FE oscillation)
7. **TFP extrapolation** — last calibration growth rate for post-cal
8. **Solver**: DampedSolver default (51s) > Anderson (111s, needs deepcopy optimization)

## Key Bugs Found and Fixed

1. **R10 DEFAULT_ELEC_SHARES** → South Korea nuclear 14pp gap (R10 average ≠ R32)
2. **Vintage investment allocation** — used GCAM effective shares as new-investment shares
3. **Preference decay after inline recal** — calibration_year not updated → H2 drift
4. **sector_pref_weight not reaching buildings subsectors** — override broke price channel
5. **TFP decreasing post-cal** — calibration pass ran for post-cal with flat GDP target
6. **Industry cobweb oscillation** — _last_demand_ej feedback loop
7. **use_gcam_gdp NameError** — leftover from AR6 removal

## Next Steps When Resuming

### High Priority
1. **Buildings 2025 gap (-4%)** — first-period price transient, demand curves not perfectly aligned
2. **Industry FE oscillation** — 697-744 EJ in post-cal (damping helps but not eliminated)
3. **CalibratedParams: load path** — pickle load → skip calibration → continue run
4. **1975 model start** — economy init at 1975, run through historical periods

### Medium Priority
5. **Anderson solver optimization** — eliminate deepcopy in template management
6. **Buildings Gompertz per subsector** — income-dependent curves (constant α insufficient)
7. **Hydro resource constraint** — max generation cap per region
8. **Population extrapolation** — SSP2 population beyond 2100

### Lower Priority
9. **Calibrator parameterization** — generic dataset loader (not just GCAM-v8.2)
10. **Legacy cleanup** — remaining R10 references in trade module
11. **DECAY mode stabilization** — smooth pref_weight transition (exponential instead of linear)

## Files Modified (Session 2)

| File | Key Changes |
|------|-------------|
| `ghim/calibration.py` | CalibrationConfig, PostCalMode, make_calibrator, save/load |
| `ghim/data/ar6_cal.py` | DELETED |
| `ghim/data/gcam_cal.py` | bld_sub_demand_curves, bld_sub_income_elas, elec_td_loss |
| `ghim/data/energy_cal.py` | Removed DEFAULT_ELEC_SHARES/TOTAL/FINAL_DEMAND |
| `ghim/build.py` | AR6 removal, time_cfg, cal_end guard, TFP extrapolation, post-cal GDP release |
| `ghim/model.py` | calibration_year fix in inline recal, T&D loss in step 4 |
| `ghim/sectors/buildings.py` | demand curves, sector_pref_weight wiring |
| `ghim/sectors/electricity.py` | profit shutdown params, FOM in var_cost, R32 init |
| `ghim/core/state.py` | Extended to_vector 325 dims |
| `ghim/core/vintage.py` | profit_shutdown, back-calculation, damped carry-forward |
| `ghim/solver/damped.py` | AndersonSolver, FE_RECAL 3→2 |
| `ghim/run.py` | --run-end, --post-cal-mode, --save-params, --load-params |

## Commits (Session 2, cht/proj/phase-1)

Latest: `c64892226` — Add GHIM sector lines to FE by Sector chart
