"""Calibration validation — compare model output vs calibration targets.

Produces comparison plots for:
  1. Regional FE totals (bar chart)
  2. Sector FE by region (grouped bar)
  3. Electricity tech shares (stacked bar, top regions)
  4. Carrier shares by sector (stacked bar)
  5. Global FE & GDP trajectory (line plot)

Usage:
    python -m ghim.output.calibration_validation --calibrator gcam
    python -m ghim.output.calibration_validation --calibrator ar6
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

logging.basicConfig(level=logging.WARNING)

# Consistent style
plt.rcParams.update({
    "figure.facecolor": "#FAFAF8",
    "axes.facecolor": "#FAFAF8",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 10,
})

SPRUCE = "#2C5F2D"
GCAM_COLOR = "#E8832A"
MODEL_COLOR = SPRUCE


def run_validation(
    calibrator_type: str = "gcam",
    scenario: str = "SSP2",
    output_dir: str = "ghim/output/runs/calibration",
) -> None:
    from ghim.data.ssp import load_ssp_data_r32
    from ghim.build import build_oop_model, oop_run_model, _apply_calibration
    from ghim.calibration import Calibrator, AR6Calibrator
    from ghim.core.config import BASE_YEAR, FUTURE_YEARS
    from ghim.sectors.electricity import OOPElectricitySector

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Loading SSP data for {scenario}...")
    ssp_data = load_ssp_data_r32(scenario)

    print(f"Building model with {calibrator_type} calibrator...")
    model, state, solver = build_oop_model(
        ssp_data, scenario, calibrator_type=calibrator_type,
    )
    cal = model.calibrator
    print(f"  Model: {cal.model_name}")

    # Apply calibration at base year
    _apply_calibration(model, state, BASE_YEAR)

    regions = list(model.regions.keys())
    # Top regions by FE
    fe_by_region = {}
    for r in regions:
        t = cal.get_fe_total(BASE_YEAR, r)
        fe_by_region[r] = t if t else 0
    top_regions = sorted(fe_by_region, key=fe_by_region.get, reverse=True)[:10]

    # ---------------------------------------------------------------
    # 1. Regional FE totals (bar chart)
    # ---------------------------------------------------------------
    print("  [1/5] Regional FE totals...")
    fig, ax = plt.subplots(figsize=(14, 5))
    x = np.arange(len(top_regions))
    targets = [fe_by_region[r] for r in top_regions]
    models = []
    for r in top_regions:
        rs = state.regions[r]
        region = model.regions[r]
        fe = 0.0
        for sec in region.demand_sectors:
            fe += sum(sec.compute_demand(rs, model.policy).values())
        models.append(fe)

    w = 0.35
    ax.bar(x - w / 2, targets, w, label="GCAM target", color=GCAM_COLOR, alpha=0.85)
    ax.bar(x + w / 2, models, w, label="GHIM model", color=MODEL_COLOR, alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(top_regions, rotation=45, ha="right")
    ax.set_ylabel("Final Energy (EJ/yr)")
    ax.set_title(f"Regional FE Totals — {cal.model_name} @ {BASE_YEAR}")
    ax.legend()
    for i in range(len(top_regions)):
        if targets[i] > 0:
            dev = (models[i] / targets[i] - 1) * 100
            ax.annotate(f"{dev:+.1f}%", (x[i] + w / 2, models[i]),
                        ha="center", va="bottom", fontsize=7, color="gray")
    fig.tight_layout()
    fig.savefig(out / "1_regional_fe_totals.png", dpi=150)
    plt.close(fig)

    # ---------------------------------------------------------------
    # 2. Sector FE by region (grouped bar)
    # ---------------------------------------------------------------
    print("  [2/5] Sector FE by region...")
    sectors = ["industry", "buildings", "transport"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=False)
    for ax, sec_name in zip(axes, sectors):
        tgts, mdls = [], []
        for r in top_regions:
            t = cal.get_sector_total(BASE_YEAR, sec_name, r) or 0
            rs = state.regions[r]
            region = model.regions[r]
            sec_idx = sectors.index(sec_name)
            m = sum(region.demand_sectors[sec_idx].compute_demand(rs, model.policy).values())
            tgts.append(t)
            mdls.append(m)
        x = np.arange(len(top_regions))
        ax.bar(x - w / 2, tgts, w, label="GCAM", color=GCAM_COLOR, alpha=0.85)
        ax.bar(x + w / 2, mdls, w, label="GHIM", color=MODEL_COLOR, alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(top_regions, rotation=45, ha="right", fontsize=8)
        ax.set_title(sec_name.capitalize())
        ax.set_ylabel("EJ/yr")
        for i in range(len(top_regions)):
            if tgts[i] > 0:
                dev = (mdls[i] / tgts[i] - 1) * 100
                ax.annotate(f"{dev:+.1f}%", (x[i] + w / 2, mdls[i]),
                            ha="center", va="bottom", fontsize=6, color="gray")
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Sector FE — {cal.model_name} @ {BASE_YEAR}", fontsize=13)
    fig.tight_layout()
    fig.savefig(out / "2_sector_fe_by_region.png", dpi=150)
    plt.close(fig)

    # ---------------------------------------------------------------
    # 3. Electricity tech shares (stacked bar, 6 regions)
    # ---------------------------------------------------------------
    print("  [3/5] Electricity tech shares...")
    elec_regions = top_regions[:6]
    # Core techs to show
    show_techs = ["coal", "gas_cc", "nuclear", "hydro", "solar", "wind",
                  "wind_offshore", "biomass", "oil", "solar_csp", "geothermal"]
    tech_colors = {
        "coal": "#333333", "gas_cc": "#6699CC", "nuclear": "#CC3333",
        "hydro": "#3399FF", "solar": "#FFB800", "wind": "#66CC66",
        "wind_offshore": "#339966", "biomass": "#8B4513", "oil": "#996633",
        "solar_csp": "#FF8C00", "geothermal": "#CC6699",
    }

    fig, axes = plt.subplots(2, 3, figsize=(16, 8))
    for ax, r in zip(axes.flat, elec_regions):
        target = cal.get_elec_target_shares(BASE_YEAR, r) or {}
        # Model shares from electricity sector
        region = model.regions[r]
        rs = state.regions[r]
        model_shares = {}
        for sector in region.transformation:
            if isinstance(sector, OOPElectricitySector):
                sector.compute_supply(rs, demand_ej=1.0)
                if sector.last_shares is not None:
                    for j, t in enumerate(sector.techs):
                        model_shares[t.name] = sector.last_shares[j]

        techs_present = [t for t in show_techs if target.get(t, 0) > 0.005 or model_shares.get(t, 0) > 0.005]

        x = np.arange(len(techs_present))
        tgt_vals = [target.get(t, 0) for t in techs_present]
        mdl_vals = [model_shares.get(t, 0) for t in techs_present]
        colors = [tech_colors.get(t, "#AAAAAA") for t in techs_present]

        ax.bar(x - 0.2, tgt_vals, 0.35, color=colors, alpha=0.5, edgecolor="black", linewidth=0.5)
        ax.bar(x + 0.2, mdl_vals, 0.35, color=colors, alpha=0.9, edgecolor="black", linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(techs_present, rotation=45, ha="right", fontsize=7)
        ax.set_title(r, fontsize=10)
        ax.set_ylim(0, 0.8)
        if ax in axes[:, 0]:
            ax.set_ylabel("Share")

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor="gray", alpha=0.5, label="GCAM target"),
                       Patch(facecolor="gray", alpha=0.9, label="GHIM model")]
    fig.legend(handles=legend_elements, loc="upper right", fontsize=9)
    fig.suptitle(f"Electricity Tech Shares — {cal.model_name} @ {BASE_YEAR}", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out / "3_elec_tech_shares.png", dpi=150)
    plt.close(fig)

    # ---------------------------------------------------------------
    # 4. Carrier shares by sector (stacked bar, USA)
    # ---------------------------------------------------------------
    print("  [4/5] Carrier shares (USA)...")
    carrier_colors = {
        "coal": "#333333", "gas": "#6699CC", "liquids": "#996633",
        "electricity": "#FFB800", "biomass": "#8B4513", "h2": "#66CCCC",
        "heat": "#CC6699", "biofuel": "#339966",
    }
    show_carriers = ["coal", "gas", "liquids", "electricity", "biomass", "h2", "heat", "biofuel"]
    r = "USA"

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    for ax, sec_name in zip(axes, sectors):
        target_cs = cal.get_sector_carrier_shares(BASE_YEAR, sec_name, r) or {}
        # Model carrier demands → shares
        sec_idx = sectors.index(sec_name)
        rs = state.regions[r]
        fe_dict = model.regions[r].demand_sectors[sec_idx].compute_demand(rs, model.policy)
        fe_total = sum(fe_dict.values())
        model_cs = {c: v / fe_total for c, v in fe_dict.items()} if fe_total > 0 else {}

        carriers = [c for c in show_carriers
                    if target_cs.get(c, 0) > 0.01 or model_cs.get(c, 0) > 0.01]
        x = np.arange(len(carriers))
        tgt_vals = [target_cs.get(c, 0) for c in carriers]
        mdl_vals = [model_cs.get(c, 0) for c in carriers]
        colors = [carrier_colors.get(c, "#AAAAAA") for c in carriers]

        ax.bar(x - 0.2, tgt_vals, 0.35, color=colors, alpha=0.5, edgecolor="black", linewidth=0.5)
        ax.bar(x + 0.2, mdl_vals, 0.35, color=colors, alpha=0.9, edgecolor="black", linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(carriers, rotation=45, ha="right", fontsize=8)
        ax.set_title(f"{sec_name.capitalize()} ({r})")
        ax.set_ylabel("Share")
        ax.set_ylim(0, 1.0)

    fig.legend(handles=legend_elements, loc="upper right", fontsize=9)
    fig.suptitle(f"Carrier Shares — {cal.model_name} @ {BASE_YEAR} (USA)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out / "4_carrier_shares_usa.png", dpi=150)
    plt.close(fig)

    # ---------------------------------------------------------------
    # 5. Global trajectory (line plot)
    # ---------------------------------------------------------------
    print("  [5/5] Global trajectory (running model)...")
    results = oop_run_model(ssp_data, scenario, calibrator_type=calibrator_type)

    periods = FUTURE_YEARS[:16]  # up to 2100
    gcam_gdp_t, model_gdp_t = [], []
    gcam_fe_t, model_fe_t = [], []

    for i, period in enumerate(periods):
        gcam_gdp_t.append(sum(cal.get_gdp(period, r) or 0 for r in results[i].regions) / 1000)
        model_gdp_t.append(sum(rs.gdp for rs in results[i].regions.values()) / 1000)
        gcam_fe_t.append(sum(cal.get_fe_total(period, r) or 0 for r in results[i].regions))
        model_fe_t.append(sum(sum(rs.final_demand.values()) for rs in results[i].regions.values()))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    ax1.plot(periods, gcam_gdp_t, "o--", color=GCAM_COLOR, label="GCAM target", markersize=4)
    ax1.plot(periods, model_gdp_t, "s-", color=MODEL_COLOR, label="GHIM model", markersize=4)
    ax1.set_xlabel("Year")
    ax1.set_ylabel("Trillion US$")
    ax1.set_title("Global GDP")
    ax1.legend()

    ax2.plot(periods, gcam_fe_t, "o--", color=GCAM_COLOR, label="GCAM target", markersize=4)
    ax2.plot(periods, model_fe_t, "s-", color=MODEL_COLOR, label="GHIM model", markersize=4)
    ax2.set_xlabel("Year")
    ax2.set_ylabel("EJ/yr")
    ax2.set_title("Global Final Energy")
    ax2.legend()

    # Add % deviation annotations
    for ax, tgt, mdl in [(ax1, gcam_gdp_t, model_gdp_t), (ax2, gcam_fe_t, model_fe_t)]:
        for j in [0, len(periods) // 2, -1]:
            if tgt[j] > 0:
                dev = (mdl[j] / tgt[j] - 1) * 100
                ax.annotate(f"{dev:+.1f}%", (periods[j], mdl[j]),
                            textcoords="offset points", xytext=(0, 10),
                            fontsize=8, color="gray", ha="center")

    fig.suptitle(f"Global Trajectory — {cal.model_name}", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out / "5_global_trajectory.png", dpi=150)
    plt.close(fig)

    print(f"\nAll plots saved to {out}/")
    print("  1_regional_fe_totals.png")
    print("  2_sector_fe_by_region.png")
    print("  3_elec_tech_shares.png")
    print("  4_carrier_shares_usa.png")
    print("  5_global_trajectory.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibration validation plots")
    parser.add_argument("--calibrator", default="gcam", choices=["ar6", "gcam"])
    parser.add_argument("--scenario", default="SSP2")
    parser.add_argument("--output-dir", default="ghim/output/runs/calibration")
    args = parser.parse_args()
    run_validation(args.calibrator, args.scenario, args.output_dir)
