# GHIM Energy Module — Model Structure

## Final Energy

Four demand sectors + bunkers side-account.
Tier-1 requires sector × fuel carrier only; deeper nesting provides Tier-2/3 for free.

### Fuel Carriers (7)

Electricity, Refined Oil, Biofuels, Gas, Coal, Solid Biomass, Hydrogen

| Internal Carrier | Transformation Sector | IAMC Tier-1 | IAMC Tier-2 |
|-----------------|----------------------|-------------|-------------|
| Electricity | Electricity Generation | `Electricity` | — |
| Refined Oil | Refined Oil | `Liquids` | `Liquids\|Oil` |
| Biofuels | Biofuels | `Liquids` | `Liquids\|Biomass` |
| Gas | Direct (primary) | `Gases` | — |
| Coal | Direct (primary) | `Solids` | `Solids\|Coal` |
| Solid Biomass | Direct (primary) | `Solids` | `Solids\|Biomass` |
| Hydrogen | Hydrogen Production | `Hydrogen` | — |

Four carriers (Electricity, Refined Oil, Biofuels, Hydrogen) are **secondary energy** produced by transformation sectors. Three carriers (Gas, Coal, Solid Biomass) are **primary energy** consumed directly at final demand, priced by trade module or exogenous supply.

### Sector Tree

```
Final Energy
├── Industry
│   ├── Energy Use                          × 7 carriers (logit)
│   └── Feedstocks                          × 4 carriers (logit, shareweight-constrained)
│
├── Residential and Commercial
│   ├── Residential
│   │   ├── Heating                         × 7 carriers (logit)
│   │   ├── Cooling                         × 7 carriers (logit)
│   │   └── Other                           × 7 carriers (logit)
│   └── Commercial
│       ├── Heating                         × 7 carriers (logit)
│       ├── Cooling                         × 7 carriers (logit)
│       └── Other                           × 7 carriers (logit)
│
├── Transportation
│   ├── Passenger                           (6 powertrains, LCOT logit)
│   │   ├── ICE → Refined Oil
│   │   ├── Bio-ICE → Biofuels
│   │   ├── HEV → Refined Oil
│   │   ├── BEV → Electricity
│   │   ├── FCEV → Hydrogen
│   │   └── NG → Gas
│   └── Freight                             (5 powertrains, LCOT logit)
│       ├── Diesel → Refined Oil
│       ├── Biodiesel → Biofuels
│       ├── Electric → Electricity
│       ├── FCEV → Hydrogen
│       └── NG → Gas
│
├── Agriculture                             × 7 carriers (logit)
│
└── Bunkers (exogenous GDP-scaled, region-less)
    ├── Aviation                            (2 powertrains, LCOT logit)
    │   ├── Jet → Refined Oil
    │   └── SAF → Biofuels
    └── Shipping                            (2 powertrains, LCOT logit)
        ├── Marine → Refined Oil
        └── LNG → Gas
```

### IAMC Reporting Coverage

| Tier | What it requires | How this structure reports it |
|------|-----------------|------------------------------|
| 1 | `Final Energy\|{Sector}\|{fuel}` | Sum each top-level sector × 7 carriers → IAMC fuel aggregates |
| 1 | `Final Energy\|{Sector}\|Liquids` | Refined Oil + Biofuels |
| 1 | `Final Energy\|{Sector}\|Solids` | Coal + Solid Biomass |
| 2 | `Final Energy\|{Sector}\|Liquids\|Oil` | Refined Oil carrier directly |
| 2 | `Final Energy\|{Sector}\|Liquids\|Biomass` | Biofuels carrier directly |
| 2 | `Final Energy\|{Sector}\|Solids\|Coal` | Coal carrier directly |
| 2 | `Final Energy\|{Sector}\|Solids\|Biomass` | Solid Biomass carrier directly |
| 2 | `Final Energy\|Residential\|{fuel}`, `\|Commercial\|{fuel}` | Direct from Residential / Commercial nodes |
| 2 | `Final Energy\|Transportation\|Passenger\|{fuel}`, `\|Freight\|{fuel}` | Powertrain shares → fuel carrier aggregation |
| 2 | `Final Energy\|Non-Energy Use\|{fuel}` | Direct from Feedstocks node |
| 3 | `Final Energy\|Residential\|Heating\|{fuel}`, etc. | Direct from end-use nodes |

### Design Notes

- **7 carriers**: Split Liquids into Refined Oil + Biofuels to separate fossil-derived and bio-derived liquids (different feedstock, AFOLU linkage, emissions accounting). Split Solids into Coal + Solid Biomass for same reasons.
- **Heat carrier**: District heat is included in Phase 1 as an 8th carrier. Buildings heating end-uses compete across all 8 carriers including Heat. See `DistrictHeatingSector` in implementation.md §5.5.
- **Feedstocks**: Use same preference-factor logit as Energy Use, with shareweights ($\alpha_i = 0$) blocking physically infeasible substitutions. Carbon in product — no combustion CO₂.
- **Cooling**: Near-pure electricity; logit is trivial.
- **Heating**: Main fuel competition node (gas vs heat pumps vs solid biomass vs hydrogen).
- **Transport powertrain logit**: Unlike other sectors (carrier logit), Transport uses powertrain competition on LCOT (capex + fuel + O&M). Each powertrain maps 1:1 to a fuel carrier. Consumers choose vehicles, not fuels. BEV battery learning curve enters LCOT explicitly.
- **Bunkers powertrain logit**: Same 1:1 powertrain→fuel approach. Aviation (Jet/SAF) and Shipping (Marine/LNG) each have 2 powertrains in Phase 1. Not part of Transport — IAMC reports `Final Energy|Bunkers` separately. Region-less by convention.
- **Agriculture**: Simple single-node sector with carrier logit. GDP-scaled production, fixed energy intensity (Phase 1).

## Secondary Energy | Electricity

17 technologies competing in one logit per region. CCS variants, solar PV/CSP, and wind onshore/offshore are separate technologies with independent cost and learning parameters.

### Technology Tree

```
Secondary Energy | Electricity (17 technologies, single logit per region)
├── Coal                ├── Coal w/ CCS
├── Gas                 ├── Gas w/ CCS
├── Oil
├── Biomass             ├── Biomass w/ CCS
├── Nuclear
├── Hydro
├── Solar | PV          ├── Solar | CSP
├── Wind | Onshore      ├── Wind | Offshore
├── Geothermal
├── Ocean
├── Hydrogen            ├── Ammonia
```

### IAMC Reporting Coverage

| Tier | Variable | How to report |
|------|----------|---------------|
| 1 | `Secondary Energy\|Electricity\|Coal` | Coal + Coal w/ CCS |
| 1 | `Secondary Energy\|Electricity\|Coal\|w/ CCS` | Coal w/ CCS directly |
| 1 | `Secondary Energy\|Electricity\|Coal\|w/o CCS` | Coal directly |
| 1 | `Secondary Energy\|Electricity\|Gas` | Gas + Gas w/ CCS |
| 1 | `Secondary Energy\|Electricity\|Gas\|w/ CCS` | Gas w/ CCS directly |
| 1 | `Secondary Energy\|Electricity\|Gas\|w/o CCS` | Gas directly |
| 1 | `Secondary Energy\|Electricity\|Biomass` | Biomass + Biomass w/ CCS |
| 1 | `Secondary Energy\|Electricity\|Biomass\|w/ CCS` | Biomass w/ CCS directly |
| 1 | `Secondary Energy\|Electricity\|Biomass\|w/o CCS` | Biomass directly |
| 1 | `Secondary Energy\|Electricity\|Solar` | Solar PV + Solar CSP |
| 1 | `Secondary Energy\|Electricity\|Solar\|PV` | Solar PV directly |
| 1 | `Secondary Energy\|Electricity\|Solar\|CSP` | Solar CSP directly |
| 1 | `Secondary Energy\|Electricity\|Wind` | Wind Onshore + Wind Offshore |
| 1 | `Secondary Energy\|Electricity\|Wind\|Onshore` | Wind Onshore directly |
| 1 | `Secondary Energy\|Electricity\|Wind\|Offshore` | Wind Offshore directly |
| 1 | `Secondary Energy\|Electricity\|{Nuclear, Hydro, Oil, Geothermal, Ocean, Hydrogen, Ammonia}` | Direct |
| 1 | `Capacity\|Electricity\|{source}` (GW) | From VintageStock, EJ → GW conversion |
| 2 | `Capacity Additions\|Electricity\|{source}` (GW/yr) | From VintageStock new investment |

### Design Notes

- **CCS variants**: Separate technologies in logit (higher capex + lower emissions), not a post-hoc capture rate.
- **Solar CSP**: Small globally (~6 GW vs ~1,400 GW PV) but distinct technology with thermal storage. Separate logit entry.
- **Geothermal, Ocean, Hydrogen, Ammonia**: Minor technologies (<1% global generation). Include in logit with near-zero base-year shares; can also be set exogenous if calibration is difficult.

## Secondary Energy | Other Transformation

Three non-electricity transformation sectors. See `design/electricity.md` and `design/other_transformation.md` for detailed designs.

### Technology Trees

```
Refined Oil                                        (1 tech, Phase 1)
└── Conventional Refining                (crude oil → refined products)

Biofuels                                           (3 techs)
├── Biodiesel (1st gen)                  (vegetable oils → biodiesel)
├── Cellulosic Ethanol (2nd gen)         (crop residues → ethanol)
└── Biomass-to-Liquids (BTL)             (woody biomass → synthetic fuel)

Hydrogen Production                                (7 techs incl. CCS)
├── SMR (Steam Methane Reforming)        ├── SMR w/ CCS
├── Coal Gasification                    ├── Coal Gasification w/ CCS
├── Electrolysis (green H₂)
├── Biomass Gasification                 ├── Biomass Gasification w/ CCS
```

Total: 11 technologies across 3 sectors.

### IAMC Reporting Coverage

| IAMC Variable | Source in model |
|---------------|----------------|
| `Secondary Energy\|Liquids\|Oil` | Refined Oil (conventional refining) |
| `Secondary Energy\|Liquids\|Biomass` | Biofuels (biodiesel + ethanol + BTL) |
| `Secondary Energy\|Hydrogen\|Gas` | SMR + SMR w/ CCS |
| `Secondary Energy\|Hydrogen\|Gas\|w/ CCS` | SMR w/ CCS |
| `Secondary Energy\|Hydrogen\|Gas\|w/o CCS` | SMR |
| `Secondary Energy\|Hydrogen\|Coal` | Coal Gasification + Coal Gasif. w/ CCS |
| `Secondary Energy\|Hydrogen\|Electricity` | Electrolysis |
| `Secondary Energy\|Hydrogen\|Biomass` | Biomass Gasif. + Biomass Gasif. w/ CCS |

### Design Notes

- **Refined Oil**: Single technology in Phase 1 (conventional refining, ~88–92% efficiency). Supply = demand. Phase 2+ adds light/heavy crude, upgrading, Fischer-Tropsch.
- **Biofuels separated from Refined Oil**: Different feedstock (biomass vs crude), different emissions accounting (carbon-neutral vs fossil CO₂), different AFOLU linkage (land competition for biofuels). Separate transformation sector with its own logit.
- **Hydrogen**: SMR dominates at base year (~95%). Electrolysis grows with cheap renewables; blue H₂ (SMR w/ CCS) is transitional. Learning curves on electrolysis capex.
- **No Gases/Solids transformation**: Gas is consumed directly from trade module. Solid biomass is direct primary use. District heat is a Phase 1 transformation sector. Phase 1 has 5 transformation sectors total (Elec + Hydrogen + District Heat + Biofuels + Refined Oil).

## Primary Energy

Accounting layer + resource supply. Uses **direct equivalent** method: primary energy of non-thermal sources (hydro, wind, solar, ocean) equals their electricity output. No substitution-method inflation.

### Accounting Method: Direct Equivalent

For all sources, `Primary Energy|X` = physical energy entering the system:

| Source | Primary Energy | Rationale |
|--------|---------------|-----------|
| Coal, Oil, Gas | Fuel input (EJ) | Physical fuel consumed |
| Nuclear | Electricity output (EJ) | Direct equivalent (not ÷ 0.33) |
| Hydro, Wind, Solar, Ocean | Electricity output (EJ) | No thermal process |
| Geothermal | Electricity output (EJ) | Direct equivalent |
| Biomass | Biomass input (EJ) | Physical fuel consumed (combustion) |

Label in IAMC metadata: `primary_energy_accounting: direct_equivalent`.

### Primary Energy Computation

No separate model layer — computed from secondary energy production and conversion efficiencies:

```
Primary Energy|Coal  = Σ (coal input to electricity, hydrogen, direct final use)
Primary Energy|Oil   = Σ (oil input to refined oil, electricity, direct final use)
Primary Energy|Gas   = Σ (gas input to electricity, hydrogen, direct final use)
Primary Energy|Biomass = Σ (biomass input to electricity, biofuels, hydrogen, direct final use)
Primary Energy|Nuclear = Secondary Energy|Electricity|Nuclear  (direct equivalent)
Primary Energy|Hydro   = Secondary Energy|Electricity|Hydro    (direct equivalent)
Primary Energy|Wind    = SE|Elec|Wind Onshore + SE|Elec|Wind Offshore  (direct equivalent)
Primary Energy|Solar   = SE|Elec|Solar PV + SE|Elec|Solar CSP  (direct equivalent)
Primary Energy|Geothermal = SE|Elec|Geothermal  (direct equivalent)
Primary Energy|Ocean   = Secondary Energy|Electricity|Ocean    (direct equivalent)
```

### Resource Supply

```
Primary Energy Supply
│
├── Fossil Fuels (trade module: grade-based supply curves, global market clearing)
│   ├── Coal
│   ├── Oil
│   └── Gas
│
├── Uranium (trade module: grade-based supply curves, global market clearing)
│
├── Biomass (trade module: global market clearing)
│   ├── Energy Crops                (land-constrained, future AFOLU linkage)
│   ├── Crop Residues               (agriculture output-linked)
│   ├── Forest Residues             (forestry output-linked)
│   ├── Municipal Solid Waste       (population-linked)
│   └── Traditional Biomass         (declining, SSP-driven)
│
└── Renewables (regional resource potential, not traded)
    ├── Hydro                       fixed potential (geography-limited)
    ├── Wind Onshore                graded potential (best sites first, land-constrained)
    ├── Wind Offshore               graded potential (depth/distance-limited)
    ├── Solar PV                    graded potential (best irradiance first, land-constrained)
    ├── Solar CSP                   graded potential (DNI-limited, land-constrained)
    ├── Geothermal                  fixed potential (geology-limited)
    └── Ocean                       fixed potential (coastline-limited)
```

### Trade Commodities (5)

All use the same bisection market-clearing framework:

| Commodity | Supply model | Trade |
|-----------|-------------|-------|
| Coal | Depletable, grade-based curves | Global market clearing |
| Oil | Depletable, grade-based curves | Global market clearing |
| Gas | Depletable, grade-based curves | Global market clearing |
| Uranium | Depletable, grade-based curves | Global market clearing |
| Biomass | Renewable but land-constrained, regional potential curves | Global market clearing |

### Renewable Resource Constraints

Renewable potentials cap the electricity logit from above:

```
Electricity logit → "solar PV wants 80% share"
Resource constraint → "region potential allows 60%"
→ solar PV capped at 60%, remainder redistributed to other techs
```

- **Hydro, Geothermal, Ocean**: Max capacity cap per region (no cost curve, just a ceiling)
- **Wind Onshore/Offshore, Solar PV/CSP**: Graded resource supply curves — best sites (high capacity factor) used first, cost increases as potential is exhausted. Data from NREL ATB + IRENA regional assessments.

### Design Notes

- **Biomass supply**: Exogenous regional potential curves for Phase 1 (calibrated from IPCC/IMAGE/GLOBIOM). Interface hooks for future AFOLU module — supply curve function accepts external land-use constraints as parameters.
- **Biomass trade**: Wood pellets, biofuels, and energy crops are internationally traded. Same bisection clearing as fossils, but supply is renewable (annual flow) not depletable (cumulative stock).
- **Uranium trade**: Small in energy terms but important for nuclear expansion scenarios. Same trade framework as fossils.
- **Direct equivalent choice**: Simplest accounting, avoids arbitrary reference efficiencies. If reviewers request substitution method, add a reporting conversion: `PE_sub = PE_direct / assumed_efficiency` for nuclear/geothermal.

## Prices

Derived from costs flowing through the supply chain. No separate price model — explicit bookkeeping at each level.

### Price Chain

```
Primary Price       extraction cost + rent (from trade market clearing)
      ↓ + conversion cost (capex + O&M) / efficiency + carbon price
Secondary Price     LCOE/LCOF/LCOH of transformation tech (share-weighted average)
      ↓ + transmission & distribution markup
Final Price         delivered energy price to end-user
      ↓ + sector-specific markup (taxes, cross-subsidies)
Sector Price        industry vs residential vs transport price
```

### IAMC Reporting Coverage

| Tier | Variable | Source |
|------|----------|--------|
| 1 | `Price\|Primary Energy\|{Coal, Oil, Gas}` | Trade module cleared prices |
| 1 | `Price\|Primary Energy\|Biomass` | Biomass trade cleared price |
| 1 | `Price\|Secondary Energy\|Electricity` | Share-weighted LCOE across techs |
| 1 | `Price\|Secondary Energy\|Liquids` | Share-weighted: Refined Oil and Biofuels |
| 1 | `Price\|Secondary Energy\|Hydrogen` | Share-weighted LCOH across techs |
| 1 | `Price\|Final Energy\|{fuel}` | Secondary price + T&D markup |
| 1 | `Price\|Final Energy\|{Sector}\|{fuel}` | Final price + sector markup |
| 1 | `Price\|Carbon` | Policy input (USD/t CO₂) |

### Design Notes

- **Carbon price pass-through**: Carbon cost enters at transformation level (fuel input × carbon coefficient × carbon price), flows into secondary and final prices automatically.
- **Sector markups**: Reflect real-world price differences — industry gets wholesale rates, residential pays retail with T&D, transport includes fuel taxes. Calibrated from IEA price data.
- **Expenditure-weighted composite price**: When multiple carriers serve the same demand, the composite price is expenditure-weighted (not simple average).
- **Direct carrier prices**: Gas, Coal, Solid Biomass prices come directly from trade module / exogenous supply + carbon price markup. No transformation cost.

## Investment

Derived from technology choice + vintage stock. No separate investment model — investment is the cost of filling the capacity gap after vintage retirement.

### Computation

```
For each transformation sector and technology:
  new_capacity_ej  = target_share × total_demand − surviving_vintage
  investment_usd   = new_capacity_ej × capex_per_ej (from learning curves)
```

### IAMC Reporting Coverage

| Tier | Variable | Source |
|------|----------|--------|
| 1 | `Investment\|Energy Supply` | Sum of all below |
| 1 | `Investment\|Energy Supply\|Electricity` | Sum across electricity techs |
| 1 | `Investment\|Energy Supply\|Electricity\|{source}` | Per-tech: new_capacity × capex |
| 1 | `Investment\|Energy Supply\|Extraction\|{Coal, Oil, Gas}` | From trade module supply curves |
| 1 | `Investment\|Energy Supply\|Extraction\|Uranium` | From uranium trade module |
| 1 | `Investment\|Energy Supply\|Hydrogen` | Per-tech: new_capacity × capex |
| 1 | `Investment\|Energy Supply\|Liquids\|Biomass` | Biofuels: new_capacity × capex |
| 2 | `Investment\|Energy Supply\|Electricity\|Storage` | Future addition |
| 2 | `Investment\|Energy Supply\|Electricity\|Transmission and Distribution` | Future addition |
| 2 | `Investment\|Energy Efficiency` | Future addition (Phase 2 R&D nest) |

### Design Notes

- **EJ → GW → USD**: VintageStock tracks capacity in EJ. Convert to GW via capacity factors, then multiply by capex (USD/GW) from learning curves. Report both GW (capacity) and USD (investment).
- **Extraction investment**: For traded commodities, investment in extraction is derivable from supply curve expansion — new production × marginal extraction capex.
- **28 supply technologies**: 17 electricity + 11 other transformation. Each has capex tracked via learning curves. Investment reporting is automatic from vintage stock gap-filling.
- **18 transport powertrains**: 6 passenger + 5 freight + 4 bunkers + 3 (duplicates across subsectors). Capex tracked via learning curves (BEV battery, FCEV fuel cell). Transport investment = new_vehicles × capex.

## Economy — KLEM Production Function

Upgraded from KLE to KLEM with EL/NEL split. Fixes national accounting (GDP = VA) and captures electrification and energy transition costs.

See: `design/economy.md` for detailed CES derivation, calibration procedure, and parameter choices.

### CES Nesting

```
       Y (Gross Output)
      / \                   σ_KLE_M ≈ 0.20
    KLE   M (exog.)
    / \                     σ_VA_E ≈ 0.4
  VA    E
  /\    /\                  σ_EL_NEL ≈ 2.0
 K  L  EL NEL
       σ_KL = 0.80
```

| Parameter | Value | Meaning |
|-----------|-------|---------|
| σ_KL | 0.80 | Capital–labor substitution (Oberfield & Raval 2021) |
| σ_VA_E | ~0.4 | Energy is complement to value added (essential) |
| σ_EL_NEL | ~2.0 | Electricity substitutes for non-electric (electrification) |
| σ_KLE_M | ~0.20 | Materials complement KLE |

### Key Identities

```
Y   = Gross Output = CES(KLE, M)        ← model's internal Y
Y   = Q − p_E·E − p_M·M                 ← GDP = net output (reported as GDP|PPP)
I   = s × Y                              ← investment from net output (GDP)
```

- **Q ≠ GDP**: Q is gross output; Y = GDP is net output (Q minus intermediate inputs)
- **Y = GDP**: Correct national accounting — intermediate inputs (E + M) excluded
- **EL/NEL split**: Captures electrification as key decarbonization pathway

### Phase 1 Connections

```
CES:  Y = CES(KLE, M)
           ↓         ↓
         KLE        M = m × VA (exogenous, GDP-proportional)
        / \
      VA    E
     / \   / \
    K   L EL  NEL
    ↑      ↓   ↓
    │   Energy Module (logit + vintage + trade)
    │      ↓
    │   I_energy = Σ(new_cap × capex)
    │      ↓
    └── I_K = s × VA − I_energy  (budget constraint)
```

Three connections in Phase 1:

| Connection | Direction | Mechanism |
|------------|-----------|-----------|
| **E ↔ Energy Module** | Bidirectional | CES determines E demand (EL, NEL); energy module returns prices → CES feedback |
| **K ← Budget Constraint** | Energy → Macro | I_energy crowds out I_K; energy transition has macro cost |
| **M = m × VA** | One-way | Exogenous material intensity ratio; scales with GDP |

### Budget Constraint

```
I_total  = s × Y                               # total investment (from macro)
I_energy = Σ (new_capacity × capex)            # energy investment (from vintage stock)
I_K      = I_total − I_energy                  # remainder → general capital
K(t+1)   = (1 − δ) × K(t) + I_K              # capital accumulation
```

Without this constraint, energy investment is "free" — no macro cost. With it, massive renewable buildout slows K accumulation and VA growth, capturing the real cost of energy transition.

### IAMC Reporting Coverage

| Tier | Variable | Source |
|------|----------|--------|
| 1 | `GDP\|PPP` | VA = TFP × K^α × L^(1-α) |
| 1 | `GDP\|MER` | VA × MER/PPP ratio (exogenous, World Bank) |
| 1 | `Population` | Exogenous from SSP |
| 1 | `Consumption` | (1 − s) × VA |
| 1 | `Capital Formation` | I = s × VA |
| 1 | `Value Added` | VA (= GDP) |
| 1 | `Value Added\|Agriculture` | VA × sector share (exogenous from SSP/OECD) |
| 1 | `Value Added\|Industry` | VA × sector share |
| 1 | `Value Added\|Services` | VA × sector share |
| — | `Expenditure\|Government` | Skip Phase 1 (needs fiscal model) |
| — | `Expenditure\|Households` | Skip Phase 1 (needs fiscal model) |
| — | `Revenue\|Government` | Skip Phase 1 (needs fiscal model) |
| — | `Labor Force\|*` | Skip Phase 1 (needs labor model) |

### Design Notes

- **Why KLEM over KLE**: KLE conflates gross output with GDP. KLEM separates them: Y = gross output, VA = GDP. National accounting is correct.
- **Why (KLE)(M) nesting**: Energy is nested with K and L because the key substitution channel is E → K (efficiency investment), not E → M. Also, M is exogenous in Phase 1 so separating it is cleaner.
- **Why EL/NEL split**: Electrification (σ_EL_NEL ≈ 2.0) is the dominant decarbonization pathway. Without this split, the macro CES cannot distinguish electric from fossil energy.
- **M in Phase 2+**: Connect to industry subsector models (steel, cement), material trade (GTAP), circular economy, AFOLU module.
- **Value Added by sector**: Exogenous shares from SSP/OECD structural change projections. Agriculture share declines, services share grows. Not endogenous in Phase 1.
- **Government/Labor variables**: Deferred. Energy models (WITCH, REMIND, GCAM) typically do not report these. Not expected from GHIM.

## Emissions

CO₂ from fuel combustion × emission coefficients. No separate emissions model — a reporting function over existing energy flows.

### Computation

```
Emissions = fuel_consumption (EJ) × carbon_coef (tC/GJ) × C_to_CO2 (44/12)
```

### Supply vs Demand Split

| Category | Source in model |
|----------|----------------|
| **Supply** | Fuel inputs to transformation sectors (electricity, refined oil, H₂) |
| **Demand** | Direct fuel combustion in final demand sectors (coal, gas at point of use) |

```
Emissions|CO2|Energy|Supply   = Σ (fuel input to each SE sector × coef)
Emissions|CO2|Energy|Demand   = Σ (coal + gas direct combustion in final demand)
Emissions|CO2|Energy          = Supply + Demand
Emissions|CO2                 = Energy + Industrial Processes (future)
```

- **Electricity, hydrogen**: Zero direct emissions at demand side — emissions counted at supply side
- **Refined oil**: Emissions counted at refining (supply side), not at tailpipe (demand side)
- **Biofuels**: Carbon-neutral by convention (biogenic carbon)
- **Solid biomass**: Carbon-neutral by convention (biogenic carbon)
- **Feedstocks**: No combustion CO₂ (carbon stays in product)
- **CCS**: Subtract captured CO₂ from supply emissions: `net = gross − capture_rate × gross`

### IAMC Reporting Coverage

| Tier | Variable | Source |
|------|----------|--------|
| 1 | `Emissions\|CO2` | Total net (supply + demand − CCS) |
| 1 | `Emissions\|CO2\|Energy` | Supply + Demand |
| 1 | `Emissions\|CO2\|Energy\|Supply` | Transformation sector fuel inputs × coefs |
| 1 | `Emissions\|CO2\|Energy\|Demand` | Final energy direct combustion (coal + gas only) |
| 1 | `Gross Emissions\|CO2` | Before CCS subtraction |
| 1 | `Gross Removals\|CO2` | CCS capture (BECCS = negative) |
| 1 | `Price\|Carbon` | Policy input (USD/t CO₂) |
| — | `Emissions\|CO2\|AFOLU` | Skip Phase 1 (needs land use module) |
| — | `Emissions\|CO2\|Industrial Processes` | Skip Phase 1 (needs process model) |
| — | Non-CO₂ (CH₄, N₂O, F-gases, etc.) | Skip Phase 1 (CO₂-only for now) |

### Design Notes

- **Emission coefficients**: Per-fuel tC/GJ values (coal ~0.0257, gas ~0.0153, oil ~0.0200). Already in model as `CARBON_COEFS`.
- **No separate module**: Emissions are a pure accounting function over energy flows. No additional state variables or calibration.
- **CCS accounting**: Technologies with CCS have a capture rate (e.g., 90%). Gross emissions from fuel input, net = gross × (1 − capture_rate). BECCS (biomass + CCS) produces negative net emissions.
- **Non-CO₂ and AFOLU**: Out of scope for energy module. Can be added as exogenous trajectories from CEDS/EDGAR for aggregate reporting, or deferred to future modules.
