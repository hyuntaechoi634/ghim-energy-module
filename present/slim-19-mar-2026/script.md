# Presentation Script — Energy Module: Model Design

**Presenter**: Hyuntae Choi
**Date**: 3rd March, 2026
**Duration target**: ~15 min + Q&A

---

## Slide 1 — Title

Hi, my name is Hyuntae Choi. I am from the Integrated Assessment Modeling group at KAIST. Today I am going to present the model design of the Energy Module of the GHIM project.

---

## Slide 2 — Contents (p.1)

I will first start with a brief introduction — covering the motivation and design goals. Then we will look through the framework and data. After that, I will discuss the model design of the three core components: economy, energy system, and technology choice. Finally, I will close with some brief prototype results and next steps.

---

## Slide 3 — Section: Introduction

---

## Slide 4 — Limitations of Current IAMs (p.2)

Let me start by explaining why we are building a new model. Current integrated assessment models have several well-known limitations. On the climate side, it is difficult to integrate climate damage feedbacks into the economy. On the economy side, most IAMs lack general equilibrium feedback between energy and GDP — energy prices don't affect output. Technology change is exogenous, meaning learning curves and R&D are not endogenously modeled. Foresight is typically limited to two extremes — either fully myopic or perfect foresight. Resolution is coarse, with 5-year time steps and around 32 regions. On the computation side, small markets often dominate solution time, making the overall model slow to run and hard to solve. And reporting often requires multiple translation layers to produce IPCC-compatible output.

---

## Slide 5 — Design Goals (p.3)

These limitations motivate our six design goals. First, GHIM should replicate SSP baselines — the reference run must reproduce standard SSP trajectories before any policy is applied. Second, the energy-economy link should be endogenous — we nest energy with capital and labor in a CES production function so that energy prices feed back into GDP. Third, we want it to be easy to solve — simulation-based with multinomial logit for Phase 1, with optimization planned for Phase 2. Fourth, transparent and reproducible — open-source Python, fully documented. Fifth, easy to report — we output directly in AR6 IAMC format with no translation needed. And sixth, expandable — designed for future country disaggregation, flexible foresight, and richer nesting.

---

## Slide 6 — Model Pipeline (p.4)

Here is the data pipeline. On the left is gcamdata — the R data package used by GCAM, which integrates data from SSP, IEA, UN, FAO, CEDS, NREL, GTAP, USGS, and EDGAR. We don't use gcamdata as-is, but we build our own data pipeline based on it. The GHIM energy module processes this data and produces output in the IAMC data template format on the right, which is directly compatible with IPCC scenario databases.

---

## Slide 7 — Section: Framework & Data

---

## Slide 8 — General Model Structure by Phase (p.5)

This table summarizes the phased development plan. In Phase 1, we use 5-year time steps from 2000 to 2150, with 32 GCAM-style regions. The economy uses CES-KLE with energy as a production factor. The solution method is recursive-dynamic. The energy system uses minimum nesting sufficient for AR6 Tier-1 reporting. Trade covers global fossil fuel market clearing. In Phase 2, we plan annual resolution, 100+ country disaggregation, endogenous energy efficiency via R&D, adjustable rolling foresight, and expanded nesting for Tier-3 reporting. Two things span both phases: technology choice uses an absolute cost logit with SSP-calibrated preference weights, and technology change uses two-factor learning combining R&D knowledge and cumulative deployment.

---

## Slide 9 — Regional Classification: GCAM 32 Regions (p.6)

For Phase 1, we adopt the GCAM 32-region classification. This map shows the geographic coverage. In Phase 2, we plan to disaggregate to 100+ individual countries.

---

## Slide 10 — Model Overview (p.7)

This is the high-level model architecture. At the top, SSP scenarios provide population and TFP. These feed into the KLEM economy module, which produces GDP using a CES production function over capital, labor, and energy. GDP drives final energy demand across industry, buildings, and transport. Energy market clearing determines prices and quantities through logit-based technology choice. Below that, we have primary energy supply, transformation — power, hydrogen, and refining — and final energy supply. Emissions are calculated from the energy mix. There are three feedback loops shown: capital accumulation, the energy-macro feedback where energy prices affect output, and climate damages feeding back to TFP.

---

## Slide 11 — Input Data (p.9)

This slide lists our data sources. Energy balances come from IEA, updated to the 2023 edition for base-year 2020 calibration. Scenarios use IIASA SSP from the AR6 2024 database. Population is from UN World Population Prospects 2022 revision. Emissions from CEDS, trade from GTAP version 10, resources from NREL ATB 2021, transport from UC Davis, and land/agriculture from FAO 2024. All data flows through gcamdata version 8.2.

---

## Slide 12 — Section: Economy

---

## Slide 13 — CES-KLE Economy — Phase 1 Design (p.10)

Now let me explain the economy module. On the left, you see the nesting structure. At the bottom level, capital K and labor L combine with a CES elasticity sigma-KL. This gives value added, VA. Then VA and energy value combine at the outer nest with elasticity sigma-KLE, which is less than 1 — meaning energy is a complement. Scarce energy bottlenecks output. On the right are the key equations. Gross output Y equals a scale factor times CES of VA and energy value. Energy demand responds to both income and price. The budget constraint says savings times output equals physical investment plus R&D investment. Capital accumulates over time. The feedback loops box at the bottom shows three channels: capital accumulation, energy-macro feedback, and climate damages.

---

## Slide 14 — Phase 2 — Energy Services Nest (p.11)

In Phase 2, we plan to add an energy services nest. The key idea is that R&D spending builds a knowledge stock, and this knowledge stock can substitute for physical energy. Better insulation means less heating fuel. Smart grids mean less transmission loss. Efficient motors mean less industrial electricity. Same energy services, less physical energy. The budget constraint is unified — savings fund physical capital, energy efficiency R&D, and sector-specific R&D. More R&D means less capital in the short term, but lower energy prices in the long term.

---

## Slide 15 — CES-KLE — Parameter Interpretation (p.12)

This table summarizes the key parameters. Sigma-KL controls how easily capital replaces labor. Sigma-KLE controls how essential energy is — being less than 1 means energy is a complement. TFP captures productivity beyond K, L, and E. The CES share parameters are calibrated from base-year cost shares. The savings rate, depreciation, capital-output ratio, and labor force participation are all region-specific. The key takeaway at the bottom: sigma-KLE less than 1 means scarce energy bottlenecks output even with abundant capital and labor.

---

## Slide 16 — Calibration — Matching SSP Trajectories (p.13)

Calibration has four steps. Step 1: CES share parameters alpha are computed from base-year cost shares. Step 2: the CES scale factor is set so output equals GDP at the base year. Step 3: TFP is solved period-by-period to match the SSP GDP path. Step 4: preference weights are calibrated from the SSP energy mix at each period. The key insight on the right is that the reference run reproduces SSP exactly. TFP maps to GDP, preference weights map to energy shares. Both deviate only when policy or energy feedback changes the equilibrium. This is by design — the model's value-added comes from the deviation, not the baseline.

---

## Slide 17 — Section: Energy System

---

## Slide 18 — Energy System Overview (p.14)

This is the full energy system nesting. At the top are three demand sectors: industry, buildings, and transport, each with their own subsectors. Below that are six energy carriers: electricity, liquids, gas, solids, hydrogen, and heat. These connect to four transformation modules: electricity generation, refining, hydrogen production, and district heat. At the bottom are eight primary energy sources: coal, oil, gas, uranium, biomass, wind, solar, and hydro.

---

## Slide 19 — Industry (p.15)

Industry has six subsectors: iron and steel, chemicals, cement, non-ferrous metals, pulp and paper, and other. Iron and steel has three process routes — blast furnace, electric arc furnace, and hydrogen-based direct reduction. Chemicals splits into ammonia, HVC, and methanol. Non-ferrous metals covers aluminum, copper, and lithium. Each subsector splits into feedstock use — where carbon stays in the product — and energy use for combustion. Six carriers serve industry: liquids, gas, solids, hydrogen, electricity, and heat.

---

## Slide 20 — Buildings (p.16)

Buildings has two subsectors: residential and commercial. Each provides heating, cooling, and other services. Commercial also includes data centers as a distinct end use, driven by compute demand that scales with GDP, chip efficiency, and a PUE overhead multiplier. Data centers consume only electricity. Each end use competes across fuel carriers via logit — electricity, gas, biomass, hydrogen, and heat.

---

## Slide 21 — Transport (p.17)

Transport splits into passenger and freight. Passenger modes are LDV, bus, rail, and aviation. Freight modes are truck, rail, and shipping. Each mode competes across powertrains via logit — ICE, BEV, PHEV, FCEV, electric, SAF for aviation, and ammonia for shipping. Autonomous vehicles are nested under each powertrain as a conventional versus AV choice. AVs add tech cost but reduce driver wages for freight and time value for passengers, and improve energy intensity.

---

## Slide 22 — Demand (p.21)

This slide shows the demand equations. For industry and transport, demand equals production times energy intensity. The growth equation shows demand evolving with GDP growth, price response, and population scaling. For buildings, demand equals floorspace times a calibration coefficient, thermal load, and service density.

---

## Slide 23 — Demand — Buildings (Detail) (p.22)

Here is the buildings demand in more detail. Floorspace is measured in square meters per capita, growing with income on an S-curve with an SSP-dependent ceiling. Thermal load is driven by degree days, shell conductance, floor-to-surface ratio, and internal gains from appliances. Service density follows a logistic saturation curve as a function of income over price, with a subsistence floor and a saturation level.

---

## Slide 24 — Primary Energy Supply — Fossil Fuels (p.18)

For fossil fuels — coal, oil, and gas — we use grade-based supply curves per region. Higher prices unlock higher-cost grades. This chart shows the piecewise-linear interpolation we use, where production ramps linearly between grade points. This is smoother than a naive step function and avoids discontinuities in the solver.

---

## Slide 25 — Primary Energy Supply — Renewables & Learning (p.19)

For renewables, there is no resource depletion. Cost is determined by LCOE, which declines via two-factor learning. The formula shows cost falling with both cumulative deployment — learning by doing — and R&D knowledge stock — learning by research. Solar has a 20% LBD rate, wind 12%, nuclear 3%, and electrolysis 15%. The floor is set at 20% of initial cost to prevent unrealistically low prices.

---

## Slide 26 — Inter-Regional Trade — Global Market Clearing (p.20)

For fossil fuel trade, we find a single world price per fuel that clears the global market — total supply equals total demand across all regions. Net trade for each region is the difference between its supply and demand at that price. We also include a calibration rent — the difference between the observed regional price and the market-cleared price at the base year. This rent is fixed and carried forward as a price adder into all future clearing, so that supply is evaluated at extraction cost plus rent.

---

## Slide 27 — Section: Technology Choice

---

## Slide 28 — Technology Share (p.23)

Technology shares are determined by an absolute cost logit. The share of technology i equals alpha-i times exp of beta times cost plus preference weight, divided by the sum over all technologies. Alpha is a binary availability gate — 0 or 1 — used to ban or enable technologies. The preference weight p is SSP-calibrated and decays over time. Cost C is sector-specific: for electricity and hydrogen, it's the full LCOE including capital, O&M, fuel, and carbon costs. For industry and buildings, it's the carrier price in dollars per GJ. For transport, it's fuel cost plus the value of travel time.

---

## Slide 29 — Two-Factor Learning (p.24)

Technology costs decline via two-factor learning. The formula shows cost falling with both R&D knowledge stock — learning by research — and cumulative deployment — learning by doing. This table shows the demand-side technologies: batteries for EVs at 10% LBD rate, fuel cells at 12%, heat pumps at 10%, CCS at 5%, and hydrogen DRI at 8%. Supply-side technologies like solar, wind, and electrolysis were already covered in the renewables slide. Demand sectors inherit supply-side learning indirectly through carrier prices.

---

## Slide 30 — Vintage Retirement (p.25)

Capacity at each vintage survives only if the plant is both young enough and profitable enough. The effective capacity sums over all vintages, weighted by age-based survival and profit-based shutdown. Age-based survival follows an S-curve — the plant operates near full capacity for most of its life, then declines steeply. We use rho of 0.75, meaning the half-life is 75% of the rated lifetime. Renewables use a hard cutoff at lifetime. Profit-based shutdown is planned — when the electricity price falls below variable cost, plants gradually shut down. This is currently a stub with parameters set but not yet wired in.

---

## Slide 31 — S-Curve Shutdown (p.26)

This chart shows the age-based survival curves. On the left, you see gradual S-curve decline for coal, gas, nuclear, hydro, biomass, and oil. Coal and gas have 45 and 34-year half-lives respectively. Nuclear survives longer due to its 60-year lifetime. On the right, renewables — wind and solar — use a simple hard cutoff at 30 years. This is a simplification, but reasonable given that wind and solar have more predictable lifetimes with less variation.

---

## Slide 32 — Profit Shutdown (p.27)

This chart illustrates the profit-based shutdown concept. The x-axis is the profit rate — revenue minus variable cost over variable cost. When profit is deeply negative, most capacity shuts down. When profit is positive, most capacity runs. The median shutdown point is at negative 0.1 — plants tolerate slight losses before shutting down. This creates a smooth transition rather than an abrupt on-off switch. As I mentioned, this is currently planned but not yet implemented.

---

## Slide 33 — Construction Lead Time (p.28)

Construction lead time affects technology choice at two levels. On the left, physical delay — some technologies take years to build. We track capacity under construction by completion year using a PipelineAwareVintageStock class. Nuclear takes two periods or 10 years. Hydro takes one period. Gap-filling accounts for in-pipeline capacity so we don't over-invest. On the right, the cost effect — capital tied up during construction earns no return. Interest during construction inflates the effective capital cost. For nuclear at 10 years and 8% interest rate, effective capital cost is 2.16 times the overnight cost. This naturally discourages long-build technologies in the logit.

---

## Slide 34 — Section: Results & Next Steps

---

## Slide 35 — Prototype Results — Electricity Generation Mix (p.29)

Here are some preliminary results from the Phase 1 prototype. This chart shows the electricity generation mix under SSP2 from 2020 to 2150. You can see coal declining, renewables — especially solar and wind — growing significantly, and nuclear maintaining a stable share. This is a baseline run without any climate policy.

---

## Slide 36 — Prototype Results — GDP Trajectory (p.30)

This chart compares the GHIM model's GDP trajectory against the SSP2 reference. The blue solid line is our model output, and the black dashed line is the SSP2 reference. They track very closely, which is expected — our calibration procedure ensures the reference run reproduces SSP exactly. The deviation under policy scenarios would show the model's energy-economy feedback at work.

---

## Slide 37 — Next Steps (p.31)

This table summarizes the roadmap. Phase 1, which is the current prototype, covers the basic structure. Phase 2 extends to annual resolution, country-level disaggregation, endogenous energy efficiency via R&D, adjustable foresight, expanded nesting, and multi-sector trade. Technology choice and technology change mechanisms are designed to work across both phases without changes.

---

## Slide 38 — Workload Plan (p.31)

This slide shows the workload distribution. Jin will handle data and calibration — processing IEA energy balances, calibrating CES parameters by region, and researching how to incorporate energy net exports into the economy module by surveying open-economy structures used in IAMs. Medina will focus on research and validation — surveying the literature for income and price elasticities and learning rates, benchmarking GHIM output against the new SSP scenarios from the AR6 database, and ensuring AR6 reporting compliance.

---

## Slide 39 — Thank You

Thank you for your attention. I am happy to take any questions.

---
