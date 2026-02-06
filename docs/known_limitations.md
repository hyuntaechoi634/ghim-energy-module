# Known Limitations and Future Work

## Current Limitations

### Energy demand

- **No autonomous energy efficiency improvement (AEEI)**: Energy demand grows proportionally with GDP (modulated only by the CES price elasticity). Real-world energy intensity has been declining at ~1-2% per year due to technological progress and structural change. Note: income elasticities < 1 partially capture this effect by dampening demand growth relative to GDP growth. Adding an explicit AEEI parameter $\gamma$ would further modify the demand equation to:

$$
E(t) = E_0 \cdot \frac{GDP(t)}{GDP_0} \cdot (1 - \gamma)^{t - t_0} \cdot \left(\frac{P_E}{P_{E,0}}\right)^{-\sigma}
$$

### Technology dynamics

- **No technology vintaging**: All capacity is treated as homogeneous. In reality, older plants have different cost and efficiency characteristics than new ones. A vintage structure would track capacity by installation year. (Stock turnover provides partial inertia but not full vintaging.)

### Market structure

- **Primary fuel prices not fully endogenous**: Coal, gas, and oil prices respond to resource depletion grades but do not fully clear supply vs. demand within each period.

- **No inter-regional trade**: Each region is self-sufficient — there is no fossil fuel trade, electricity interconnection, or embodied energy in goods trade.

### Policy and climate

- **No carbon pricing**: There is no carbon tax or cap-and-trade system. All emission trajectories are "baseline" (no climate policy).

- **No climate feedback**: The model does not include a climate module — there is no temperature trajectory or climate damage function affecting GDP. Integration with a simple climate model (e.g., FaIR, Hector) would close this loop.

- **No non-CO$_2$ emissions**: Only energy-related CO$_2$ is tracked. CH$_4$, N$_2$O, F-gases, and land-use emissions are not modeled.

### Calibration

- **Approximate energy data**: Base-year energy balance values are approximate, sourced from publicly available summaries rather than licensed IEA or UN energy statistics. This affects the absolute level of emissions and energy quantities (though relative patterns and trends are reasonable).

### Historical data

- **No historical period tracking**: The model covers 2000-2150 but historical periods (2000-2020) currently use SSP scenario data backfilled from the nearest available year, not actual IEA/BP historical energy data. This means historical periods don't reflect real energy transition trajectories.

## Planned Improvements

### Phase 2 (near-term)

| Feature | Status | Description |
|---------|--------|-------------|
| ~~Learning curves~~ | **Done** | WITCH-style experience curves for wind, solar, batteries |
| ~~Full market clearing~~ | **Partially done** | Endogenous GDP with energy cost feedback, but primary fuels still exogenous |
| AEEI | Planned | Autonomous efficiency improvement parameter |
| Carbon pricing | Planned | Exogenous carbon tax applied to fossil fuel costs |
| IEA calibration | Planned | Use licensed IEA World Energy Balance for precise base-year data |
| Historical period tracking | Planned | Load actual IEA/CDIAC data for 2000-2020 |

### Phase 3 (medium-term)

| Feature | Description |
|---------|-------------|
| Inter-regional trade | Fossil fuel trade flows based on comparative advantage |
| Climate module | Integration with Hector or FaIR for temperature feedback |
| Intertemporal optimization | Alternative solve mode using Pyomo/IPOPT |
| CCS technologies | Carbon capture and storage as abatement option |
| Electricity storage | Battery storage for integrating variable renewables |

### Phase 4 (long-term)

| Feature | Description |
|---------|-------------|
| Land use sector | Agriculture, forestry, bioenergy supply |
| Non-CO$_2$ emissions | CH$_4$, N$_2$O from energy and agriculture |
| Detailed transport | Vehicle stock model with mode choice |
| Regional disaggregation | Move from R10 to R32 or country-level |
