# Calibration Methodology

Calibration ensures that the model reproduces observed base-year (2020) data before projecting forward. This chapter describes how each component is initialized and what assumptions underlie the calibration process.

## Overview

GHIM calibrates five components at the base year:

1. **TFP trajectory** — so that endogenous GDP tracks SSP GDP without energy shocks
2. **Capital stock** — from an assumed capital-output ratio
3. **Logit preference factors** — so that base-year technology shares are reproduced
4. **Energy demand** — from approximate IEA 2020 sectoral totals
5. **CES share parameters** — from observed factor cost shares

The calibration is **deterministic** — there is no statistical estimation, optimization, or fitting to time series. All parameters are either taken directly from the literature or back-calculated from base-year identities.

## TFP Calibration

Total factor productivity $A(t)$ is the key bridge between exogenous SSP scenarios and endogenous GDP. It is pre-computed so that, without energy price shocks, the DICE production function reproduces the SSP GDP path exactly.

### Base-year calibration

At the base year, TFP is the residual from the production function:

$$
A_0 = \frac{Y_0}{K_0^{\alpha} \cdot L_0^{1-\alpha}}
$$

where:
- $Y_0$ is base-year GDP from the SSP database (billion USD PPP),
- $K_0 = 3 \times Y_0$ is the initial capital stock (see below),
- $L_0 = \text{Population}_0 \times 0.65$ is the labor force,
- $\alpha = 0.3$ is the capital share.

### Full trajectory

For all model years, a reference capital path is simulated assuming no energy shocks:

$$
K_{\text{ref}}(t+\Delta t) = (1 - \delta)^{\Delta t} \cdot K_{\text{ref}}(t) + I_{\text{ref}}(t) \cdot \Delta t
$$

$$
I_{\text{ref}}(t) = \min\!\bigl(s \cdot Y_{\text{SSP}}(t),\; r_{\text{cap}} \cdot K_{\text{ref}}(t)\bigr)
$$

Then TFP at each period is:

$$
A(t) = \frac{Y_{\text{SSP}}(t)}{K_{\text{ref}}(t)^{\alpha} \cdot L(t)^{1-\alpha}}
$$

Once computed, $A(t)$ is **fixed** for the entire model run. Endogenous GDP deviates from the SSP path only through the energy cost feedback loop, which alters net output, investment, and thus the actual capital trajectory.

> **Note**: This calibration strategy follows DICE/RICE: TFP absorbs all structural change, technological progress, and institutional improvement that are not explicitly modeled. The SSP scenario determines the "potential" GDP; energy costs determine the "realized" GDP.

**Implementation**: [`ghim/econ/klem.py`](../ghim/econ/klem.py) — `KLEMDriver.__init__` (base year), `KLEMDriver.init_tfp_trajectory` (full path).

## Capital Stock Initialization

The base-year capital stock is initialized using an assumed capital-output ratio:

$$
K_0 = 3 \times Y_0
$$

A $K/Y$ ratio of 3.0 is consistent with Penn World Table estimates for the global economy and is the standard DICE assumption. This means a region with \$10 trillion GDP starts with \$30 trillion in capital stock.

Capital evolves endogenously from the base year forward via the perpetual inventory equation:

$$
K(t+\Delta t) = (1 - \delta)^{\Delta t} \cdot K(t) + I(t) \cdot \Delta t
$$

with $\delta = 0.05$ (5% annual depreciation) and $\Delta t = 5$ years.

**Implementation**: [`ghim/econ/klem.py`](../ghim/econ/klem.py) — `KLEMDriver.__init__`, line `self.capital_stock = base_gdp * 3.0`.

## Logit Share Calibration

Technology shares in the base year must match observed data. The model supports two calibration approaches, corresponding to the two logit variants.

### Relative cost logit calibration

Given observed shares $\bar{s}_i$ and costs $\bar{c}_i$ at the base year, share weights are back-calculated:

$$
\alpha_i = \frac{\bar{s}_i}{\bar{c}_i^{\,\beta}}
$$

Weights are normalized so the largest equals 1.0 (GCAM convention). Verification: substituting $\alpha_i$ and $\bar{c}_i$ into the logit formula reproduces $\bar{s}_i$ exactly.

### Preference factor logit calibration (Phase 2 primary)

The preference factor approach designates a **reference technology** $r$ (the one with the largest observed share) and sets $P_r = 0$. All other preference factors are:

$$
P_i = (C_r - C_i) - \frac{\ln(\bar{s}_i / \bar{s}_r)}{k}
$$

where:
- $C_i$ is the base-year LCOE of technology $i$ ($/GJ),
- $\bar{s}_i$ is the observed base-year market share,
- $k = 0.3$ is the preference logit scale parameter.

**Interpretation**: The preference factor captures non-cost barriers. A technology with high share despite high cost (e.g., coal in Eastern Asia) gets a **negative** $P_i$ (a bonus), reflecting established infrastructure and supply chains. A technology with low share despite low cost (e.g., solar in 2020) gets a **positive** $P_i$ (a penalty), reflecting grid integration challenges, permitting delays, and consumer inertia.

### Preference decay

Preference factors decay toward zero over time:

$$
P_i(t) = P_i^{\text{base}} \cdot (1 - d)^{(t - t_0)}
$$

with $d = 0.02$ per year. This gives a half-life of $\ln(2)/0.02 \approx 35$ years. By 2055, half of the base-year non-cost barriers have eroded; by 2100, only ~20% remain. As preferences decay, the model converges toward pure-cost competition.

**Implementation**: [`ghim/energy/logit.py`](../ghim/energy/logit.py) — `preference_calibrate`, `preference_decay`, `logit_calibrate`.

## Energy Demand Calibration

Base-year energy demand is specified exogenously for each region and sector. The values in `DEFAULT_FINAL_DEMAND` approximate IEA 2020 data:

| Sector | Global total (EJ) | Source |
|--------|-------------------|--------|
| Industry | 136 | IEA World Energy Balances (approximate) |
| Buildings | 102 | IEA World Energy Balances (approximate) |
| Transport | 102 | IEA World Energy Balances (approximate) |
| **Total** | **340** | |

Within each sector, fuel shares are specified per subsector in the nested demand tree (e.g., transport passenger: 87% refined liquids, 5% electricity, 4% gas, 2% hydrogen, 2% biomass). These shares determine the initial state of the stock turnover mechanism.

Total demand in future periods scales with GDP via income elasticity:

$$
E_{\text{sector}}(t) = E_{\text{sector,base}} \cdot \left(\frac{Y(t)}{Y_{\text{base}}}\right)^{\epsilon}
$$

where $\epsilon$ is the income elasticity of energy demand:

| Sector | $\epsilon$ | Interpretation |
|--------|-----------|----------------|
| Industry | 0.6 | Less than proportional — structural change reduces energy intensity |
| Buildings | 0.5 | Efficiency improvements partially offset income growth |
| Transport | 0.7 | Relatively income-elastic — mobility demand rises with income |

**Implementation**: [`ghim/energy/demand.py`](../ghim/energy/demand.py) — `FinalDemand`, `INCOME_ELASTICITY`; [`ghim/data/energy_cal.py`](../ghim/data/energy_cal.py) — `DEFAULT_FINAL_DEMAND`.

## CES Share Parameter Calibration

The CES production function share parameters $\alpha_i$ are calibrated from observed base-year cost shares (see [Mathematical Framework](mathematical_framework.md)). The key assumptions are:

| Factor | Cost share of GDP | Source |
|--------|-------------------|--------|
| Value Added (K + L) | 80% | Standard macroeconomic assumption |
| Energy | 8% | IEA World Energy Outlook |
| Materials | 12% | Residual |

Given observed cost shares $s_i$ and prices $\bar{p}_i$, the CES share parameters are:

$$
\alpha_i = \frac{s_i \cdot \bar{p}_i^{\,\sigma-1}}{\sum_j s_j \cdot \bar{p}_j^{\,\sigma-1}}
$$

This is a roundtrip calibration: the parameters are chosen so that, at base-year prices, the CES demand functions reproduce the observed factor quantities.

**Implementation**: [`ghim/econ/ces.py`](../ghim/econ/ces.py) — `ces_calibrate`.

## What Is NOT Calibrated

For transparency, GHIM does not:

- **Statistically estimate parameters**: No econometric fitting, maximum likelihood, or Bayesian inference. All parameters are from published literature.
- **Calibrate to historical time series**: The model is calibrated to a single base year (2020), not to a time series of historical energy data.
- **Use actual IEA data**: Base-year energy values are approximate. Actual IEA data is proprietary; GHIM uses representative defaults.
- **Region-differentiate technology costs**: All regions share the same technology parameters. Regional differences emerge through energy mix calibration and demand structure, not through differentiated costs.
- **Calibrate learning curves to historical deployment**: Base cumulative capacities are set to approximate 2020 values; learning rates are from the literature, not fitted to observed cost trajectories.
