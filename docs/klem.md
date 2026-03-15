# KLEM Macroeconomic Component

Detailed technical documentation for the fully nested CES-KLE macroeconomic driver in GHIM.

**Source files:**
- `ghim/econ/klem.py` — `KLEMDriver` class
- `ghim/econ/ces.py` — CES utility functions (`ces_output`, `ces_calibrate`)
- `ghim/solver/recursive.py` — `solve_period()`, `run_model()`
- `ghim/config.py` — parameters

---

## 1. What Is a Production Function?

A production function describes how an economy turns **inputs** (things you use) into **output** (the goods and services produced, measured as GDP).

### 1.1 The Simplest Case: One Input

Suppose output depends only on labor:

$$
Y = A \cdot L
$$

$A$ is "productivity" — how much each worker produces. If $A = 50{,}000$ and $L = 1{,}000$ workers, then $Y = 50$ million. A country with better technology, education, or institutions has higher $A$.

### 1.2 Two Inputs: Cobb-Douglas

Economies also use capital (machines, factories, infrastructure). The standard Cobb-Douglas production function is:

$$
Y = A \cdot K^{\alpha} \cdot L^{1-\alpha}
$$

where:
- $K$ = capital stock (billion USD)
- $L$ = labor force (millions of workers)
- $\alpha$ = capital share (how much of output comes from capital, typically 0.30)
- $A$ = Total Factor Productivity (TFP, everything else: technology, institutions, etc.)

The exponents $\alpha$ and $1-\alpha$ sum to 1, giving **constant returns to scale**: doubling both $K$ and $L$ doubles $Y$.

#### Understanding $\alpha$: The Capital Share

$\alpha$ is the **capital share of national income** — the fraction of GDP paid to capital owners (as corporate profits, dividends, interest, and depreciation), as opposed to workers (wages and benefits). In national accounts data:

- $\alpha \approx 0.30$: roughly 30% of GDP goes to capital, 70% to labor
- This split is one of **Kaldor's stylized facts** (1961): the capital–labor income shares are approximately constant across countries and over time, despite vast differences in development levels

**Output elasticities.** The exponents in Cobb-Douglas are exactly the output elasticities:

| | Expression | Value | Meaning |
|---|---|---|---|
| Capital elasticity | $\frac{\partial Y}{Y} / \frac{\partial K}{K} = \alpha$ | 0.30 | 1% more capital → 0.3% more output |
| Labor elasticity | $\frac{\partial Y}{Y} / \frac{\partial L}{L} = 1-\alpha$ | 0.70 | 1% more labor → 0.7% more output |

**Implications for GHIM:**

- **Income distribution**: $\alpha$ determines how sensitive output is to capital accumulation versus population growth. A higher $\alpha$ means the economy is more *capital-intensive* — investment matters more, demographic changes matter less.
- **Diminishing returns and convergence**: Because $\alpha < 1$, additional capital has decreasing marginal product ($MPK = \alpha A (K/L)^{\alpha-1}$). This is why capital-rich countries grow more slowly from capital accumulation alone, and why TFP growth (rising $A$) is the only source of sustained long-run growth.
- **Euler's theorem**: With constant returns to scale ($\alpha + (1-\alpha) = 1$), total output is exactly exhausted when each factor is paid its marginal product: $Y = MPK \times K + MPL \times L$. There is no "residual" — the income distribution is fully determined by $\alpha$.

#### Formal Derivation: $\alpha$ = Capital Income Share

This result follows from two standard assumptions: (i) constant returns to scale and (ii) competitive factor markets (each factor is paid its marginal product).

**Step 1: Marginal products.** Differentiate $Y = A K^{\alpha} L^{1-\alpha}$:

$$
MPK \equiv \frac{\partial Y}{\partial K} = \alpha A K^{\alpha - 1} L^{1-\alpha} = \alpha \frac{Y}{K}
$$

$$
MPL \equiv \frac{\partial Y}{\partial L} = (1-\alpha) A K^{\alpha} L^{-\alpha} = (1-\alpha) \frac{Y}{L}
$$

**Step 2: Competitive pricing.** In a competitive economy, factor prices equal marginal products:

$$
r = MPK = \alpha \frac{Y}{K}, \qquad w = MPL = (1-\alpha) \frac{Y}{L}
$$

**Step 3: Income shares.** Multiply each factor price by its quantity:

$$
\underbrace{r \cdot K}_{\text{capital income}} = \alpha \cdot Y \qquad \implies \qquad \frac{r \cdot K}{Y} = \alpha
$$

$$
\underbrace{w \cdot L}_{\text{labor income}} = (1-\alpha) \cdot Y \qquad \implies \qquad \frac{w \cdot L}{Y} = 1 - \alpha
$$

So $\alpha$ is literally the fraction of GDP paid to capital (corporate profits + interest + depreciation), and $(1-\alpha)$ is the fraction paid to labor (wages + benefits + self-employment income).

**Step 4: Euler's theorem (income exhaustion).** Adding the two:

$$
r \cdot K + w \cdot L = \alpha Y + (1-\alpha) Y = Y
$$

Total factor payments *exactly exhaust* total output. There is no residual profit. This is a consequence of constant returns to scale (homogeneity of degree 1) and holds for any homogeneous-of-degree-1 production function, not just Cobb-Douglas.

**Step 5: Why constant shares?** Notice that $r \cdot K / Y = \alpha$ regardless of the levels of $K$, $L$, $r$, or $w$. This is the Kaldor fact: in Cobb-Douglas, income shares are structurally constant. No matter how capital-rich or labor-rich the economy becomes, capital always receives exactly fraction $\alpha$ of GDP. This is a *very strong* restriction — one that CES relaxes (see §2.5).

**Connection to national accounts.** In practice, $\alpha$ is measured from the income side of GDP:

$$
\alpha = 1 - \text{labsh} \approx 1 - 0.70 = 0.30
$$

where $\text{labsh}$ is the labor share from the Penn World Table (`labsh` variable) or the BEA NIPA Table 1.12 (compensation of employees / national income). The global cross-country median is approximately $\alpha = 0.30$ (Gollin, 2002, *Journal of Monetary Economics*), though individual countries range from 0.20 (labor-intensive LICs) to 0.45 (resource-rich economies like Saudi Arabia).

**Empirical range.** Most estimates place $\alpha$ between 0.25 and 0.35. We use 0.30, the standard value from the Solow growth model.

### 1.3 What TFP Means

TFP captures the part of GDP that can't be explained by capital and labor alone. Two countries with identical $K$ and $L$ can have very different GDP because of:
- Technology level (a robot factory vs a manual factory)
- Institutional quality (rule of law, property rights)
- Human capital (education, skills)
- Resource allocation efficiency

In GHIM, TFP is **calibrated** from SSP GDP paths (Section 9): given SSP projections for $K$, $L$, and $Y$, we solve for $A$.

### 1.4 Diminishing Returns

Cobb-Douglas has a key property: **diminishing returns** to each factor. If you double capital while holding labor constant, output less than doubles (because $\alpha < 1$). This is why rich countries grow slower — adding more capital yields less and less extra output.

### 1.5 Deriving the K-L Elasticity of Substitution

The **elasticity of substitution** $\sigma_{KL}$ measures how easily firms switch between capital and labor when their relative price changes. For Cobb-Douglas, $\sigma_{KL} = 1$ always — this is a defining property.

**Derivation.** A cost-minimizing firm solves:

$$
\min_{K, L} \;\; r \cdot K + w \cdot L \quad \text{s.t.} \quad A \cdot K^{\alpha} \cdot L^{1-\alpha} = \bar{Y}
$$

The first-order conditions (divide $\partial \mathcal{L}/\partial K$ by $\partial \mathcal{L}/\partial L$):

$$
\frac{r}{w} = \frac{\alpha}{1-\alpha} \cdot \frac{L}{K}
$$

Rearranging:

$$
\frac{K}{L} = \frac{\alpha}{1-\alpha} \cdot \frac{w}{r}
$$

Taking logarithms:

$$
\ln\!\left(\frac{K}{L}\right) = \text{const} + 1 \cdot \ln\!\left(\frac{w}{r}\right)
$$

The elasticity of substitution is:

$$
\sigma_{KL} = -\frac{d \ln(K/L)}{d \ln(r/w)} = 1
$$

**Meaning**: a 1% increase in the wage-to-rental ratio causes firms to substitute toward capital, raising the $K/L$ ratio by exactly 1%. This is fixed by construction in Cobb-Douglas — it is the reason we use the more flexible CES for the outer nest (VA vs Energy).

---

## 2. What Is CES?

### 2.1 The Limitation of Cobb-Douglas

Cobb-Douglas forces the **elasticity of substitution** to equal exactly 1. This means that when one input gets more expensive, firms always substitute at the same rate. But in reality:
- It's easy to substitute between different brands of steel (high elasticity)
- It's hard to substitute energy for labor (low elasticity)

We need a production function where substitution elasticity is a free parameter.

### 2.2 CES Definition

The **Constant Elasticity of Substitution** (CES) function is:

$$
Y = A \left[\alpha_1 X_1^{\rho} + \alpha_2 X_2^{\rho}\right]^{1/\rho}
$$

where:
- $X_1$, $X_2$ = two inputs
- $\alpha_1$, $\alpha_2$ = share parameters (how important each input is)
- $\rho = (\sigma - 1)/\sigma$ where $\sigma$ is the elasticity of substitution
- $A$ = scale factor

**Yes, $\alpha_1 + \alpha_2 = 1$.** The `ces_calibrate()` function (in `ghim/econ/ces.py`) explicitly normalizes: `return raw / raw.sum()`. This ensures **constant returns to scale** — if both inputs double, output doubles. It is the CES analogue of the Cobb-Douglas requirement that exponents sum to 1.

### 2.3 What the Elasticity of Substitution ($\sigma$) Means

$\sigma$ controls how easily firms switch between inputs when relative prices change:

| $\sigma$ | Meaning | Example |
|---------|---------|---------|
| $\sigma = 0$ | **Leontief** (perfect complements) | Left shoes and right shoes — you need them in fixed proportions |
| $\sigma = 1$ | **Cobb-Douglas** (unit elasticity) | The standard growth model |
| $\sigma \to \infty$ | **Perfect substitutes** | Two identical brands of gasoline |

For energy and value-added, empirical estimates place $\sigma$ in the range **0.3–0.5**: the economy *can* reduce energy use when prices rise, but not easily.

### 2.4 Visual Intuition

Think of isoquant curves (all combinations of two inputs that produce the same output):
- **$\sigma = 0$** (Leontief): L-shaped curves — no substitution possible
- **$\sigma = 1$** (Cobb-Douglas): smooth hyperbolas
- **$\sigma \to \infty$**: straight lines — perfect substitution

CES with $\sigma = 0.4$ gives curves that are "more angular" than Cobb-Douglas — firms can substitute, but it's costly.

### 2.5 CES Marginal Products and Income Shares

This section derives results that are central to interpreting CES production functions: the marginal product of each factor, the resulting income shares, and how those shares respond to changes in factor proportions.

#### 2.5.1 Marginal Products

Starting from the two-factor CES:

$$
Y = A \left[\alpha_1 X_1^{\rho} + \alpha_2 X_2^{\rho}\right]^{1/\rho}
$$

Define $S \equiv \alpha_1 X_1^{\rho} + \alpha_2 X_2^{\rho}$, so $Y = A \cdot S^{1/\rho}$.

**Differentiate** with respect to $X_i$:

$$
\frac{\partial Y}{\partial X_i} = A \cdot \frac{1}{\rho} \cdot S^{1/\rho - 1} \cdot \alpha_i \cdot \rho \cdot X_i^{\rho - 1} = A \cdot \alpha_i \cdot X_i^{\rho - 1} \cdot S^{(1-\rho)/\rho}
$$

Since $S^{1/\rho} = Y/A$, we have $S = (Y/A)^{\rho}$, so:

$$
S^{(1-\rho)/\rho} = \left[(Y/A)^{\rho}\right]^{(1-\rho)/\rho} = (Y/A)^{1-\rho}
$$

Substituting:

$$
\boxed{\frac{\partial Y}{\partial X_i} = \alpha_i \cdot A^{\rho} \cdot X_i^{\rho - 1} \cdot Y^{1-\rho} = \alpha_i \left(\frac{Y}{A \cdot X_i}\right)^{1-\rho} \cdot A}
$$

This can also be written in a more intuitive form:

$$
\frac{\partial Y}{\partial X_i} = \frac{\alpha_i}{X_i} \cdot \left(\frac{X_i}{Y/A}\right)^{\rho} \cdot Y = \frac{\alpha_i \cdot X_i^{\rho}}{S} \cdot \frac{Y}{X_i}
$$

**Verify for Cobb-Douglas ($\rho \to 0$, $\sigma = 1$):** When $\rho = 0$, we need the limit. With $\alpha_1 + \alpha_2 = 1$ and $Y = A \prod X_i^{\alpha_i}$:

$$
\frac{\partial Y}{\partial X_i} = \alpha_i \frac{Y}{X_i}
$$

This is the standard Cobb-Douglas marginal product, confirming that CES generalizes Cobb-Douglas.

#### 2.5.2 Income Shares under CES

In a competitive economy, factor $i$ is paid its marginal product: $p_i = \partial Y / \partial X_i$. The **income share** of factor $i$ is:

$$
s_i \equiv \frac{p_i \cdot X_i}{Y} = \frac{\partial Y}{\partial X_i} \cdot \frac{X_i}{Y}
$$

Substituting the CES marginal product:

$$
s_i = \alpha_i \cdot A^{\rho} \cdot X_i^{\rho-1} \cdot Y^{1-\rho} \cdot \frac{X_i}{Y} = \alpha_i \cdot A^{\rho} \cdot \frac{X_i^{\rho}}{Y^{\rho}}
$$

Since $Y^{\rho} = A^{\rho} \cdot S = A^{\rho} \cdot (\alpha_1 X_1^{\rho} + \alpha_2 X_2^{\rho})$:

$$
\boxed{s_i = \frac{\alpha_i \cdot X_i^{\rho}}{\alpha_1 X_1^{\rho} + \alpha_2 X_2^{\rho}} = \frac{\alpha_i \cdot X_i^{\rho}}{S}}
$$

This is the **fundamental CES income share formula**. Note that $s_1 + s_2 = 1$ (Euler's theorem is satisfied).

#### 2.5.3 Special Case: Cobb-Douglas ($\sigma = 1$, $\rho = 0$)

When $\rho \to 0$, $X_i^{\rho} \to 1$ for all $i$, so:

$$
s_i \to \frac{\alpha_i \cdot 1}{\alpha_1 \cdot 1 + \alpha_2 \cdot 1} = \frac{\alpha_i}{\alpha_1 + \alpha_2} = \alpha_i
$$

Income shares are **constant** — always equal to the CES share parameters regardless of input quantities. This is why Cobb-Douglas predicts Kaldor's stylized fact (stable capital-labor income split), and why it cannot explain observed shifts in income distribution.

#### 2.5.4 How Income Shares Respond to Factor Proportions ($\sigma \neq 1$)

When $\sigma \neq 1$, income shares become functions of the input ratio $X_1 / X_2$. To see this, rewrite the capital share for a K-L economy ($X_1 = K$, $X_2 = L$):

$$
s_K = \frac{\alpha_K \cdot K^{\rho}}{\alpha_K \cdot K^{\rho} + \alpha_L \cdot L^{\rho}} = \frac{1}{1 + \frac{\alpha_L}{\alpha_K} \left(\frac{L}{K}\right)^{\rho}}
$$

Differentiating with respect to $K$ (holding $L$ fixed):

$$
\frac{\partial s_K}{\partial K} \propto \rho \cdot \alpha_K \cdot K^{\rho - 1} \cdot \alpha_L \cdot L^{\rho}
$$

The sign depends on $\rho$:

| Regime | $\sigma$ | $\rho$ | Capital deepening ($K/L \uparrow$) | Interpretation |
|--------|----------|--------|--------------------------------------|----------------|
| **Gross complements** | $\sigma < 1$ | $\rho < 0$ | Capital share **falls** | Scarce factor (labor) commands a higher premium; capital becomes "cheap" |
| **Unit elasticity** | $\sigma = 1$ | $\rho = 0$ | Capital share **unchanged** | Kaldor's stylized fact |
| **Gross substitutes** | $\sigma > 1$ | $\rho > 0$ | Capital share **rises** | Abundant factor (capital) captures more income; Piketty mechanism |

**Numerical illustration.** Consider $\alpha_K = \alpha_L = 0.5$ (symmetric CES for clarity) with initial $K = L = 100$. Now double $K$ to $200$:

| $\sigma$ | $\rho$ | $s_K$ before | $s_K$ after $K$ doubles | Change |
|-----------|--------|--------------|-------------------------|--------|
| 0.4 | $-1.50$ | 0.500 | 0.261 | $-24$ pp |
| 0.8 | $-0.25$ | 0.500 | 0.457 | $-4$ pp |
| 1.0 | $0$ | 0.500 | 0.500 | 0 |
| 1.25 | $0.20$ | 0.500 | 0.535 | $+4$ pp |
| 2.0 | $0.50$ | 0.500 | 0.586 | $+9$ pp |

**For GHIM** ($\sigma_{KL} = 0.8$, $\rho = -0.25$): as the economy accumulates capital (rising $K/L$), the capital income share *slowly declines*. Over the 130-year horizon (2020–2150), if $K/L$ doubles, the capital share falls by roughly 4 percentage points (from 0.30 to ~0.26). This is the standard neoclassical result — diminishing returns to capital in the income distribution sense.

#### 2.5.5 The Piketty Debate

Thomas Piketty (*Capital in the Twenty-First Century*, 2014) documented a rising capital share in advanced economies since the 1980s. Two interpretations exist:

1. **$\sigma > 1$ (Karabarbounis & Neiman, 2014, *QJE*):** If capital and labor are gross substitutes, capital deepening (falling relative price of investment goods → more $K$) directly increases the capital share. Their estimate: $\sigma \approx 1.25$.

2. **$\sigma < 1$ + other forces (Oberfield & Raval, 2021, *JPE*; Chirinko, 2008, *Macro Annual*):** Most firm-level and industry-level studies estimate $\sigma \in [0.4, 0.8]$. The rising capital share must then come from other channels: increasing markups, a shift toward capital-intensive sectors, or rising housing wealth (which is not "productive" capital).

We follow the micro-evidence consensus ($\sigma_{KL} = 0.8$). GHIM does not need to reproduce the rising capital share, because the model's SSP GDP paths are exogenous reference trajectories — the capital share only matters for how the model responds to *deviations* from reference (e.g., energy shocks).

#### 2.5.6 Isoquant Comparison

An isoquant is the set of input combinations $(X_1, X_2)$ that produce the same output $\bar{Y}$. The curvature reflects the elasticity of substitution:

```
  X₂ (Labor)
  │
  │╲                    σ = 5.0 (near-substitutes)
  │ ╲  ___________      Almost linear: easy to trade
  │  ╲╱              one input for the other
  │   ╲
  │────┐╲               σ = 1.0 (Cobb-Douglas)
  │    │ ╲  ────────    Smooth hyperbola: standard
  │    │  ╲──────       substitution
  │    │   ╲
  │    │    ╲            σ = 0.4 (our VA-E)
  │    │     ╲           Near-Leontief: angular curves,
  │    │      ╲───       both inputs essential
  │    │       ╲
  │    │        ╲
  └────┴─────────────── X₁ (Capital or Energy)
```

- $\sigma = 0.4$: The curve bends sharply near the "corner." Reducing one input even slightly requires a large increase in the other. This captures the reality that you cannot easily substitute energy for labor+capital.
- $\sigma = 1.0$: The classic Cobb-Douglas hyperbola. A 1% reduction in one input requires exactly a 1% increase in the other (at constant output).
- $\sigma = 5.0$: Near-linear. Inputs are almost interchangeable. Rare in practice at the macro level.

**For GHIM:** The inner nest (K-L) has $\sigma = 0.8$, giving gently curved isoquants — capital and labor substitute fairly well but not perfectly. The outer nest (VA-E) has $\sigma = 0.4$, giving sharply curved isoquants — the economy *must* use energy; no amount of capital and labor can fully compensate for energy loss.

---

## 3. Why Energy Matters in Production

### 3.1 The Missing Factor

Standard growth models (Solow, DICE) treat GDP as a function of capital and labor only. Energy is either ignored or treated as an exogenous driver. But the economy fundamentally needs energy:
- Factories need electricity to run machines
- Transport needs fuel to move goods
- Buildings need heating and cooling
- Data centers need power for computation

### 3.2 The Problem

When energy is not a production factor, the model has no way to respond to energy price changes:
- A carbon tax raises fuel prices. What happens to GDP? The model can't tell you.
- Oil supply disruptions reduce available energy. What happens to output? Silence.

### 3.3 The Solution

Add energy ($E$) as an explicit factor of production alongside capital ($K$) and labor ($L$). Now the production function is:

$$
Y = f(K, L, E)
$$

When energy prices rise, firms use less energy, and output falls — naturally, through the production function itself.

---

## 4. Our Two-Level Production Structure

GHIM uses a **two-level nested CES** structure:

### Level 1 (Inner): Value Added

$$
VA = A(t) \cdot \text{CES}(K, L;\; \sigma_{KL}) \qquad \text{[CES, } \sigma_{KL} = 0.8\text{]}
$$

Capital and labor are combined via CES with $\sigma_{KL} = 0.8$ — slightly less substitutable than Cobb-Douglas ($\sigma = 1$). This means the economy cannot fully compensate for labor loss by adding capital, and vice versa.

#### Why CES instead of Cobb-Douglas for K-L?

Cobb-Douglas forces $\sigma_{KL} = 1$ and predicts constant capital income shares. However:

- **Income shares are not constant.** As shown in §2.5.4, when $\sigma \neq 1$, the capital income share varies with $K/L$. Cobb-Douglas cannot capture *any* endogenous shift in factor income distribution. With $\sigma_{KL} = 0.8$, capital deepening causes the capital share to *decline gradually* — the standard neoclassical result (diminishing returns dominating). See §2.5.5 for the debate on the sign of these shifts.
- **Oberfield & Raval (2021, *JPE*)** estimate aggregate $\sigma_{KL} \approx 0.7$ for the US manufacturing sector. Other estimates: Chirinko (2008, *NBER Macro Annual*) surveys the literature and finds a central range of 0.4–0.6; Antràs (2004, *REStat*) gets 0.8–1.0 from aggregate time series. Our choice of 0.8 sits near the upper end of micro estimates.
- **Long time horizon**: GHIM runs to 2150. Over 130 years, K/L ratios may change dramatically (automation, demographic transitions). Even small deviations from $\sigma = 1$ compound — the capital share can shift by several percentage points (§2.5.4, numerical table).
- **GCAM, REMIND, WITCH** all use CES for K-L. Nested CES is the standard in IAMs.

The cost: one additional parameter ($\sigma_{KL}$). Cobb-Douglas is recovered as the special case $\sigma_{KL} = 1$.

#### K-L Calibration

At the base year, factor prices are derived from the capital share $\alpha$:

$$
r = \frac{\alpha \cdot GDP}{K} \qquad \text{(rental rate of capital)}
$$

$$
w = \frac{(1-\alpha) \cdot GDP}{L} \qquad \text{(wage rate)}
$$

These satisfy Euler's theorem ($r \cdot K + w \cdot L = GDP$) regardless of the production function form. The CES share parameters $\alpha_K$, $\alpha_L$ are then calibrated from $\{K, L, r, w, \sigma_{KL}\}$ using `ces_calibrate()`, the same procedure used for the outer nest.

### Level 2 (Outer): Gross Output

$$
Y = A_{\text{CES}} \left[\alpha_{VA} \cdot VA^{\rho} + \alpha_E \cdot E_{\text{val}}^{\rho}\right]^{1/\rho} \qquad \text{[CES, } \sigma_{KLE} = 0.4\text{]}
$$

where $E_{\text{val}} = E \times P_{E,0}$ is energy in value terms (Section 5), and $\rho = (\sigma_{KLE} - 1)/\sigma_{KLE}$.

#### Why $\rho$ Is Negative

With our parameter $\sigma_{KLE} = 0.4$:

$$
\rho = \frac{0.4 - 1}{0.4} = -1.5
$$

A negative $\rho$ means the CES aggregator raises inputs to a *negative power*: $X^{-1.5}$. This is a decreasing, convex function of $X$ — smaller input values produce *larger* terms inside the bracket. The outer exponent $1/\rho$ (also negative) then flips this back, so that lower inputs reduce output. The net effect:

- **Bottleneck behavior**: the input in shortest supply dominates the aggregate. If energy drops while VA is abundant, output is pulled down toward the energy bottleneck.
- **Complementarity**: both inputs are needed — you cannot compensate for a large drop in one by increasing the other.

Contrast with $\rho > 0$ (i.e., $\sigma > 1$): inputs become more substitutable, and the *largest* input dominates the aggregate. Our $\rho = -1.5$ reflects the empirical reality that value-added and energy are **complements, not substitutes** — the economy cannot easily replace energy with more capital and labor.

#### Why Fixed Base-Year Prices for $E_{\text{val}}$

The base-year price $P_{E,0}$ serves as a **fixed unit conversion factor** (EJ → billion USD), analogous to deflating GDP to constant dollars. The *current* price $P_E(t)$ drives substitution through the energy demand equation (Section 6). If we used current prices inside $E_{\text{val}}$, price changes would be counted twice: once in the demand equation (reducing $E$) and again in $E_{\text{val}}$ (changing the value per unit). See Section 5.3 for a detailed explanation and numerical example.

### 4.1 Why Two Levels?

Each level captures a different kind of substitution:

- **Level 1 ($K$ vs $L$, $\sigma_{KL} = 0.8$)**: Capital and labor are moderately substitutable. Richer countries invest more in capital (machines replace workers), but not without limit — some tasks fundamentally require human labor ($\sigma < 1$ means complements).

- **Level 2 ($VA$ vs $E$, $\sigma_{KLE} = 0.4$)**: Value-added and energy are harder to substitute. When energy gets expensive, the economy shifts toward less energy-intensive activities — but not easily.

### 4.2 Diagram

```
    SSP Scenarios (Population, GDP|PPP)
                  │
    TFP calibrated once (so Y ≈ Y_SSP in reference case)
                  │
                  ▼
    ┌────────────────────────────┐
    │    Value Added (inner)     │
    │  VA = TFP × CES(K, L; σ_KL) │  ← CES (σ_KL = 0.8)
    └────────────┬───────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │  CES Gross Output (outer)  │
    │  Y = CES(VA, E_val; σ)     │  ← Energy as explicit factor
    └────────────┬───────────────┘
                 │
    ┌────────────┴───────────────┐
    │                            │
    ▼                            ▼
  Energy demand              Investment
  E = E₀·(VA/VA₀)·          I = s × Y
    (P_E/P_E₀)^(-σ)         K(t+1) = K(t) + I·dt
```

The key difference from earlier DICE-style models: **investment comes from gross CES output**, not from a "net output" that subtracts energy costs. Energy's drag on the economy is captured inside the CES production function itself.

#### Why Investment Comes from Gross Output

In the CES framework, energy is a **production input** — it sits *inside* the production function, not outside it. Consider an analogy: a car factory buys steel (input) and produces cars (output $Y$). The factory invests a fraction of car revenue into new equipment. You would not compute investment as "car revenue minus steel costs," because the production function already incorporates steel as an input that determines output.

The same logic applies here:
- Energy is inside $Y = \text{CES}(VA, E_{\text{val}})$. When energy falls, $Y$ falls directly.
- Investment $I = s \times Y$ is then naturally lower — no additional subtraction needed.
- Subtracting energy cost *again* ($I = s \times (Y - P_E \cdot E)$) would **double-count**: the CES already reduced $Y$ when $E$ fell.

The "net output" approach ($Y_{\text{net}} = VA - \text{EnergyCost}$) was a DICE-style shortcut for when energy was *not* a factor of production. With full CES, $I = s \times Y$ is standard practice in GCAM and other CGE models (see §15 for a detailed comparison).

---

## 5. The Unit Problem and How We Solve It

### 5.1 The Problem

CES requires its inputs to be in comparable units. But:
- $VA$ is measured in **billion USD**
- $E$ is measured in **EJ** (exajoules, a physical unit)

You can't add dollars and joules in $[\alpha_{VA} \cdot VA^{\rho} + \alpha_E \cdot E^{\rho}]$.

### 5.2 The Solution: Energy Value

Convert energy to value terms using the **base-year energy price** as a fixed conversion factor:

$$
E_{\text{val}} = E \;\text{(EJ)} \times P_{E,0} \;\text{(\$/GJ)} = \text{billion USD}
$$

This works because 1 EJ = $10^9$ GJ, so EJ $\times$ \$/GJ = billion USD.

### 5.3 Why Base-Year Price? (And Why Not Current Price?)

$P_{E,0}$ is a **fixed constant** — it never changes during the simulation. It acts like a unit conversion factor (analogous to using 2.54 to convert inches to centimeters). The *current* energy price drives substitution through the energy demand equation (Section 6), not through $E_{\text{val}}$.

This is the same approach used by GCAM: base-year prices are baked into the CES share parameters during calibration. The CES $\alpha$ parameters absorb any remaining scale differences between $VA$ and $E_{\text{val}}$.

#### The Two Distinct Roles of Price

It is essential to understand the **separation of responsibilities** between the fixed and current prices:

| | $P_{E,0}$ (fixed) | $P_E(t)$ (varies) |
|---|---|---|
| **Role** | Unit converter: EJ → billion USD | Substitution driver: determines how much energy firms demand |
| **Where used** | $E_{\text{val}} = E \times P_{E,0}$ (CES input) | $E = E_0 \cdot (VA/VA_0) \cdot (P_E/P_{E,0})^{-\sigma}$ (demand equation) |
| **Changes over time?** | No — frozen at base year | Yes — responds to carbon prices, supply shifts, etc. |

#### Why Using Current Prices Would Be Wrong

If we used $E_{\text{val}} = E \times P_E(t)$ instead, price changes would be **counted twice**:

1. In the demand equation: $P_E \uparrow$ → $E \downarrow$ (correct price response)
2. In $E_{\text{val}}$: the remaining energy would be valued at a *higher* price, inflating its contribution to output

**Numerical proof.** Suppose energy price doubles from $P_{E,0} = 7.5$ to $P_E = 15.0$ $/GJ:

- Energy demand falls: $E = E_0 \times (15/7.5)^{-0.4} = E_0 \times 0.76$ (24% reduction)

With **current prices** (wrong): $E_{\text{val}} = 0.76 \cdot E_0 \times 15.0 = 1.52 \cdot E_{\text{val,base}}$. Energy's *value contribution rises* despite using less energy — nonsensical. The CES would compute a *higher* output.

With **fixed prices** (correct): $E_{\text{val}} = 0.76 \cdot E_0 \times 7.5 = 0.76 \cdot E_{\text{val,base}}$. Energy's value contribution falls proportionally with physical consumption — the CES correctly computes lower output.

The fixed-price approach ensures the CES production function measures energy's *real* (volume) contribution to output, while the demand equation handles the behavioral response to prices. This clean separation is what GCAM and other CGE models do.

### 5.4 Calibration at Base Year

At the base year (2020), both $VA$ and $E_{\text{val}}$ are known:
- $VA \approx GDP$ (e.g., \$21,000 billion for North America)
- $E_{\text{val}} = E_0 \times P_{E,0}$ (e.g., 37 EJ $\times$ 7.5 \$/GJ = \$277.5 billion)

The CES share parameters are calibrated from:

$$
\alpha_i = \frac{X_i}{\sum_j X_j}
$$

And a CES scale factor $A_{\text{CES}}$ ensures $Y = \text{CES}(VA, E_{\text{val}}) = GDP$ exactly at the base year.

---

## 6. How Much Energy Does the Economy Need?

### 6.1 The CES First-Order Condition (FOC)

Starting from the CES production function, a firm minimizes cost subject to a target output level. The first-order conditions from this optimization yield an energy demand function.

### 6.2 Full Derivation

**Step 1: CES production function**

$$
Y = A \left[\alpha_{VA} \cdot VA^{\rho} + \alpha_E \cdot E^{\rho}\right]^{1/\rho}
$$

**Step 2: Cost minimization**

$$
\min_{VA, E} \quad P_{VA} \cdot VA + P_E \cdot E \quad \text{subject to} \quad Y = \bar{Y}
$$

**Step 3: Form the Lagrangian**

$$
\mathcal{L} = P_{VA} \cdot VA + P_E \cdot E - \lambda \left(A \left[\alpha_{VA} \cdot VA^{\rho} + \alpha_E \cdot E^{\rho}\right]^{1/\rho} - \bar{Y}\right)
$$

**Step 4: First-order conditions**

$$
\frac{\partial \mathcal{L}}{\partial VA} = P_{VA} - \lambda A \cdot \alpha_{VA} \cdot VA^{\rho-1} \cdot \left[\cdots\right]^{1/\rho - 1} = 0
$$

$$
\frac{\partial \mathcal{L}}{\partial E} = P_E - \lambda A \cdot \alpha_E \cdot E^{\rho-1} \cdot \left[\cdots\right]^{1/\rho - 1} = 0
$$

**Step 5: Divide the two FOCs**

The $\lambda$, $A$, and the $[\cdots]^{1/\rho-1}$ terms cancel:

$$
\frac{P_{VA}}{P_E} = \frac{\alpha_{VA}}{\alpha_E} \cdot \left(\frac{VA}{E}\right)^{\rho-1}
$$

**Step 6: Solve for $E/VA$**

$$
\frac{E}{VA} = \left(\frac{\alpha_E}{\alpha_{VA}}\right)^{\sigma} \cdot \left(\frac{P_{VA}}{P_E}\right)^{\sigma}
$$

where $\sigma = 1/(1-\rho)$ is the elasticity of substitution.

**Step 7: Normalize to base year**

At the base year, this ratio equals $E_0/VA_0$ by construction. Dividing the current-year expression by the base-year expression, the $\alpha$ terms cancel completely:

$$
\frac{E/VA}{E_0/VA_0} = \left(\frac{P_{VA}/P_E}{P_{VA,0}/P_{E,0}}\right)^{\sigma}
$$

Assuming $P_{VA}$ is roughly constant (or varies slowly compared to $P_E$), this simplifies to:

$$
E = E_0 \cdot \frac{VA}{VA_0} \cdot \left(\frac{P_E}{P_{E,0}}\right)^{-\sigma_{KLE}}
$$

This is the **isoelastic energy demand function** used in GHIM.

### 6.3 Deriving the VA-E Elasticity of Substitution

From Step 5 above, we have the FOC ratio:

$$
\frac{P_{VA}}{P_E} = \frac{\alpha_{VA}}{\alpha_E} \cdot \left(\frac{VA}{E}\right)^{\rho - 1}
$$

Taking logarithms:

$$
\ln\!\left(\frac{P_{VA}}{P_E}\right) = \ln\!\left(\frac{\alpha_{VA}}{\alpha_E}\right) + (\rho - 1) \cdot \ln\!\left(\frac{VA}{E}\right)
$$

The elasticity of substitution is:

$$
\sigma = -\frac{d \ln(VA/E)}{d \ln(P_{VA}/P_E)} = \frac{-1}{\rho - 1} = \frac{1}{1 - \rho} = \sigma_{KLE}
$$

With $\rho = -1.5$: $\sigma = 1/(1 - (-1.5)) = 1/2.5 = 0.4$ ✓

**Meaning**: a 1% increase in the relative price of energy ($P_E / P_{VA}$) causes the economy to shift its input mix, raising the $VA/E$ ratio by $\sigma_{KLE} = 0.4\%$. This is the fundamental behavioral parameter of the model — it governs how strongly GDP responds to energy price shocks.

### 6.4 What "FOC" Means

"First-Order Condition" is a calculus term for setting the derivative of the objective function to zero. In economics, it means: the firm adjusts its inputs until the marginal cost of each input equals its marginal product. The FOC gives us the optimal input ratio as a function of prices and the substitution elasticity.

### 6.5 Income Effect vs Price Effect

The demand equation has two multiplicative parts:

1. **Income effect** $(VA / VA_0)$: Energy demand grows with economic output. If the economy doubles, energy demand doubles. This is a unit income elasticity at the aggregate level.

2. **Price effect** $(P_E / P_{E,0})^{-\sigma_{KLE}}$: Higher prices reduce demand. With $\sigma_{KLE} = 0.4$:
   - A 10% price increase $\to$ ~4% demand reduction
   - A doubling of prices $\to$ ~24% demand reduction
   - A tripling of prices $\to$ ~36% demand reduction

### 6.6 AEEI (Autonomous Energy Efficiency Improvement)

AEEI captures exogenous technological progress in energy efficiency — improvements that occur independently of price signals (e.g., building codes, appliance standards, industrial best practices).

$$
E_{\text{eff}}(t) = E(t) \times \text{AEEI}(t)
$$

where $\text{AEEI}(t) = (1 - r)^{t - t_0}$ and $r$ is the annual improvement rate.

#### Implementation: `EfficiencyStandard` (in `ghim/policy.py`)

AEEI is fully configurable via the `EfficiencyStandard` dataclass. The default factor is **1.0** (no efficiency improvement). It can be set globally or per-sector, with time-varying rates:

| Configuration | Example | Effect |
|---|---|---|
| **Global rate** | `rates={"global": {2020: 0.02}}` | 2%/yr for all sectors from 2020 |
| **Sector-specific** | `rates={"transport": {2020: 0.03}, "buildings": {2020: 0.01}}` | Different rates per sector |
| **Time-varying** | `rates={"global": {2020: 0.01, 2040: 0.03}}` | Ramp up over time |

**CLI**: `--efficiency-rate 0.02` applies a 2%/yr global rate.
**JSON policy file**: set `efficiency_standards.rates` in the scenario JSON.

**Where it is applied** (in `ghim/solver/recursive.py`):

1. **Macro level**: total CES energy demand is scaled by `cumulative_factor("global", year, BASE_YEAR)`
2. **Sector level**: each demand sector's carrier demands are further scaled by `cumulative_factor(sector_name, year, BASE_YEAR)`, falling back to `"global"` if no sector-specific rate is defined

At a 2% annual rate, the cumulative factor after 30 years is $(1-0.02)^{30} = 0.545$ — a 45.5% reduction in energy intensity.

---

## 7. Gross Output from CES

### 7.1 The CES Production Function

Gross output is computed as:

$$
Y = A_{\text{CES}} \left[\alpha_{VA} \cdot VA^{\rho} + \alpha_E \cdot E_{\text{val}}^{\rho}\right]^{1/\rho}
$$

where:
- $VA$ = value added from the Cobb-Douglas inner nest
- $E_{\text{val}} = E \times P_{E,0}$ = energy in value terms
- $\alpha_{VA}$, $\alpha_E$ = share parameters from calibration
- $A_{\text{CES}}$ = scale factor ensuring $Y = GDP$ at base year
- $\sigma_{KLE} = 0.4$, $\rho = (\sigma - 1)/\sigma = -1.5$

### 7.2 How Energy Affects Output

When energy falls (due to higher prices or supply constraints), the CES output falls directly:

$$
E \downarrow \;\implies\; E_{\text{val}} \downarrow \;\implies\; Y \downarrow
$$

The magnitude depends on $\sigma_{KLE}$:
- With $\sigma = 0.4$, reducing energy by 20% reduces output by roughly 1–2% (because energy value is a small share of total inputs)
- The effect is larger in energy-intensive economies (higher $\alpha_E$)

### 7.3 Investment from Gross Output

Investment is computed directly from CES gross output:

$$
I = \min\bigl(s \cdot Y,\;\; \text{cap\_rate} \cdot K\bigr) = \min\bigl(0.22 \cdot Y,\;\; 0.10 \cdot K\bigr)
$$

There is **no separate energy cost subtraction**. Energy's drag on the economy is fully captured by the CES function:
- Higher energy prices $\to$ less energy consumed $\to$ lower $E_{\text{val}}$ $\to$ lower $Y$ $\to$ lower $I$ $\to$ slower capital growth

This is cleaner than the old "net output" approach and avoids double-counting.

---

## 8. Composite Energy Price

### 8.1 Expenditure-Weighted Average

The economy uses multiple fuels (coal, gas, oil, electricity, biomass, hydrogen). The composite price is:

$$
P_E = \frac{\sum_c \bigl(\text{Price}_c \times \text{Demand}_c\bigr)}{\sum_c \text{Demand}_c}
$$

Fuels that represent a larger share of the energy bill have more influence.

### 8.2 Why Not a Simple Average?

Consider an economy using 80% cheap coal (\$2/GJ) and 20% expensive electricity (\$20/GJ):

- **Arithmetic mean**: $(\$2 + \$20) / 2 = \$11$/GJ — overstates cost
- **Expenditure-weighted**: $(\$2 \times 0.8 + \$20 \times 0.2) / 1.0 = \$5.6$/GJ — reflects actual spending

### 8.3 Updated Within Price Iteration

The composite price is recalculated **within** the solver's price iteration loop. As electricity and hydrogen prices converge, the composite shifts, which changes CES energy demand, which changes sector demands, which changes supply-side prices. This inner loop converges in 3–5 iterations.

---

## 9. TFP Calibration

### 9.1 The Goal

TFP ($A$) is calibrated once at initialization so that CES gross output matches the SSP GDP projection **in the absence of energy shocks**:

$$
Y = A_{\text{CES}} \cdot \text{CES}\bigl(A \cdot \text{CES}_{KL}(K, L),\; E_{\text{val}}\bigr) = Y_{\text{SSP}}
$$

During simulation, TFP is frozen. GDP diverges from SSP only through the CES feedback: energy prices $\to$ energy demand $\to$ CES output $\to$ investment $\to$ capital $\to$ future output.

### 9.2 The Chicken-and-Egg Problem

To compute $A(t)$ we need $K(t)$. But $K(t)$ depends on past investment, which depends on past GDP. We only know $K$ at the base year:

$$
K(2020) = Y_{\text{SSP}}(2020) \times 3.0
$$

### 9.3 The Forward-Only Algorithm

**Step 1: Base Year $A(2020)$**

Find $A$ such that $\text{CES}(A \cdot \text{CES}_{KL}(K, L),\; E_{\text{val}}) = Y_{\text{SSP}}(2020)$:

Starting from an approximation $A_0 = Y_{\text{SSP}} / \text{CES}_{KL}(K, L)$, iterate:

$$
VA = A_n \cdot \text{CES}_{KL}(K, L)
$$

$$
Y_n = A_{\text{CES}} \cdot \text{CES}(VA,\; E_{\text{val}})
$$

$$
A_{n+1} = A_n \times \frac{Y_{\text{SSP}}}{Y_n}
$$

This converges in 1–2 iterations because energy value is a small fraction of VA.

**Step 2: Construct Reference $K$ Trajectory**

Starting from $K(2020)$, evolve forward:

$$
K_{\text{ref}}(t + \Delta t) = (1-\delta)^{\Delta t} \cdot K_{\text{ref}}(t) + I_{\text{ref}}(t) \cdot \Delta t
$$

where the reference investment is:

$$
I_{\text{ref}}(t) = \min\bigl(s \cdot Y_{\text{SSP}}(t),\;\; \text{cap\_rate} \cdot K_{\text{ref}}(t)\bigr)
$$

Note: investment is from gross SSP GDP directly — consistent with the CES approach where $I = s \times Y$.

**Step 3: Back Out $A(t)$**

At each future year, find $A(t)$ such that:

$$
A_{\text{CES}} \cdot \text{CES}\bigl(A(t) \cdot \text{CES}_{KL}(K_{\text{ref}}, L(t)),\; E_{\text{ref,val}}(t)\bigr) = Y_{\text{SSP}}(t)
$$

where $E_{\text{ref}}(t) = E_0 \cdot (Y_{\text{SSP}}(t) / Y_0)$ scales with GDP at base prices (no price shocks in reference).

Same iterative method as Step 1, converges in 1–2 iterations.

### 9.4 Worked Example (North America, SSP2)

**Base year (2020):**

$$
K(2020) = 21{,}000 \times 3.0 = 63{,}000
$$

$$
L = 370 \times 0.61 = 225.7
$$

$$
K^{\alpha} L^{1-\alpha} = 63{,}000^{0.3} \times 225.7^{0.7} = 5{,}073.6
$$

$$
E_{\text{val}} = 37.0 \times 7.5 = 277.5 \;\text{billion USD}
$$

Starting guess: $A_0 = 21{,}000 / 5{,}073.6 = 4.14$. After CES iteration, $A(2020) \approx 4.14$ (converges immediately because $E_{\text{val}} \ll VA$).

**Forward to 2025** ($Y_{\text{SSP}} = 23{,}178$):

$$
I_{\text{ref}} = \min(0.22 \times 21{,}000,\; 0.10 \times 63{,}000) = 4{,}620
$$

$$
K_{\text{ref}}(2025) = 0.7738 \times 63{,}000 + 4{,}620 \times 5 = 71{,}849
$$

$$
A(2025) \approx 4.40
$$

### 9.5 Properties of Calibrated TFP

- $A(\text{BASE\_YEAR})$ **reproduces base GDP exactly** (by construction)
- Monotonically increasing for growing GDP with constant population
- No discontinuity (single anchor at $K(2020)$, forward-only)
- Robust to all SSP scenarios
- Capital stock unchanged after calibration (no reset to historical values)

---

## 10. Capital Stock Dynamics

### 10.1 Accumulation Law

Capital evolves via the perpetual inventory method:

$$
K(t + \Delta t) = (1 - \delta)^{\Delta t} \cdot K(t) + I(t) \cdot \Delta t
$$

where:
- $\delta = 0.05$/year (annual depreciation)
- $(1 - \delta)^{\Delta t} = 0.95^5 = 0.7738$ (5-year decay factor)
- $I(t)$ = annual investment rate

### 10.2 Investment

Investment is a constant fraction of CES gross output, capped by the capital stock:

$$
I(t) = \min\bigl(s \cdot Y(t),\;\; \text{cap\_rate} \cdot K(t)\bigr) = \min\bigl(0.22 \cdot Y(t),\;\; 0.10 \cdot K(t)\bigr)
$$

The cap prevents implausibly fast capital accumulation when GDP surges.

### 10.3 Base-Year Initialization

$$
K(2020) = Y_{\text{SSP}}(2020) \times \frac{K}{Y}\bigg|_{\text{ratio}} \qquad \left(\frac{K}{Y} = 3.0\right)
$$

For North America with base-year GDP of ~\$21 trillion, $K = $ \$63 trillion.

---

## 11. Regional Labor Force Participation

Different regions have very different labor force participation (LFP) rates. Using a single global value (65%) would systematically over-estimate labor in low-participation regions and under-estimate it in high-participation ones.

GHIM uses **ILO 2020 estimates** for each R10 region:

| Region | LFP Rate |
|--------|----------|
| Africa | 0.63 |
| Asia-Pacific Developed | 0.61 |
| Eastern Asia | 0.68 |
| Eurasia | 0.59 |
| Europe | 0.58 |
| Latin America and Caribbean | 0.62 |
| Middle East | 0.51 |
| North America | 0.61 |
| South-East Asia and developing Pacific | 0.67 |
| Southern Asia | 0.50 |

**Data source disclaimer.** These values are *approximate*, derived from ILO ILOSTAT modelled estimates for 2020 (ages 15+, both sexes). ILO publishes country-level LFP, not R10-level. The R10 values were computed by population-weighted aggregation of country-level rates, mapping countries to AR6 R10 regions. This aggregation was performed manually and should be verified against official ILOSTAT bulk downloads (`indicator: EAP_DWAP_SEX_AGE_RT`, modelled estimates). The values were not provided by any external data file — they are hardcoded in `ghim/config.py:REGIONAL_LFP`.

The effect is significant: Middle East (LFP=0.51) has 22% less effective labor than the global average, which raises its calibrated TFP correspondingly.


#### Future Improvement: Region-Specific $\alpha$

Currently GHIM uses a single global $\alpha = 0.30$ for all regions. In principle, capital shares vary by country (e.g., resource-rich economies tend to have higher capital shares). One could gather country-level capital share data from the Penn World Table (variable `labsh` = labor share, so $\alpha = 1 - \text{labsh}$) and compute population- or GDP-weighted averages for each R10 region, analogous to the LFP aggregation above. This would allow capital-intensive regions (e.g., Middle East, Eurasia) to have $\alpha > 0.30$ and labor-intensive regions (e.g., Southern Asia) to have $\alpha < 0.30$. This is not yet implemented.

---

## 12. KLEM-Sector Coupling

### 12.1 How Sectoral Demands Are Determined

Each demand sector (transport, buildings, industry) independently computes its energy demand through a two-step process:

**Step 1: Total sector demand scales with GDP.**

$$
D_{\text{sector}}(t) = D_{\text{sector,0}} \times \left(\frac{GDP(t)}{GDP_0}\right)^{\eta_{\text{sector}}}
$$

where $\eta$ is the sector's income elasticity (transport ~0.7, buildings ~0.5, industry ~0.6). Richer economies demand more energy services, but with diminishing intensity.

**Where is the price effect?** The price response enters in Step 2, not Step 1. Total sector demand is driven by income (GDP), but the *fuel mix within* each sector responds to prices via the preference-factor logit: when electricity gets cheaper, the electricity share rises and the gas share falls. Additionally, the macro CES scaling factor $\lambda$ (§12.3) implicitly transmits the aggregate price effect — when the composite energy price rises, $E_{\text{KLEM}}$ falls (via the CES FOC), so $\lambda < 1$, uniformly scaling down all sector demands. This two-tier design separates the income-driven *composition* effect (bottom-up sectors) from the price-driven *level* effect (top-down CES).

**Step 2: Fuel allocation within each sector via nested logit trees.**

Each sector has a hierarchical structure:
- **Structural level** (e.g., passenger vs freight in transport, heavy vs light in industry): slow economic shifts, simple share-blending turnover
- **Carrier level** (electricity, gas, coal, refined liquids, hydrogen, biomass): physical capital stock, vintage S-curve retirement with `retire_and_invest()` determining new investment shares

The preference-factor logit ($s_i = \alpha_i \cdot \exp(-k \cdot P_i) \cdot C_i^{\beta} / \Sigma$) allocates demand across carriers based on delivered cost and calibrated preferences.

**Result**: each sector produces a dictionary `{carrier: demand_EJ}` independently — without any knowledge of the macro CES constraint.

#### Does the Iteration Loop Make Everything Consistent?

**Yes.** The price iteration loop (§13.1, step 3) ensures that energy consumption, energy prices, and GDP ($Y$) are mutually consistent at convergence. Each iteration:
1. CES determines total energy demand $E$ at the current composite price
2. Sector demands are scaled to match $E$ and fed to supply modules
3. Supply modules return updated electricity/hydrogen/refining prices
4. The composite price is recomputed → feeds back to step 1

This converges in 3–5 iterations (with 50% damping) because energy is a small share of GDP, so the feedback is weak.

**Why sequential (Gauss-Seidel) rather than simultaneous (Newton)?** The sequential approach is chosen for simplicity and robustness:
- A Newton solver would require computing Jacobians ($\partial \text{supply} / \partial \text{price}$) for all sectors simultaneously — complex to implement and maintain given the discrete logit + vintage stock structures
- The sequential loop is easy to debug, each step has clear economic interpretation, and it converges quickly because the energy-GDP feedback is modest ($E_{\text{val}}/Y \approx 1\text{--}3\%$)
- GCAM uses a similar approach (Broyden solver on supply-demand gaps, but conceptually the same iterative structure)
- For a model with 10 regions and 6 carriers, the computational cost is negligible — Newton would save microseconds per period

If convergence became problematic (e.g., at very high carbon prices), one could switch to a Broyden quasi-Newton method, which builds an approximate Jacobian from successive iterations without explicit derivative computation.

### 12.2 The Gap Between Macro and Sector Totals

The CES energy demand equation (Section 6) determines **total** energy demand from macro variables (VA, composite price, $\sigma_{KLE}$). The sectors determine **relative** energy demands from income elasticities and fuel switching. These two totals won't generally match:

$$
E_{\text{KLEM}} \neq \sum_{\text{sector}} E_{\text{sector}}
$$

**Units**: both $E_{\text{KLEM}}$ and $E_{\text{sector}}$ are measured in **physical units (EJ)**, not value. The CES demand equation (§6.2) produces $E$ in EJ; sector models also produce demands in EJ. Scaling in physical units preserves the fuel mix directly.

**Why not use sectoral price indices instead?** An alternative approach would be to compute a separate CES for each sector with sector-specific energy prices, so that sectoral demands automatically sum to the macro total. This is what full CGE models (like GCAM) do — each sector has its own nested CES demand system. We use the simpler uniform-scaling approach because:

1. **The bottom-up sector models already have rich fuel-switching logic** (preference logit + vintage stock). Adding a per-sector CES on top would create two competing substitution mechanisms.
2. **The macro CES captures the aggregate energy-GDP feedback** — the key relationship we need for policy analysis. Sector composition is driven by the logit trees.
3. **Uniform scaling is exact at the base year** ($\lambda = 1.0$) and deviates only when macro CES and sector income elasticities disagree — typically $\lambda \in [0.85, 1.15]$.

In short: the macro CES answers "how much total energy does the economy need?" and the sector models answer "how is that energy distributed across fuels?" The scaling factor $\lambda$ reconciles the two.

### 12.3 The Solution: Uniform Scaling

The CES total determines the **level**, sector demands determine the **composition**:

$$
\lambda = \frac{E_{\text{KLEM}}}{\sum_s E_s^{\text{raw}}} \qquad \implies \qquad E_s^{\text{scaled}} = \lambda \cdot E_s^{\text{raw}}
$$

This preserves the relative fuel mix from the bottom-up sector models while enforcing macro-level consistency from the CES production function. The scaling factor $\lambda$ is typically close to 1.0 and varies smoothly — there is no clamping, because the CES naturally constrains the aggregate.

---

## 13. Solver Integration

### 13.1 Period Solution Flow

For each region in each period:

1. **Set TFP** from pre-computed trajectory
2. **Compute value added**: $VA = A \cdot K^{\alpha} \cdot L^{1-\alpha}$
3. **Price iteration loop** (up to 100 iterations):
   a. Compute CES energy demand: $E = E_0 \cdot (VA/VA_0) \cdot (P_E/P_{E,0})^{-\sigma}$
   b. Apply AEEI factor
   c. Compute CES gross output: $Y = \text{CES}(VA, E_{\text{val}})$
   d. Compute raw sector demands (income-driven, from logit trees)
   e. Scale sector demands to match CES total (natural coupling)
   f. Solve electricity supply (8-tech preference logit + vintage stock + learning)
   g. Solve refining supply
   h. Solve hydrogen supply
   i. Update electricity, refined liquids, hydrogen prices
   j. Update composite energy price (expenditure-weighted)
   k. Check convergence (relative price change $< 0.001$)
   l. Damped update (50% damping on new prices)
4. **Compute investment**: $I = s \times Y$ (from CES gross output)
5. **Compute emissions** (electricity + refining + hydrogen + direct combustion)
6. **Revenue recycling** (if carbon pricing active, diagnostic only)
7. **Update capital** for next period

### 13.2 Key Difference from Cost Feedback Approach

In the old approach, investment came from "net output" ($Y - \text{EnergyCost}$). Now investment comes directly from CES gross output ($Y$). Energy's effect on investment is captured through the CES production function: when energy falls due to high prices, CES output $Y$ is lower, so investment is lower.

### 13.3 Revenue Recycling

If carbon pricing is active, carbon tax revenue is computed as a diagnostic:

$$
\text{Revenue} = \tau_{\text{carbon}} \times \frac{\text{Emissions}_{\text{MtCO}_2}}{1000} \times f_{\text{recycle}}
$$

In the CES approach, this revenue is reported but does not directly affect investment (which comes from gross output). The carbon price's effect on the economy flows through: carbon price $\to$ higher fuel prices $\to$ higher composite price $\to$ lower energy demand $\to$ lower CES output.

### 13.4 Full Model Run

```python
for year in [2020, 2025, 2030, ..., 2150]:   # SOLVE_YEARS
    if trade_enabled:
        clear_global_fuel_markets()  # bisection on coal, oil, gas
    for region in R10_REGIONS:
        solve_period(region, year, trade_prices=...)
```

Historical years (2000–2015) are not solved — they contain calibration data (GCAM convention).

---

### 13.5 Composite Energy Price Calculation

The composite energy price $P_E$ used in the CES demand equation is an **expenditure-weighted average across 6 final-energy carriers**:

$$
P_E = \frac{\sum_{c \in \mathcal{C}} P_c \times D_c}{\sum_{c \in \mathcal{C}} D_c}
$$

where $\mathcal{C}$ = {coal, refined liquids, gas, electricity, biomass, hydrogen} (defined in `ghim/energy/demand.py:ENERGY_CARRIERS`).

These are **carrier-level** (final energy) prices, not technology-level or sector-level:
- **Coal, gas, biomass**: exogenous base prices (or trade-determined world prices + transport costs)
- **Refined liquids**: output of the refining module (oil feedstock cost + refining margin)
- **Electricity**: weighted-average LCOE across 8 generation technologies (coal, gas_cc, nuclear, hydro, wind, solar, biomass, oil)
- **Hydrogen**: weighted-average cost across production technologies (SMR, electrolysis)

The weights $D_c$ are the **total demand** (EJ) for each carrier, summed across all demand sectors. This means carriers with larger physical consumption have proportionally more influence on the composite price.

The composite price is recalculated at each iteration within the price loop (§13.1, step j), so it converges jointly with the supply-side prices.

**Implementation**: `KLEMDriver.composite_energy_price()` in `ghim/econ/klem.py:285`.

---

## 14. Trade Integration

The trade module affects the KLEM driver through **delivered fuel prices**:

1. The trade module estimates regional fuel demands
2. Global market clearing via bisection determines world prices for coal, oil, gas
3. Regional delivered prices = world price + transport cost
4. `solve_period()` receives these delivered prices, which enter the composite price calculation

The CES energy demand responds to trade-determined prices with $\sigma_{KLE}$:

$$
P_{\text{oil}}^{\text{world}} \uparrow \;\implies\; P_E \uparrow \;\implies\; E \downarrow \;\implies\; Y \downarrow \;\implies\; D_{\text{oil}} \downarrow \;\implies\; P_{\text{oil}}^{\text{world}} \downarrow \;\text{(clearing)}
$$

---

## 15. Why Full CES and Not Cost Feedback?

### 15.1 Historical Context

An earlier version of GHIM used:
- $Y = VA$ (value added only)
- $Y_{\text{net}} = VA - \text{EnergyCost}$
- $I = s \times Y_{\text{net}}$

Energy affected the economy only through cost subtraction — not through the production function itself.

### 15.2 Problems with Cost Feedback

**Problem 1: Naming confusion.** "Value Added" in economics means output *net* of intermediate inputs. Using $Y = VA$ while separately subtracting energy cost means energy is not actually netted from VA — the naming is misleading.

**Problem 2: TFP calibration inconsistency.** TFP was calibrated so that $VA = GDP_{\text{SSP}}$ (gross). But investment used $Y_{\text{net}} = VA - \text{EnergyCost}$ (net). At the base year, the reference capital trajectory uses one measure of output while the solver uses a different one.

**Problem 3: High carbon prices.** At $300/tCO2, energy cost shares can reach 10–15% of GDP in coal-heavy regions. The "small share" assumption that justifies treating energy as a simple cost subtraction breaks down. Net output can fall dramatically, causing model instability.

### 15.3 How Full CES Resolves These

- **Energy is in the production function**: $Y = \text{CES}(VA, E_{\text{val}})$ — no separate subtraction
- **No double-counting**: $I = s \times Y$ directly. Energy reduces $Y$ through lower $E_{\text{val}}$.
- **Consistent TFP**: Calibrate TFP so $\text{CES}(VA, E_{\text{val}}) = GDP_{\text{SSP}}$. Same measure used for investment.
- **Robust at high prices**: CES is well-behaved even when energy value drops significantly
- **The demand equation is identical**: The CES FOC gives the same energy demand formula in both approaches

---

## 16. Parameters Reference

| Parameter | Symbol | Default | Source |
|-----------|--------|---------|--------|
| Capital share | $\alpha$ | 0.30 | Gollin (2002), PWT `labsh` |
| K-L substitution | $\sigma_{KL}$ | 0.8 | Oberfield & Raval (2021) |
| VA-Energy substitution | $\sigma_{KLE}$ | 0.4 | van der Werf (2008) |
| Savings rate | $s$ | 0.22 | PWT `csh_i`, Mankiw et al. (1992) |
| Depreciation rate | $\delta$ | 0.05/yr | PWT `delta`, standard |
| Investment cap | cap\_rate | 0.10 | Prevents >10%/yr capital growth |
| Capital-output ratio | $K/Y$ | 3.0 | PWT `ck` / `rgdpo` |
| Min energy cost share | — | 0.05 | Floor for calibration stability |
| Timestep | $\Delta t$ | 5 years | GCAM convention |
| Price damping | — | 0.5 | Solver stability |
| Price tolerance | — | 0.001 | Convergence criterion |
| Max price iterations | — | 100 | Safety bound |

### 16.1 Literature for Each Parameter

#### Capital share $\alpha = 0.30$

The capital share is one of the most studied parameters in macroeconomics.

| Study | Estimate | Method | Notes |
|-------|----------|--------|-------|
| Gollin (2002, *JME*) | 0.20–0.35, median 0.30 | National accounts, 36 countries | Corrects for self-employment income attribution |
| Karabarbounis & Neiman (2014, *QJE*) | ~0.30 (1980), ~0.38 (2010) | Corporate sector, 59 countries | Documents declining labor share |
| Penn World Table 10.01 | `labsh` variable | Income approach | Cross-country median $1 - \text{labsh} \approx 0.30$ |
| Mankiw, Romer & Weil (1992, *QJE*) | 0.33 | Solow model calibration | "Textbook" augmented Solow |

GHIM uses 0.30 globally. In principle, $\alpha$ varies by country (resource-rich economies like Saudi Arabia have $\alpha > 0.40$; labor-intensive LICs have $\alpha \approx 0.20$). Region-specific values from PWT `labsh` could be implemented (see §11).

#### K-L substitution elasticity $\sigma_{KL} = 0.8$

| Study | Estimate | Method | Notes |
|-------|----------|--------|-------|
| **Oberfield & Raval (2021, *JPE*)** | **0.7** (aggregate US manufacturing) | Firm-level production function estimation | Micro-founded, most cited recent estimate |
| Chirinko (2008, *NBER Macro Annual*) | 0.4–0.6 | Survey of 30+ studies | "Best guess" from pooling diverse methods |
| Antràs (2004, *REStat*) | 0.8–1.0 | Aggregate US time series (1948–1998) | Higher due to aggregation bias |
| Karabarbounis & Neiman (2014, *QJE*) | ~1.25 | Corporate sector, cross-country | Identified from investment price decline |
| Knoblach et al. (2020, *OEP*) | 0.45–0.87 (meta-analysis) | 121 studies, 3,186 estimates | Preferred range after correcting for publication bias |

**Our choice: 0.8.** This is near the upper end of micro estimates (Chirinko's range) and consistent with Antràs's time-series result. It is conservative relative to the strong complementarity (0.4–0.6) found in plant-level data, reflecting that aggregate substitution includes between-sector reallocation that raises the effective elasticity.

#### VA-Energy substitution elasticity $\sigma_{KLE} = 0.4$

| Study | Estimate | Method | Notes |
|-------|----------|--------|-------|
| **van der Werf (2008, *Resource and Energy Economics*)** | 0.17–0.61, median ~0.4 | Cross-country panel, nested CES | Specifically estimates VA-E nest |
| Koesler & Schymura (2015, *Energy Economics*) | 0.2–0.5 | CGE model calibration | Tests different nesting structures |
| Berndt & Wood (1975, *REStat*) | 0.36 | US manufacturing time series | Foundational K-L-E study |
| GCAM documentation | ~0.35 | Model calibration | Applied in GCAM's macro module |
| WITCH model | 0.3–0.5 | Model calibration | Energy-economy coupling |
| Hassler et al. (2021, *ARE*) | 0.02–0.05 (short-run), ~0.4 (long-run) | Structural model | Emphasizes SR/LR distinction |

**Our choice: 0.4.** Central estimate from van der Werf (2008), consistent with long-run GCAM/WITCH calibrations. This is a *long-run* elasticity appropriate for our 5-year timestep and 130-year horizon. Short-run substitution is much harder (Hassler et al. estimate ~0.04), but our model's 5-year periods implicitly allow capital stock adjustment.

#### Savings rate $s = 0.22$

| Study | Estimate | Method | Notes |
|-------|----------|--------|-------|
| Mankiw, Romer & Weil (1992, *QJE*) | 0.05–0.35, mean ~0.22 | Cross-country Solow calibration | 98 non-oil countries |
| Penn World Table 10.01 | `csh_i` variable | Investment / GDP at constant prices | OECD median ~0.22, range 0.10–0.40 |
| Solow (1956) | treated as parameter | Theoretical | Growth model foundation |

**Our choice: 0.22.** The cross-country average from MRW (1992). In principle, $s$ varies by region (East Asia ~0.35, Sub-Saharan Africa ~0.12). A future extension could use PWT `csh_i` values by region.

#### Depreciation rate $\delta = 0.05$/yr

| Study | Estimate | Method | Notes |
|-------|----------|--------|-------|
| Penn World Table 10.01 | `delta` variable | Perpetual inventory method | Median ~0.04–0.06 |
| BEA Fixed Asset Tables | 0.05–0.06 | Survey-based service lives | US economy |
| Mankiw, Romer & Weil (1992) | 0.03 + 0.02 = 0.05 | $\delta$ + technical progress | "Standard assumption" |

**Our choice: 0.05.** The textbook value. Structure depreciation is lower (~3%); equipment is higher (~8–12%); aggregate averages to ~5%.

#### Capital-output ratio $K/Y = 3.0$

| Study | Estimate | Method | Notes |
|-------|----------|--------|-------|
| Penn World Table 10.01 | `ck` / `rgdpo` | Perpetual inventory | OECD range 2.5–4.0, median ~3.0 |
| IMF WEO | ~3.0 (advanced), ~2.5 (emerging) | National accounts | Varies by development level |
| Piketty & Zucman (2014, *QJE*) | 4.0–6.0 | Wealth-to-income (includes housing) | Higher because includes non-productive wealth |

**Our choice: 3.0.** Standard Solow calibration for *productive* capital (excludes housing). PWT `ck` at constant national prices gives OECD median ~3.0.

---

## 17. Numerical Example

### 17.1 Base Year (North America, 2020)

**Inputs:**
- $Y_{\text{SSP}} = 21{,}000$ billion USD (PPP)
- Population $= 370$ million
- LFP $= 0.61$ (North America)
- Total final energy $= 37.0$ EJ
- Composite energy price $= 7.5$ \$/GJ

**Capital stock:**

$$K = 21{,}000 \times 3.0 = 63{,}000 \text{ billion USD}$$

**Labor:**

$$L = 370 \times 0.61 = 225.7 \text{ million}$$

**TFP (calibrated via CES iteration):**

$$\text{CES}_{KL}(K, L;\; \sigma_{KL}=0.8) \text{ calibrated with } r = 0.3 \times 21{,}000 / 63{,}000 = 0.10, \quad w = 0.7 \times 21{,}000 / 225.7 = 65.1$$

$$A \text{ calibrated iteratively so that } A_{\text{CES}} \cdot \text{CES}(A \cdot \text{CES}_{KL}, E_{\text{val}}) = 21{,}000$$

**Value Added:**

$$VA = A \times \text{CES}_{KL}(63{,}000,\; 225.7) \approx 21{,}005 \text{ billion USD}$$

**Energy value:**

$$E_{\text{val}} = 37.0 \times 7.5 = 277.5 \text{ billion USD}$$

**CES gross output:**

$$Y = A_{\text{CES}} \cdot \text{CES}(21{,}005,\; 277.5;\; 0.4) = 21{,}000 \quad \checkmark$$

(The scale factor $A_{\text{CES}}$ is calibrated to ensure this.)

**CES Energy Demand (at base prices):**

$$E = 37.0 \times \frac{21{,}000}{21{,}000} \times \left(\frac{7.5}{7.5}\right)^{-0.4} = 37.0 \text{ EJ} \quad \checkmark$$

### 17.2 Carbon Tax Scenario (\$50/tCO2)

Suppose a carbon tax raises the composite energy price from 7.5 to 12.0 \$/GJ:

**Energy demand:**

$$E = 37.0 \times 1.0 \times \left(\frac{12.0}{7.5}\right)^{-0.4} = 37.0 \times 0.829 = 30.7 \text{ EJ}$$

(Verification: $(1.6)^{-0.4} = e^{-0.4 \ln 1.6} = e^{-0.188} = 0.829$.)

**Energy value (with reduced energy):**

$$E_{\text{val}} = 30.7 \times 7.5 = 230.3 \text{ billion USD}$$

(Note: we use $P_{E,0} = 7.5$ for $E_{\text{val}}$, not the current price.)

**CES gross output:**

$$Y = \text{CES}(21{,}005,\; 230.3;\; 0.4) \approx 20{,}800 \text{ billion USD}$$

A ~1% GDP reduction from the energy effect in the production function.

**Investment:**

$$I = \min(0.22 \times 20{,}800,\; 0.10 \times 63{,}000) = \min(4{,}576,\; 6{,}300) = 4{,}576$$

Lower than reference ($4{,}620$), so capital accumulates slower $\to$ future GDP diverges further from SSP.

**Energy cost share (diagnostic):**

$$\text{cost\_share} = \frac{12.0 \times 30.7}{20{,}800} = \frac{368.4}{20{,}800} = 1.8\%$$

---

## 18. Comparison with GCAM

GHIM's CES-KLE approach is modeled on GCAM's macro-energy coupling:

| Feature | GHIM | GCAM |
|---------|------|------|
| Production function | CES(VA, E_val) | CES(VA, E_val) |
| Energy value conversion | E × P_E_base | E × P_E_base |
| VA-E substitution | σ_KLE = 0.4 | ~0.35 |
| K-L inner nest | CES (σ_KL = 0.8) | CES (σ<1) |
| Investment | I = s × Y | General equilibrium |
| Equilibrium type | Partial (energy only) | General (all markets) |
| Regions | 10 (AR6 R10) | 32 |

Key similarity: both convert energy to value terms using base-year prices, calibrate CES share parameters, and derive energy demand from the FOC.

Key difference: GCAM is a full general equilibrium model where all prices (including wages and capital returns) are endogenous. GHIM is partial equilibrium — energy prices are endogenous but labor and capital markets use fixed parameters (savings rate, capital-output ratio).

---

## 19. Known Limitations

1. **Zero population fallback** — If a region has zero population, TFP defaults to a fallback value rather than handling it gracefully (`klem.py:80`).

2. **Price iteration non-convergence** — If the price iteration loop doesn't converge within 100 iterations, the solver silently continues with the last prices. No warning is emitted.

3. **Approximate energy data** — Base-year energy values are approximate IEA 2020 values, not sourced from an actual IEA database extract.

4. **LFP is time-invariant** — Regional labor force participation rates are fixed at 2020 values. In reality, LFP changes with economic development.

5. **Unitary aggregate income elasticity** — The CES FOC assumes $E$ grows proportionally with $VA$ at the aggregate level. Sector-specific elasticities handle the composition effect.

6. **Revenue recycling not in CES loop** — Carbon tax revenue is computed as a diagnostic but doesn't directly reduce energy costs for the CES calculation (unlike the old net-output approach).

---

## 20. Data Sources

| Data | Source | Path |
|------|--------|------|
| Population | SSP Database 2024 | `ghim/data/external/ssp/SSP_database_2024.csv.gz` |
| GDP (PPP) | SSP Database 2024 | same |
| Historical data | "Historical Reference" scenario | same |
| Region mapping | AR6 R10 classification | `ghim/data/external/region_classification.tsv` |
| Base-year energy | Approximate IEA 2020 | `ghim/data/energy_cal.py` |
| Labor force participation | ILO 2020 estimates | Hardcoded in `ghim/config.py` |
