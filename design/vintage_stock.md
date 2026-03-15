# GHIM Energy Module — Vintage Stock Design

## 1. Overview

Vintage stock tracks installed capacity by technology/carrier and installation year. Equipment retires gradually via an S-curve. New investment fills the gap between target capacity (from logit/powertrain shares) and surviving stock. This provides **hard inertia** — physically installed equipment constrains the speed of technology transition regardless of cost signals.

All sectors except Agriculture use vintage stock. Agriculture uses preference-factor decay (soft inertia) only.


## 2. Sectors with Vintage

| Sector | Vintage level | # Entries per region |
|--------|--------------|---------------------|
| Electricity | Technology (17) | 17 × ~16 vintages |
| Hydrogen Production | Technology (7) | 7 × ~16 vintages |
| Transport Passenger | Powertrain (6) | 6 × ~16 vintages |
| Transport Freight | Powertrain (5) | 5 × ~16 vintages |
| Bunkers Aviation | Powertrain (2) | 2 × ~16 vintages |
| Bunkers Shipping | Powertrain (2) | 2 × ~16 vintages |
| Industry EU | Carrier (7) | 7 × ~16 vintages |
| Industry FS | Carrier (5) | 5 × ~16 vintages |
| Buildings Res | End-use × Carrier (3 × 8) | ~20 × ~16 vintages |
| Buildings Com | End-use × Carrier (3 × 8) | ~20 × ~16 vintages |

Buildings: 8 carriers (Electricity, Gas, Coal, Refined Oil, Solid Biomass, Biofuels, Hydrogen, Heat), but not all end-use × carrier combinations are active (e.g., Heat only for Heating, Coal not for Cooling). Effective count ~20 per subsector.

Total: ~100 entries per region × ~16 vintages × 32 regions = ~51,200 bins. Computationally trivial.


## 3. Retirement

### 3.1 S-curve retirement

Fraction of vintage surviving at age $a$:

$$S(a) = \frac{1 / (1 + \exp(k \cdot (a - \rho \cdot L)))}{S(0)}$$

Normalized so $S(0) = 1.0$. Hard cutoff at lifetime $L$: $S(a) = 0$ for $a \geq L$.

| Parameter | Value | Meaning |
|-----------|-------|---------|
| $k$ | 0.1 | Steepness of retirement curve |
| $\rho$ | 0.75 | Half-life ratio (midpoint of retirement = 75% of lifetime) |
| $L$ | Technology-specific | Maximum lifetime (hard cutoff) |

### 3.2 Retirement profiles

**Gradual S-curve** (default): Equipment fails stochastically. Some units retire early, most near the expected lifetime, none survive past $L$. Used for thermal plants, boilers, industrial equipment.

**Hard cutoff only** (no gradual): All capacity survives until age $L$, then retires completely. Used for technologies where the equipment doesn't degrade (solar panels, wind turbines, batteries, electrolyzers). Retirement is driven by warranty/contract expiry, not failure.

```
S-curve (thermal plant, L=40):       Hard cutoff (solar PV, L=25):
1.0 ┤████████████████████████▓▓░░       1.0 ┤█████████████████████████
    │                        ▓▓░░           │                         │
0.5 ┤                          ▓▓░      0.5 ┤                         │
    │                            ▓░         │                         │
0.0 ┤                             ░      0.0 ┤                         └──
    0          30        40 years            0              25 years
```


## 4. Lifetimes

### 4.1 Electricity generation

| Technology | Lifetime $L$ (years) | Retirement type |
|-----------|---------------------|-----------------|
| Coal | 60 | S-curve |
| Coal CCS | 60 | S-curve |
| Gas CC | 45 | S-curve |
| Gas CCS | 45 | S-curve |
| Oil | 45 | S-curve |
| Biomass | 60 | S-curve |
| Biomass CCS | 60 | S-curve |
| Nuclear | 60 | S-curve |
| Hydro | 80 | S-curve |
| Solar PV | 30 | Hard cutoff |
| Solar CSP | 30 | Hard cutoff |
| Wind Onshore | 30 | Hard cutoff |
| Wind Offshore | 25 | Hard cutoff |
| Geothermal | 30 | S-curve |
| Ocean | 30 | Hard cutoff |
| Hydrogen (turbine) | 30 | S-curve |
| Ammonia (turbine) | 30 | S-curve |

### 4.2 Hydrogen production

| Technology | Lifetime (years) | Retirement type |
|-----------|-----------------|-----------------|
| SMR | 30 | S-curve |
| SMR CCS | 30 | S-curve |
| Coal Gasification | 35 | S-curve |
| Coal Gasification CCS | 35 | S-curve |
| Electrolysis | 20 | Hard cutoff |
| Biomass Gasification | 30 | S-curve |
| Biomass Gasification CCS | 30 | S-curve |

### 4.3 Transport powertrains

| Powertrain | Lifetime (years) | Retirement type |
|-----------|-----------------|-----------------|
| ICE | 15 | S-curve |
| Bio-ICE | 15 | S-curve |
| HEV | 15 | S-curve |
| BEV | 15 | Hard cutoff (battery warranty) |
| FCEV | 15 | Hard cutoff |
| NG | 15 | S-curve |
| Diesel | 18 | S-curve |
| Biodiesel | 18 | S-curve |
| Electric Truck | 18 | Hard cutoff |
| FCEV Truck | 18 | Hard cutoff |
| NG Truck | 18 | S-curve |

Bunkers:

| Powertrain | Lifetime (years) | Retirement type |
|-----------|-----------------|-----------------|
| Jet | 25 | S-curve |
| SAF | 25 | S-curve |
| Marine | 30 | S-curve |
| LNG | 30 | S-curve |

### 4.4 Industry

| Carrier | EU Lifetime (years) | FS Lifetime (years) |
|---------|--------------------|--------------------|
| Electricity | 25 | — |
| Gas | 30 | 30 |
| Coal | 40 | 40 |
| Refined Oil | 25 | 25 |
| Solid Biomass | 25 | 25 |
| Biofuels | 25 | — |
| Hydrogen | 20 | 20 |

All S-curve retirement. Industry equipment is long-lived (blast furnaces 40+ years, gas boilers 30 years). This creates strong lock-in.

### 4.5 Buildings

| End-use | Equipment | Lifetime (years) |
|---------|-----------|-----------------|
| Heating | Gas boiler | 20 |
| Heating | Heat pump | 18 |
| Heating | Coal stove | 25 |
| Heating | Oil boiler | 20 |
| Heating | Biomass stove | 15 |
| Heating | Biofuel boiler | 20 |
| Heating | H₂ boiler | 20 |
| Heating | District heat connection | 30 |
| Cooling | AC / heat pump | 15 |
| Other | Appliances | 12 |
| Other | Cooking (gas) | 15 |
| Other | Cooking (biomass) | 10 |

All S-curve retirement. Cooling is shorter-lived than heating equipment.

For simplicity, Phase 1 uses a **single lifetime per end-use** (not per carrier):

| End-use | Uniform lifetime |
|---------|-----------------|
| Heating | 20 years |
| Cooling | 15 years |
| Other | 12 years |


## 5. Effective Capacity and Gap-Filling

### 5.1 Effective surviving capacity

Capacity at vintage $v$ survives only if the plant is both young enough **AND** profitable enough:

$$Q_{eff}(t) = \sum_v C_{i,v} \cdot S(t - v) \cdot P(\pi_{i,v})$$

Two independent mechanisms reduce capacity:
1. **Physical retirement** $S(age)$: age-driven, irreversible
2. **Economic shutdown** $P(\pi)$: price-driven, reversible if prices recover

### 5.2 Gap-filling logic

Each period, compute:

1. **Target capacity** = logit share × total demand
2. **Surviving capacity** = $Q_{eff}$ (after physical retirement + economic shutdown)
3. **Under construction** = capacity committed in pipeline but not yet delivered (§6)
4. **Gap** = target − surviving − under_construction

```python
def retire_and_invest(target_shares, total_demand, prices, period):
    for tech in technologies:
        target = target_shares[tech] * total_demand

        # Physical retirement + economic shutdown
        surviving = 0.0
        for yr in vintage[tech]:
            physical = vintage[tech][yr] * S(period - yr)
            profit = compute_profit(tech, prices)
            operating = physical * P_shutdown(profit)
            surviving += operating

        # Subtract capacity under construction (not yet delivered)
        under_construction = sum(pipeline[tech].get(yr, 0)
                                 for yr in range(period + TIMESTEP, period + max_build * TIMESTEP + 1, TIMESTEP))

        gap = target - surviving - under_construction
        if gap > 0:
            if tech in PIPELINE_TECHS:
                pipeline_invest(tech, gap, period)   # delayed delivery
            else:
                vintage[tech][period] = gap           # immediate
        else:
            # Overcapacity: scale down all vintages proportionally
            scale = target / surviving if surviving > 0 else 0
            for yr in vintage[tech]:
                vintage[tech][yr] *= scale
```

### 5.3 Overcapacity handling

When surviving capacity exceeds target (demand shrinks or technology loses share):
- Scale down all vintages proportionally (demand-shrink scaling)
- Additionally, profit-shutdown retires unprofitable capacity early

### 5.4 Profit-based shutdown

Surviving capacity can shut down **early** when operating becomes unprofitable. This is modeled as an additional survival factor applied after S-curve physical retirement.

#### Profit rate

For each technology/carrier, the profit rate measures whether revenue covers variable costs:

$$\pi_i = \frac{p_{output} - c_{var,i}}{|c_{var,i}|}$$

**Supply technologies (electricity, hydrogen):**

$$c_{var,i} = \frac{fuel_i}{eff_i} + \frac{coef_i \times (1 - capture_i) \times p_{carbon}}{eff_i} + VOM_i$$

$$\pi_i = \frac{p_{elec} - c_{var,i}}{|c_{var,i}|}$$

**Demand-side equipment (industry, buildings, transport):**

$$\pi_i = \frac{P_{service} - C_i / eff_i}{|C_i / eff_i|}$$

where $C_i / eff_i$ is the cost per unit of service from carrier/powertrain $i$, and $P_{service}$ is the average service price across all carriers/powertrains.

- $\pi > 0$: profitable (revenue exceeds variable cost)
- $\pi = 0$: breakeven
- $\pi < 0$: unprofitable (variable cost exceeds revenue)

Note: capex is sunk — shutdown depends only on variable cost vs revenue. A plant with high capex but low fuel cost stays open; a plant with zero capex but high fuel cost shuts down.

#### Shutdown probability

Smooth S-curve in profitability:

$$P(\pi_i) = \frac{1}{1 + \exp(-n \cdot (\pi_i - m))}$$

| Parameter | Value | Meaning |
|-----------|-------|---------|
| $P(\pi)$ | [0, 1] | Fraction of capacity that continues operating |
| $m$ | −0.1 | Median (50% shutdown point) |
| $n$ | 6 | Steepness (higher = sharper shutdown threshold) |

Behavior:
- $\pi \gg 0$: $P \approx 1$ (profitable → stays open)
- $\pi = m = -0.1$: $P = 0.5$ (slightly unprofitable → 50% operate)
- $\pi \ll 0$: $P \approx 0$ (deep loss → shuts down)

The median at $m = -0.1$ means plants tolerate up to ~10% loss ratio before the majority shut down. This is realistic — plants may run at a small loss temporarily for contractual obligations, minimum generation requirements, or restart avoidance.

```
P(π):
1.0 ┤                         ████████    Profitable
    │                      ███              (most capacity runs)
0.5 ┤                   █                ← m = −0.1
    │                ███                    Marginal
0.0 ┤████████████████                      Uneconomic
    ────────────────┼────────────────── π   (capacity shuts down)
              -0.4  -0.1   0   +0.4
```

#### Shutdown by sector

| Sector | Shutdown applies to | Key trigger |
|--------|-------------------|-------------|
| Electricity | Coal, Gas, Oil plants | Carbon price → $c_{var} > p_{elec}$ |
| Hydrogen | SMR, Coal Gasification | Carbon price → $c_{var} > p_{H2}$ |
| Transport | ICE, Diesel, NG vehicles | Fuel tax / carbon price → $C/eff > P_{service}$ |
| Industry | Coal, Gas equipment | Carbon price → carrier too expensive |
| Buildings | Coal stoves, oil boilers | Carbon price + carrier price rise |

Technologies with zero fuel cost (solar, wind, BEV) have $\pi \approx +\infty$ always — they never shut down on profitability. Only fuel-burning technologies face shutdown risk.

#### Reversibility

Unlike physical retirement (permanent), shutdown is **reversible**. If prices change:
- Gas plant shuts down when carbon price = $100/tCO₂
- Carbon price drops to $50 → gas plant profit turns positive → resumes operation

In the model, this happens automatically: $P(\pi)$ is recomputed each period from current prices. Shut-down capacity isn't destroyed — it's idle. If $P$ rises again, the capacity returns.

Implementation: store raw vintage capacity separately from operating capacity. Each period: $operating = raw \times S(age) \times P(\pi)$.

### 5.5 New investment output

New investment feeds into:
- **Learning curves**: cumulative deployment → capex decline
- **Budget constraint**: $I_{energy} = \sum new\_cap \times capex$
- **IAMC reporting**: `Capacity Additions|*` and `Investment|*`


## 6. Construction Pipeline

Some technologies have multi-period construction delays:

| Technology | Construction time | Periods | Mechanism |
|-----------|------------------|---------|-----------|
| Nuclear | 10 years | 2 periods | PipelineAwareVintageStock |
| Hydro | 5 years | 1 period | PipelineAwareVintageStock |
| All others | Immediate | 0 | Standard VintageStock |

### 6.1 Gap-filling with pipeline

Gap-filling subtracts under-construction capacity to avoid over-ordering:

$$gap = target - surviving - under\_construction$$

Under-construction capacity is tracked by expected delivery year. It does NOT count toward surviving stock until delivery.

### 6.2 Phase 1: Simple pipeline

Logit decision at period $t$ → capacity arrives after construction delay. No partial delivery, no cancellation. Just a delay queue.

```python
CONSTRUCTION_DELAY = {"nuclear": 2, "hydro": 1}  # periods

def pipeline_invest(tech, gap, period):
    delay = CONSTRUCTION_DELAY.get(tech, 0)
    if delay > 0:
        delivery = period + delay * TIMESTEP
        pipeline[tech][delivery] += gap
    else:
        vintage[tech][period] = gap
```

During the construction wait, the capacity gap is filled by other technologies (gas, solar, wind).

### 6.3 Interest During Construction (IDC)

Capital tied up during construction earns no return. The effective capital cost increases:

$$K_{eff} = K_0 \times (1 + r)^{T_{build}}$$

| Technology | $T_{build}$ | $r$ | IDC multiplier |
|-----------|------------|-----|---------------|
| Nuclear | 10 yr | 8% | 2.16× |
| Hydro | 5 yr | 8% | 1.47× |

IDC naturally discourages long-build technologies in the logit — their effective capex is higher. **Phase 2+**: IDC applied to LCOE/LCOH calculation. Phase 1: simplified (capex charged at delivery without IDC markup).

### 6.4 Pipeline pre-population

Reactors and dams currently under construction are pre-populated from WNA/GEM data with expected delivery year:

```python
NUCLEAR_PIPELINE_R32 = {
    "Eastern Asia": {2025: 15.0, 2030: 12.0, 2035: 5.0},  # GW
    "Southern Asia": {2025: 3.0, 2030: 5.0},
    ...
}
```

### 6.5 Phase 2+ extensions

| Feature | Phase 1 | Phase 2+ |
|---------|---------|----------|
| Cost timing | Charged at delivery | Spread over construction |
| IDC | Not applied | $K_{eff} = K_0 \times (1+r)^T$ |
| Cancellation | No | Yes (lose sunk cost) |
| Pipeline techs | Nuclear, Hydro | + Offshore wind |


## 7. Calibration

### 7.1 initialize_uniform()

For sectors without plant-level age data, assume installed stock is uniformly distributed across ages 0 to $L$:

```python
def initialize_uniform(total_capacity, lifetime, base_year, timestep=5):
    """Create uniform vintage distribution so surviving stock = total_capacity."""
    n_vintages = lifetime // timestep
    cap_per_vintage = total_capacity / sum(
        S(age) for age in range(0, lifetime, timestep)
    )
    vintages = {}
    for v in range(n_vintages):
        year = base_year - v * timestep
        vintages[year] = cap_per_vintage
    return vintages
```

The normalization ensures that after applying S-curve retirement at base year, the total surviving stock equals the observed installed capacity.

### 7.2 Data sources

| Sector | Calibration data | Method |
|--------|-----------------|--------|
| Electricity | GEM (Global Energy Monitor) | Plant-level age data where available |
| Hydrogen | Limited plant data | initialize_uniform() |
| Transport | Vehicle registration statistics | Age distributions where available |
| Industry | No plant-level data | initialize_uniform() |
| Buildings | No equipment-level data | initialize_uniform() |
| Bunkers | Fleet age data (aviation/shipping) | Partial, supplement with uniform |


## 8. Interaction with Other Components

### 8.1 Logit / Powertrain competition → Vintage

Logit determines **target shares**. Vintage stock determines **actual shares** (constrained by surviving stock). The actual share converges to the target share over time as old stock retires and new investment fills at target shares.

```
Period t:
  Logit target:    ICE 40%, BEV 50%, FCEV 10%
  Surviving stock: ICE 70%, BEV 20%, FCEV 2%   (old fleet)
  Gap:             ICE -30%, BEV +30%, FCEV +8%
  Investment:      ICE 0 (overcapacity), BEV +30%, FCEV +8%
  Actual share:    ICE ~55%, BEV ~35%, FCEV ~5% (mix of old + new)
```

### 8.2 Vintage → Learning curves

New investment adds to cumulative deployment:

$$Q_i^{cum}(t+1) = Q_i^{cum}(t) + new\_investment_i(t)$$

### 8.3 Vintage → Budget constraint

$$I_{energy}(t) = \sum_{sectors} \sum_i new\_investment_i(t) \times capex_i(t)$$

### 8.4 Vintage → Emissions

Surviving stock determines actual carrier mix → actual fuel demand → actual emissions. Even if the logit says "switch to clean," surviving dirty stock continues emitting until retirement.

### 8.5 Carbon price → Shutdown → Emissions

Carbon price enters variable cost → profit turns negative → shutdown → capacity idles → emissions drop. This is the mechanism by which carbon pricing **accelerates** the retirement of fossil capacity beyond natural S-curve retirement.

```
Carbon price ↑ → VC_coal ↑ → π_coal < 0 → P(π) → 0 → coal capacity idles
                                                     → coal emissions ↓ (immediate)
                                                     → gap opens → renewables fill
```

Without shutdown, coal plants would continue operating until physical retirement (age 60). With shutdown, they idle as soon as variable cost exceeds revenue — potentially decades earlier.


## 9. User Configurables

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| Lifetime $L$ per technology | §4 tables | Per-technology |
| Retirement steepness $k$ | 0.1 | Global |
| Half-life ratio $\rho$ | 0.75 | Global |
| Retirement type (S-curve vs hard cutoff) | Per-technology (§4 tables) | Per-technology |
| Shutdown median $m$ | −0.1 | Global / per-sector |
| Shutdown steepness $n$ | 6 | Global |
| Construction delay (periods) | Nuclear 2, Hydro 1 | Per-technology |
| Pipeline pre-population | WNA/GEM data | Per-region, per-technology |

Three-level parameter specification applies: global scalar → regional → regional × temporal.


## 10. Data Requirements

### Base-year calibration data

| Data | Source | Resolution | Notes |
|------|--------|------------|-------|
| Electricity plant capacity + age | GEM (Global Energy Monitor) | Plant-level → R32 | For vintage initialization |
| Hydrogen production capacity | IEA Hydrogen Database | Country → R32 | Limited, supplement with uniform |
| Vehicle fleet age distributions | National registries, OICA | Country → R32 | For transport vintage init |
| Industrial equipment capacity | IEA WEB (energy consumption proxy) | R32 | initialize_uniform() |
| Building equipment stock | Literature estimates | R32 | initialize_uniform() |
| Nuclear under construction | WNA | Plant-level → R32 | Pipeline pre-population |
| Hydro under construction | GEM | Plant-level → R32 | Pipeline pre-population |

### Exogenous trajectories

| Data | Source | Notes |
|------|--------|-------|
| Fuel prices(t) | Energy module | For profit calculation (endogenous) |
| Carbon price(t) | Policy module | For profit shutdown trigger |
| Electricity/H₂ prices(t) | Energy module | For supply-side profit calculation |


## 11. IAMC Reporting

| Variable | Source |
|----------|--------|
| `Capacity\|Electricity\|{source}` (GW) | Surviving stock (EJ → GW) |
| `Capacity Additions\|Electricity\|{source}` (GW/yr) | New investment |
| `Capital Stock\|Transport\|{powertrain}` | Surviving vehicle stock |
| `Investment\|Energy Supply\|{sector}\|{source}` | new_cap × capex |


## 12. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| Electricity | Full VintageStock (17 techs) | Same |
| Hydrogen | Full VintageStock (7 techs) | Same |
| Transport | Full VintageStock (18 powertrains) | + Mode-level stock |
| Industry | VintageStock by carrier (EU + FS) | + Subsector-level |
| Buildings | VintageStock by end-use × carrier | + Building shell vintage |
| Agriculture | No vintage (preference decay only) | Optional |
| Construction pipeline | Nuclear (2 periods), Hydro (1 period) | + Offshore wind |
| IDC | Not applied (capex at delivery) | $K_{eff} = K_0 \times (1+r)^T$ |
| Profit shutdown | Full ($P(\pi)$ on all fuel-burning techs) | Same |
| Overcapacity | Proportional scaling + shutdown | Same |
| Calibration | initialize_uniform() + GEM | + Plant-level databases |
| Efficiency by vintage | Same for all vintages | Vintage-specific efficiency |

### Phase transition notes

- **Phase 1 → 2**: Add IDC to LCOE/LCOH (raises effective capex for nuclear, hydro). Add offshore wind to construction pipeline (1 period delay). Add building shell vintage (insulation age → heating demand). No structural code change — IDC is a capex multiplier, pipeline is config.
- **Phase 2 → 3**: Vintage-specific efficiency (newer plants more efficient than old). Construction cost spreading (1/3 per period during build). Pipeline cancellation with sunk cost. Plant-level databases replace initialize_uniform().
