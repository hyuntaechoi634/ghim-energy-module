# API Reference

This page provides a summary of all public modules, classes, and functions in the GHIM package.

## Configuration

### `ghim.config`

| Constant | Value | Description |
|----------|-------|-------------|
| `BASE_YEAR` | 2020 | Model base year |
| `END_YEAR` | 2100 | Final model year |
| `TIMESTEP` | 5 | Years per period |
| `MODEL_YEARS` | [2020, 2025, ..., 2100] | All 17 model periods |
| `DISCOUNT_RATE` | 0.05 | Annual discount rate |
| `DEPRECIATION_RATE` | 0.05 | Annual capital depreciation |
| `SIGMA_VA` | 0.5 | CES elasticity: Capital vs Labor |
| `SIGMA_EM` | 0.5 | CES elasticity: Energy-Materials |
| `SIGMA_E` | 1.0 | CES elasticity: Electric vs Non-electric |
| `SIGMA_NE` | 2.0 | CES elasticity: Among non-electric fuels |
| `ELEC_LOGIT_EXP` | -4.0 | Logit exponent for electricity sector |
| `DEMAND_LOGIT_EXP` | -3.0 | Logit exponent for fuel switching |
| `PRICE_TOL` | 0.001 | Relative price convergence tolerance |
| `PRICE_DAMP` | 0.5 | Damping factor for price updates |

**`capital_recovery_factor(rate, lifetime) → float`**
: Compute the annualized payment factor $CRF = r(1+r)^T / [(1+r)^T - 1]$.

---

## Regions

### `ghim.regions`

**`R10_REGIONS`** — list of 10 AR6 region names.

**`load_region_mapping() → DataFrame`**
: Load the ISO → R10 mapping from `mapping/region_classification.tsv`.

**`build_iso_to_r10() → dict[str, str]`**
: Return a dictionary mapping ISO alpha-3 codes to R10 region names.

**`build_country_to_r10() → dict[str, str]`**
: Return a dictionary mapping country names to R10 region names.

---

## Economics

### `ghim.econ.ces`

**`ces_output(inputs, alphas, sigma, scale=1.0) → float`**
: Compute CES aggregate output $Y = A[\sum \alpha_i X_i^\rho]^{1/\rho}$.

**`ces_price(prices, alphas, sigma) → float`**
: Compute the CES dual (composite) price index.

**`ces_demand(output, price_out, prices_in, alphas, sigma) → ndarray`**
: Compute cost-minimizing input demands via Shephard's lemma.

**`ces_calibrate(base_inputs, base_prices, sigma) → ndarray`**
: Recover CES share parameters from observed quantities and prices.

### `ghim.econ.klem`

**`KLEMDriver(base_gdp, base_population, base_energy_demand_ej, ...)`**
: KLEM macro driver for a single region. Calibrates CES share parameters from base-year data.

Methods:
- **`compute_energy_demand(gdp, population, energy_price) → float`** — Returns total energy demand in EJ.
- **`update_capital(investment) → None`** — Advance capital stock by one timestep.

---

## Energy Sector

### `ghim.energy.logit`

**`relative_cost_logit(costs, share_weights, logit_exp) → ndarray`**
: Compute market shares using relative cost logit $s_i = \alpha_i c_i^\beta / \sum \alpha_j c_j^\beta$.

**`absolute_cost_logit(costs, share_weights, logit_exp, base_value=1.0) → ndarray`**
: Compute shares using absolute cost logit.

**`logit_shares(costs, share_weights, logit_exp, mode="relative") → ndarray`**
: Unified interface — dispatches to `relative_cost_logit` or `absolute_cost_logit`.

**`logit_calibrate(base_shares, base_costs, logit_exp, ...) → ndarray`**
: Calibrate share weights to reproduce observed base-year shares.

**`logit_average_cost(costs, share_weights, logit_exp, ...) → float`**
: Compute share-weighted average cost.

### `ghim.energy.technology`

**`Technology`** (dataclass)
: Represents a single energy conversion technology.

Fields: `name`, `sector`, `fuel_input`, `efficiency`, `capital_cost`, `om_fixed`, `om_variable`, `capacity_factor`, `lifetime`, `share_weight`, `carbon_coef`.

Methods:
- **`levelized_cost(fuel_price, discount_rate=0.05) → float`** — Compute LCOE in $/GJ.
- **`annual_emissions_tc(output_ej) → float`** — Compute annual emissions in MtC.

Factory functions:
- **`default_electricity_techs() → list[Technology]`** — 8 generation technologies.
- **`default_refining_techs() → list[Technology]`** — Oil refining.
- **`default_hydrogen_techs() → list[Technology]`** — SMR + electrolysis.

### `ghim.energy.electricity`

**`ElectricitySector(techs=None, logit_exp=-4.0)`**
: Electricity generation sector for a single region.

Methods:
- **`calibrate(base_shares, fuel_prices)`** — Calibrate share weights from observed generation shares.
- **`compute_supply(fuel_prices, total_demand_ej) → dict[str, float]`** — Compute generation by technology.
- **`weighted_cost(fuel_prices) → float`** — Compute sector-average electricity price.
- **`fuel_consumption(generation_by_tech) → dict[str, float]`** — Compute fuel inputs.
- **`emissions_mtc(generation_by_tech) → float`** — Compute total CO$_2$ emissions.

### `ghim.energy.refining`

**`RefiningSector(techs=None)`**
: Oil refining for a single region.

- **`compute_supply(demand_ej, oil_price) → dict`** — Returns output, oil input, cost, and emissions.

### `ghim.energy.hydrogen`

**`HydrogenSector(techs=None, logit_exp=-3.0)`**
: Hydrogen production for a single region (SMR + electrolysis).

Methods: `calibrate`, `compute_supply`, `fuel_consumption`, `weighted_cost`, `emissions_mtc`.

### `ghim.energy.demand`

**`FinalDemand(sector, base_demand_ej, fuel_shares=None, logit_exp=-3.0)`**
: Final energy demand for one sector in one region.

Methods:
- **`calibrate(fuel_prices, base_gdp)`** — Calibrate fuel switching weights.
- **`compute_demand(gdp, fuel_prices) → dict[str, float]`** — Compute demand by carrier.

### `ghim.energy.supply`

**`ResourceSupply(fuel, grades, cumulative_extracted=0.0)`**
: Supply curve for a primary energy resource.

- **`marginal_cost() → float`** — Current extraction cost based on depletion.
- **`extract(amount_ej) → float`** — Extract resource, return average cost.

---

## Solver

### `ghim.solver.recursive`

**`PeriodResult`** (dataclass)
: Results for one region in one period. See [Usage Guide](usage.md) for field descriptions.

**`RegionModel`** (dataclass)
: All model components for a single region (KLEM, electricity, refining, hydrogen, demand sectors, prices).

**`build_region_model(region, base_gdp, base_pop) → RegionModel`**
: Initialize and calibrate a region model.

**`solve_period(region_model, gdp, population, year) → PeriodResult`**
: Solve a single period with price iteration until convergence.

**`run_model(ssp_data, scenario="SSP2") → list[PeriodResult]`**
: Run the full model for all regions and periods.

---

## Data Loading

### `ghim.data.ssp`

**`load_ssp_data(scenario="SSP2") → dict[str, DataFrame]`**
: Load SSP population and GDP, aggregated to R10 regions. Returns `{"population": df, "gdp": df}`.

### `ghim.data.energy_cal`

Default energy balance dictionaries:
- **`DEFAULT_PRIMARY_ENERGY`** — region → fuel → EJ
- **`DEFAULT_ELEC_SHARES`** — region → tech → fraction
- **`DEFAULT_ELEC_TOTAL_EJ`** — region → total electricity (EJ)
- **`DEFAULT_FINAL_DEMAND`** — region → sector → EJ

---

## Output

### `ghim.output.reporting`

**`results_to_dataframe(results) → DataFrame`**
: Convert a list of `PeriodResult` to a pandas DataFrame.

**`export_csv(results, output_dir="ghim_output")`**
: Write results to CSV files.

**`print_summary(results)`**
: Print a formatted summary table to stdout.
