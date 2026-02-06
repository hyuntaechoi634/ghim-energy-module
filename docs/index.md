# GHIM Energy Module

**GHIM** (Global Hybrid Integrated Model) is a recursive-dynamic energy system model that projects energy supply, demand, and CO$_2$ emissions for 10 world regions from 2020 to 2100 at 5-year intervals.

The model combines a **KLEM nested CES production function** for macroeconomic energy demand with **logit-based discrete choice** for technology competition across the energy supply chain. It is designed as a modular, transparent alternative to large-scale integrated assessment models (IAMs), implemented entirely in Python.

---

## Documentation Contents

```{toctree}
:maxdepth: 2
:caption: Model Description

overview
mathematical_framework
energy_supply_chain
solver
```

```{toctree}
:maxdepth: 2
:caption: Data & Usage

data_pipeline
usage
```

```{toctree}
:maxdepth: 2
:caption: Reference

api_reference
known_limitations
```
