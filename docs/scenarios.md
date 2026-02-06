# SSP Scenarios

GHIM is driven by **Shared Socioeconomic Pathways (SSPs)**, which provide population and GDP trajectories for each region. This chapter describes the SSP framework, the data source, how SSPs enter the model, and the extrapolation methods used to extend projections beyond the SSP database horizon.

## SSP Overview

The SSP framework defines five narratives describing alternative socioeconomic futures. Each pathway represents a coherent story about global development, inequality, and environmental pressures:

| SSP | Name | Narrative |
|-----|------|-----------|
| SSP1 | Sustainability | Rapid technological progress, strong institutions, low population growth, shift toward sustainable practices |
| SSP2 | Middle of the Road | Historical trends continue; moderate growth, uneven development, gradual progress |
| SSP3 | Regional Rivalry | Nationalism, slow economic growth, high population in developing regions, weak international cooperation |
| SSP4 | Inequality | High inequality within and across countries; advanced economies grow while others stagnate |
| SSP5 | Fossil-fueled Development | Rapid growth powered by fossil fuels; high energy demand, high GDP, low population growth |

> **Note**: SSPs drive the macroeconomic boundary conditions (population, GDP trajectory). The energy system response is endogenous. Climate policies (carbon pricing, emissions targets, technology constraints, etc.) are specified separately via the [Policy Variables](policy.md) system and can be combined with any SSP scenario.

## Data Source

GHIM uses the **SSP 2024 database** distributed with gcamdata:

```
input/gcamdata/inst/extdata/socioeconomics/SSP/SSP_database_2024.csv.gz
```

Two variables are extracted:

| Variable | Unit | Description |
|----------|------|-------------|
| `Population` | Millions | Total population by country and SSP |
| `GDP\|PPP` | Billion USD 2017 PPP | Gross domestic product at purchasing power parity |

The database provides values at 5-year intervals from **2005 to 2100** for approximately 200 countries. Country names are linked to ISO codes via a companion file (`iso_SSP_regID.csv`), then aggregated to AR6 R10 regions (see [Regional Specification](regions.md)).

## How SSPs Drive the Model

SSP data enters the model through two channels:

### 1. TFP Calibration (GDP path)

The SSP GDP trajectory determines the **total factor productivity** path $A(t)$ in the DICE production function. At each model period, TFP is back-calculated so that, without energy price shocks, the model reproduces the SSP GDP:

$$
A(t) = \frac{Y_{\text{SSP}}(t)}{K_{\text{ref}}(t)^{\alpha} \cdot L(t)^{1-\alpha}}
$$

where $K_{\text{ref}}(t)$ is a reference capital trajectory assuming full savings of gross output. Once calibrated, $A(t)$ is **fixed** for the scenario run. Deviations from SSP GDP arise endogenously through the energy cost feedback loop.

### 2. Labor Force (Population)

Population directly determines the labor input:

$$
L(t) = \text{Population}(t) \times \text{LFPR}
$$

where $\text{LFPR} = 0.65$ is the labor force participation rate. Higher population increases gross output and energy demand.

### Scenario comparison: Global totals

Approximate global totals from the SSP database at key years:

| SSP | Pop. 2020 (B) | Pop. 2050 (B) | Pop. 2100 (B) | GDP 2020 (T$) | GDP 2050 (T$) | GDP 2100 (T$) |
|-----|---------------|---------------|---------------|----------------|----------------|----------------|
| SSP1 | 7.8 | 9.0 | 7.4 | 130 | 260 | 460 |
| SSP2 | 7.8 | 9.4 | 9.0 | 130 | 230 | 400 |
| SSP3 | 7.8 | 9.7 | 10.4 | 130 | 180 | 250 |
| SSP4 | 7.8 | 9.3 | 8.9 | 130 | 220 | 370 |
| SSP5 | 7.8 | 8.9 | 7.0 | 130 | 300 | 550 |

Values are approximate sums across all R10 regions. All SSPs share the same 2020 base year; divergence grows over time.

## Extrapolation Beyond 2100

The SSP database covers 2005-2100, but GHIM runs to **2150**. The function `_extrapolate_beyond()` in [`ghim/data/ssp.py`](../ghim/data/ssp.py) extends the data using the trailing growth rate from the last available interval:

### GDP: Compound Annual Growth Rate (CAGR)

The growth rate from 2090 to 2100 is annualized and applied forward:

$$
g = \left(\frac{\text{GDP}_{2100}}{\text{GDP}_{2090}}\right)^{1/10}
$$

$$
\text{GDP}_{t} = \text{GDP}_{t-\Delta t} \cdot g^{\Delta t}, \quad t \in \{2105, 2110, \ldots, 2150\}
$$

This assumes that the growth trend at end-of-century persists. For SSP2, this typically gives ~1.5% annual growth for high-income regions and ~2-3% for developing regions.

### Population: Same CAGR method

Population is extrapolated using the same compound growth approach as GDP. The growth rate from the 2090-2100 interval is applied forward. For SSP1 and SSP5 (which have declining populations by 2100), this naturally produces continued population decline post-2100.

> **Note**: The extrapolation is applied per-region, preserving regional heterogeneity in growth trends. Regions that are decelerating by 2100 will continue to decelerate.

## Historical Backfill

The SSP database begins at 2005, but GHIM's time horizon starts at **2000**. For model years before the earliest SSP data point (2000, typically filled from 2005), the nearest available year is used:

$$
X(t) = X(t_{\text{nearest}}), \quad t < t_{\text{first}}
$$

This nearest-year fill approach is implemented in `load_ssp_data()` and affects only the 2000 period, which falls within the historical initialization window (2000-2015). Since TFP is calibrated to match the SSP trajectory, small inaccuracies in these early years have minimal impact on model results from 2020 onward.

**Implementation**: [`ghim/data/ssp.py`](../ghim/data/ssp.py) — functions `load_ssp_data`, `_extrapolate_beyond`, `_build_ssp_country_to_r10`.

## Policy Scenarios

In addition to SSP socioeconomic pathways, GHIM supports **policy scenarios** that overlay climate and energy policies on top of any SSP. These are specified via JSON files or CLI flags and include carbon pricing, renewable subsidies, efficiency standards, emissions caps, technology constraints, and revenue recycling.

Example scenario files are provided in the `scenarios/` directory:

| File | Description |
|------|-------------|
| `scenarios/carbon_tax_50.json` | Constant $50/tCO$_2$ carbon tax |
| `scenarios/net_zero_2050.json` | Rising carbon price + coal phase-out + renewables floor + subsidies + AEEI + emissions cap |

Running with a policy:

```bash
# SSP2 + net zero policy
python -m ghim.run --scenario SSP2 --policy scenarios/net_zero_2050.json

# SSP3 + simple carbon tax
python -m ghim.run --scenario SSP3 --carbon-price 100
```

See [Policy Variables](policy.md) for the full specification.
