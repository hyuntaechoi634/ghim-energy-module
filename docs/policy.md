# Policy Variables

GHIM includes a policy layer that enables carbon pricing, renewable subsidies, energy efficiency standards, emissions caps, technology share constraints, and carbon revenue recycling. All policies default to zero/disabled, so existing behavior is unchanged when no policy arguments are provided.

Policies are specified via a **JSON scenario file** (`--policy path.json`) for complex time-varying policies, or via **CLI flags** (`--carbon-price 50`) for simple constant policies.

---

## Policy Types

### 1. Carbon Price

A carbon price ($/tCO$_2$) adds a cost penalty to fossil fuels proportional to their carbon content. The price is injected at the **fuel level** before energy sectors compute costs:

$$
p'_f = p_f + \underbrace{c_f \cdot \frac{44}{12}}_{\text{tCO}_2/\text{GJ}} \cdot \tau
$$

where:
- $p_f$ is the base fuel price ($/GJ),
- $c_f$ is the carbon coefficient (tC/GJ) from `CARBON_COEFS`,
- $\frac{44}{12}$ converts tC to tCO$_2$,
- $\tau$ is the carbon price ($/tCO$_2$).

This propagates automatically through `levelized_cost()` in all sectors. Less efficient plants pay more per GJ of output since LCOE divides fuel cost by efficiency. Secondary fuels (electricity, hydrogen, refined liquids) have zero carbon coefficients, so they don't double-count -- their costs rise naturally through the price iteration as input fuels become more expensive.

**JSON**:
```json
{
  "carbon_price": {
    "trajectory": {"2025": 30, "2030": 80, "2050": 300}
  }
}
```

**CLI**: `--carbon-price 50` (constant $/tCO$_2$)

### 2. Renewable Subsidies

Per-technology cost reductions ($/GJ) subtracted from the levelized cost before logit competition. Costs are floored at 0.01 $/GJ to maintain numerical stability.

$$
\text{LCOE}'_i = \max(\text{LCOE}_i - \text{subsidy}_i, \; 0.01)
$$

**JSON**:
```json
{
  "renewable_subsidies": {
    "subsidies": {
      "solar": {"2025": 2.0, "2040": 0.5, "2050": 0.0},
      "wind": {"2025": 1.5, "2040": 0.0}
    }
  }
}
```

Subsidies are applied to both electricity and hydrogen sectors -- any technology name matching a subsidy key receives the cost reduction.

### 3. Efficiency Standards (AEEI)

Autonomous energy efficiency improvement applied as a cumulative demand multiplier. The cumulative factor for year $t$ relative to base year $t_0$ is:

$$
\text{AEEI}(t) = (1 - r)^{(t - t_0)}
$$

where $r$ is the annual improvement rate. This is applied in two places:
1. **Total energy demand** (global rate): multiplied after the KLEM energy demand calculation
2. **Per-sector demand** (sector-specific or global fallback): multiplied on each carrier demand in the final demand loop

**JSON**:
```json
{
  "efficiency_standards": {
    "rates": {
      "global": {"2025": 0.01, "2050": 0.02},
      "industry": {"2025": 0.015}
    }
  }
}
```

Sector-specific rates override the global rate for that sector; otherwise the global rate is used as a fallback.

**CLI**: `--efficiency-rate 0.01` (1% annual, applied globally)

### 4. Emissions Cap

A global emissions cap (MtCO$_2$) triggers a bisection search over carbon prices in `run_model()`. For each year with a cap, the solver:

1. Saves the state of all region models (`copy.deepcopy`)
2. Bisects on a shadow carbon price $\tau \in [0, 2000]$ $/tCO$_2$
3. At each trial price, solves all regions for that year
4. Checks if global emissions $\approx$ cap (within 2% tolerance)
5. Restores state and re-solves with the best price found

The shadow carbon price is reported in `PeriodResult.carbon_price_usd_tco2`.

**JSON**:
```json
{
  "emissions_cap": {
    "caps": {
      "global": {"2030": 35000, "2050": 5000, "2060": 0}
    }
  }
}
```

The cap trajectory is linearly interpolated between specified years and held flat beyond endpoints.

### 5. Technology Constraints

Minimum and maximum share bounds for specific technologies within a sector. After the preference logit and stock turnover compute unconstrained shares, the constraint algorithm:

1. Iteratively clamps shares that violate bounds
2. Redistributes excess/deficit proportionally among unconstrained technologies
3. Renormalizes to ensure shares sum to 1.0

**JSON**:
```json
{
  "tech_constraints": [
    {
      "sector": "electricity",
      "technology": "coal",
      "constraint_type": "max",
      "trajectory": {"2030": 0.30, "2050": 0.0}
    },
    {
      "sector": "electricity",
      "technology": "solar",
      "constraint_type": "min",
      "trajectory": {"2030": 0.15, "2050": 0.30}
    }
  ]
}
```

This can model coal phase-out policies (declining max share) and renewable portfolio standards (increasing min share).

### 6. Revenue Recycling

A fraction of carbon tax revenue is recycled to offset energy costs, partially mitigating the GDP impact of carbon pricing:

$$
R = \tau \cdot E_{\text{CO}_2} \cdot f / 1000
$$

$$
\text{Energy cost}' = \max(\text{Energy cost} - R, \; 0)
$$

where:
- $\tau$ is the carbon price ($/tCO$_2$),
- $E_{\text{CO}_2}$ is total emissions (MtCO$_2$),
- $f \in [0, 1]$ is the recycling fraction,
- Division by 1000 converts MtCO$_2$ to GtCO$_2$ for consistent $/billion units.

**JSON**:
```json
{
  "revenue_recycling": {"fraction": 0.5}
}
```

**CLI**: `--recycling-fraction 0.5`

---

## Trajectory Interpolation

All year-indexed trajectories use **linear interpolation** between specified waypoints and are held **flat beyond endpoints**:

- Year before first point: uses first value
- Year between points: linear interpolation
- Year after last point: uses last value

For example, `{"2025": 30, "2050": 300}` gives:
- 2020: 30 (flat before first point)
- 2025: 30
- 2037: 165 (midpoint interpolation)
- 2050: 300
- 2100: 300 (flat after last point)

---

## JSON Schema

A complete policy scenario file combines any subset of the six policy types:

```json
{
  "name": "net_zero_2050",
  "carbon_price": {
    "trajectory": {"2025": 30, "2030": 80, "2050": 300}
  },
  "renewable_subsidies": {
    "subsidies": {
      "solar": {"2025": 2.0, "2040": 0.5, "2050": 0.0},
      "wind": {"2025": 1.5, "2040": 0.0}
    }
  },
  "efficiency_standards": {
    "rates": {
      "global": {"2025": 0.01, "2050": 0.02}
    }
  },
  "emissions_cap": {
    "caps": {"global": {"2030": 35000, "2050": 5000, "2060": 0}}
  },
  "tech_constraints": [
    {"sector": "electricity", "technology": "coal", "constraint_type": "max",
     "trajectory": {"2030": 0.30, "2050": 0.0}},
    {"sector": "electricity", "technology": "solar", "constraint_type": "min",
     "trajectory": {"2030": 0.15, "2050": 0.30}}
  ],
  "revenue_recycling": {"fraction": 0.5}
}
```

All fields are optional. Omitted fields default to zero/disabled.

---

## Example Scenario Files

Two example scenarios are included in the `scenarios/` directory:

### `scenarios/carbon_tax_50.json`

A simple constant carbon tax of $50/tCO$_2$ from 2020 onward:

```json
{
  "name": "carbon_tax_50",
  "carbon_price": {
    "trajectory": {"2020": 50, "2150": 50}
  }
}
```

### `scenarios/net_zero_2050.json`

A comprehensive decarbonization scenario combining rising carbon prices, coal phase-out, renewable mandates, subsidies, efficiency improvements, and an emissions cap converging to zero:

```json
{
  "name": "net_zero_2050",
  "carbon_price": {"trajectory": {"2025": 30, "2030": 80, "2050": 300}},
  "renewable_subsidies": {"subsidies": {"solar": {"2025": 2.0, "2040": 0.5, "2050": 0.0}, "wind": {"2025": 1.5, "2040": 0.0}}},
  "efficiency_standards": {"rates": {"global": {"2025": 0.01, "2050": 0.02}}},
  "emissions_cap": {"caps": {"global": {"2030": 35000, "2050": 5000, "2060": 0}}},
  "tech_constraints": [
    {"sector": "electricity", "technology": "coal", "constraint_type": "max", "trajectory": {"2030": 0.30, "2050": 0.0}},
    {"sector": "electricity", "technology": "solar", "constraint_type": "min", "trajectory": {"2030": 0.15, "2050": 0.30}}
  ],
  "revenue_recycling": {"fraction": 0.5}
}
```

---

## Design Decisions

### Carbon price at fuel level, not in `levelized_cost()`

Injecting carbon cost into `prices[fuel]` before passing to sectors is cleaner than modifying `Technology.levelized_cost()` signatures. The existing `fuel_price / efficiency` in LCOE automatically makes inefficient plants pay more. Secondary fuels (electricity, hydrogen, refined liquids) have `CARBON_COEFS = 0.0` so they don't double-count.

### AEEI in solver, not in `FinalDemand`

The efficiency factor is applied as a post-multiplier in `solve_period()` rather than inside `FinalDemand.compute_demand()`. This keeps the demand class policy-unaware and makes the efficiency factor visible in the solver call stack and in `PeriodResult.aeei_factor`.

### Clamp-and-redistribute for tech constraints

After logit shares and stock turnover, shares are iteratively clamped to [min, max] bounds with proportional redistribution among unconstrained technologies. This is simpler and more transparent than adjusting preference factors, though it may slightly distort unconstrained tech ratios.

### Emissions cap via bisection in `run_model()`

A global cap requires summing emissions across all regions, which happens at the `run_model()` level. Bisection on carbon price with `copy.deepcopy` for state save/restore ensures that the cap year doesn't corrupt model state.

**Implementation**: [`ghim/policy.py`](../ghim/policy.py) -- all dataclasses, loading, interpolation, and constraint logic.
