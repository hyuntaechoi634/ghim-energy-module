# GHIM Energy Module — Other Transformation Sectors Design

Covers Oil Refining, Biorefining, Hydrogen Production, and District Heating. Electricity Generation is in `design/electricity.md`.


## 1. Overview

All transformation sectors follow the same pattern:
- **Demand** = sum of carrier demand from all final demand sectors
- **Supply** = technology logit → shares × demand
- **Price** = share-weighted production cost → carrier price feedback to demand sectors
- **Emissions** = supply-side CO₂ (fuel input × carbon coef / efficiency)

```
Transformation Sectors
├── Electricity Generation     → Electricity carrier       (see electricity.md)
├── Oil Refining               → Refined Oil carrier
├── Biorefining                → Biofuels carrier
├── Hydrogen Production        → Hydrogen carrier
└── District Heating           → Heat carrier
```


## 2. Oil Refining

### 2.1 Scope

Crude oil → refined products (gasoline, diesel, jet fuel, naphtha, etc.). Phase 1: single aggregated refining technology. Phase 2+: product-specific refining (light/heavy crude, upgrading).

### 2.2 Technology

| Technology | Input | Phase 1 |
|-----------|-------|---------|
| Conventional refining | Crude oil | Default (single tech) |

Phase 2+: add coking, hydrocracking, Fischer-Tropsch for heavy crude.

### 2.3 Demand

$$RO_{demand}(t) = \sum_{sectors} E_{sector,\text{refined oil}}(t)$$

Includes: Industry (EU + FS), Buildings, Transport (dominant), Agriculture, Bunkers.

### 2.4 Supply and price

Single technology in Phase 1 — no logit (demand = supply):

$$RO_{supply} = RO_{demand}$$

$$p_{RO} = \frac{p_{crude}}{eff_{ref}} + cost_{processing} + \frac{coef_{crude} \cdot p_{carbon}}{eff_{ref}}$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $p_{crude}$ | Crude oil price ($/GJ, from trade module) | Endogenous |
| $eff_{ref}$ | Refining efficiency | **0.90** |
| $cost_{processing}$ | Non-fuel processing cost ($/GJ output) | **1.5** $/GJ |
| $coef_{crude}$ | Carbon coefficient of crude oil (tC/GJ) | **0.0200** |
| $p_{carbon}$ | Carbon price ($/tCO₂) | Policy |

### 2.5 Emissions

$$CO2_{ref} = \frac{RO_{supply}}{eff_{ref}} \times coef_{crude} \times \frac{44}{12}$$

This covers **all** refined oil combustion emissions (counted at supply side). Final demand sectors report 0 for refined oil carrier.

### 2.6 Fuel input to primary energy

$$Crude_{demand} = \frac{RO_{supply}}{eff_{ref}}$$

Enters trade module for oil market clearing.


## 3. Biorefining

### 3.1 Scope

Biomass → liquid fuels. Separate from Refined Oil to reflect different feedstock (biomass vs crude), AFOLU land competition, and cost structure.

### 3.2 Technologies

| Technology | Input | Output | Phase 1 |
|-----------|-------|--------|---------|
| Biodiesel (1st gen) | Vegetable oils, waste fats | Biodiesel | Yes |
| Cellulosic ethanol (2nd gen) | Crop residues, wood | Ethanol | Yes |
| Biomass-to-liquids (BTL) | Woody biomass | Synthetic diesel/gasoline | Yes |

Phase 2+: SAF (sustainable aviation fuel), renewable diesel, bio-methanol.

### 3.3 Demand

$$BF_{demand}(t) = \sum_{sectors} E_{sector,\text{biofuels}}(t)$$

Primary demand from Transport (logit competition with refined oil) and Bunkers (SAF).

### 3.4 Supply and price

Technology logit:

$$s_i = \frac{\alpha_i \cdot \exp\!\bigl(\beta \cdot (LCOF_i + p_i)\bigr)}{\sum_j \alpha_j \cdot \exp\!\bigl(\beta \cdot (LCOF_j + p_j)\bigr)}$$

$$BF_{supply,i} = s_i \times BF_{demand}$$

$$p_{BF} = \sum_i s_i \times LCOF_i$$

where LCOF (Levelized Cost of Fuel):

$$LCOF_i = \frac{capex_i \cdot FCR}{CF_i} + \frac{p_{biomass}}{eff_i} + cost_{processing,i} + VOM_i$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $p_{biomass}$ | Biomass feedstock price ($/GJ, from primary supply) | Endogenous |
| $eff_i$ | Conversion efficiency (GJ fuel / GJ biomass) | 0.35–0.55 per tech |
| $cost_{processing,i}$ | Non-fuel processing cost ($/GJ) | Per tech |
| $capex_i$ | Capital cost ($/GJ/yr capacity) | Per tech |

VintageStock applies to biorefining capacity with lifetime ~30 years. Profit shutdown applies (same framework as electricity §4.3).

### 3.5 Emissions

Biofuels are **carbon-neutral** (biogenic carbon):

$$CO2_{biofuels} = 0$$

Lifecycle emissions (land-use change, processing energy) are out of scope for Phase 1. Phase 2+: AFOLU tracks indirect land-use change emissions.

### 3.6 Biomass input and AFOLU linkage

$$Biomass_{demand,BF} = \sum_i \frac{BF_{supply,i}}{eff_i}$$

This biomass demand competes with:
- Solid biomass demand (direct combustion in Buildings, Industry, Elec Gen)
- Biomass w/ CCS (BECCS) in electricity
- Food/feed demand (AFOLU land competition)

Phase 1: biomass supply = exogenous regional potential. Phase 2+: AFOLU land allocation constrains total biomass available.

### 3.7 Resource constraint

$$\sum_{uses} Biomass_{demand} \leq Biomass_{supply}(region)$$

If total biomass demand exceeds supply, biomass price rises → biofuels become more expensive → logit share decreases. Market clearing via price iteration.


## 4. Hydrogen Production

### 4.1 Scope

Multiple primary/secondary energy sources → H₂. Key decarbonization vector for Industry (DRI steel, ammonia) and Transport (FCEV). Also used as electricity storage via H₂ turbines (in electricity.md).

### 4.2 Technologies

| Technology | Input | Phase 1 | CCS variant? |
|-----------|-------|---------|-------------|
| SMR (steam methane reforming) | Gas | Yes (dominant, ~75%) | Yes |
| Coal gasification | Coal | Yes | Yes |
| Electrolysis | Electricity | Yes (growing) | — |
| Biomass gasification | Biomass | Yes | Yes |

CCS variants follow the same pattern as electricity CCS: 90% capture rate, efficiency penalty, additional capex, blocked until availability year (default 2030).

### 4.3 Demand

$$H2_{demand}(t) = \sum_{sectors} E_{sector,\text{hydrogen}}(t)$$

### 4.4 Supply and price

Technology logit (same as electricity):

$$s_i = \frac{\alpha_i \cdot \exp\!\bigl(\beta \cdot (LCOH_i + p_i)\bigr)}{\sum_j \alpha_j \cdot \exp\!\bigl(\beta \cdot (LCOH_j + p_j)\bigr)}$$

$$H2_{supply,i} = s_i \times H2_{demand}$$

$$p_{H2} = \sum_i s_i \times LCOH_i$$

where LCOH (Levelized Cost of Hydrogen):

$$LCOH_i = \frac{capex_i \cdot FCR}{CF_i} + FOM_i + \frac{fuel_i}{eff_i} + \frac{coef_i \cdot (1 - capture_i) \cdot p_{carbon}}{eff_i} + VOM_i + TS_i$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $capex_i$ | Capital cost ($/kW), learning curve for electrolysis | Per tech (IRENA) |
| $fuel_i$ | Input fuel price (gas, coal, electricity, biomass) | Endogenous |
| $eff_i$ | Conversion efficiency | SMR 0.72, Coal 0.60, Elec 0.65, Bio 0.55 |
| $capture_i$ | CCS capture rate | 0 or 0.9 |
| $TS_i$ | CO₂ transport & storage (CCS only) | **15** $/tCO₂ |

VintageStock applies with technology-specific lifetimes (~25–30 years). Profit shutdown applies (same framework as electricity §4.3): when $p_{H2} < c_{var,i}$, unprofitable H₂ plants shut down.

### 4.5 Emissions

$$CO2_{H2} = \sum_i \frac{H2_{supply,i}}{eff_i} \times coef_i \times (1 - capture_i) \times \frac{44}{12}$$

Reported as `Emissions|CO2|Energy|Supply`.

Electrolysis: zero direct emissions (electricity emissions counted at generation).
Biomass gasification w/ CCS: **negative emissions** (same as BECCS in electricity).

### 4.6 Fuel inputs to primary energy

$$Gas_{demand,H2} = \sum_{i \in \{SMR, SMR+CCS\}} \frac{H2_{supply,i}}{eff_i}$$
$$Coal_{demand,H2} = \sum_{i \in \{coal\,gasif.\}} \frac{H2_{supply,i}}{eff_i}$$
$$Elec_{demand,H2} = \sum_{i \in \{electrolysis\}} \frac{H2_{supply,i}}{eff_i}$$
$$Biomass_{demand,H2} = \sum_{i \in \{bio\,gasif.\}} \frac{H2_{supply,i}}{eff_i}$$

Gas and coal demands enter trade module. Electricity demand adds to Elec Gen load (circular: electricity price → LCOH → H₂ demand → electricity demand, resolved by fixed-point iteration). Biomass competes with biofuels and direct use.

### 4.7 Learning curves

Electrolysis capex declines via two-factor learning:

$$capex_{elec}(t) = capex_0 \times \left(\frac{Q^{cum}}{Q_0}\right)^{-\lambda_{LBD}} \times \left(\frac{H^{RD}}{H_0}\right)^{-\lambda_{RND}}$$

LBD rate ~15%. Floor at 20% of initial capex. This is the key mechanism for green hydrogen cost reduction.

SMR and coal gasification: mature technologies, no learning (cost constant).


## 5. District Heating

### 5.1 Scope

Produces the **Heat carrier** consumed by Buildings (heating and cooling end-uses). Converts gas, coal, biomass, electricity, and waste heat into district heat distributed via pipe networks.

Phase 1: simple single-node sector with technology logit. Phase 2+: CHP (combined heat and power), industrial waste heat recovery, seasonal storage.

### 5.2 Technologies

| Technology | Input | Phase 1 | Notes |
|-----------|-------|---------|-------|
| Gas boiler | Gas | Yes (dominant) | Incumbent in most urban networks |
| Coal boiler | Coal | Yes (declining) | Common in China, Eastern Europe |
| Biomass boiler | Biomass | Yes | Growing in Nordics |
| Electric boiler | Electricity | Yes | For RE integration |
| Heat pump (large-scale) | Electricity | Yes | COP 3.0–4.0, growing |
| Geothermal direct | Geothermal | Yes | Region-specific |

Phase 2+: CHP (gas turbine + heat recovery), industrial waste heat, solar thermal, seasonal pit storage.

### 5.3 Demand

$$Heat_{demand}(t) = \sum_{sub \in \{res,com\}} \sum_{svc \in \{heat,cool\}} E_{sub,svc,heat}(t)$$

District heat demand comes from Buildings carrier allocation (logit share of Heat carrier in heating and cooling end-uses).

### 5.4 Supply and price

Technology logit on LCOH (Levelized Cost of Heat):

$$s_i = \frac{\alpha_i \cdot \exp\!\bigl(\beta \cdot (LCOH_i + p_i)\bigr)}{\sum_j \alpha_j \cdot \exp\!\bigl(\beta \cdot (LCOH_j + p_j)\bigr)}$$

$$LCOH_i = \frac{capex_i \cdot FCR}{CF_i} + FOM_i + \frac{fuel_i}{eff_i} + \frac{coef_i \cdot p_{carbon}}{eff_i} + VOM_i + dist\_cost$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $capex_i$ | Capital cost ($/kW-th) | Per tech |
| $eff_i$ | Conversion efficiency | Gas 0.90, Coal 0.80, Bio 0.85, Elec 0.98, HP 3.5, Geo 1.0 |
| $dist\_cost$ | Distribution network cost ($/GJ) | **3.0** $/GJ |

$$p_{Heat} = \sum_i s_i \times LCOH_i$$

This price feeds back to Buildings as the Heat carrier price.

### 5.5 Emissions

$$CO2_{DH} = \sum_i \frac{Heat_{supply,i}}{eff_i} \times coef_i \times \frac{44}{12}$$

Reported as `Emissions|CO2|Energy|Supply|Heat`.

### 5.6 Fuel inputs

Gas, coal, biomass, electricity demands from district heating add to respective primary/transformation sector demands. Electricity demand (electric boiler + heat pump) adds to Elec Gen load.

### 5.7 VintageStock

District heating infrastructure has long lifetimes (~30–40 years). VintageStock applies with S-curve retirement. Profit shutdown applies: when heat price from competing individual boilers (gas, heat pump) undercuts district heat LCOH, existing plants shut down.


## 6. Carrier Summary

| Carrier | Transformation | IAMC mapping |
|---------|---------------|-------------|
| Electricity | Elec. Gen. | `Secondary Energy\|Electricity` |
| Refined Oil | Oil Refining | `Secondary Energy\|Liquids\|Oil` |
| Biofuels | Biorefining | `Secondary Energy\|Liquids\|Biomass` |
| Hydrogen | H₂ Prod. | `Secondary Energy\|Hydrogen` |
| Heat | District Heating | `Secondary Energy\|Heat` |
| Gas | Direct (primary) | `Final Energy\|*\|Gases` |
| Coal | Direct (primary) | `Final Energy\|*\|Solids\|Coal` |
| Solid Biomass | Direct (primary) | `Final Energy\|*\|Solids\|Biomass` |


## 7. User Configurables

### Oil Refining

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| $eff_{ref}$ | 0.90 | Global / regional |
| $cost_{processing}$ | 1.5 $/GJ | Global / regional |

### Biorefining

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| Technology set | 3 techs | Add/remove via config |
| $capex_i$, $eff_i$ | Per-tech | Per-tech, per-region |
| Biomass supply potential | Regional (exogenous) | Per-region |
| $\alpha_i$ (availability) | 1 for all | Per-tech, per-period (policy JSON) |
| Logit parameter ($\beta$) | Global default | Sector override |

### Hydrogen Production

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| Technology set | 4 techs + CCS variants | Add/remove via config |
| $capex_i$, $eff_i$ | Per-tech | Per-tech, per-region |
| CCS availability year | 2030 | Per-tech (policy JSON) |
| Electrolysis learning rate | 15% | Per-tech |
| Capex floor | 20% of initial | Per-tech |
| $\alpha_i$ (availability) | 1 (0 for CCS before avail. year) | Per-tech, per-period |
| Logit parameter ($\beta$) | Global default | Sector override |

### District Heating

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| Technology set | 6 techs | Add/remove via config |
| $capex_i$, $eff_i$ | Per-tech | Per-tech, per-region |
| $dist\_cost$ | 3.0 $/GJ | Per-region |
| Infrastructure lifetime | 30–40 yr | Per-tech |
| $\alpha_i$ (availability) | 1 for all | Per-tech, per-period |
| Logit parameter ($\beta$) | Global default | Sector override |


## 8. Data Requirements

### Base-year calibration data

| Data | Source | Resolution | Notes |
|------|--------|------------|-------|
| Refinery throughput | IEA WEB via gcamdata | R32 | For refining demand calibration |
| Biofuels production by type | IEA Renewables | R32 | For biorefining tech shares |
| H₂ production by source | IEA Hydrogen, IRENA | R32 | For H₂ tech shares |
| District heat production | IEA WEB | R32 | For DH demand calibration |
| Technology costs | NREL ATB, IRENA, IEA | Global + regional | For LCOE/LCOH/LCOF |
| Biomass supply potential | IRENA, IPCC | R32 | For resource constraint |

### Exogenous trajectories

| Data | Source | Notes |
|------|--------|-------|
| Fuel prices(t) | Trade module / energy module | Endogenous within solver loop |
| $P_{carbon}(t)$ | Policy JSON | Affects CCS competitiveness |
| Cumulative deployment | Model-endogenous | For electrolysis learning |

### Phase 2+ additional data

| Data | Source | Notes |
|------|--------|-------|
| CHP heat-to-power ratios | IEA CHP data | For CHP technologies |
| Industrial waste heat potential | IEA, national surveys | For DH waste heat recovery |
| SAF production cost curves | IEA, IRENA | For aviation biofuels |
| H₂ distribution costs | IEA Hydrogen report | For pipeline/trucking cost |


## 9. Module Interfaces (Phase 2+)

Same multiplier pattern as electricity:

| Parameter | Affects | Phase 1 | Phase 2+ source |
|-----------|---------|---------|----------------|
| `biomass_supply` | Biofuels + solid biomass ceiling | Exogenous | AFOLU land allocation |
| `crude_supply` | Refined oil ceiling | Trade module | Trade module |
| `eff_multiplier[refining]` | Refining efficiency | 1.0 | Climate (cooling water) |

### Feedback directions

```
AFOLU → Biorefining:
  Land allocation → biomass supply constraint
  Energy crop yields → biomass price

Biorefining → AFOLU:
  Biomass demand → land pressure for energy crops

Electricity → H₂:
  Electricity price → electrolysis LCOH (dominant cost)
  Renewable curtailment → cheap off-peak electrolysis (Phase 2+)

H₂ → Electricity:
  H₂ demand → electricity demand (electrolysis load)
  H₂ turbines → electricity supply (fuel cell / combustion)

Buildings → District Heating:
  Heat carrier demand → DH load

District Heating → Buildings:
  Heat carrier price → Buildings logit (competes with individual boilers/heat pumps)
```


## 10. IAMC Reporting Summary

### Secondary Energy (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Secondary Energy\|Liquids` | Refined Oil + Biofuels |
| `Secondary Energy\|Liquids\|Oil` | Refined Oil |
| `Secondary Energy\|Liquids\|Biomass` | Biofuels |
| `Secondary Energy\|Hydrogen` | H₂ total |
| `Secondary Energy\|Heat` | District Heat total |

### Emissions (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Emissions\|CO2\|Energy\|Supply` | Includes refining + H₂ production + district heating |

### Investment (Tier-2)

| Variable | How reported |
|----------|-------------|
| `Investment\|Energy Supply\|Hydrogen` | New H₂ capacity × capex |
| `Investment\|Energy Supply\|Liquids\|Biomass` | New biofuels capacity × capex |
| `Investment\|Energy Supply\|Heat` | New DH capacity × capex |


## 11. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| Oil Refining | Single tech (conventional) | Light/heavy crude, upgrading |
| Biorefining | 3 techs (biodiesel, ethanol, BTL) | + SAF, renewable diesel, bio-methanol |
| Hydrogen | 4 techs + CCS variants, electrolysis learning | + Ammonia cracking, LOHC, distribution cost |
| District Heating | 6 techs (boilers, HP, geothermal) | + CHP, industrial waste heat, solar thermal, seasonal storage |
| Biomass supply | Exogenous regional potential | AFOLU land allocation |
| Biofuel mandates | Policy (share constraint via $\alpha$) | + endogenous blend optimization |
| H₂ infrastructure | Not modeled | Distribution cost, storage cost |
| DH network | Fixed distribution cost | Network expansion model |

### Phase transition notes

- **Phase 1 → 2**: Oil refining gets product differentiation (light/heavy). Biorefining adds SAF for aviation. H₂ gets distribution cost and ammonia as carrier. District heating adds CHP (combined heat and power from gas turbines) and industrial waste heat. Biomass supply constrained by AFOLU land allocation.
- **Phase 2 → 3**: Refining integrates with petrochemical Industry (naphtha, feedstocks). H₂ gets LOHC (liquid organic hydrogen carriers) for long-distance transport. DH gets seasonal pit storage and solar thermal. Full circular economy linkage between transformation sectors.
