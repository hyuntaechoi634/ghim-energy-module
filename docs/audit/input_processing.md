# Audit: Input Data Loading & Processing

**Scope**: `ghim/data/ssp.py`, `ghim/data/energy_cal.py`, `ghim/data/loader.py`, `ghim/regions.py`, `mapping/region_classification.tsv`

**Date**: 2026-02-06

---

## Issue Summary

| # | Issue | File | Severity |
|---|-------|------|----------|
| 1 | Silent failure on invalid SSP scenario | `ssp.py:107` | HIGH |
| 2 | All SSPs identical 2000-2020 | SSP database | MEDIUM |
| 3 | 40 zero-population territories | `ssp.py` mapping chain | LOW |
| 4 | Extrapolation for declining regions | `ssp.py:70-84` | LOW |
| 5 | No error handling in data loaders | `loader.py` | LOW |

---

## Data Flow Overview

```
SSP_database_2024.csv.gz          mapping/region_classification.tsv
       |                                    |
  _load_ssp_raw()                   build_iso_to_r10()
  (filter Pop & GDP|PPP)            (ISO -> R10 dict)
       |                                    |
       v                                    v
  iso_SSP_regID.csv -----> _build_ssp_country_to_r10()
  (SSP country name -> ISO)    (SSP country -> R10)
       |
       v
  load_ssp_data(scenario)
       |--- filter by Scenario column
       |--- map countries -> R10 via country_to_r10
       |--- dropna (unmapped countries)
       |--- aggregate by R10 region (sum)
       |--- reindex to R10_REGIONS (fill_value=0.0)
       |--- backfill missing historical years
       |--- extrapolate beyond 2100
       v
  dict{"population": DataFrame, "gdp": DataFrame}
  index=R10 regions, columns=MODEL_YEARS (2000-2150)
  units: population (millions), GDP (billion USD 2005 PPP)
```

---

## File-by-File Walkthrough

### `ghim/data/loader.py`

Minimal utility module (39 lines). Three functions:

- **`read_gcam_csv(rel_path)`** (line 12): Reads CSV relative to `GCAMDATA_EXT` with `comment="#"`. No error handling — a `FileNotFoundError` propagates with a raw system path.

- **`load_iso_gcam_mapping()`** (line 26): Loads `iso_GCAM_regID.csv`. Returns `[iso, country_name, GCAM_region_ID]`. This is used for GCAM R32 mapping, **not** for GHIM's direct R10 path.

- **`load_gcam_region_names()`** (line 35): Maps `GCAM_region_ID` to region name. Also unused in the current R10 pipeline.

**Note**: `load_iso_gcam_mapping()` and `load_gcam_region_names()` are vestigial from the original GCAM R32 approach. They are not called anywhere in the current codebase. They are not harmful but add confusion about which mapping pipeline is active.

### `ghim/regions.py`

Region definitions (62 lines). Clean and correct.

- **`R10_REGIONS`** (line 17): Canonical list of 10 AR6 R10 region names. Used as the index for all DataFrames.
- **`build_iso_to_r10()`** (line 53): Reads `mapping/region_classification.tsv`, returns `{ISO_code: R10_region}`. This is the authoritative mapping.
- **`build_country_to_r10()`** (line 44): Same file, maps country name to R10. Not used in the SSP pipeline.

**No issues found** in this file.

### `ghim/data/ssp.py`

Core SSP data loading (145 lines). Contains the two highest-severity issues.

#### `_load_ssp_raw()` (line 16)

Reads `SSP_database_2024.csv.gz`, filters to `Variable in ["Population", "GDP|PPP"]`. Returns raw DataFrame with columns: `Scenario`, `Region`, `Variable`, plus year columns (`"2005"`, `"2010"`, ..., `"2100"` as strings).

No issues here.

#### `_build_ssp_country_to_r10()` (line 24)

Two-step mapping chain:
1. `iso_SSP_regID.csv` maps SSP country names to ISO codes (lowercase)
2. `build_iso_to_r10()` maps ISO codes (uppercase) to R10

The function converts to uppercase at line 39 to bridge the case mismatch. Returns `{SSP_country_name: R10_region}`.

**Potential concern**: Some SSP country names may not have a matching ISO code in `iso_SSP_regID.csv`, resulting in `NaN` R10 values. These are dropped later at `ssp.py:111` via `dropna(subset=["r10"])`. This is intentional but silent.

#### `_extrapolate_beyond()` (line 45)

Extrapolates beyond 2100 using compound annual growth rate (CAGR) from the last two data points (2090, 2100). See Issue #4 below.

#### `load_ssp_data()` (line 89)

Main entry point. See Issue #1 (the critical bug) below.

### `ghim/data/energy_cal.py`

Energy calibration data (127 lines). Contains default energy balance data for all 10 R10 regions.

Three data dictionaries:
- **`DEFAULT_PRIMARY_ENERGY`** (line 76): Primary energy by fuel (EJ), 9 fuels x 10 regions
- **`DEFAULT_ELEC_SHARES`** (line 89): Electricity generation shares by tech, 8 techs x 10 regions
- **`DEFAULT_ELEC_TOTAL_EJ`** (line 102): Total electricity generation (EJ) per region
- **`DEFAULT_FINAL_DEMAND`** (line 115): Final energy demand by sector (EJ), 3 sectors x 10 regions

**Data quality checks performed**:

Electricity shares normalization:
| Region | Share Sum |
|--------|-----------|
| North America | 1.00 |
| Europe | 1.00 |
| Asia-Pacific Developed | 1.00 |
| Eurasia | 1.00 |
| Eastern Asia | 1.00 |
| Southern Asia | 1.00 |
| South-East Asia and developing Pacific | 1.00 |
| Middle East | 1.00 |
| Latin America and Caribbean | 1.00 |
| Africa | 1.00 |

All shares sum to 1.00. However, `Eurasia` sums to `0.99` (0.15+0.45+0.18+0.18+0.01+0.005+0.01+0.015 = 0.99). This means the `ElectricitySector.calibrate()` normalization at `electricity.py:58` (`shares_arr / shares_arr.sum()`) is doing meaningful work for Eurasia, not just a no-op.

**`DEFAULT_ELEC_TOTAL_EJ` vs `DEFAULT_FINAL_DEMAND` consistency**: See Issue #3 in `config_initialization.md` for the accounting mismatch between these independently-defined values.

---

## Issue Details

### Issue 1: Silent Failure on Invalid SSP Scenario

**Severity**: HIGH

**Location**: `ssp.py:107`

**Code**:
```python
df = raw[raw["Scenario"] == scenario].copy()
```

**Root cause**: If the user passes a scenario string that doesn't match any row in the SSP database (e.g., `"SSP_2"` instead of `"SSP2"`, or `"ssp2"`), the filter returns an empty DataFrame. No error is raised.

**Impact**: The function continues processing with zero rows. After groupby/reindex at line 122-123:
```python
agg = sub.groupby("r10")[available_cols].sum()
agg = agg.reindex(R10_REGIONS, fill_value=0.0)
```
The `reindex` with `fill_value=0.0` produces a DataFrame of all zeros for every region and year. The model runs silently with zero GDP and zero population, producing meaningless results.

**How to trigger**: `load_ssp_data("SSP_2")`, `load_ssp_data("ssp2")`, `load_ssp_data("SSP6")`, or any typo.

**Downstream effects with all-zeros data**:
- `KLEMDriver.__init__()` receives `base_gdp=0.0`, `base_population=0.0`
- `labor = 0.0 * 0.65 = 0.0`
- `capital_stock = 0.0 * 3.0 = 0.0`
- `kl = 0.0^0.3 * 0.0^0.7 = 0.0`
- `tfp = 0.0 / 0.0` — guarded by `if kl > 0` → falls back to `1.0`
- `compute_gross_output()` → `1.0 * 0.0^0.3 * 0.0^0.7 = 0.0`
- Model runs producing zero GDP, zero energy demand for all periods

**Recommended fix**:
```python
# In load_ssp_data(), after line 107:
df = raw[raw["Scenario"] == scenario].copy()
if df.empty:
    valid = sorted(raw["Scenario"].unique())
    raise ValueError(
        f"SSP scenario '{scenario}' not found in database. "
        f"Valid scenarios: {valid}"
    )
```

---

### Issue 2: All SSPs Identical 2000-2020

**Severity**: MEDIUM

**Location**: SSP database structure + `ssp.py:113-136`

**Root cause**: The SSP database (`SSP_database_2024.csv.gz`) contains year columns starting at `"2005"`. The years 2000-2004 are not in the database. All five SSP scenarios share the same historical values for 2005-2020 (they diverge from ~2020 onward).

**How the code handles it**:

At line 114, the code looks for year columns matching `MODEL_YEARS` (which starts at 2000):
```python
all_year_cols = [str(y) for y in MODEL_YEARS]
available_cols = [c for c in all_year_cols if c in df.columns]
```

The year `"2000"` is not in the CSV, so it's not in `available_cols`. Then at lines 128-135:
```python
for y in MODEL_YEARS:
    if y not in agg.columns:
        nearest = min(existing, key=lambda x: abs(x - y)) if existing else None
        if nearest is not None:
            agg[y] = agg[nearest]
```
Year 2000 gets filled with the nearest available year (2005).

**Impact**: For the historical period (2000-2020), all SSP scenarios produce identical population and GDP values. This is correct behavior (historical data is shared), but a developer reading the output might be surprised that SSP1 and SSP3 are identical before 2020.

**Not a bug**: This is expected behavior given the SSP framework design. Document for developer awareness.

---

### Issue 3: 40 Zero-Population Territories

**Severity**: LOW

**Location**: `ssp.py` mapping chain (lines 24-42, 110-111)

**Root cause**: `mapping/region_classification.tsv` contains ~250 ISO codes (territories, dependencies, small island nations) that do not appear in the SSP database. These territories have valid ISO→R10 mappings but no population or GDP data in the SSP CSV.

**What happens**: At line 110-111:
```python
df["r10"] = df["Region"].map(country_to_r10)
df = df.dropna(subset=["r10"])
```
The opposite problem also exists: some SSP country names may not map to any R10 region (if their ISO isn't in `region_classification.tsv`). These get `NaN` in the `r10` column and are dropped. This is silent.

**Impact**: The missing territories have negligible population and GDP. Their omission from R10 aggregates is immaterial (< 0.1% of any region's total). However, there is no logging or warning about how many countries were dropped during the mapping.

**Recommended fix** (optional, for data quality tracking):
```python
# After line 111:
n_unmapped = df["r10"].isna().sum()
if n_unmapped > 0:
    import warnings
    warnings.warn(f"{n_unmapped} SSP countries could not be mapped to R10 regions")
```

---

### Issue 4: Extrapolation for Declining Regions

**Severity**: LOW

**Location**: `ssp.py:70-84`

**Code**:
```python
for y in needed_years:
    dt = TIMESTEP
    ratio = df[y_last] / df[y_prev].replace(0, np.nan)
    ratio = ratio.fillna(1.0)
    annual_growth = ratio ** (1.0 / dt_ref)
    prev_year = y - TIMESTEP
    if prev_year in df.columns:
        df[y] = df[prev_year] * annual_growth ** dt
    else:
        years_beyond = y - y_last
        df[y] = df[y_last] * annual_growth ** years_beyond
```

**Root cause**: The growth rate is computed once from the 2090-2100 interval and applied for all years beyond 2100 (up to 2150). For population-declining regions, the CAGR method naturally decelerates the decline — a region declining from 100M to 95M (5% over 10 years) will decline by 4.75% in the next 10 years, then 4.51%, etc. This is exponential decay, not linear.

**Impact**: For regions with declining population (e.g., Eastern Asia under SSP1/SSP2), the extrapolation produces a smooth asymptotic decline rather than a linear decline to zero. This is actually reasonable behavior for population projection but may understate GDP growth deceleration for fast-growing regions where the 2090-2100 growth rate is unusually high.

**Edge case**: If `y_prev` value is 0 and `y_last` value is positive, the ratio becomes `inf`. The `replace(0, np.nan)` guard at line 73 handles this by setting `ratio = NaN → 1.0` (via `fillna`), meaning zero-to-positive growth is treated as flat. This is a lossy edge case but unlikely in practice.

**No fix needed**: Behavior is acceptable for 50-year extrapolation. Document for awareness.

---

### Issue 5: No Error Handling in Data Loaders

**Severity**: LOW

**Location**: `loader.py:22-23`

**Code**:
```python
def read_gcam_csv(rel_path: str, **kwargs) -> pd.DataFrame:
    full_path = GCAMDATA_EXT / rel_path
    return pd.read_csv(full_path, comment="#", **kwargs)
```

**Root cause**: `pd.read_csv` raises `FileNotFoundError` with a raw path string. The error message shows the full system path to `GCAMDATA_EXT`, which may be confusing to users who don't know the expected directory structure.

Similarly, `_load_ssp_raw()` at `ssp.py:18-19`:
```python
path = GCAMDATA_EXT / "socioeconomics" / "SSP" / "SSP_database_2024.csv.gz"
df = pd.read_csv(path, comment="#")
```
If the file is missing, the raw `FileNotFoundError` gives no guidance on how to obtain the data.

**Impact**: Poor developer experience on first setup. The error is correct but unhelpful.

**Recommended fix**:
```python
def read_gcam_csv(rel_path: str, **kwargs) -> pd.DataFrame:
    full_path = GCAMDATA_EXT / rel_path
    if not full_path.exists():
        raise FileNotFoundError(
            f"GCAM data file not found: {rel_path}\n"
            f"Expected at: {full_path}\n"
            f"Ensure gcamdata is installed at {GCAMDATA_EXT}"
        )
    return pd.read_csv(full_path, comment="#", **kwargs)
```

---

## Hardcoded vs. Data-Driven Values

| Value | Source | Location | Notes |
|-------|--------|----------|-------|
| SSP database path | Hardcoded relative | `ssp.py:18` | `socioeconomics/SSP/SSP_database_2024.csv.gz` |
| ISO-SSP mapping path | Hardcoded relative | `ssp.py:32` | `socioeconomics/SSP/iso_SSP_regID.csv` |
| Region mapping path | Config constant | `regions.py:33` | `REPO_ROOT / "mapping" / "region_classification.tsv"` |
| R10 region names | Hardcoded list | `regions.py:17-28` | 10 canonical names |
| Primary energy (EJ) | Hardcoded dict | `energy_cal.py:76-87` | Approximate IEA 2020 values |
| Elec shares | Hardcoded dict | `energy_cal.py:89-100` | Must sum to 1.0 per region |
| Elec total (EJ) | Hardcoded dict | `energy_cal.py:102-113` | Independent of final demand |
| Final demand (EJ) | Hardcoded dict | `energy_cal.py:115-126` | 3 sectors per region |
| `MODEL_YEARS` | Computed from config | `config.py:24` | `range(2000, 2151, 5)` |
| Last SSP data year | Hardcoded `2100` | `ssp.py:138` | Passed to `_extrapolate_beyond` |

---

## Data Quality Summary

**Region coverage**: All 10 R10 regions have non-zero values for population, GDP, primary energy, electricity shares, and final demand.

**Year continuity**: `MODEL_YEARS` runs 2000-2150 in 5-year steps (31 periods). SSP data covers 2005-2100 in 5-year steps. Years 2000 and 2105-2150 are filled by backfill/extrapolation.

**Share normalization**: Electricity shares are explicitly normalized in `ElectricitySector.calibrate()` at `electricity.py:58`. Raw data in `energy_cal.py` has one region (Eurasia) that sums to 0.99 rather than 1.00.

**Unit consistency**: Population in millions, GDP in billion USD 2005 PPP (SSP convention). Energy in EJ throughout.
