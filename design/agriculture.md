# GHIM Energy Module — Agriculture Sector Design

## 1. Scope

Agriculture is a **final energy demand sector**. Energy is consumed for mechanization (tractors, harvesters), irrigation pumping, greenhouse heating/cooling, crop drying, and livestock operations.

Phase 1: single-node sector with GDP-driven demand and carrier logit. Phase 2+: connects to AFOLU, Water, and Climate modules via interface parameters.


## 2. Sector Structure

```
Agriculture                        × 7 carriers (logit)
```

No end-use disaggregation in Phase 1. Single logit pool across all agricultural energy uses.

### Carrier Table

| Carrier | Use cases | Phase 1 role |
|---------|-----------|-------------|
| Refined Oil | Tractors, harvesters, irrigation pumps, diesel generators | Dominant (~50–60%) |
| Electricity | Irrigation pumps, livestock operations, grain drying, greenhouses | Growing (~20–30%) |
| Gas | Greenhouse heating, crop drying | Moderate (~10%) |
| Coal | Small-scale heating, drying (declining) | Minor |
| Solid Biomass | Traditional agriculture (developing regions), crop residue use | Declining |
| Biofuels | Biofuel-powered tractors/equipment | $\alpha = 0$ in Phase 1 |
| Hydrogen | Future fuel cell tractors, ammonia synthesis | $\alpha = 0$ in Phase 1 |


## 3. Energy Demand

### 3.1 Agricultural output

Agricultural output serves as the intermediate demand driver, with price response:

$$Q_{ag}(t) = Q_{ag,base} \times \left(\frac{GDP(t)}{GDP_{base}}\right)^{\alpha_{ag}} \times \left(\frac{P_{ag}(t)}{P_{ag,base}}\right)^{\gamma_{ag}}$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $Q_{ag,base}$ | Base-year agricultural output index | Normalized to 1.0 |
| $\alpha_{ag}$ | Income elasticity of agricultural output | **0.3** |
| $\gamma_{ag}$ | Price elasticity of agricultural output | **−0.2** |
| $P_{ag}$ | Agriculture energy price index ($/GJ, see §3.4) | Endogenous |

Low elasticities reflect: (1) food production is a necessity, (2) energy is a small share of total agricultural costs (~5–10%), (3) mechanization is already mature in developed regions.

Phase 2+: $Q_{ag}$ is overridden by the AFOLU module (see §5).

### 3.2 Energy demand

$$E_{ag}(t) = ei_{ag} \times Q_{ag}(t)$$

| Parameter | Meaning | Phase 1 |
|-----------|---------|---------|
| $ei_{ag}$ | Energy intensity of agriculture (GJ/unit output) | Fixed at base-year value |

$ei_{ag}$ is **fixed** in Phase 1 — same rationale as Industry and Buildings. No exogenous AEEI. Efficiency improvement comes only from **carrier switching** via logit (e.g., diesel pumps → electric pumps). Phase 2+ can endogenize efficiency via the energy services nest or technology improvement.

### 3.3 Carrier allocation

Preference-factor logit (same framework as all other sectors):

$$s_c = \frac{\alpha_c \cdot \exp\!\bigl(\beta \cdot (C_c + p_c)\bigr)}{\sum_j \alpha_j \cdot \exp\!\bigl(\beta \cdot (C_j + p_j)\bigr)}$$

where $\alpha_c$ = availability {0, 1}, $\beta < 0$ = cost sensitivity, $C_c$ = carrier price ($/GJ), $p_c$ = preference factor ($/GJ, calibrated, decays).

Stock turnover: equipment lifetime ~15–20 years (tractors, pumps). Note: stock turnover operates at the **carrier level** — the single-node Agriculture structure has no structural sub-choices to track.

### 3.4 Agriculture price index

Expenditure-weighted carrier price:

$$P_{ag} = \sum_c s_c \times C_c$$

No efficiency conversion (unlike Buildings/Transport) — agriculture consumes energy directly, not as a service intermediate.

### 3.5 Reconciliation with macro CES

Same as all other sectors:

$$E_{ag}^{actual} = E_{ag}^{raw} \times \frac{E_{CES}}{\sum_{sectors} E_{sector}^{raw}}$$


## 4. Emissions

Agriculture computes **both** energy combustion emissions and non-energy emissions (CH$_4$, N$_2$O). All are driven by the same production index $Q_{ag}(t)$.

### 4.1 Energy combustion CO$_2$

Standard framework — same carbon coefficients as all other demand sectors:

$$CO2_{ag} = \sum_{c} E_{ag,c} \times CO2\_FACTOR_c$$

Only coal and gas have non-zero demand-side factors; refined oil, electricity, biomass, etc. are counted upstream.

### 4.2 Non-energy emissions from production index

Non-energy agricultural emissions scale directly with $Q_{ag}(t)$:

$$CH_4^{ag}(t) = CH_{4,0}^{ag} \times Q_{ag}(t)$$
$$N_2O^{ag}(t) = N_2O_{0}^{ag} \times Q_{ag}(t)$$

where $CH_{4,0}^{ag}$ and $N_2O_{0}^{ag}$ are base-year emissions (from EDGAR) and $Q_{ag}$ is the production index (§3.1, base = 1.0).

This captures:
- **CH$_4$**: enteric fermentation (livestock) + rice cultivation — both scale with agricultural output
- **N$_2$O**: fertilizer application (soil emissions) + manure management — both scale with agricultural output

No separate livestock/rice/fertilizer sub-indices. The production index is the single driver.

### 4.3 Implementation

```python
class AgricultureSector(DemandSector):
    base_ch4: float   # MtCH4, base-year (from EDGAR)
    base_n2o: float   # MtN2O, base-year (from EDGAR)

    def compute_emissions(self, rs: RegionState) -> EmissionResult:
        # Energy combustion (standard)
        result = self._combustion_emissions(rs.final_demand["agriculture"])
        # Non-energy: production index drives both
        idx = self.production_index(rs)
        result.ch4 += self.base_ch4 * idx
        result.n2o += self.base_n2o * idx
        return result
```

### 4.4 Base-year non-energy emissions

Source: EDGAR v8.0, disaggregated to R32 regions.

| Emission | Global total (2020) | Unit |
|----------|-------------------|------|
| CH$_4$ enteric + rice | 2,600 | MtCO$_2$eq |
| N$_2$O soils + manure | 2,600 | MtCO$_2$eq |

Phase 2+: AFOLU module overrides $Q_{ag}$ and may provide separate livestock/crop indices for finer decomposition.


## 5. Module Interfaces (Phase 2+)

Agriculture is the primary connection point between the energy module and AFOLU, Water, and Climate modules. Phase 1 designs the interface parameters with default values; external modules override them when connected.

### 5.1 AFOLU → Agriculture

| Interface parameter | Phase 1 default | Phase 2+ override |
|--------------------|-----------------|-------------------|
| $Q_{ag}(t)$ (agricultural output) | GDP-and-price-scaled (§3.1) | AFOLU crop + livestock output |
| Biomass supply constraint | Literature values (exogenous) | AFOLU land allocation (energy crops vs food) |
| Crop residue availability | Fixed fraction of $Q_{ag}$ | AFOLU residue balance |

### 5.2 Water → Agriculture (via AFOLU)

Water availability affects agriculture **indirectly through AFOLU**, not as a direct interface to the energy module.

```
Water Module → AFOLU (irrigation water allocation, crop yield impact)
                 ↓
              AFOLU → Agriculture (Q_ag override, biomass constraint)
```

In Phase 1, water is unconstrained (AFOLU not connected, so the default GDP-driven Q_ag applies). In Phase 2+, water scarcity reduces AFOLU crop output → lower Q_ag → lower agricultural energy demand.

### 5.3 Climate → Agriculture

| Interface parameter | Phase 1 default | Phase 2+ override |
|--------------------|-----------------|-------------------|
| Crop yield multiplier | 1.0 | Climate damage function on agriculture |

The yield multiplier affects $Q_{ag}$ in Phase 2+ (either directly or via AFOLU). In Phase 1, default 1.0 (no climate feedback).

### 5.4 Agriculture → Other modules

| Output | Destination | Mechanism |
|--------|-------------|-----------|
| Agricultural energy demand by carrier | Energy module (trade clearing) | Adds to regional fuel demand |
| Biomass demand | AFOLU module | Land pressure for energy crops |
| Fertilizer energy (gas for ammonia) | Industry feedstocks | Currently in Industry FS, future: explicit link |


## 6. Calibration

### Energy intensity

From base-year IEA energy balances (Agriculture/Forestry row):

$$ei_{ag,base} = \frac{E_{ag,base}}{Q_{ag,base}}$$

### Logit preference factors

Same as all other sectors:

$$p_c = \frac{1}{\beta} \cdot \ln\!\left(\frac{S_c}{S_r}\right) - (C_c - C_r)$$

### Elasticities

| Parameter | Phase 1 default | Range | References |
|-----------|-----------------|-------|------------|
| $\alpha_{ag}$ (income elasticity) | **0.3** | 0.2–0.5 | FAO, GCAM |
| $\gamma_{ag}$ (price elasticity) | **−0.2** | −0.1 to −0.3 | GCAM, EPPA |


## 7. User Configurables

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| $\alpha_{ag}$ (income elasticity) | 0.3 | Global / regional |
| $\gamma_{ag}$ (price elasticity) | −0.2 | Global / regional |
| $ei_{ag}$ | Base-year calibrated | Regional (auto-calibrated from data) |
| Carrier set | 7 carriers (Biofuel, H₂ blocked) | Add/remove via config |
| $\alpha_c$ (availability) | 1 for 5 carriers, 0 for Biofuel/H₂ | Per-carrier, per-period (policy JSON) |
| $P_c$ decay rate | Per-carrier default | Per-carrier override (policy JSON) |
| Equipment lifetime | 15–20 yr | Per-carrier override |
| Logit parameter ($\beta$) | Global default | Sector override |

Three-level parameter specification applies: global scalar → regional → regional × temporal.


## 8. Data Requirements

### Base-year calibration data

| Data | Source | Resolution | Notes |
|------|--------|------------|-------|
| Agriculture FE by carrier | IEA WEB via gcamdata | R32 | Agriculture/Forestry row |
| Agricultural output index | FAO, World Bank | R32 | For intensity calibration |
| Carrier prices | IEA, energy module | R32 | For logit calibration |

### Exogenous trajectories

| Data | Source | Notes |
|------|--------|-------|
| GDP(t) | SSP database | Drives $Q_{ag}$ via income elasticity |
| Carrier prices(t) | Energy module | Endogenous within solver loop |

### Phase 2+ additional data

| Data | Source | Notes |
|------|--------|-------|
| Crop/livestock output projections | FAO, AFOLU module | Overrides GDP-driven $Q_{ag}$ |
| Biomass supply potential | IRENA, IPCC | For biomass constraint |
| Irrigation energy by region | FAO AQUASTAT | For end-use disaggregation |
| Climate damage functions | ISIMIP, AgMIP | Yield multipliers |


## 9. IAMC Reporting Summary

### Final Energy (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Final Energy\|Agriculture` | $E_{ag}$ |
| `Final Energy\|Agriculture\|{fuel}` | By carrier from logit |

### Emissions (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Emissions\|CO2\|Energy\|Demand` | Includes agriculture direct combustion |
| `Emissions\|CO2\|Energy\|Demand\|Agriculture` | $CO2_{ag}$ (Tier-2) |


## 10. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| Demand driver | GDP-and-price-scaled | AFOLU crop/livestock output |
| End-use disaggregation | None (single node) | Irrigation, mechanization, heating |
| Intensity $ei_{ag}$ | Fixed | Endogenous (energy services nest or tech improvement) |
| Irrigation | Implicit in total | Explicit (Water module → AFOLU linkage) |
| Biomass supply | Exogenous potential | AFOLU land competition |
| Climate feedback | None | Yield multiplier (via AFOLU) |
| Non-CO₂ emissions | Production-index-scaled (CH₄, N₂O) | AFOLU module feedback (separate indices) |
| Fertilizer energy | In Industry feedstocks | Explicit Agriculture ↔ Industry link |
| Biofuels, H₂ carriers | Blocked ($\alpha = 0$) | Enabled as tech matures |

### Phase transition notes

- **Phase 1 → 2**: AFOLU module overrides $Q_{ag}$ with crop/livestock output projections. Biomass supply constrained by land competition. Climate damage function reduces yields. No structural code change — interface parameters switch from defaults to external module values.
- **Phase 2 → 3**: End-use disaggregation (irrigation vs mechanization vs heating). Explicit water-energy nexus. Fertilizer energy linked to Industry feedstocks.
