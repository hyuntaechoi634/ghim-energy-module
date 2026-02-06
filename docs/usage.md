# Usage Guide

## Installation

### Prerequisites

- Python 3.10 or later
- Conda (recommended) or pip

### Setting up the environment

```bash
# Create and activate a dedicated conda environment
conda create -n ghim python=3.11 -y
conda activate ghim

# Install dependencies and the package (from the repository root)
pip install -e ".[dev]"
```

The `.[dev]` install includes test dependencies (pytest, pytest-cov).

### Verify installation

```bash
# Run the test suite
python -m pytest ghim/tests/ -v
```

All 38 tests should pass.

## Running the Model

### Basic usage

```bash
python -m ghim.run --scenario SSP2
```

This runs the full model for all 10 regions, 17 periods (2020–2100), and writes results to `ghim_output/`.

### Command-line options

| Option | Default | Description |
|--------|---------|-------------|
| `--scenario` | `SSP2` | SSP scenario: SSP1, SSP2, SSP3, SSP4, SSP5 |
| `--output-dir` | `ghim_output` | Directory for CSV output |
| `--no-csv` | (flag) | Skip CSV export, print summary only |

### Example output

```
=== GHIM Energy Model Results ===

Global Totals:
  Year  CO2 (GtCO2)  Energy (EJ)   GDP (T$)  Pop (B)
----------------------------------------------------
  2020         37.7        380.2      123.7     7.78
  2030         46.4        528.7      173.4     8.48
  2050         61.8        847.1      280.8     9.58
  2070         76.7       1230.5      412.3    10.07
  2100         96.3       1889.3      640.6     9.87
```

## Output files

When CSV export is enabled (default), the model writes three files:

### `ghim_output/results.csv`

Full results table with columns:
- `year`, `region`, `gdp`, `population`
- `total_energy_demand_ej`, `emissions_mtco2`
- `electricity_price`, `refined_liquids_ej`
- Electricity generation by technology
- Hydrogen production by technology
- Final demand by sector and carrier

### `ghim_output/emissions.csv`

Year × region matrix of CO$_2$ emissions (MtCO$_2$).

### `ghim_output/energy_mix.csv`

Year × region × technology matrix of electricity generation (EJ).

## Using as a library

GHIM can also be used programmatically:

```python
from ghim.data.ssp import load_ssp_data
from ghim.solver.recursive import run_model

# Load SSP2 data
ssp_data = load_ssp_data("SSP2")

# Run the model
results = run_model(ssp_data, "SSP2")

# Analyze results
for r in results:
    if r.region == "North America" and r.year == 2050:
        print(f"NA 2050 emissions: {r.emissions_mtco2:.0f} MtCO2")
        print(f"NA 2050 electricity mix: {r.electricity_gen_ej}")
```

### Key data structures

**`PeriodResult`** — result for one region in one period:

| Field | Type | Description |
|-------|------|-------------|
| `year` | int | Model year |
| `region` | str | R10 region name |
| `gdp` | float | GDP in billion USD PPP |
| `population` | float | Population in millions |
| `total_energy_demand_ej` | float | Total energy demand (EJ) |
| `electricity_gen_ej` | dict[str, float] | Tech → generation (EJ) |
| `electricity_price` | float | Weighted avg electricity cost ($/GJ) |
| `refined_liquids_ej` | float | Refined liquids demand (EJ) |
| `hydrogen_ej` | dict[str, float] | H$_2$ tech → production (EJ) |
| `final_demand_ej` | dict[str, dict] | Sector → carrier → demand (EJ) |
| `fuel_prices` | dict[str, float] | Carrier → price ($/GJ) |
| `emissions_mtco2` | float | Total CO$_2$ emissions (MtCO$_2$) |

## Testing

### Run all tests

```bash
python -m pytest ghim/tests/ -v
```

### Test structure

| Test file | Tests | What it covers |
|-----------|-------|---------------|
| `test_ces.py` | 8 | CES output, price, demand, calibration; Cobb-Douglas and Leontief limits |
| `test_logit.py` | 9 | Logit shares, calibration roundtrip, edge cases |
| `test_data_loading.py` | 7 | Region mapping, SSP data loading, population/GDP validation |
| `test_electricity.py` | 8 | Supply sums, calibration, emissions, LCOE |
| `test_solver.py` | 6 | Single-period solve, full model run, emissions sanity check |

## Building Documentation

```bash
# Install documentation dependencies
pip install sphinx myst-parser sphinx-book-theme sphinx-copybutton sphinx-design

# Build HTML documentation
cd docs
sphinx-build -b html . _build/html

# View in browser
open _build/html/index.html  # macOS
xdg-open _build/html/index.html  # Linux
```
