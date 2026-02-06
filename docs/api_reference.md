# API Reference

This page provides a summary of all public modules, classes, and functions in the GHIM package.

## Configuration

### `ghim.config`

| Constant | Value | Description |
|----------|-------|-------------|
| `BASE_YEAR` | 2020 | Model base year |
| `END_YEAR` | 2150 | Final model year |
| `TIMESTEP` | 5 | Years per period |
| `MODEL_YEARS` | [2000, 2005, ..., 2150] | All 31 model periods |
| `HISTORY_START` | 2000 | First year of historical data |
| `DISCOUNT_RATE` | 0.05 | Annual discount rate |
| `DEPRECIATION_RATE` | 0.05 | Annual capital depreciation |
| `CAPITAL_SHARE` | 0.3 | α in Cobb-Douglas production function |
| `SAVINGS_RATE` | 0.22 | Fraction of net output saved as investment |
| `INVESTMENT_CAP_RATE` | 0.10 | Max annual investment as fraction of K |
| `LABOR_FORCE_PARTICIPATION` | 0.65 | Fraction of population as labor |
| `SIGMA_VA` | 0.5 | CES elasticity: Capital vs Labor |
| `SIGMA_EM` | 0.5 | CES elasticity: Energy-Materials |
| `SIGMA_E` | 1.0 | CES elasticity: Electric vs Non-electric |
| `SIGMA_NE` | 2.0 | CES elasticity: Among non-electric fuels |
| `ELEC_LOGIT_EXP` | -4.0 | Logit exponent for electricity sector |
| `DEMAND_LOGIT_EXP` | -3.0 | Logit exponent for fuel switching |
| `PREF_LOGIT_SCALE` | 0.3 | k in preference factor logit exp(-k*(C+P)) |
| `PREF_DECAY_RATE` | 0.02 | Annual preference factor decay rate |
| `PRICE_TOL` | 0.001 | Relative price convergence tolerance |
| `PRICE_DAMP` | 0.5 | Damping factor for price updates |
| `TURNOVER_TIMES` | dict | Sector-specific stock turnover times (years) |
| `LEARNING_RATES` | dict | Technology learning rates (0-1) |
| `COST_FLOOR_FRACTION` | 0.2 | Minimum cost as fraction of initial |

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

**`KLEMDriver(base_gdp, base_population, base_energy_demand_ej, capital_share=0.3, savings_rate=0.22, sigma_em=0.5)`**
: DICE-style macro driver. Calibrates TFP, manages capital stock, computes endogenous GDP.

Methods:
- **`init_tfp_trajectory(ssp_gdp_by_year, pop_by_year)`** — Pre-compute TFP trajectory from SSP GDP path.
- **`set_tfp_for_year(year)`** — Set current TFP from trajectory.
- **`compute_gross_output(population) → float`** — $Y = A K^\alpha L^{1-\alpha}$.
- **`compute_energy_demand(gross_output, energy_price_index) → float`** — $E = E_{base} \cdot (Y / Y_{base}) \cdot (P / P_{base})^{-\sigma}$.
- **`compute_energy_cost(energy_ej, avg_price_per_gj) → float`** — Static. Cost in billion USD.
- **`compute_net_output(gross_output, energy_cost) → float`** — Static. Net = gross - cost (floor 1%).
- **`compute_investment(net_output) → float`** — $I = \min(s \cdot \text{net}, \text{cap} \cdot K)$.
- **`update_capital(investment)`** — $K(t+dt) = (1-\delta)^{dt} K + I \cdot dt$.

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

**`preference_logit(costs, pref_factors, scale_k) → ndarray`**
: Compute shares via preference logit $s_i = \exp(-k (C_i + P_i)) / \sum \exp(-k (C_j + P_j))$.

**`preference_calibrate(base_shares, base_costs, scale_k) → ndarray`**
: Inverse logit to recover preference factors from observed base-year shares and costs.

**`preference_decay(pref_factors, years_elapsed, decay_rate) → ndarray`**
: Apply preference decay $P(t) = P_{base} \cdot (1-d)^{\text{years}}$.

### `ghim.energy.stock`

**`apply_stock_turnover(current_shares, target_shares, dt, turnover_time) → ndarray`**
: Gradual share transition: $\text{new} = \text{old} + (\text{target} - \text{old}) \cdot \min(dt / \tau, 1)$. Returns renormalized shares.

### `ghim.energy.technology`

**`Technology`** (dataclass)
: Represents a single energy conversion technology.

Fields: `name`, `sector`, `fuel_input`, `efficiency`, `capital_cost`, `om_fixed`, `om_variable`, `capacity_factor`, `lifetime`, `share_weight`, `carbon_coef`, `base_capital_cost`, `base_cumulative`, `cumulative_capacity`, `learning_rate`, `cost_floor`.

Methods:
- **`levelized_cost(fuel_price, discount_rate=0.05) → float`** — Compute LCOE in $/GJ.
- **`annual_emissions_tc(output_ej) → float`** — Compute annual emissions in MtC.
- **`update_learning(new_capacity)`** — Update cumulative deployment, reduce capital cost via experience curve.

Factory functions:
- **`default_electricity_techs() → list[Technology]`** — 8 generation technologies.
- **`default_refining_techs() → list[Technology]`** — Oil refining.
- **`default_hydrogen_techs() → list[Technology]`** — SMR + electrolysis.

### `ghim.energy.electricity`

**`ElectricitySector(techs=None, logit_exp=-4.0, scale_k=0.3, turnover_time=40.0)`**
: Electricity generation sector for a single region. Includes preference logit, stock turnover, and technology learning.

Methods:
- **`calibrate(base_shares, fuel_prices)`** — Calibrate share weights from observed generation shares.
- **`compute_supply(fuel_prices, total_demand_ej, years_from_base=0, cost_adjustments=None, share_constraints=None, year=None) → dict[str, float]`** — Compute generation by technology. Optional `cost_adjustments` (tech→$/GJ subsidy) and `share_constraints` (list of `TechConstraint`) for policy support.
- **`weighted_cost(fuel_prices) → float`** — Compute sector-average electricity price.
- **`fuel_consumption(generation_by_tech) → dict[str, float]`** — Compute fuel inputs.
- **`emissions_mtc(generation_by_tech) → float`** — Compute total CO$_2$ emissions.

### `ghim.energy.refining`

**`RefiningSector(techs=None)`**
: Oil refining for a single region.

- **`compute_supply(demand_ej, oil_price) → dict`** — Returns output, oil input, cost, and emissions.

### `ghim.energy.hydrogen`

**`HydrogenSector(techs=None, logit_exp=-3.0, scale_k=0.3, turnover_time=25.0)`**
: Hydrogen production for a single region (SMR + electrolysis). Includes preference logit, stock turnover, and technology learning.

Methods:
- **`calibrate(base_shares, fuel_prices)`** — Calibrate share weights from observed production shares.
- **`compute_supply(fuel_prices, demand_ej, years_from_base=0, cost_adjustments=None, share_constraints=None, year=None) → dict[str, float]`** — Compute production by technology. Optional `cost_adjustments` and `share_constraints` for policy support.
- **`fuel_consumption(production_by_tech) → dict[str, float]`** — Compute fuel inputs.
- **`weighted_cost(fuel_prices) → float`** — Compute sector-average hydrogen price.
- **`emissions_mtc(production_by_tech) → float`** — Compute total CO$_2$ emissions.

### `ghim.energy.demand`

**`DemandLeaf(name, carrier)`**
: Terminal node mapping to an energy carrier.

**`DemandNode(name, children, base_shares, scale_k=0.3, turnover_time=30.0)`**
: Branch node with preference logit + stock turnover for nested demand allocation.

Methods:
- **`calibrate(fuel_prices)`** — Recursive bottom-up calibration.
- **`compute_carrier_demands(total_ej, fuel_prices) → dict[str, float]`** — Recursive top-down allocation.

**`FinalDemand(sector, base_demand_ej, tree=None, income_elasticity=None)`**
: Wrapper with GDP-driven total demand. Uses a `DemandNode` tree for fuel allocation.

Methods:
- **`calibrate(fuel_prices, base_gdp)`** — Calibrate tree and store base GDP.
- **`compute_demand(gdp, fuel_prices) → dict[str, float]`** — Compute fuel demand by carrier.

### `ghim.energy.supply`

**`ResourceSupply(fuel, grades, cumulative_extracted=0.0)`**
: Supply curve for a primary energy resource.

- **`marginal_cost() → float`** — Current extraction cost based on depletion.
- **`extract(amount_ej) → float`** — Extract resource, return average cost.

---

## Solver

### `ghim.solver.recursive`

**`PeriodResult`** (dataclass)
: Results for one region in one period. See [Usage Guide](usage.md) for field descriptions. Includes fields: `gross_output`, `net_output`, `capital_stock`, `investment`, `energy_cost`, `ssp_reference_gdp`, `tfp`, `carbon_price_usd_tco2`, `carbon_revenue_billion_usd`, `aeei_factor`.

**`RegionModel`** (dataclass)
: All model components for a single region (KLEM, electricity, refining, hydrogen, demand sectors, prices).

**`build_region_model(region, base_gdp, base_pop) → RegionModel`**
: Initialize and calibrate a region model.

**`solve_period(region_model, ssp_gdp, population, year, policy=None) → PeriodResult`**
: Solve a single period with price iteration until convergence. Optional `policy` parameter (`PolicyScenario`) injects carbon pricing, subsidies, efficiency standards, and tech constraints into the solve.

**`run_model(ssp_data, scenario="SSP2", policy=None) → list[PeriodResult]`**
: Run the full model for all regions and periods. When `policy` includes an emissions cap, uses bisection on carbon price to find the shadow price that meets the cap.

---

## Policy

### `ghim.policy`

**`PolicyScenario`** (dataclass)
: Root container holding all sub-policies. All fields default to zero/disabled.

Fields:
- `name: str` — scenario name
- `carbon_price: CarbonPricePolicy`
- `renewable_subsidies: RenewableSubsidy`
- `efficiency_standards: EfficiencyStandard`
- `emissions_cap: EmissionsCap`
- `tech_constraints: list[TechConstraint]`
- `revenue_recycling: RevenueRecycling`

**`CarbonPricePolicy(trajectory: dict[int, float])`**
: Carbon price trajectory (year → $/tCO$_2$). Linearly interpolated, flat beyond endpoints.

- **`get_price(year) → float`** — Interpolated price at given year.

**`RenewableSubsidy(subsidies: dict[str, dict[int, float]])`**
: Per-technology subsidies (tech name → year → $/GJ cost reduction).

- **`get_subsidy(tech, year) → float`** — Interpolated subsidy for a technology.

**`EfficiencyStandard(rates: dict[str, dict[int, float]])`**
: AEEI rates (scope → year → annual improvement rate). Scope can be `"global"` or a sector name.

- **`cumulative_factor(sector, year, base_year) → float`** — Returns $(1-r)^{(year - base\_year)}$. Falls back to `"global"` if sector not found.

**`EmissionsCap(caps: dict[str, dict[int, float]])`**
: Emissions cap trajectory (scope → year → MtCO$_2$).

- **`get_cap(scope, year) → float | None`** — Interpolated cap value.
- **`has_cap(year) → bool`** — Whether any cap is active for this year.

**`TechConstraint(sector, technology, constraint_type, trajectory)`**
: Share constraint for a technology. `constraint_type` is `"max"` or `"min"`.

- **`get_bound(year) → float`** — Interpolated bound value.

**`RevenueRecycling(fraction: float)`**
: Fraction of carbon revenue recycled to reduce energy cost (0–1).

**`load_policy(path) → PolicyScenario`**
: Load a `PolicyScenario` from a JSON file. Converts string year keys to int.

**`policy_from_cli(carbon_price=0, efficiency_rate=0, recycling_fraction=0) → PolicyScenario`**
: Build a constant-value `PolicyScenario` from CLI flag values.

**`apply_share_constraints(shares, tech_names, constraints, year, sector) → ndarray`**
: Clamp technology shares to min/max bounds and renormalize. Uses iterative clamp-and-redistribute algorithm.

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
