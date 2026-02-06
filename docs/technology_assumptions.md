# Technology Assumptions

This chapter documents all technology parameters used in the GHIM energy model. Parameter values are drawn from NREL ATB 2023, IEA WEO 2023, GCAM defaults, and IPCC emission factor databases.

## Electricity Generation Technologies

GHIM models 8 electricity generation technologies competing via preference-factor logit with learning-by-doing cost reductions.

| Parameter | Coal | Gas CC | Nuclear | Hydro | Wind | Solar | Biomass | Oil |
|-----------|------|--------|---------|-------|------|-------|---------|-----|
| Capital cost ($/kW) | 1500 | 900 | 5500 | 2500 | 1200 | 900 | 2500 | 800 |
| Fixed O&M ($/kW/yr) | 40 | 12 | 100 | 30 | 25 | 12 | 50 | 15 |
| Variable O&M ($/GJ) | 0.5 | 0.3 | 0.5 | 0.1 | 0.0 | 0.0 | 0.5 | 0.8 |
| Efficiency | 0.39 | 0.55 | 0.33 | 1.0 | 1.0 | 1.0 | 0.35 | 0.37 |
| Capacity factor | 0.75 | 0.60 | 0.90 | 0.45 | 0.35 | 0.22 | 0.70 | 0.30 |
| Lifetime (years) | 40 | 30 | 60 | 80 | 25 | 30 | 30 | 30 |
| Carbon coef. (tC/GJ) | 0.0257 | 0.0153 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0200 |
| Learning rate | 0% | 0% | 3% | 0% | 12% | 20% | 5% | 0% |
| Base cum. capacity (GW) | 2100 | 1800 | 440 | 1300 | 740 | 710 | 150 | 500 |

- **Efficiency**: Thermal technologies use heat rate convention (output/input < 1). Renewables and hydro use 1.0 by convention (primary energy = electricity output).
- **Capacity factor**: Annual average availability. Reflects both technical availability and curtailment.
- **Carbon coefficient**: Emissions from fuel combustion at the point of generation. Biomass is treated as carbon-neutral (biogenic carbon cycle).

## Hydrogen Production Technologies

Two hydrogen production pathways compete:

| Parameter | SMR (Steam Methane Reforming) | Electrolysis |
|-----------|-------------------------------|--------------|
| Capital cost ($/kW) | 600 | 1000 |
| Fixed O&M ($/kW/yr) | 20 | 25 |
| Variable O&M ($/GJ) | 0.3 | 0.1 |
| Efficiency | 0.72 | 0.70 |
| Capacity factor | 0.90 | 0.50 |
| Lifetime (years) | 25 | 20 |
| Carbon coef. (tC/GJ) | 0.0153 | 0.0 |
| Learning rate | 0% | 15% |
| Base cum. capacity (GW) | 100 | 1 |
| Fuel input | Gas | Electricity |

Electrolysis has a very small base cumulative capacity (1 GW), which allows rapid learning — each doubling takes less absolute deployment. The 15% learning rate means electrolysis capital costs decline faster than any other technology when deployment scales up.

## Oil Refining

| Parameter | Oil Refining |
|-----------|--------------|
| Capital cost ($/kW) | 500 |
| Fixed O&M ($/kW/yr) | 15 |
| Variable O&M ($/GJ) | 0.2 |
| Efficiency | 0.90 |
| Capacity factor | 0.85 |
| Lifetime (years) | 40 |
| Carbon coef. (tC/GJ) | 0.0200 |
| Learning rate | 0% |
| Fuel input | Crude oil |

Refining converts crude oil to refined liquids at 90% efficiency. It is treated as a mature technology with no learning.

## Fuel Prices

Base-year (2020) fuel prices in $/GJ:

| Fuel | Price ($/GJ) | Notes |
|------|-------------|-------|
| Coal | 2.5 | Thermal coal, delivered |
| Gas | 4.0 | Natural gas, weighted global average |
| Oil (crude) | 8.0 | Crude oil input to refining |
| Refined liquids | 12.0 | Gasoline/diesel, wholesale |
| Nuclear | 0.7 | Uranium fuel cycle cost |
| Biomass | 3.0 | Woody biomass, pellets |
| Hydro | 0.0 | No fuel cost |
| Wind | 0.0 | No fuel cost |
| Solar | 0.0 | No fuel cost |
| Electricity | 20.0 | Endogenous (from electricity sector) |
| Hydrogen | 15.0 | Endogenous (from hydrogen sector) |

Electricity and hydrogen prices are endogenously determined by the model and updated each period via the price iteration loop. The base-year values serve as initial conditions.

## Levelized Cost of Energy (LCOE)

Technology competition is based on the levelized cost, computed as:

$$
\text{LCOE} = \frac{C_{\text{cap}} \cdot \text{CRF}}{\text{CF} \cdot 8760 \cdot 3.6 \times 10^{-3}} + \frac{C_{\text{om,f}}}{\text{CF} \cdot 8760 \cdot 3.6 \times 10^{-3}} + \frac{p_{\text{fuel}}}{\eta} + C_{\text{om,v}}
$$

where:
- $C_{\text{cap}}$ is capital cost ($/kW),
- $\text{CRF} = \frac{r(1+r)^T}{(1+r)^T - 1}$ is the capital recovery factor at discount rate $r = 5\%$,
- $\text{CF}$ is capacity factor,
- $8760 \cdot 3.6 \times 10^{-3}$ converts kW capacity to GJ/yr output (31.536 GJ/yr per kW at CF=1),
- $p_{\text{fuel}}$ is fuel price ($/GJ),
- $\eta$ is thermal efficiency,
- $C_{\text{om,f}}$ and $C_{\text{om,v}}$ are fixed and variable O&M costs.

The LCOE is expressed in **$/GJ of output**, the consistent unit used throughout the model.

**Implementation**: [`ghim/energy/technology.py`](../ghim/energy/technology.py) — method `Technology.levelized_cost`.

## Learning Curves

Technology costs decline with cumulative deployment following WITCH-style experience curves:

$$
C(t) = \max\!\left(C_0 \cdot \left(\frac{Q_{\text{cum}}(t)}{Q_0}\right)^{-\lambda},\; 0.2 \cdot C_0\right)
$$

where:
- $\lambda = \ln(1 - \text{LR}) / \ln(2)$ is the learning index,
- $\text{LR}$ is the learning rate (fractional cost reduction per capacity doubling),
- $Q_0$ is base-year cumulative capacity,
- The **cost floor** at 20% of initial cost prevents unrealistically low values.

### Learning rates by technology

| Technology | LR | $\lambda$ | Meaning |
|------------|-----|-----------|---------|
| Solar PV | 20% | 0.322 | 20% cost reduction per capacity doubling |
| Electrolysis | 15% | 0.234 | Scaling technology with rapid learning |
| Wind | 12% | 0.184 | Moderate learning, approaching maturity |
| Biomass | 5% | 0.074 | Slow incremental improvement |
| Nuclear | 3% | 0.044 | Very slow learning (complex technology) |
| Coal, Gas, Hydro, Oil, SMR | 0% | 0.0 | Mature technologies, no cost reduction |

**Implementation**: [`ghim/energy/technology.py`](../ghim/energy/technology.py) — method `Technology.update_learning`; rates in [`ghim/config.py`](../ghim/config.py) — `LEARNING_RATES`.

## Stock Turnover Times

Energy capital cannot be replaced instantaneously. Stock turnover times determine how quickly actual technology shares converge toward logit-determined target shares:

| Sector | $\tau$ (years) | Rationale |
|--------|----------------|-----------|
| Electricity | 40 | Power plant technical lifetime |
| Hydrogen | 25 | H2 production facility |
| Industry | 30 | Boilers, furnaces, industrial equipment |
| Buildings | 50 | Heating/cooling systems, long-lived |
| Transport | 15 | Vehicle fleet replacement cycle |
| Refining | 40 | Refinery infrastructure |
| Data centers | 7 | Server hardware refresh cycle |

The stock adjustment formula is:

$$
S_i^{\text{new}} = S_i^{\text{old}} + \left(S_i^{\text{target}} - S_i^{\text{old}}\right) \cdot \min\!\left(\frac{\Delta t}{\tau},\; 1\right)
$$

With $\Delta t = 5$ years and $\tau = 40$ years (electricity), only 12.5% of the gap between current and target shares is closed per period. Data centers ($\tau = 7$ years) adjust 71% per period — nearly complete turnover in a single timestep.

**Implementation**: [`ghim/config.py`](../ghim/config.py) — `TURNOVER_TIMES`; [`ghim/energy/stock.py`](../ghim/energy/stock.py) — `apply_stock_turnover`.

## Carbon Coefficients

Emissions factors for fossil fuel combustion:

| Fuel | tC/GJ | kgCO$_2$/GJ | Source |
|------|-------|-------------|--------|
| Coal | 0.0257 | 94.6 | IPCC default for bituminous coal |
| Gas | 0.0153 | 56.1 | IPCC default for natural gas |
| Refined liquids | 0.0200 | 73.3 | IPCC default for petroleum products (weighted avg) |
| Biomass | 0.0 | 0.0 | Carbon neutral (biogenic) |
| Nuclear, Hydro, Wind, Solar | 0.0 | 0.0 | Zero direct combustion emissions |
| Electricity, Hydrogen | 0.0 | 0.0 | Emissions accounted at production stage |

The conversion from tC to tCO$_2$ uses the molecular weight ratio: $\text{tCO}_2 = \text{tC} \times 44/12 \approx 3.667$.

**Implementation**: [`ghim/config.py`](../ghim/config.py) — `CARBON_COEFS`, `TC_TO_TCO2`.

## Data Sources

| Parameter category | Primary source | Notes |
|-------------------|----------------|-------|
| Electricity capital costs | NREL ATB 2023 | US-centric; adjusted for global average |
| Capacity factors | IEA WEO 2023 | Global average values |
| Learning rates | IPCC AR6 WGIII, WITCH model | Empirical and model literature |
| Carbon coefficients | IPCC 2006 Guidelines | Default emission factors |
| Fuel prices | IEA WEO 2023 | Approximate 2020 global averages |
| Stock turnover times | GCAM, WITCH | Sector-specific capital lifetimes |

> **Note**: All technology parameters are global defaults applied uniformly across regions. Region-specific technology characteristics (e.g., higher solar capacity factors in the Middle East) are not yet implemented. Regional differentiation emerges through the energy mix calibration and demand structure.
