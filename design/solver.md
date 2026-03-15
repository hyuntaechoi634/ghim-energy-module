# GHIM Energy Module — Solver Design

## 1. Fixed-Point Formulation

The entire model is formulated as a fixed-point problem: find $\mathbf{x}^*$ such that $F(\mathbf{x}^*) = \mathbf{x}^*$.

### 1.1 State Vector

$$\mathbf{x} = [\underbrace{Y_r, \; I_{E,r}, \; p_{elec,r}, \; p_{H_2,r}}_{\text{Regional} \times 32}, \quad \underbrace{p_{coal}^W, \; p_{oil}^W, \; p_{gas}^W, \; p_{bio}^W, \; p_U^W}_{\text{Global} \times 1}]$$

$$4 \times 32 + 5 = \mathbf{133} \text{ dimensions}$$

| Component | Count | Scope | Meaning |
|-----------|-------|-------|---------|
| $Y_r$ | 32 | Regional | GDP (billion USD PPP) |
| $I_{E,r}$ | 32 | Regional | Energy investment (billion USD/yr) |
| $p_{elec,r}$ | 32 | Regional | Electricity price ($/GJ) |
| $p_{H_2,r}$ | 32 | Regional | Hydrogen price ($/GJ) |
| $p_{coal}^W$ | 1 | Global | World coal price ($/GJ) |
| $p_{oil}^W$ | 1 | Global | World oil price ($/GJ) |
| $p_{gas}^W$ | 1 | Global | World gas price ($/GJ) |
| $p_{bio}^W$ | 1 | Global | World biomass price ($/GJ) |
| $p_U^W$ | 1 | Global | World uranium price ($/GJ) |

**Why these 133?** These are the **independent** variables the fixed-point loop solves for. All other prices and quantities are **derived** within F(x):
- Refined liquids price = f($p_{oil}^W$, refining cost) — derived
- Heat price = f($p_{gas}^W$, $p_{coal}^W$, ...) — derived from district heating dispatch
- Carrier prices for demand sectors = primary prices + transport cost + markup — derived
- Composite energy price = expenditure-weighted average of carrier prices — derived

### 1.2 Equilibrium Condition

$\mathbf{x}^* = F(\mathbf{x}^*)$ means:
- Sectoral demand = sectoral supply at consistent prices
- Trade clears globally for each primary commodity
- Electricity and hydrogen markets clear regionally
- Macro output Y is consistent with energy quantity and price
- Energy investment is consistent with budget ($I_K = s \cdot Y - I_E - I_{RD} \geq 0$)


## 2. Model Pass F(x)

Seven steps, each producing outputs that feed the next:

```
┌─────────────────────────────────────────┐
│ 1. Final Energy Demand                  │
│    Industry / Transport / Buildings /   │──→ carrier demands
│    Agriculture / Bunkers                │
├─────────────────────────────────────────┤
│ 2. Technology Share                     │
│    s_i ∝ α_i · exp(β·C_i + p_i)       │──→ tech/powertrain shares
├─────────────────────────────────────────┤
│ 3. Primary Energy Demand               │
│    Aggregate fuel demands from shares   │──→ coal, oil, gas, biomass, uranium
├─────────────────────────────────────────┤
│ 4. Global Market Clearing              │
│    Σ_r Q^s_r(p) = Σ_r Q^d_r           │──→ p^W_coal, p^W_oil, p^W_gas,
│    Bisection per commodity              │    p^W_bio, p^W_U
├─────────────────────────────────────────┤
│ 5. Secondary Market Clearing           │
│    Electricity / Hydrogen /            │──→ p_elec, p_H2, I_E
│    District Heating / Refining         │
├─────────────────────────────────────────┤
│ 6. Macro Economy Update                │
│    Y = Q - p_E·E - p_M·M              │──→ Y
├─────────────────────────────────────────┤
│ 7. Financial Market Clearing           │
│    I_K = s·Y - I_E - I_RD ≥ 0         │──→ I_K
└─────────────────────────────────────────┘
```

### Step 1: Final Energy Demand

Each demand sector computes carrier demands from GDP, prices, and structural drivers:
- **Industry**: GDP-scaled output × fixed energy intensity × carrier logit
- **Buildings**: Floorspace × service intensity × carrier logit (with HDD/CDD from Climate)
- **Transport**: Service demand × LCOT-based powertrain logit
- **Agriculture**: GDP-scaled output × fixed energy intensity × carrier logit
- **Bunkers**: World-GDP-scaled demand × LCOT-based powertrain logit

All sectors apply policy instruments (carbon tax, tech availability, share constraints) at this step.

### Step 2: Technology Share

Preference-factor logit determines shares within each sector/market:

$$s_i = \frac{\alpha_i \cdot \exp(\beta \cdot C_i + p_i)}{\sum_j \alpha_j \cdot \exp(\beta \cdot C_j + p_j)}$$

Closed-form, no iteration needed. Share constraints (RES, min/max) applied after logit.

### Step 3: Primary Energy Demand

Aggregate carrier demands across all sectors and regions → total demand for each primary commodity. Includes transformation sector fuel inputs (gas for electricity, oil for refining, biomass for biofuels, etc.).

### Step 4: Global Market Clearing

Bisection per commodity finds world price where global supply = global demand:

$$\sum_r Q_r^s(p^W + rent_r) = \sum_r Q_r^d$$

Five markets cleared: coal, oil, gas, biomass, uranium. Cross-commodity effects (e.g., gas price affects electricity price affects coal demand) resolved by the **outer** fixed-point loop, not within this step.

### Step 5: Secondary Market Clearing

Transformation sectors compute supply mix and carrier prices:
- **Electricity**: LCOE logit → generation mix → $p_{elec}$ (share-weighted LCOE + T&D markup)
- **Hydrogen**: LCOH logit → production mix → $p_{H_2}$ (share-weighted LCOH)
- **District Heating**: LCOH logit → heat mix → $p_{heat}$ (share-weighted + distribution)
- **Refining**: Oil → refined liquids at processing cost → $p_{liquids}$

Energy investment $I_E$ computed: $\sum_{sectors} \sum_i new\_capacity_i \times capex_i$.

### Step 6: Macro Economy Update

CES production function computes gross output from value added and energy:

$$Y = Q - p_E \cdot E - p_M \cdot M$$

where $Q = A_{CES} \cdot CES(KLE, M)$ and $KLE = CES(KL, E_{val})$.

Composite energy price $p_E$ updated from carrier prices weighted by expenditure shares.

### Step 7: Financial Market Clearing

Budget constraint ensures investment is feasible:

$$I_K = s \cdot Y - I_E - \sum_j I_{RD,j} \geq 0$$

If $I_K < 0$, energy investment crowds out physical capital → GDP growth slows. This is the mechanism by which expensive energy transitions have macro cost.


## 3. Solution Methods

### Phase 1: Damped Iteration

$$\mathbf{x}_{n+1} = (1 - \alpha) \cdot \mathbf{x}_n + \alpha \cdot F(\mathbf{x}_n)$$

$\alpha$ small enough (typically 0.3–0.5) guarantees convergence (Banach contraction).

```python
x = x_init  # warm-start from previous period
for n in range(max_iter):
    x_new = F(x)
    residual = norm(x_new - x) / norm(x)
    x = (1 - alpha) * x + alpha * x_new
    if residual < tol:
        break
```

- **Warm-start**: Previous period's solution as initial guess (recursive-dynamic)
- **Typical convergence**: 3–10 iterations per period
- **Bisection inside F**: Trade clearing runs inside each F evaluation (~20 inner iterations)

### Phase 2: Anderson Acceleration

Same F, smarter mixing of past iterates. 2–3× fewer iterations.

```python
scipy.optimize.anderson(F - id, x_0, M=5)
```

- **M = 3–5**: Memory depth (number of past iterates)
- **Drop-in replacement**: Same F, different solver — no model changes

### Phase 3+: Newton-Krylov

For very large systems (100+ countries):

```python
scipy.optimize.newton_krylov(F - id, x_0)
```

- Approximates Jacobian via Krylov subspace methods (no explicit Jacobian needed)
- Quadratic convergence near solution
- Only needed if Anderson is too slow at country-level resolution


## 4. Banach Fixed-Point Theorem

**Theorem**: If $F$ is a contraction ($\|F(\mathbf{x}) - F(\mathbf{y})\| \leq q\|\mathbf{x} - \mathbf{y}\|$ for some $q < 1$), then:
1. A unique fixed point $\mathbf{x}^*$ exists
2. The iteration $\mathbf{x}_{n+1} = F(\mathbf{x}_n)$ converges from any starting point
3. Convergence rate: $\|\mathbf{x}_n - \mathbf{x}^*\| \leq q^n \cdot \|\mathbf{x}_0 - \mathbf{x}^*\|$

**In practice**: The undamped $F$ may not be a contraction (price–demand feedback can amplify). Damping ensures contraction:

$$F_{damped}(\mathbf{x}) = \alpha \cdot F(\mathbf{x}) + (1 - \alpha) \cdot \mathbf{x}$$

If the Lipschitz constant of $F$ is $L$, then $F_{damped}$ has Lipschitz constant $\alpha \cdot L$. For $\alpha < 1/L$, $F_{damped}$ is a contraction and convergence is guaranteed.


## 5. Convergence Monitoring

### Overall residual

$$\text{residual} = \frac{\|\mathbf{x}_{n+1} - \mathbf{x}_n\|}{\|\mathbf{x}_n\|}$$

| Threshold | Meaning |
|-----------|---------|
| > 1.0 | Diverging — reduce damping $\alpha$ |
| 0.01–1.0 | Converging slowly — increase m (Anderson) or adjust $\alpha$ |
| < 0.01 | Near convergence |
| < 1e-6 | Converged |

### Per-component diagnostics

When overall convergence is slow, decompose residual by component:

```
‖ΔY‖ / ‖Y‖           → macro not converging (energy cost feedback too strong?)
‖Δp_coal‖ / ‖p_coal‖  → trade clearing oscillating (grade boundary jump?)
‖Δp_elec‖ / ‖p_elec‖  → electricity price unstable (logit sensitivity?)
‖ΔI_E‖ / ‖I_E‖        → energy investment volatile (learning curve feedback?)
```

### Scaling

State vector components have different magnitudes (Y ~ trillions, prices ~ $/GJ). Normalize before computing residuals: use relative norm $\|\Delta x\| / \|x\|$ or pre-scale the vector.


## 6. Recursive-Dynamic Run Loop

```python
def run_model(model, solver, periods, ssp_data):
    """Solve period-by-period with warm-start."""
    results = []
    state = model.initialize(ssp_data, periods[0])

    for period in periods:
        # Update exogenous inputs
        state.period = period
        state.population = get_population(ssp_data, period)

        # Solve fixed-point for this period
        state = solver.solve(model, state)

        # Inter-period updates (NOT part of F)
        model.tech_change.update(state)              # learning curves
        model.update_capital(state)                   # K(t+1) = (1-δ)K + I_K
        model.update_vintage(state)                   # retirement + new investment
        model.trade.update_depletion(state)           # resource depletion

        results.append(deepcopy(state))
        # state carries forward as warm-start

    return results
```

**Inter-period updates** happen BETWEEN periods, not inside F. They update:
- Capital stock: $K(t+1) = (1-\delta)^{\Delta t} \cdot K(t) + I_K \cdot \Delta t$
- Vintage stock: retire old, add new investment
- Cumulative deployment: $Q^{cum}(t+1) = Q^{cum}(t) + new\_cap$
- Knowledge stock: $H(t+1) = (1-\delta_H) \cdot H(t) + RD$
- Resource depletion: reduce available grades


## 7. User Configurables

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| Solver method | `damped` | `damped`, `anderson`, `newton_krylov` |
| Damping $\alpha$ | 0.5 | Global (0.1–0.9) |
| Anderson memory $M$ | 5 | Global (3–10) |
| Convergence tolerance | 1e-3 (Phase 1) | Global |
| Max iterations | 50 | Global |
| Warm-start | Enabled | Global (disable for debugging) |


## 8. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| Solver | Damped iteration ($\alpha = 0.3$–$0.5$) | Anderson acceleration ($M = 5$) |
| State vector | 133 dim (4×32 + 5) | 4×N + 5 (N = country count) |
| Trade clearing | Bisection inside F | Same |
| Convergence criterion | Relative norm < 1e-3 | < 1e-6 |
| Fallback | Manual $\alpha$ adjustment | Automatic fallback to damped |
| Diagnostics | Per-component residual | + Jacobian condition number estimate |

### Phase transition notes

- **Phase 1 → 2**: Replace DampedSolver with AndersonSolver. Same F, same state vector, different solver. Tighten tolerance. Add automatic fallback.
- **Phase 2 → 3**: Newton-Krylov for 100+ country resolution. State vector grows to ~400+ dimensions. May need preconditioning.
