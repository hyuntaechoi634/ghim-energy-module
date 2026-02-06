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

### Preference factor logit (MERGE-style)

An alternative logit formulation inspired by MERGE uses **preference factors** to capture non-cost barriers such as regulatory hurdles, infrastructure availability, and social acceptance:

$$
s_i = \frac{\exp\!\bigl(-k\,(C_i + P_i)\bigr)}{\sum_{j} \exp\!\bigl(-k\,(C_j + P_j)\bigr)}
$$

where:
- $C_i$ is the levelized cost of technology $i$ ($/GJ),
- $P_i$ is the **preference factor** ($/GJ-equivalent penalty or bonus),
- $k = 0.3$ is the **scale parameter** controlling cost sensitivity.

#### Calibration

Given observed base-year shares $\bar{s}_i$ and costs $\bar{C}_i$, designate a reference technology $r$ with $P_r = 0$. The preference factors for all other technologies are:

$$
P_i = (C_r - C_i) - \frac{\ln(\bar{s}_i / \bar{s}_r)}{k}
$$

A positive $P_i$ means technology $i$ faces non-cost barriers relative to the reference; a negative value indicates non-cost advantages.

#### Preference decay

Preference factors decay over time, reflecting the gradual removal of non-cost barriers as technologies mature and infrastructure develops:

$$
P_i(t) = P_i^{\text{base}} \cdot (1 - d)^{(t - t_0)}
$$

where $d = 0.02$ is the annual decay rate, giving a half-life of approximately 35 years. As $t \to \infty$, preferences vanish and the model converges toward a **pure-cost outcome**.

> **Note**: Preference factors capture real-world frictions — permitting delays, grid connection queues, consumer habits, fuel supply chain maturity — that are not reflected in LCOE alone. The decay mechanism ensures these barriers erode over long horizons without requiring exogenous scenario assumptions.

**Implementation**: [`ghim/energy/logit.py`](../ghim/energy/logit.py) — functions `preference_logit`, `preference_calibrate`, `preference_decay`.

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

### Energy demand equation (endogenous GDP)

GDP is **endogenous** in Phase 2, following a DICE-style Cobb-Douglas production function with energy cost feedback.

#### Gross output

$$
Y(t) = A(t) \cdot K(t)^{\alpha} \cdot L(t)^{1-\alpha}
$$

where:
- $A(t)$ is **total factor productivity** (TFP), calibrated from the SSP GDP path (see below),
- $K(t)$ is physical capital stock (billion USD),
- $L(t)$ is labor (population, from SSP demographics),
- $\alpha = 0.3$ is the capital share.

#### TFP calibration

TFP is back-calculated so that, in the absence of energy price shocks, the model reproduces the SSP GDP trajectory:

$$
A(t) = \frac{Y_{\text{SSP}}(t)}{K_{\text{SSP}}(t)^{\alpha} \cdot L(t)^{1-\alpha}}
$$

Once calibrated, $A(t)$ is **fixed** for the scenario run. Deviations from the SSP path arise endogenously through the energy cost feedback described below.

#### Energy demand

$$
E(t) = E_{\text{base}} \cdot \frac{Y(t)}{Y_{\text{base}}} \cdot \left(\frac{P_E(t)}{P_{E,\text{base}}}\right)^{-\sigma_{EM}}
$$

where:
- $E_{\text{base}}$ is base-year energy demand (EJ),
- $Y(t)$ is **gross output** (not exogenous SSP GDP),
- $P_E(t)/P_{E,\text{base}}$ is the energy price index relative to the base year,
- $\sigma_{EM} = 0.5$ is the energy-macro price elasticity.

#### Energy cost and net output

Total energy cost is:

$$
\text{Cost} = E \;(\text{EJ}) \times P_E \;(\$/\text{GJ})
$$

expressed in billion USD (the $10^9$ factors in EJ and $/GJ cancel). Net output available for consumption and investment is:

$$
Y_{\text{net}} = \max\!\bigl(Y - \text{Cost},\; 0.01 \cdot Y\bigr)
$$

The floor at 1% of gross output prevents negative net output in extreme price scenarios.

#### Investment

$$
I(t) = \min\!\bigl(s \cdot Y_{\text{net}},\; r_{\text{cap}} \cdot K(t)\bigr)
$$

where $s = 0.22$ is the savings rate and $r_{\text{cap}} = 0.10$ is a capital growth cap that prevents unrealistically fast accumulation.

#### Feedback mechanism

The energy cost feedback loop is the central macro mechanism in Phase 2:

$$
\text{Expensive energy} \;\to\; \text{lower } Y_{\text{net}} \;\to\; \text{less investment } I \;\to\; \text{lower } K \;\to\; \text{lower future } Y
$$

Conversely, cheap energy (e.g., from learning-driven cost reductions in renewables) raises net output and accelerates capital accumulation. Without energy price shocks, the model tracks the SSP GDP path by construction.

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

**Implementation**: [`ghim/econ/klem.py`](../ghim/econ/klem.py) — class `KLEMDriver`.

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

---

## Stock Turnover

Energy capital stock (power plants, vehicles, industrial equipment) cannot be replaced instantaneously. The **stock turnover** mechanism governs how quickly actual technology shares converge toward the target shares determined by the logit/preference factor model.

The actual share of technology $i$ evolves as:

$$
S_i^{\text{new}} = S_i^{\text{old}} + \bigl(S_i^{\text{target}} - S_i^{\text{old}}\bigr) \cdot \min\!\left(\frac{\Delta t}{\tau}, \; 1\right)
$$

where:
- $S_i^{\text{target}}$ is the share from the logit competition (what the market "wants"),
- $S_i^{\text{old}}$ is the share at the beginning of the period,
- $\Delta t$ is the model timestep (5 years),
- $\tau$ is the **turnover time** (sector-specific capital lifetime).

The $\min(\cdot, 1)$ clamp ensures that shares never overshoot the target. When $\Delta t \ll \tau$, stock adjustment is slow (only a fraction $\Delta t / \tau$ of the gap is closed per period). When $\Delta t \geq \tau$, the stock fully adjusts within one period.

### Turnover times by sector

| Sector | $\tau$ (years) | Interpretation |
|--------|----------------|----------------|
| Electricity | 40 | Power plant lifetime |
| Hydrogen | 25 | H2 production facility |
| Transport | 15 | Vehicle fleet replacement |
| Industry | 30 | Industrial equipment |
| Buildings | 50 | Heating system lifetime |
| Refining | 40 | Refinery lifetime |
| Data centers | 7 | Server hardware lifecycle |

**Implementation**: [`ghim/energy/stock.py`](../ghim/energy/stock.py) — function `apply_stock_turnover`.

---

## Learning-by-Doing

Technology costs decline with cumulative deployment following **one-factor experience curves** (WITCH-style). This creates a positive feedback loop: deployment reduces costs, which increases competitiveness, which drives further deployment.

### Experience curve

$$
C(t) = C_0 \cdot \left(\frac{Q_{\text{cum}}(t)}{Q_0}\right)^{-\lambda}
$$

where:
- $C_0$ is the initial unit cost,
- $Q_{\text{cum}}(t)$ is cumulative installed capacity (or cumulative production) at time $t$,
- $Q_0$ is the base-year cumulative capacity,
- $\lambda = \frac{\ln(1 - LR)}{\ln 2}$ is the **learning index**, derived from the learning rate $LR$.

The learning rate $LR$ represents the fractional cost reduction for each doubling of cumulative capacity. For example, $LR = 0.20$ means costs fall by 20% each time cumulative capacity doubles.

### Cost floor

To prevent unrealistically low costs, a floor is imposed:

$$
C(t) \geq 0.2 \cdot C_0
$$

Costs cannot fall below 20% of their initial value, reflecting irreducible material and labor costs.

### Learning rates by technology

| Technology | Learning Rate | Meaning |
|------------|---------------|---------|
| Solar PV | 20% | 20% cost reduction per capacity doubling |
| Wind | 12% | |
| Electrolysis | 15% | |
| Biomass | 5% | |
| Nuclear | 3% | |
| Coal | 0% | Mature technology |
| Gas | 0% | Mature technology |
| Hydro | 0% | Mature technology |
| Oil | 0% | Mature technology |
| SMR | 0% | Mature technology |

Technologies with $LR = 0\%$ are considered mature — their costs are fixed and do not benefit from further deployment.

**Implementation**: [`ghim/energy/technology.py`](../ghim/energy/technology.py) — method `Technology.update_learning`.
