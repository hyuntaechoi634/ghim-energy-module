# Data Pipeline

## Data Sources

GHIM reads two categories of input data:

### 1. SSP scenario data (population and GDP)

**Source file**: `input/gcamdata/inst/extdata/socioeconomics/SSP/SSP_database_2024.csv.gz`

This is the IIASA SSP database (v3.0.1) containing country-level projections for 5 Shared Socioeconomic Pathways:

| Scenario | Narrative | GDP growth | Pop growth |
|----------|-----------|-----------|-----------|
| SSP1 | Sustainability | High | Low (peaks ~2060) |
| SSP2 | Middle of the Road | Medium | Medium (peaks ~2070) |
| SSP3 | Regional Rivalry | Low | High (continues growing) |
| SSP4 | Inequality | Medium-Low | Medium |
| SSP5 | Fossil-fueled Development | High | Low (peaks ~2060) |

**Variables extracted**: `Population` (millions) and `GDP|PPP` (billion USD 2017 PPP).

### 2. Region mapping

**Source file**: `mapping/region_classification.tsv`

Tab-separated file with columns:
- `ISO`: ISO 3166-1 alpha-3 country code (e.g., `USA`, `CHN`, `IND`)
- `name`: Country name
- `region_ar6_10`: AR6 R10 region assignment

This file provides the **direct** ISO → R10 mapping, avoiding any intermediate aggregation through GCAM's 32-region system.

## Aggregation Pipeline

The data pipeline aggregates ~195 countries to 10 regions through the following chain:

```
SSP country name → ISO code → AR6 R10 region
```

### Step 1: Country name to ISO code

The SSP database uses country names (e.g., "United States", "China"). These are mapped to ISO codes using the GCAM mapping file:

```
input/gcamdata/inst/extdata/socioeconomics/SSP/iso_SSP_regID.csv
```

This file provides a `ssp_country_name` → `iso` mapping.

### Step 2: ISO code to R10 region

ISO codes are mapped directly to AR6 R10 regions using `mapping/region_classification.tsv`:

```
USA → North America
CHN → Eastern Asia
IND → Southern Asia
BRA → Latin America and Caribbean
DEU → Europe
RUS → Eurasia
...
```

### Step 3: Aggregation

Population and GDP are **summed** across all countries within each R10 region. The result is two DataFrames with:
- **Index**: 10 R10 region names
- **Columns**: Model years (2020, 2025, ..., 2100)

## Base-year validation

The pipeline produces the following global totals for the base year (2020, SSP2):

| Variable | GHIM value | Reference value | Source |
|----------|-----------|-----------------|--------|
| Population | 7.78 billion | 7.79 billion | UN WPP 2022 |
| GDP PPP | $123.7 trillion | $130 trillion | World Bank |
| CO$_2$ emissions | 37.7 GtCO$_2$ | 36.7 GtCO$_2$ | IEA 2021 |
| Total energy | 380 EJ | 583 EJ | IEA 2021 |

Note: The energy and emissions values are based on approximate default calibration data, not actual IEA statistics (which are proprietary). The order of magnitude is correct, but exact calibration requires licensed IEA data.

## Energy calibration data

Base-year energy balance data (primary energy, electricity mix, final demand) is stored as **default dictionaries** in `ghim/data/energy_cal.py`. These contain approximate regional energy balances based on publicly available IEA and BP Statistical Review data.

Key data structures:

| Variable | Structure | Units |
|----------|-----------|-------|
| `DEFAULT_PRIMARY_ENERGY` | region → fuel → EJ | EJ |
| `DEFAULT_ELEC_SHARES` | region → tech → fraction | - |
| `DEFAULT_ELEC_TOTAL_EJ` | region → EJ | EJ |
| `DEFAULT_FINAL_DEMAND` | region → sector → EJ | EJ |

**Implementation**: [`ghim/data/ssp.py`](../ghim/data/ssp.py), [`ghim/data/energy_cal.py`](../ghim/data/energy_cal.py), [`ghim/regions.py`](../ghim/regions.py).
