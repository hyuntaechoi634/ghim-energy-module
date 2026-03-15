# GHIM — Regional Data Requirements

Currently hardcoded as global defaults in `ghim/build.py`. Need region-specific (R32) data from gcamdata or IEA to replace.

## 1. Carrier Prices ($/GJ, base year)

Currently `_default_carrier_prices()` in `build.py:76-82`:

| Carrier | Default | Source needed |
|---------|---------|---------------|
| Electricity | 20.0 | IEA regional electricity prices |
| Gas | 5.0 | IEA regional gas prices |
| Coal | 3.0 | IEA regional coal prices |
| Liquids | 12.0 | IEA regional oil product prices |
| Biomass | 3.0 | gcamdata biomass supply curves |
| Biofuel | 12.0 | gcamdata / literature |
| H2 | 15.0 | Literature (grey/green H2 by region) |
| Heat | 10.0 | IEA district heat prices |

**Impact**: These flow into KLEM calibration via `composite_energy_price()` → `base_energy_price` → TFP calibration. Wrong prices → wrong TFP → wrong GDP trajectory.

## 2. Carrier Demands (EJ, base year)

Currently `_industry_carrier_demands()`, `_buildings_carrier_demands()`, `_transport_carrier_demands()` in `build.py:89-112` — global splits hardcoded.

| Sector | What's needed | Source |
|--------|--------------|--------|
| Industry | Carrier-level FE by R32 | IEA energy balances / gcamdata `module_energy_L1*` |
| Buildings | Carrier-level FE by R32 | IEA energy balances / gcamdata |
| Transport | Carrier-level FE by R32 | IEA energy balances / gcamdata |

**Impact**: Carrier splits determine demand-side logit calibration and AR6 preference factors.

## 3. Derived Quantities (computed, not directly needed)

These are computed from (1) and (2) above — no separate data source needed:

- `composite_energy_price` = expenditure-weighted average of carrier prices
- `base_el_price`, `base_nel_price` = electricity vs non-electric composite
- `E_val` = E (EJ) × p_E ($/GJ) → billion $ for CES nests

## 4. Priority

**High** — regional price variation is large (electricity: ~5 $/GJ in China vs ~30 $/GJ in Japan). Using a single global default distorts TFP calibration and cross-region comparisons.

## 5. Potential Sources

1. **gcamdata outputs**: `module_energy_L1*` chunks already have IEA energy balances by GCAM region. R32→R32 direct mapping.
2. **IEA World Energy Balances**: Most comprehensive, but requires license. Covers prices + quantities by country → aggregate to R32.
3. **AR6 SSP database**: Has final energy by carrier by R5. Could downscale to R32 via GDP shares (already done for FE level scaling).
