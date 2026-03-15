# GHIM Energy Module — Bunkers Sector Design

## 1. Scope

Bunkers covers **international aviation** and **international shipping** — cross-border transport energy not attributed to any single region. Modeled as a separate sector per IAMC convention (`Final Energy|Bunkers` ≠ `Final Energy|Transportation`).

Phase 1: exogenous demand scaled by world GDP, 2 powertrains per subsector competing via LCOT logit. Phase 2+: adds more powertrains (hydrogen aircraft, ammonia ships, electric).


## 2. Sector Structure

```
Bunkers (region-less)
├── Aviation                        (2 powertrains, LCOT logit)
│   ├── Jet                        → Refined Oil
│   └── SAF                        → Biofuels
│
└── Shipping                        (2 powertrains, LCOT logit)
    ├── Marine                     → Refined Oil
    └── LNG                        → Gas
```

### Powertrain → Fuel Mapping (1:1)

| Powertrain | Fuel Carrier | Phase 1 role |
|------------|-------------|-------------|
| Jet | Refined Oil | Dominant (incumbent) |
| SAF | Biofuels | Policy-driven (EU ReFuelEU mandate) |
| Marine | Refined Oil | Dominant (incumbent) |
| LNG | Gas | Growing (~30% of new ship orders) |

Every powertrain maps to exactly one carrier. Same 1:1 principle as Transport.

Both subsectors have independent demand. They do not compete with each other.


## 3. Energy Demand

### 3.1 International Aviation

$$E_{avi}(t) = E_{avi,base} \times \left(\frac{GDP_{world}(t)}{GDP_{world,base}}\right)^{\alpha_{avi}}$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $E_{avi,base}$ | Base-year international aviation energy (EJ) | IEA (~5.5 EJ) |
| $\alpha_{avi}$ | Income elasticity of international air travel | **1.0** |
| $GDP_{world}$ | World GDP (sum across regions) | Endogenous |

No price response in Phase 1 — aviation demand is highly inelastic to fuel prices (fuel is ~20–30% of operating cost; airlines pass through to tickets). Phase 2+ can add price elasticity.

### 3.2 International Shipping

$$E_{ship}(t) = E_{ship,base} \times \left(\frac{GDP_{world}(t)}{GDP_{world,base}}\right)^{\alpha_{ship}}$$

| Parameter | Meaning | Phase 1 default |
|-----------|---------|-----------------|
| $E_{ship,base}$ | Base-year international shipping energy (EJ) | IEA (~4.5 EJ) |
| $\alpha_{ship}$ | Income elasticity of international trade volume | **0.8** |
| $GDP_{world}$ | World GDP (sum across regions) | Endogenous |

Shipping tracks trade volume, which grows slower than GDP at high income levels (services grow faster than goods trade).

### 3.3 Powertrain competition

Powertrains compete via preference-factor logit on LCOT within each subsector:

$$s_i = \frac{\alpha_i \cdot \exp\!\bigl(\beta \cdot (LCOT_i + p_i)\bigr)}{\sum_j \alpha_j \cdot \exp\!\bigl(\beta \cdot (LCOT_j + p_j)\bigr)}$$

where $\alpha_i$ = availability {0, 1}, $\beta < 0$ = cost sensitivity, $LCOT_i$ = levelized cost, $p_i$ = preference factor (calibrated, decays).

Stock turnover: aircraft lifetime ~25–30 years, ship lifetime ~25–35 years. Long asset lives mean slow powertrain transitions.

### 3.4 Levelized Cost of Transport (LCOT)

$$LCOT_i = \frac{capex_i \times FCR}{annual\_SD_i} + \frac{C_{fuel,i}}{eff_i} + O\&M_i$$

| Component | Aviation | Shipping |
|-----------|----------|----------|
| $capex_i$ | Aircraft purchase/lease cost | Ship purchase/build cost |
| $annual\_SD_i$ | Annual flight-km or seat-km | Annual ton-km |
| $C_{fuel,i}$ | Jet fuel or SAF price ($/GJ) | HFO/MDO or LNG price ($/GJ) |
| $eff_i$ | Fuel efficiency (seat-km/GJ) | Fuel efficiency (ton-km/GJ) |
| $O\&M_i$ | Maintenance, crew, landing fees | Maintenance, crew, port fees |

All efficiencies **fixed** in Phase 1. Same rationale as all other sectors.

**Aviation**: SAF has same capex and efficiency as Jet (drop-in fuel, same engine). LCOT difference is purely fuel price: SAF is currently ~2–4× more expensive than jet fuel. SAF share is driven by mandates (policy) and price convergence.

**Shipping**: LNG ships have higher capex (~10–20% premium) but lower fuel cost (LNG cheaper than HFO in many regions) and comply with IMO sulfur regulations without scrubbers.

### 3.5 Fuel demand

$$E_{avi,fuel}(t) = E_{avi}(t) \times s_{pt(fuel)}^{avi}$$
$$E_{ship,fuel}(t) = E_{ship}(t) \times s_{pt(fuel)}^{ship}$$

Aviation fuel carriers: Refined Oil (Jet share) + Biofuels (SAF share).
Shipping fuel carriers: Refined Oil (Marine share) + Gas (LNG share).

### 3.6 Region-less accounting

Bunkers are **not allocated to regions**. They draw from the global fuel pool:

- Bunkers fuel demand is added to global demand before trade clearing
- No regional attribution — consistent with IEA/IAMC convention
- Emissions from bunkers reported separately


## 4. Emissions

### Carbon coefficients by fuel

| Fuel Carrier | Coef (tC/GJ) | Demand-side CO₂? |
|-------------|-------------|-------------------|
| Refined Oil | 0.0 | No (counted at refining) |
| Biofuels | 0.0 | No (biogenic) |
| Gas | 0.0153 | Yes (direct combustion) |

### Bunkers emissions calculation

$$CO2_{bunkers} = E_{ship,LNG} \times 0.0153 \times \frac{44}{12}$$

Aviation: zero demand-side emissions (Jet uses refined oil → supply-side; SAF is biogenic).
Shipping: LNG combustion is demand-side; Marine uses refined oil → supply-side.

### Memo item (for reporting)

Total bunkers combustion emissions (including supply-side attribution):

$$CO2_{bunkers}^{memo} = \sum_{sub} \sum_i \frac{E_{sub} \times s_i}{eff_i} \times coef_i^{full} \times \frac{44}{12}$$

where $coef^{full}$ uses the actual carbon content (0.0200 for refined oil, 0.0153 for gas, 0.0 for biofuels).


## 5. Calibration

### Base-year energy

From IEA World Energy Balances, "International Marine Bunkers" and "International Aviation Bunkers" rows.

### Base-year powertrain shares

| Subsector | Dominant | Alternative |
|-----------|----------|-------------|
| Aviation | Jet ~99% | SAF ~1% (growing from mandates) |
| Shipping | Marine ~95% | LNG ~5% (new orders ~30%) |

### Logit preference factors

Calibrated by inverting the logit at base year:

$$p_i = \frac{1}{\beta} \cdot \ln\!\left(\frac{S_i}{S_r}\right) - (LCOT_i - LCOT_r)$$

### Elasticities

| Parameter | Phase 1 default | Range | References |
|-----------|-----------------|-------|------------|
| $\alpha_{avi}$ (aviation) | **1.0** | 0.8–1.2 | ICAO, IEA ETP |
| $\alpha_{ship}$ (shipping) | **0.8** | 0.6–1.0 | IMO, UNCTAD Review of Maritime Transport |

Aviation elasticity higher (air travel is a luxury good at global level). Shipping elasticity tracks trade volume, which grows slower than GDP at high income levels.


## 6. User Configurables

| Parameter | Default | Configurable as |
|-----------|---------|----------------|
| $\alpha_{avi}$ (aviation income elast.) | 1.0 | Global |
| $\alpha_{ship}$ (shipping income elast.) | 0.8 | Global |
| $E_{avi,base}$, $E_{ship,base}$ | IEA values | Global |
| Powertrain set (Aviation) | 2 (Jet, SAF) | Add/remove via config |
| Powertrain set (Shipping) | 2 (Marine, LNG) | Add/remove via config |
| $capex_i$ | Per-powertrain | Per-powertrain |
| $eff_i$ | Per-powertrain | Per-powertrain |
| $O\&M_i$ | Per-powertrain | Per-powertrain |
| $\alpha_i$ (availability) | 1 for all | Per-powertrain, per-period (policy JSON) |
| $P_i$ decay rate | Per-powertrain default | Per-powertrain override (policy JSON) |
| Asset lifetime | 25–30 yr (avi), 25–35 yr (ship) | Per-powertrain |
| Logit parameter ($\beta$) | Global default | Sector override |

Bunkers parameters are **global only** (no regional dimension) since bunkers are region-less.


## 7. Data Requirements

### Base-year calibration data

| Data | Source | Resolution | Notes |
|------|--------|------------|-------|
| International aviation energy | IEA WEB | Global | "Int'l Aviation Bunkers" row |
| International shipping energy | IEA WEB | Global | "Int'l Marine Bunkers" row |
| SAF production / blend share | IEA, ICAO | Global | For base-year aviation split |
| LNG ship fleet share | Clarksons, DNV | Global | For base-year shipping split |
| Fuel prices | IEA, energy module | Global | For logit calibration |

### Exogenous trajectories

| Data | Source | Notes |
|------|--------|-------|
| $GDP_{world}(t)$ | SSP database (sum of regions) | Drives both aviation and shipping demand |
| Fuel prices(t) | Energy module | Endogenous within solver loop |

### Phase 2+ additional data

| Data | Source | Notes |
|------|--------|-------|
| Hydrogen aircraft specs | Airbus ZEROe, literature | For Phase 2+ powertrain expansion |
| Ammonia ship specs | IMO, DNV | For Phase 2+ powertrain expansion |
| SAF production cost curves | IEA, IRENA | For SAF cost convergence |
| ICAO/IMO efficiency targets | CORSIA, IMO GHG Strategy | For efficiency improvement curves |


## 8. IAMC Reporting Summary

### Final Energy (Tier-1)

| Variable | How reported |
|----------|-------------|
| `Final Energy\|Bunkers` | $E_{avi} + E_{ship}$ |
| `Final Energy\|Bunkers\|International Aviation` | $E_{avi}$ |
| `Final Energy\|Bunkers\|International Shipping` | $E_{ship}$ |
| `Final Energy\|Bunkers\|Liquids` | Refined Oil (Jet + Marine shares) |
| `Final Energy\|Bunkers\|Liquids\|Biomass` | Biofuels (SAF share) |
| `Final Energy\|Bunkers\|Gases` | Gas (LNG share) |

### Emissions

| Variable | How reported |
|----------|-------------|
| `Emissions\|CO2\|Energy\|Demand\|Bunkers` | LNG combustion (Tier-2) |


## 9. Phased Implementation

| Component | Phase 1 | Phase 2+ |
|-----------|---------|----------|
| Demand | Exogenous (GDP-scaled) | Same + trade volume linkage |
| Aviation powertrains | Jet, SAF (2) | + Hydrogen Aircraft, Electric Short-haul |
| Shipping powertrains | Marine, LNG (2) | + Ammonia, Methanol, Biofuel Marine |
| Competition | LCOT logit | Same |
| SAF mandate | Policy share constraint ($\alpha$ override) | Same + endogenous cost parity |
| Efficiency | Fixed per powertrain | IMO/ICAO efficiency target curves |
| Regional attribution | None (region-less) | Same |
| Price response | None | Price elasticity on demand |

### Phase transition notes

- **Phase 1 → 2**: Expand powertrain sets (hydrogen aircraft for short-haul, ammonia/methanol ships). Add efficiency improvement curves tied to ICAO CORSIA and IMO GHG Strategy targets. Add price elasticity to demand equations. No structural code change — just more entries in powertrain config and one extra term in demand.
- **Phase 2 → 3**: Bunkers fuel demand linked to explicit trade model (shipping volume from trade module, not just GDP proxy). Aviation connected to tourism/business travel models.
