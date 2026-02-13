# GHIM Energy Module

**GHIM** (Global Hybrid Integrated Model) is a recursive-dynamic energy system model that projects energy supply, demand, and CO$_2$ emissions for 10 world regions from 2000 to 2150 at 5-year intervals.

The model combines a **DICE-style endogenous GDP** engine ($Y = AK^\alpha L^{1-\alpha}$ with energy cost feedback), **MERGE-style preference factor logit** for technology competition, **WITCH-style learning curves** for cost dynamics, and a **nested CES production function** for macroeconomic energy demand. It is designed as a modular, transparent alternative to large-scale integrated assessment models (IAMs), implemented entirely in Python.

---

## Documentation Contents

```{toctree}
:maxdepth: 2
:caption: Model Description

overview
mathematical_framework
klem
energy_supply_chain
trade
solver
```

```{toctree}
:maxdepth: 2
:caption: Data & Configuration

data_pipeline
regions
scenarios
technology_assumptions
calibration
policy
```

```{toctree}
:maxdepth: 2
:caption: Reference

usage
api_reference
validation
known_limitations
```
