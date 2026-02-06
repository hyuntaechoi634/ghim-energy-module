# Mathematical Framework

This chapter describes the three core mathematical building blocks of the GHIM model: the CES production function, the logit discrete choice model, and their integration in the KLEM macro driver.

## CES Production Function

The **Constant Elasticity of Substitution (CES)** function is the workhorse of production theory in computable general equilibrium models. It generalizes several well-known functional forms under a single parameterization.

### Primal form (output aggregation)

Given $n$ input factors $X_1, \ldots, X_n$ with share parameters $\alpha_1, \ldots, \alpha_n$ ($\sum \alpha_i = 1$), the CES aggregate output is:

$$
Y = A \left[ \sum_{i=1}^{n} \alpha_i \, X_i^{\rho} \right]^{1/\rho}
$$

where:
- $A$ is total factor productivity (scale parameter),
- $\rho = \frac{\sigma - 1}{\sigma}$ is the substitution parameter,
- $\sigma > 0$ is the **elasticity of substitution** between inputs.

### Special cases

The CES function nests several important functional forms:

::::{grid} 1 1 2 3
:gutter: 3

:::{grid-item-card} Cobb-Douglas ($\sigma = 1$)
$$Y = A \prod_{i} X_i^{\alpha_i}$$
Inputs are imperfect substitutes with unit elasticity. Used when factor shares are roughly constant over time.
:::

:::{grid-item-card} Leontief ($\sigma \to 0$)
$$Y = A \min_i \left(\frac{X_i}{\alpha_i}\right)$$
Inputs are perfect complements — no substitution possible. Used for fixed-proportion technologies.
:::

:::{grid-item-card} Linear ($\sigma \to \infty$)
$$Y = A \sum_i \alpha_i X_i$$
Inputs are perfect substitutes. Rarely used in practice as it implies corner solutions.
:::
::::

### Dual form (composite price)

The cost-minimizing composite price index dual to the CES production function is:

$$
P = \left[ \sum_{i=1}^{n} \alpha_i^{\sigma} \, p_i^{1-\sigma} \right]^{1/(1-\sigma)}
$$

where $p_i$ is the price of input $i$. For the Cobb-Douglas case ($\sigma = 1$):

$$
P = \prod_{i} \left(\frac{p_i}{\alpha_i}\right)^{\alpha_i}
$$

### Input demand functions

From Shephard's lemma, the cost-minimizing demand for input $i$ given output level $Y$ is:

$$
X_i = \alpha_i^{\sigma} \left(\frac{P}{p_i}\right)^{\sigma} Y
$$

This says that demand for each input depends on:
- The share parameter $\alpha_i$ (structural weight of the input),
- The ratio of aggregate price to own price $(P/p_i)^\sigma$ (substitution effect),
- The output level $Y$ (scale effect).

### Calibration

Given base-year observed input quantities $\bar{X}_i$ and prices $\bar{p}_i$, and an assumed elasticity $\sigma$, the share parameters are recovered as:

$$
\alpha_i = \frac{s_i \cdot \bar{p}_i^{\,\sigma-1}}{\sum_j s_j \cdot \bar{p}_j^{\,\sigma-1}}
$$

where $s_i = \bar{p}_i \bar{X}_i / \sum_j \bar{p}_j \bar{X}_j$ are the observed cost shares.

**Implementation**: [`ghim/econ/ces.py`](../ghim/econ/ces.py) — functions `ces_output`, `ces_price`, `ces_demand`, `ces_calibrate`.

---

## Logit Discrete Choice

The **logit model** determines market shares among competing technologies based on their relative costs. GHIM implements two variants following the GCAM approach.

### Relative cost logit (primary)

The market share of technology $i$ is:

$$
s_i = \frac{\alpha_i \, c_i^{\beta}}{\sum_{j} \alpha_j \, c_j^{\beta}}
$$

where:
- $c_i$ is the levelized cost of technology $i$,
- $\alpha_i$ is the calibrated **share weight** (captures non-cost preferences, policy effects, inertia),
- $\beta < 0$ is the **logit exponent** (more negative = stronger cost sensitivity).

The logit exponent $\beta$ controls how aggressively the market concentrates on the cheapest technology:

| $\beta$ | Behavior |
|---------|----------|
| $-1$ | Mild cost sensitivity — diverse technology mix |
| $-3$ | Moderate — cheapest technology dominates but alternatives persist |
| $-6$ | Strong — near winner-take-all (used for refining) |
| $-\infty$ | Perfect competition — cheapest technology takes 100% |

### Absolute cost logit (alternative)

An alternative formulation uses exponential rather than power-law sensitivity:

$$
s_i = \frac{\alpha_i \, \exp(\beta \, c_i / c_0)}{\sum_{j} \alpha_j \, \exp(\beta \, c_j / c_0)}
$$

where $c_0$ is a normalization scale. This form is more sensitive to absolute cost differences rather than relative ratios.

### Numerical implementation

All logit computations use **log-space arithmetic** for numerical stability:

$$
\log s_i = \log \alpha_i + \beta \log c_i - \log \sum_j \exp\!\left(\log \alpha_j + \beta \log c_j\right)
$$

The log-sum-exp trick (subtracting the maximum before exponentiating) prevents overflow:

```python
log_unnorm = np.log(share_weights) + logit_exp * np.log(costs)
log_unnorm -= log_unnorm.max()  # numerical stability
unnorm = np.exp(log_unnorm)
shares = unnorm / unnorm.sum()
```

### Share weight calibration

To reproduce observed base-year market shares $\bar{s}_i$ at observed costs $\bar{c}_i$, the share weights are:

$$
\alpha_i = \frac{\bar{s}_i}{\bar{c}_i^{\,\beta}}
$$

Weights are normalized so the largest equals 1.0 (GCAM convention), which ensures stable numerical behavior and provides a natural reference point.

### Composite sector cost

The **share-weighted average cost** (also called the logit price) is:

$$
\bar{c} = \sum_i s_i \, c_i
$$

This serves as the sector-level price seen by upstream consumers.

**Implementation**: [`ghim/energy/logit.py`](../ghim/energy/logit.py) — functions `relative_cost_logit`, `absolute_cost_logit`, `logit_calibrate`, `logit_average_cost`.

---

## KLEM Macro Driver

The **KLEM** (Capital-Labor-Energy-Materials) framework determines aggregate energy demand from macroeconomic conditions. It uses the CES production function at each nesting level.

### Nesting structure

```
Output (Y = GDP)
├── Value Added (VA)          [CES, σ_VA = 0.5]
│   ├── Capital (K)
│   └── Labor (L)
└── Energy-Materials (EM)     [CES, σ_EM = 0.5]
    ├── Energy (E)            → drives energy sector model
    └── Materials (M)
```

Within the Energy aggregate, a further nesting separates electric and non-electric energy:

```
Energy (E)                    [CES, σ_E = 1.0]
├── Electric energy
└── Non-electric energy       [CES, σ_NE = 2.0]
    ├── Coal
    ├── Refined liquids
    ├── Gas
    └── Biomass
```

### Elasticity of substitution values

| Nesting level | Symbol | Value | Interpretation |
|--------------|--------|-------|---------------|
| Value Added (K, L) | $\sigma_{VA}$ | 0.5 | Low substitutability — capital and labor are complements |
| Energy-Materials | $\sigma_{EM}$ | 0.5 | Low — energy demand responds weakly to price |
| Electric vs. non-electric | $\sigma_E$ | 1.0 | Cobb-Douglas — unit elasticity between carriers |
| Among non-electric fuels | $\sigma_{NE}$ | 2.0 | High — fuels are fairly substitutable |

These values are consistent with the empirical literature (Koesler & Schymura, 2015; Van der Werf, 2008) and similar to the WITCH model parameterization.

### Energy demand equation

In the recursive-dynamic mode, GDP is exogenous (from SSP scenarios). Energy demand is computed as:

$$
E(t) = E_0 \cdot \frac{GDP(t)}{GDP_0} \cdot \left(\frac{P_E(t)}{P_{E,0}}\right)^{-\sigma_{EM}}
$$

where:
- $E_0$ is base-year energy demand (EJ),
- $GDP_0$ is base-year GDP,
- $P_E(t)/P_{E,0}$ is the energy price index relative to the base year,
- $\sigma_{EM} = 0.5$ is the price elasticity.

This formulation captures two key drivers:
1. **Income effect**: Energy demand grows with GDP (elasticity = 1 in the simplified form).
2. **Price effect**: Higher energy prices reduce demand, with elasticity $-\sigma_{EM}$.

### Capital accumulation

Capital stock evolves according to the perpetual inventory method:

$$
K(t+\Delta t) = (1 - \delta)^{\Delta t} \cdot K(t) + I(t) \cdot \Delta t
$$

where:
- $\delta = 0.05$ is the annual depreciation rate,
- $\Delta t = 5$ years is the model timestep,
- $I(t)$ is gross investment.

### Base-year calibration

The KLEM driver is calibrated to base-year (2020) data using assumed cost shares:

| Factor | Cost share of GDP | Source |
|--------|-------------------|--------|
| Value Added (K + L) | 80% | Standard macroeconomic assumption |
| Energy | 8% | IEA World Energy Outlook |
| Materials | 12% | Residual |

The capital-output ratio $K/Y$ is assumed to be 3.0, consistent with Penn World Table estimates for the global economy.

**Implementation**: [`ghim/econ/klem.py`](../ghim/econ/klem.py) — class `KLEMDriver` with methods `compute_energy_demand`, `update_capital`.

---

## Levelized Cost of Energy (LCOE)

Technology competition in the energy sectors is based on the levelized cost of energy. For a technology with capital cost $C_{cap}$ ($/kW), fixed O&M $C_{om,f}$ ($/kW/yr), variable O&M $C_{om,v}$ ($/GJ), fuel price $p_{fuel}$ ($/GJ), efficiency $\eta$, capacity factor $CF$, lifetime $T$, and discount rate $r$:

$$
LCOE = \frac{C_{cap} \cdot CRF}{CF \cdot 8760 \cdot 3.6 \times 10^{-3}} + \frac{C_{om,f}}{CF \cdot 8760 \cdot 3.6 \times 10^{-3}} + \frac{p_{fuel}}{\eta} + C_{om,v}
$$

where:
- $CRF = \frac{r(1+r)^T}{(1+r)^T - 1}$ is the capital recovery factor,
- $CF \cdot 8760 \cdot 3.6 \times 10^{-3}$ converts from kW capacity to GJ/yr output.

The LCOE is expressed in **$/GJ of output**, which is the consistent unit used throughout the model for price-based technology competition.

**Implementation**: [`ghim/energy/technology.py`](../ghim/energy/technology.py) — method `Technology.levelized_cost`.
