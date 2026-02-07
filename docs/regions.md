# Regional Specification

GHIM uses the **AR6 10-region (R10)** classification from the IPCC Sixth Assessment Report Working Group III. This chapter explains the rationale for this choice, the mapping methodology, and base-year regional statistics.

## Why AR6 R10?

Most integrated assessment models define their own regional aggregations: GCAM uses 32 regions, REMIND uses 12, MESSAGE uses 11. These model-specific structures make cross-model comparison difficult and create unnecessary complexity.

GHIM instead adopts the **standardized AR6 R10 classification** for three reasons:

1. **IPCC alignment**: The R10 regions are used throughout the IPCC AR6 scenario database, enabling direct comparison of GHIM outputs with assessed literature ranges.
2. **Transparency**: A well-documented, externally defined classification avoids ad hoc aggregation decisions embedded within the model.
3. **Fewer free parameters**: 10 regions versus 32 means fewer region-specific parameters to calibrate, reducing overfitting risk while retaining meaningful heterogeneity.

> **Note**: The R10 classification groups countries by geographic and economic similarity. It is coarser than GCAM R32 but captures the key distinctions (e.g., separating Eastern Asia from Southern Asia, or Eurasia from Europe) that matter for energy system modeling.

## Region Definitions

The 10 regions, with representative countries and approximate 2020 statistics:

| Region | Representative Countries | Pop. (M) | GDP (T$ PPP) | Energy (EJ) |
|--------|------------------------|-----------|---------------|-------------|
| Africa | Nigeria, South Africa, Ethiopia, Egypt, Kenya | 1,340 | 6.5 | 29.5 |
| Asia-Pacific Developed | Japan, South Korea, Australia, New Zealand | 205 | 10.5 | 21.1 |
| Eastern Asia | China, Mongolia, Hong Kong, Taiwan | 1,470 | 28.0 | 117.6 |
| Eurasia | Russia, Ukraine, Kazakhstan, Uzbekistan, Belarus | 295 | 5.5 | 62.9 |
| Europe | EU-27, UK, Norway, Switzerland, Turkey | 610 | 25.0 | 45.8 |
| Latin America and Caribbean | Brazil, Mexico, Argentina, Colombia, Chile | 650 | 10.0 | 34.5 |
| Middle East | Saudi Arabia, Iran, Iraq, UAE, Israel | 275 | 6.0 | 72.6 |
| North America | USA, Canada, Bermuda, Greenland | 370 | 25.5 | 97.8 |
| South-East Asia and developing Pacific | Indonesia, Thailand, Vietnam, Philippines, Malaysia | 690 | 8.5 | 28.5 |
| Southern Asia | India, Pakistan, Bangladesh, Sri Lanka, Nepal | 1,900 | 12.0 | 32.9 |

Population and GDP values are from the SSP2 scenario at 2020; energy values are approximate sums from `DEFAULT_PRIMARY_ENERGY` in [`ghim/data/energy_cal.py`](../ghim/data/energy_cal.py).

## Mapping Methodology

### Direct ISO to R10

GHIM maps countries to R10 regions **directly** using ISO 3166-1 alpha-3 codes. There is no intermediate aggregation step (e.g., no GCAM R32 intermediary).

The mapping file is:

```
ghim/data/external/region_classification.tsv
```

with three columns:

| Column | Description | Example |
|--------|-------------|---------|
| `ISO` | ISO 3166-1 alpha-3 code | `USA`, `CHN`, `IND` |
| `name` | Country name | `United States`, `China`, `India` |
| `region_ar6_10` | AR6 R10 region | `North America`, `Eastern Asia`, `Southern Asia` |

The file contains **250 entries** covering all countries and territories in the SSP database.

### Mapping chain for SSP data

SSP scenario data uses country names rather than ISO codes. The mapping chain is:

$$
\text{SSP country name} \xrightarrow{\text{iso\_SSP\_regID.csv}} \text{ISO code} \xrightarrow{\text{region\_classification.tsv}} \text{R10 region}
$$

The first step uses the SSP-provided ISO mapping file (`ghim/data/external/ssp/iso_SSP_regID.csv`); the second uses GHIM's direct ISO-to-R10 mapping. This two-step chain is handled by `_build_ssp_country_to_r10()` in [`ghim/data/ssp.py`](../ghim/data/ssp.py).

## Data Aggregation

Country-level SSP data is aggregated to R10 regions by simple summation:

- **Population**: Additive (millions of people)
- **GDP|PPP**: Additive (billion USD 2017 PPP)

$$
X_{\text{R10}} = \sum_{c \in \text{R10}} X_c
$$

This is appropriate because both variables are extensive quantities. The aggregation is performed in `load_ssp_data()` using a pandas `groupby().sum()` operation.

> **Note**: Intensive quantities (e.g., GDP per capita, energy intensity) are computed *after* aggregation from the regional totals, not averaged across countries.

## Base-Year Energy Balance

The base-year (2020) energy balance for each region is specified in `DEFAULT_PRIMARY_ENERGY` and `DEFAULT_FINAL_DEMAND` in [`ghim/data/energy_cal.py`](../ghim/data/energy_cal.py). These are approximate values based on IEA 2020 data.

### Primary energy by region (EJ, 2020)

| Region | Coal | Gas | Oil | Nuclear | Hydro | Wind | Solar | Biomass |
|--------|------|-----|-----|---------|-------|------|-------|---------|
| Africa | 4.0 | 6.5 | 7.5 | 0.2 | 1.0 | 0.1 | 0.1 | 10.0 |
| Asia-Pacific Developed | 3.5 | 5.0 | 1.5 | 3.0 | 1.2 | 0.5 | 1.0 | 1.0 |
| Eastern Asia | 82.0 | 7.0 | 8.0 | 3.5 | 4.5 | 5.0 | 3.0 | 4.5 |
| Eurasia | 6.5 | 27.0 | 24.0 | 2.2 | 2.0 | 0.1 | 0.1 | 1.0 |
| Europe | 5.0 | 8.0 | 5.0 | 7.5 | 2.8 | 4.5 | 1.8 | 6.0 |
| Latin America and Caribbean | 0.8 | 6.0 | 14.0 | 0.5 | 5.5 | 1.0 | 0.5 | 6.0 |
| Middle East | 0.1 | 22.0 | 50.0 | 0.1 | 0.2 | 0.1 | 0.1 | 0.1 |
| North America | 12.0 | 35.0 | 28.0 | 8.8 | 3.0 | 3.5 | 2.0 | 5.0 |
| SE Asia and dev. Pacific | 5.0 | 9.0 | 5.5 | 0.3 | 1.2 | 0.2 | 0.3 | 6.0 |
| Southern Asia | 16.0 | 2.0 | 1.5 | 1.2 | 1.5 | 1.5 | 1.2 | 8.0 |

### Final energy demand by sector (EJ, 2020)

| Region | Industry | Buildings | Transport | Total |
|--------|----------|-----------|-----------|-------|
| Africa | 4.0 | 8.0 | 4.0 | 16.0 |
| Asia-Pacific Developed | 8.0 | 7.0 | 6.0 | 21.0 |
| Eastern Asia | 45.0 | 15.0 | 15.0 | 75.0 |
| Eurasia | 10.0 | 10.0 | 6.0 | 26.0 |
| Europe | 13.0 | 18.0 | 14.0 | 45.0 |
| Latin America and Caribbean | 8.0 | 5.0 | 10.0 | 23.0 |
| Middle East | 8.0 | 5.0 | 8.0 | 21.0 |
| North America | 18.0 | 20.0 | 28.0 | 66.0 |
| SE Asia and dev. Pacific | 10.0 | 6.0 | 6.0 | 22.0 |
| Southern Asia | 12.0 | 8.0 | 5.0 | 25.0 |

The global total final energy demand is approximately 340 EJ, and total primary energy approximately 543 EJ. The difference reflects conversion losses in electricity generation, refining, and other transformation sectors.

**Implementation**: [`ghim/regions.py`](../ghim/regions.py), [`ghim/data/ssp.py`](../ghim/data/ssp.py), [`ghim/data/external/region_classification.tsv`](../ghim/data/external/region_classification.tsv).
