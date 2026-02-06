# Validation and Benchmarks

This chapter describes how GHIM outputs are validated against external benchmarks and what diagnostic outputs are available. GHIM is a stylized model — it aims for qualitative agreement with established data rather than precise numerical matching.

## Base-Year Benchmarks (2020)

The model's base-year outputs should be compared against IEA and other authoritative sources:

| Metric | GHIM (approximate) | IEA / Reference | Agreement |
|--------|-------------------|-----------------|-----------|
| Global primary energy | ~543 EJ | 583 EJ (IEA 2020) | Within 7% |
| Global final energy demand | ~340 EJ | 378 EJ (IEA 2020) | Within 10% |
| Global CO$_2$ emissions | ~36 GtCO$_2$ | 36.8 GtCO$_2$ (IEA 2020) | Within 3% |
| Global electricity generation | ~96 EJ | 99 EJ (IEA 2020) | Within 3% |
| Global population | 7.8 billion | 7.8 billion (UN) | Exact (from SSP) |
| Global GDP | ~130 T$ PPP | ~130 T$ PPP (World Bank) | Exact (from SSP) |

> **Note**: Base-year energy values are approximate defaults, not actual IEA data (which is proprietary). The close agreement is by design — the defaults were chosen to approximate IEA values. True validation would require licensed IEA energy balance data.

### Electricity mix comparison (2020)

Global electricity generation shares (approximate):

| Technology | GHIM | IEA 2020 | Notes |
|------------|------|----------|-------|
| Coal | ~35% | 36% | Good agreement |
| Gas | ~18% | 23% | Slightly low |
| Nuclear | ~10% | 10% | Good agreement |
| Hydro | ~13% | 16% | Slightly low |
| Wind | ~6% | 6% | Good agreement |
| Solar | ~3% | 3% | Good agreement |
| Biomass | ~3% | 2% | Slightly high |
| Oil | ~2% | 3% | Reasonable |

Regional variation is captured through `DEFAULT_ELEC_SHARES` in [`ghim/data/energy_cal.py`](../ghim/data/energy_cal.py). Eastern Asia (China-dominated) has 62% coal; Latin America has 55% hydro; the Middle East has 65% gas — all consistent with IEA regional patterns.

## GDP Tracking

A key validation metric is whether endogenous GDP tracks the SSP reference GDP. Without energy price shocks, the model should reproduce the SSP path exactly (by construction of the TFP calibration).

### What to check

The diagnostic output `gdp_comparison.csv` contains both `gdp_billion_usd` (endogenous net output) and `ssp_reference_gdp_billion_usd` for each region and year. Expected behavior:

- **Early periods (2020-2040)**: Endogenous GDP should track SSP GDP very closely (<2% deviation), as learning curve effects and stock turnover have not yet caused large price shifts.
- **Mid-century (2040-2070)**: Moderate deviations may appear if energy cost changes are significant. Renewable learning driving costs down → net output slightly above SSP; fossil scarcity driving costs up → net output slightly below.
- **Late century (2070-2100)**: Larger deviations are possible as cumulative effects of the energy transition compound.

### Interpreting deviations

- **Endogenous GDP > SSP GDP**: Energy costs have fallen below the implicit energy cost in the SSP trajectory (e.g., rapid renewable deployment reducing average energy prices).
- **Endogenous GDP < SSP GDP**: Energy costs have risen (e.g., resource constraints, slow transition).
- **Large deviations (>10%)**: May indicate parameter issues — check fuel prices, learning rates, and demand elasticities.

## Electricity Mix Evolution

The electricity mix should evolve plausibly over the century. Qualitative expectations under SSP2 (no carbon pricing):

### 2020 to 2050

- Solar and wind shares should increase, driven by learning-curve cost reductions (solar 20% LR, wind 12% LR).
- Coal share should decline but remain significant due to stock turnover inertia ($\tau = 40$ years).
- Nuclear share should remain roughly stable (slow learning, long lifetime).

### 2050 to 2100

- Renewables should dominate new capacity additions as costs continue falling toward the 20% floor.
- Coal and gas persist due to stock inertia but their shares decline gradually.
- The exact shares depend on regional starting points: Eastern Asia transitions away from coal more slowly than Europe.

### Comparison with IPCC AR6 ranges

For SSP2 without climate policy, the IPCC AR6 database shows:

| Metric | IPCC AR6 range (2050, no policy) | Expected GHIM |
|--------|----------------------------------|---------------|
| Coal share of electricity | 15-30% | Within range |
| Renewables share (wind+solar) | 20-40% | Within range |
| Total electricity (EJ) | 130-180 | ~140-160 |

## Known Deviations and Limitations

### Energy data is approximate

Base-year energy values are representative defaults, not actual IEA energy balances. This means:
- Regional energy mix shares are approximately correct but not precisely calibrated.
- Total primary energy and final demand are within ~10% of IEA values.
- Sector-level fuel splits are stylized (especially the nested demand tree subsector shares).

### No AEEI

GHIM does not include autonomous energy efficiency improvement (AEEI). In practice, energy intensity (EJ per dollar of GDP) has declined historically at ~1-2% per year. Without AEEI, GHIM's energy demand may grow faster than models that include it. The income elasticities ($\epsilon < 1$) partially compensate but do not fully capture efficiency trends.

### No carbon pricing

GHIM does not implement carbon pricing or emissions constraints. This means:
- The model cannot reproduce policy scenarios (e.g., SSP1-2.6 or SSP2-4.5).
- The fossil-to-renewable transition is driven only by cost competition and preference decay, not by policy signals.
- Emissions trajectories may be higher than in models with integrated climate policy.

### No trade

Regions are modeled independently — there is no energy trade, technology transfer, or capital flows between regions. Each region has its own fuel prices, technology deployment, and capital stock.

## Cross-Model Comparison

GHIM's results can be compared qualitatively with other IAMs:

| Feature | GHIM | GCAM | MESSAGE | WITCH |
|---------|------|------|---------|-------|
| GDP | Endogenous (DICE) | Exogenous | Exogenous | Endogenous |
| Technology choice | Preference logit | Relative cost logit | Optimization | Optimization |
| Learning curves | One-factor | None (exogenous cost) | Two-factor | One-factor |
| Stock turnover | Explicit | Vintage tracking | Vintage tracking | Explicit |
| Regions | 10 (R10) | 32 | 11 | 13 |
| Time horizon | 2000-2150 | 2010-2100 | 2010-2100 | 2005-2100 |
| Solver | Recursive-dynamic | Recursive-dynamic | Intertemporal optimization | Hybrid |

GHIM is closest to WITCH in its combination of endogenous GDP and one-factor learning curves, but uses logit discrete choice (like GCAM) rather than optimization.

## Diagnostic Outputs

### CSV files

The `export_csv()` function in [`ghim/output/reporting.py`](../ghim/output/reporting.py) produces:

| File | Contents |
|------|----------|
| `model_results.csv` | Full results: GDP, energy, emissions, electricity mix by region and year |
| `emissions_by_region.csv` | CO$_2$ emissions pivot table (region $\times$ year) |
| `energy_by_region.csv` | Total energy demand pivot table (region $\times$ year) |
| `gdp_comparison.csv` | Endogenous GDP vs SSP reference GDP (region $\times$ year) |

### Console summary

The `print_summary()` function displays:
- Global totals by year: CO$_2$ (GtCO$_2$), energy (EJ), GDP (T$), SSP GDP, population
- Global electricity mix at first and last model year (EJ and % share)

## How to Run Validation

1. Run the model:

```bash
python -m ghim.run --scenario SSP2
```

2. Check console output for global totals — verify base-year CO$_2$ is approximately 36 GtCO$_2$ and energy is approximately 340 EJ (final demand).

3. Examine CSV outputs in the `output/` directory:
   - `gdp_comparison.csv`: Endogenous GDP should track SSP reference GDP closely in early periods.
   - `emissions_by_region.csv`: Global emissions should start at ~36 GtCO$_2$ and evolve plausibly.
   - `model_results.csv`: Check that electricity mix shifts toward renewables over time.

4. Run the test suite:

```bash
python -m pytest ghim/tests/ -v
```

All 40 tests should pass, confirming numerical correctness of individual components.
