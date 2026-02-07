# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: ghim
#     language: python
#     name: python3
# ---

# %% [markdown]
# # KLEM Macroeconomic Component Validation
#
# End-to-end validation of the KLEM (Capital–Labor–Energy–Materials) driver within GHIM,
# using **SSP2** as the reference scenario.
#
# **Model summary:**
# - Production function: $Y = A \cdot K^\alpha \cdot L^{1-\alpha}$ (DICE-style Cobb-Douglas)
# - TFP $A(t)$ calibrated from SSP GDP path so $Y_\text{model} \approx Y_\text{SSP}$ without energy shocks
# - Energy cost feedback: $\text{Net}_Y = Y - \text{EnergyCost}$, investment from Net_Y accumulates K
# - Fuel switching: MERGE-style preference logit with stock turnover
# - 10 AR6 R10 regions, 5-year timesteps, 2000–2150
#
# See `docs/klem.md` for the full technical specification.

# %%
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib

matplotlib.rcParams.update({"figure.figsize": (14, 6), "font.size": 11})

from ghim.data.ssp import load_ssp_data
from ghim.data.energy_cal import (
    DEFAULT_FINAL_DEMAND, DEFAULT_ELEC_TOTAL_EJ,
    DEFAULT_ELEC_SHARES, DEFAULT_PRIMARY_ENERGY,
)
from ghim.econ.klem import KLEMDriver
from ghim.config import (
    BASE_YEAR, MODEL_YEARS, TIMESTEP,
    CAPITAL_OUTPUT_RATIO, LABOR_FORCE_PARTICIPATION, CAPITAL_SHARE,
    SAVINGS_RATE, INVESTMENT_CAP_RATE, DEPRECIATION_RATE,
)
from ghim.regions import R10_REGIONS
from ghim.solver.recursive import run_model, build_region_model
from ghim.output.reporting import results_to_dataframe

print(f"Python {sys.version}")
print(f"Regions: {len(R10_REGIONS)}, Periods: {len(MODEL_YEARS)} ({MODEL_YEARS[0]}–{MODEL_YEARS[-1]})")
print(f"Base year: {BASE_YEAR}, Timestep: {TIMESTEP} yr")

# %% [markdown]
# ---
# ## 1. SSP2 Data Preparation

# %%
ssp_data = load_ssp_data("SSP2")
pop_df = ssp_data["population"]
gdp_df = ssp_data["gdp"]

print(f"Population shape: {pop_df.shape}")
print(f"GDP shape:        {gdp_df.shape}")
print(f"Year range:       {pop_df.columns.min()}–{pop_df.columns.max()}")

# %%
# Population and GDP trajectories by region
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

for region in R10_REGIONS:
    years = sorted(pop_df.columns)
    axes[0].plot(years, pop_df.loc[region, years], label=region, linewidth=1.2)
    axes[1].plot(years, gdp_df.loc[region, years] / 1e3, label=region, linewidth=1.2)

axes[0].set_title("Population (millions)")
axes[0].set_ylabel("Millions")
axes[0].grid(True, alpha=0.3)
axes[0].axvline(BASE_YEAR, color="gray", ls="--", alpha=0.5, label=f"Base year ({BASE_YEAR})")

axes[1].set_title("GDP PPP (trillion USD)")
axes[1].set_ylabel("Trillion USD PPP")
axes[1].grid(True, alpha=0.3)
axes[1].axvline(BASE_YEAR, color="gray", ls="--", alpha=0.5)
axes[1].legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")

plt.tight_layout()
plt.show()

# %% [markdown]
# ---
# ## 2. Base-Year KLEM Initialization
#
# For each region, the KLEM driver initializes:
# - **Capital stock**: $K_0 = Y_\text{SSP} \times \text{K/Y ratio}$ (default 3.0)
# - **Labor**: $L = \text{Population} \times \text{LFP}$ (default 0.65)
# - **TFP**: $A = Y / (K^\alpha \cdot L^{1-\alpha})$

# %%
# Build KLEMDrivers and validate initialization
init_rows = []
for region in R10_REGIONS:
    base_gdp = float(gdp_df.loc[region, BASE_YEAR])
    base_pop = float(pop_df.loc[region, BASE_YEAR])
    fd = DEFAULT_FINAL_DEMAND.get(region, {"industry": 5.0, "buildings": 5.0, "transport": 5.0})
    total_final = sum(fd.values())
    klem = KLEMDriver(base_gdp, base_pop, total_final)

    init_rows.append({
        "Region": region,
        "GDP (B$)": f"{base_gdp:,.0f}",
        "Pop (M)": f"{base_pop:,.0f}",
        "K (B$)": f"{klem.capital_stock:,.0f}",
        "K/Y": f"{klem.capital_stock / base_gdp:.2f}",
        "Labor (M)": f"{klem.labor:,.0f}",
        "TFP": f"{klem.tfp:.4f}",
        "Energy (EJ)": f"{klem.base_energy:.1f}",
    })

init_df = pd.DataFrame(init_rows)
print("Base-Year (2020) KLEM Initialization\n")
print(init_df.to_string(index=False))

# %% [markdown]
# **Checks:**
# - K/Y ratio should be exactly 3.0 for all regions (by construction)
# - TFP varies across regions (captures institutions, technology, etc.)
# - Labor = Population x 0.65

# %% [markdown]
# ---
# ## 3. TFP Trajectory Calibration
#
# Two-step algorithm:
# 1. **Backward K solve** — invert capital accumulation from K(2020) back to K(2000)
# 2. **Forward TFP** — at each year, $A(t) = Y_\text{SSP}(t) / (K(t)^\alpha \cdot L(t)^{1-\alpha})$

# %%
# Compute TFP trajectories
tfp_data = {}
klem_drivers = {}
for region in R10_REGIONS:
    base_gdp = float(gdp_df.loc[region, BASE_YEAR])
    base_pop = float(pop_df.loc[region, BASE_YEAR])
    fd = DEFAULT_FINAL_DEMAND.get(region, {"industry": 5.0, "buildings": 5.0, "transport": 5.0})
    total_final = sum(fd.values())
    klem = KLEMDriver(base_gdp, base_pop, total_final)

    ssp_gdp_series = {y: float(gdp_df.loc[region, y]) for y in MODEL_YEARS if y in gdp_df.columns}
    pop_series = {y: float(pop_df.loc[region, y]) for y in MODEL_YEARS if y in pop_df.columns}
    klem.init_tfp_trajectory(ssp_gdp_series, pop_series)
    tfp_data[region] = dict(klem._tfp_trajectory)
    klem_drivers[region] = klem

# %%
# TFP absolute level
fig, ax = plt.subplots(figsize=(14, 6))
for region in R10_REGIONS:
    years = sorted(tfp_data[region].keys())
    vals = [tfp_data[region][y] for y in years]
    ax.plot(years, vals, label=region, linewidth=1.2)
ax.axvline(BASE_YEAR, color="gray", ls="--", alpha=0.5, label=f"Base year ({BASE_YEAR})")
ax.set_title("TFP Trajectories by Region (absolute level)")
ax.set_ylabel("A(t)")
ax.grid(True, alpha=0.3)
ax.legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")
plt.tight_layout()
plt.show()

# %%
# TFP indexed to 2020 = 100
fig, ax = plt.subplots(figsize=(14, 6))
for region in R10_REGIONS:
    years = sorted(tfp_data[region].keys())
    base_val = tfp_data[region][BASE_YEAR]
    vals = [100.0 * tfp_data[region][y] / base_val for y in years]
    ax.plot(years, vals, label=region, linewidth=1.2)
ax.axhline(100, color="gray", ls=":", alpha=0.5)
ax.axvline(BASE_YEAR, color="gray", ls="--", alpha=0.5)
ax.set_title("TFP Index (2020 = 100)")
ax.set_ylabel("Index")
ax.grid(True, alpha=0.3)
ax.legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")
plt.tight_layout()
plt.show()

# %% [markdown]
# **Interpretation:** Rising TFP reflects SSP2 assumptions of continued technological progress.
# Historical TFP (2000–2015) is computed from backward-solved capital stocks, so it may
# differ from the base-year value due to different K/L ratios in the past.

# %% [markdown]
# ---
# ## 4. Full Model Run (No Trade)
#
# Run the model with trade **disabled** to isolate KLEM behavior.
# All fuel prices are exogenous constants — no supply curve or market clearing effects.

# %%
results_notrade = run_model(ssp_data, "SSP2", trade_enabled=False)
df = results_to_dataframe(results_notrade)
print(f"Results: {len(df)} rows ({len(df['region'].unique())} regions x {len(df['year'].unique())} periods)")
print(f"Columns: {list(df.columns)}")

# %% [markdown]
# ---
# ## 5. GDP Fidelity: Model vs SSP Reference
#
# The key validation: does endogenous GDP track SSP2?
# Divergence arises only through energy cost feedback.

# %%
# Scatter: gross output vs SSP reference GDP
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

future_df = df[df["year"] >= BASE_YEAR]

# Scatter
ax = axes[0]
ax.scatter(future_df["ssp_reference_gdp_billion_usd"] / 1e3,
           future_df["gross_output_billion_usd"] / 1e3,
           alpha=0.3, s=10, c="steelblue")
lim = max(future_df["ssp_reference_gdp_billion_usd"].max(),
          future_df["gross_output_billion_usd"].max()) / 1e3 * 1.05
ax.plot([0, lim], [0, lim], "k--", alpha=0.5, label="1:1 line")
ax.set_xlabel("SSP2 Reference GDP (trillion USD)")
ax.set_ylabel("Model Gross Output (trillion USD)")
ax.set_title("GDP Fidelity: Model vs SSP2")
ax.legend()
ax.grid(True, alpha=0.3)

# Relative error histogram
ax = axes[1]
errors = ((future_df["gross_output_billion_usd"] - future_df["ssp_reference_gdp_billion_usd"])
          / future_df["ssp_reference_gdp_billion_usd"] * 100)
ax.hist(errors, bins=50, color="steelblue", alpha=0.7, edgecolor="white")
ax.axvline(0, color="red", ls="--", alpha=0.5)
ax.set_xlabel("Relative Error (%)")
ax.set_ylabel("Count")
ax.set_title(f"GDP Error Distribution (mean={errors.mean():.1f}%, std={errors.std():.1f}%)")
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()

# %%
# 5x2 subplot: per-region GDP comparison
fig, axes = plt.subplots(5, 2, figsize=(16, 24), sharex=True)
axes_flat = axes.flatten()

for i, region in enumerate(R10_REGIONS):
    ax = axes_flat[i]
    rdf = df[(df["region"] == region) & (df["year"] >= BASE_YEAR)].sort_values("year")

    ax.plot(rdf["year"], rdf["ssp_reference_gdp_billion_usd"] / 1e3,
            "k-", linewidth=2, label="SSP2 reference")
    ax.plot(rdf["year"], rdf["gross_output_billion_usd"] / 1e3,
            "b--", linewidth=1.5, label="Model gross output")
    ax.plot(rdf["year"], rdf["gdp_billion_usd"] / 1e3,
            "r:", linewidth=1.5, label="Model net output")
    ax.fill_between(rdf["year"],
                     rdf["gdp_billion_usd"] / 1e3,
                     rdf["gross_output_billion_usd"] / 1e3,
                     alpha=0.15, color="orange", label="Energy cost")
    ax.set_title(region, fontsize=10)
    ax.grid(True, alpha=0.3)
    if i == 0:
        ax.legend(fontsize=7)
    ax.set_ylabel("Trillion USD")

plt.suptitle("GDP Comparison by Region: SSP2 vs Model (No Trade)", fontsize=14, y=1.01)
plt.tight_layout()
plt.show()

# %% [markdown]
# **Reading the charts:**
# - **Black line** = SSP2 reference GDP (exogenous target)
# - **Blue dashed** = model gross output $Y = A K^\alpha L^{1-\alpha}$ (endogenous)
# - **Red dotted** = net output $Y - \text{EnergyCost}$ (what drives investment)
# - **Orange shading** = energy cost wedge
#
# The gap between gross and net output widens as energy demand grows, representing the
# energy cost drag on GDP growth.

# %% [markdown]
# ---
# ## 6. Capital Stock and Investment

# %%
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

for region in R10_REGIONS:
    rdf = df[(df["region"] == region) & (df["year"] >= BASE_YEAR)].sort_values("year")
    axes[0].plot(rdf["year"], rdf["capital_stock_billion_usd"] / 1e3, label=region, linewidth=1.2)
    axes[1].plot(rdf["year"], rdf["investment_billion_usd"], label=region, linewidth=1.2)

axes[0].set_title("Capital Stock (trillion USD)")
axes[0].set_ylabel("Trillion USD")
axes[0].grid(True, alpha=0.3)

axes[1].set_title("Annual Investment (billion USD/yr)")
axes[1].set_ylabel("Billion USD/yr")
axes[1].grid(True, alpha=0.3)
axes[1].legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")

plt.tight_layout()
plt.show()

# %%
# Capital stock growth rate (%) — should be smooth
fig, ax = plt.subplots(figsize=(14, 6))
for region in R10_REGIONS:
    rdf = df[(df["region"] == region) & (df["year"] >= BASE_YEAR)].sort_values("year")
    k = rdf["capital_stock_billion_usd"].values
    growth = np.diff(k) / k[:-1] * 100
    ax.plot(rdf["year"].values[1:], growth, label=region, linewidth=1.0, alpha=0.8)
ax.axhline(0, color="gray", ls=":", alpha=0.5)
ax.set_title("Capital Stock Growth Rate (%/period)")
ax.set_ylabel("% change per 5-year period")
ax.grid(True, alpha=0.3)
ax.legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")
plt.tight_layout()
plt.show()

# %% [markdown]
# ---
# ## 7. Energy Demand

# %%
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

for region in R10_REGIONS:
    rdf = df[(df["region"] == region) & (df["year"] >= BASE_YEAR)].sort_values("year")
    axes[0].plot(rdf["year"], rdf["total_energy_ej"], label=region, linewidth=1.2)

axes[0].set_title("Total Energy Demand by Region (EJ)")
axes[0].set_ylabel("EJ")
axes[0].grid(True, alpha=0.3)
axes[0].legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")

# Global total
global_energy = df[df["year"] >= BASE_YEAR].groupby("year")["total_energy_ej"].sum()
axes[1].plot(global_energy.index, global_energy.values, "k-", linewidth=2)
axes[1].set_title("Global Total Energy Demand (EJ)")
axes[1].set_ylabel("EJ")
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
plt.show()

# %%
# Energy intensity: energy/GDP (MJ per USD)
fig, ax = plt.subplots(figsize=(14, 6))
for region in R10_REGIONS:
    rdf = df[(df["region"] == region) & (df["year"] >= BASE_YEAR)].sort_values("year")
    intensity = rdf["total_energy_ej"].values / rdf["gross_output_billion_usd"].values * 1e3  # EJ/B$ -> MJ/$
    ax.plot(rdf["year"].values, intensity, label=region, linewidth=1.2)
ax.set_title("Energy Intensity (MJ per USD GDP)")
ax.set_ylabel("MJ / USD")
ax.grid(True, alpha=0.3)
ax.legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")
plt.tight_layout()
plt.show()

# %% [markdown]
# **Energy intensity** should decline over time as TFP grows faster than energy demand
# (sub-unitary income elasticity in the demand function). This represents energy decoupling
# from economic growth.

# %% [markdown]
# ---
# ## 8. Energy Cost Feedback

# %%
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

for region in R10_REGIONS:
    rdf = df[(df["region"] == region) & (df["year"] >= BASE_YEAR)].sort_values("year")
    cost_share = rdf["energy_cost_billion_usd"].values / rdf["gross_output_billion_usd"].values * 100
    axes[0].plot(rdf["year"].values, cost_share, label=region, linewidth=1.2)

axes[0].set_title("Energy Cost as % of Gross Output")
axes[0].set_ylabel("% of GDP")
axes[0].grid(True, alpha=0.3)
axes[0].legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")

# Global energy cost share
global_cost = df[df["year"] >= BASE_YEAR].groupby("year").agg(
    energy_cost=("energy_cost_billion_usd", "sum"),
    gross_output=("gross_output_billion_usd", "sum"),
)
global_cost["share"] = global_cost["energy_cost"] / global_cost["gross_output"] * 100
axes[1].plot(global_cost.index, global_cost["share"], "k-", linewidth=2)
axes[1].set_title("Global Energy Cost Share (%)")
axes[1].set_ylabel("% of GDP")
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
plt.show()

# %%
# GDP gap: (SSP - Model) / SSP — shows cumulative impact of energy cost feedback
fig, ax = plt.subplots(figsize=(14, 6))
for region in R10_REGIONS:
    rdf = df[(df["region"] == region) & (df["year"] >= BASE_YEAR)].sort_values("year")
    gap = ((rdf["ssp_reference_gdp_billion_usd"].values - rdf["gross_output_billion_usd"].values)
           / rdf["ssp_reference_gdp_billion_usd"].values * 100)
    ax.plot(rdf["year"].values, gap, label=region, linewidth=1.2)
ax.axhline(0, color="gray", ls=":", alpha=0.5)
ax.set_title("GDP Gap: (SSP2 - Model Gross Output) / SSP2 (%)")
ax.set_ylabel("% gap")
ax.grid(True, alpha=0.3)
ax.legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")
plt.tight_layout()
plt.show()

# %% [markdown]
# **Interpretation:** The GDP gap represents the cumulative impact of the energy cost
# feedback loop. A positive gap means the model GDP is lower than SSP reference because
# energy costs reduced net output -> investment -> capital stock -> future GDP.
# A negative gap (model > SSP) can occur in early periods before the feedback accumulates.

# %% [markdown]
# ---
# ## 9. Emissions

# %%
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

for region in R10_REGIONS:
    rdf = df[(df["region"] == region) & (df["year"] >= BASE_YEAR)].sort_values("year")
    axes[0].plot(rdf["year"], rdf["emissions_mtco2"] / 1e3, label=region, linewidth=1.2)

axes[0].set_title("CO2 Emissions by Region (GtCO2)")
axes[0].set_ylabel("GtCO2")
axes[0].grid(True, alpha=0.3)
axes[0].legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")

# Global emissions
global_emis = df[df["year"] >= BASE_YEAR].groupby("year")["emissions_mtco2"].sum() / 1e3
axes[1].plot(global_emis.index, global_emis.values, "k-", linewidth=2)
axes[1].set_title("Global CO2 Emissions (GtCO2)")
axes[1].set_ylabel("GtCO2")
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
plt.show()

# %%
# Emissions intensity: tCO2/$ GDP
fig, ax = plt.subplots(figsize=(14, 6))
for region in R10_REGIONS:
    rdf = df[(df["region"] == region) & (df["year"] >= BASE_YEAR)].sort_values("year")
    intensity = rdf["emissions_mtco2"].values / rdf["gross_output_billion_usd"].values  # MtCO2/B$ = tCO2/1000$
    ax.plot(rdf["year"].values, intensity, label=region, linewidth=1.2)
ax.set_title("Carbon Intensity (MtCO2 per billion USD GDP)")
ax.set_ylabel("MtCO2 / B$")
ax.grid(True, alpha=0.3)
ax.legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")
plt.tight_layout()
plt.show()

# %% [markdown]
# ---
# ## 10. Electricity Mix Over Time

# %%
# Stacked area chart: global electricity generation by technology
ELEC_TECHS = ["coal", "gas_cc", "nuclear", "hydro", "wind", "solar", "biomass", "oil"]
ELEC_COLORS = {
    "coal": "dimgray", "gas_cc": "sandybrown", "nuclear": "mediumpurple",
    "hydro": "deepskyblue", "wind": "teal", "solar": "gold",
    "biomass": "forestgreen", "oil": "sienna",
}

fig, ax = plt.subplots(figsize=(14, 6))
years_proj = sorted(df[df["year"] >= BASE_YEAR]["year"].unique())

# Aggregate global electricity by tech
tech_data = {t: [] for t in ELEC_TECHS}
for year in years_proj:
    ydf = df[df["year"] == year]
    for tech in ELEC_TECHS:
        col = f"elec_{tech}_ej"
        if col in ydf.columns:
            tech_data[tech].append(ydf[col].sum())
        else:
            tech_data[tech].append(0.0)

bottoms = np.zeros(len(years_proj))
for tech in ELEC_TECHS:
    vals = np.array(tech_data[tech])
    ax.bar(years_proj, vals, bottom=bottoms, width=4, color=ELEC_COLORS.get(tech, "gray"),
           label=tech, edgecolor="white", linewidth=0.3)
    bottoms += vals

ax.set_title("Global Electricity Generation by Technology (EJ)")
ax.set_ylabel("EJ")
ax.legend(fontsize=8, bbox_to_anchor=(1.02, 1), loc="upper left")
ax.grid(True, alpha=0.3, axis="y")
plt.tight_layout()
plt.show()

# %% [markdown]
# ---
# ## 11. Diagnostic Summary

# %%
# Automated pass/fail checks
check_results = []
for region in R10_REGIONS:
    rdf = df[(df["region"] == region) & (df["year"] >= BASE_YEAR)]

    # GDP reproduction: model gross output within 30% of SSP reference
    max_gdp_err = abs(
        (rdf["gross_output_billion_usd"] - rdf["ssp_reference_gdp_billion_usd"])
        / rdf["ssp_reference_gdp_billion_usd"]
    ).max() * 100

    # Capital positivity
    k_positive = (rdf["capital_stock_billion_usd"] > 0).all()

    # TFP positivity
    tfp_positive = (rdf["tfp"] > 0).all()

    # Energy positivity
    e_positive = (rdf["total_energy_ej"] > 0).all()

    # Energy cost < gross output
    cost_lt_output = (rdf["energy_cost_billion_usd"] < rdf["gross_output_billion_usd"]).all()

    # Net output > 0
    net_positive = (rdf["gdp_billion_usd"] > 0).all()

    # Emissions non-negative
    emis_nonneg = (rdf["emissions_mtco2"] >= 0).all()

    check_results.append({
        "Region": region,
        "GDP err <30%": "PASS" if max_gdp_err < 30 else f"FAIL ({max_gdp_err:.0f}%)",
        "K > 0": "PASS" if k_positive else "FAIL",
        "TFP > 0": "PASS" if tfp_positive else "FAIL",
        "E > 0": "PASS" if e_positive else "FAIL",
        "Cost < Y": "PASS" if cost_lt_output else "FAIL",
        "Net Y > 0": "PASS" if net_positive else "FAIL",
        "Emis >= 0": "PASS" if emis_nonneg else "FAIL",
    })

check_df = pd.DataFrame(check_results)
print("Diagnostic Checks (all regions, projection years)\n")
print(check_df.to_string(index=False))

total_checks = len(check_df) * (len(check_df.columns) - 1)
passes = sum(1 for _, row in check_df.iterrows() for col in check_df.columns[1:] if row[col] == "PASS")
print(f"\n{passes}/{total_checks} checks passed")

# %% [markdown]
# ---
# ## 12. Summary Statistics Table

# %%
# Summary table at selected years
summary_years = [2020, 2030, 2050, 2075, 2100, 2150]
rows = []
for year in summary_years:
    ydf = df[df["year"] == year]
    if ydf.empty:
        continue
    rows.append({
        "Year": year,
        "Global GDP (T$)": f"{ydf['gross_output_billion_usd'].sum() / 1e3:.1f}",
        "Global Net Y (T$)": f"{ydf['gdp_billion_usd'].sum() / 1e3:.1f}",
        "Energy Cost (T$)": f"{ydf['energy_cost_billion_usd'].sum() / 1e3:.1f}",
        "Cost/GDP (%)": f"{ydf['energy_cost_billion_usd'].sum() / ydf['gross_output_billion_usd'].sum() * 100:.1f}",
        "Energy (EJ)": f"{ydf['total_energy_ej'].sum():.0f}",
        "Emissions (GtCO2)": f"{ydf['emissions_mtco2'].sum() / 1e3:.1f}",
        "Global K (T$)": f"{ydf['capital_stock_billion_usd'].sum() / 1e3:.1f}",
    })

summary_df = pd.DataFrame(rows)
print("Global Summary Statistics (No-Trade Run)\n")
print(summary_df.to_string(index=False))
