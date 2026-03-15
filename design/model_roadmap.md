# GHIM — Model Improvement Roadmap

Near-term fixes and enhancements needed before publication-quality runs.

## 1. Constant Dollar Year Consistency

**Status**: Inconsistent

| Component | Current | Source |
|-----------|---------|--------|
| GDP (AR6 SSP) | billion US$2010/yr | AR6 CSV data |
| GDP docstring | US$2005/yr | Wrong — needs fix |
| Carrier prices | No year specified | Hardcoded defaults, ~IEA 2020 |
| Capital stock (K=3Y) | Inherits GDP unit | US$2010 if GDP is |
| LCOE / tech costs | No year specified | Literature mix |

**Action**: Pick one base year (2010 or 2017 PPP), deflate all monetary inputs consistently. Document in `config.py`.

## 2. Regional Energy Data (see also `data_requirements.md`)

**Status**: Global defaults hardcoded

- Carrier prices ($/GJ) — single global value per carrier
- Carrier demand splits — same % for all 32 regions
- Composite energy price p_E — global average

**Action**: Source region-specific IEA energy balances and prices via gcamdata, or use AR6 R5 data with R32 downscaling.

## 3. Known Bugs

- Emissions ~50,000× too high (emission factor units)
- Zero population → arbitrary TFP fallback (`klem.py:85-86`)
- Oil/liquids carrier_price stuck at ~0.6 $/GJ (refining pathway)
- `PREF_DECAY_RATE` defined but never wired

## 4. Phase B: Endogenous GDP

Two-pass calibration (exog → endog bootstrap). Plan exists at `.claude/plans/golden-plotting-lantern.md`.

## 5. Calibration Refinements

- Base-year electricity price: 20 $/GJ global → regional IEA data
- Non-elec price: currently residual from composite → should be independently sourced
- Buildings HDD/CDD: currently 1.0 → need regional climate normals
