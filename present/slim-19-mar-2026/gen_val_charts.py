#!/usr/bin/env python3
"""Regenerate validation charts: 2-panel (Global + South Korea), 1975-2100."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sys
from pathlib import Path

ACCENT = "#2C5F2D"
GCAM_COLOR = "#E8832A"
BG = "#FAFAF8"
TEXT = "#4A4A4A"
DPI = 200
OUT = Path(__file__).resolve().parent

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Calibri", "DejaVu Sans", "Arial"],
    "axes.facecolor": BG, "figure.facecolor": BG, "savefig.facecolor": BG,
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT, "ytick.color": TEXT,
    "axes.edgecolor": "#CCCCCC", "grid.color": "#E0E0E0", "grid.linewidth": 0.6,
    "axes.titlesize": 13, "axes.labelsize": 11,
    "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 9,
})

# Load GCAM-calibrated model results (2025-2150)
df = pd.read_csv(OUT / "../../ghim_output/model_results.csv")
model_years = sorted(df["year"].unique())
regions = sorted(df["region"].unique())

# Load GCAM calibration targets (1975-2100)
sys.path.insert(0, str(OUT / "../.."))
from ghim.data.gcam_cal import load_gcam_calibration
cal = load_gcam_calibration()

# GCAM full year range
gcam_years = sorted(set(y for r in regions for y in cal.gdp.get(r, {}).keys()))
# Limit everything to <= 2100
gcam_years = [y for y in gcam_years if y <= 2100]
model_years_plot = [y for y in model_years if y <= 2100]
overlap = sorted(set(model_years_plot) & set(gcam_years))


def get_gcam(field, region, year):
    d = getattr(cal, field, {})
    return d.get(region, {}).get(year, 0)


def get_gcam_dict(field, region, year):
    d = getattr(cal, field, {})
    v = d.get(region, {}).get(year, {})
    return v if isinstance(v, dict) else {}


def cc_mae(target, model):
    t, m = np.array(target, dtype=float), np.array(model, dtype=float)
    mask = np.isfinite(t) & np.isfinite(m) & (t > 0)
    t, m = t[mask], m[mask]
    if len(t) < 2:
        return 1.0, 0.0
    return float(np.corrcoef(t, m)[0, 1]), float(np.mean(np.abs(t - m)))


# ── Chart 1: GDP (2 panels) ──────────────────────────────────────
def chart_gdp():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    for ax, title, region_filter in [
        (ax1, "Global", None),
        (ax2, "South Korea", "South Korea"),
    ]:
        # GCAM targets: full 1975-2100
        if region_filter is None:
            gcam_vals = [sum(get_gcam("gdp", r, y) for r in regions) / 1000
                         for y in gcam_years]
            ghim_vals = [df[df["year"] == y]["gdp_billion_usd"].sum() / 1000
                         for y in model_years_plot]
            ylabel = "Trillion US$2010 (MER)"
        else:
            gcam_vals = [get_gcam("gdp", region_filter, y) for y in gcam_years]
            sub = df[df["region"] == region_filter]
            ghim_vals = [sub[sub["year"] == y]["gdp_billion_usd"].values[0]
                         for y in model_years_plot]
            ylabel = "Billion US$2010"

        ax.plot(gcam_years, gcam_vals, "o--", color=GCAM_COLOR, ms=4, lw=1.5,
                label="GCAM v8.2", zorder=3)
        ax.plot(model_years_plot, ghim_vals, "-", color=ACCENT, lw=2.2,
                label="GHIM (endogenous)", zorder=2)
        ax.set_title(title, fontweight="bold", color=ACCENT, pad=8)
        ax.set_ylabel(ylabel)
        ax.set_xlim(1975, 2105)
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.4)

    fig.tight_layout()
    fig.savefig(OUT / "val_gdp_2p.png", dpi=DPI)
    plt.close(fig)
    print("  saved val_gdp_2p.png")


# ── Chart 2: FE by Sector (2 panels) ─────────────────────────────
def chart_fe_sector():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))
    colors = {"industry": ACCENT, "buildings": GCAM_COLOR, "transport": "#2471A3"}

    for ax, title, region_filter in [
        (ax1, "Global", None),
        (ax2, "South Korea", "South Korea"),
    ]:
        for sname, color in colors.items():
            gcam_s = []
            for y in gcam_years:
                if region_filter is None:
                    val = sum(get_gcam_dict("sector_totals", r, y).get(sname, 0)
                              for r in regions)
                else:
                    val = get_gcam_dict("sector_totals", region_filter, y).get(sname, 0)
                gcam_s.append(val)
            ax.plot(gcam_years, gcam_s, "o--", color=color, ms=3, lw=1.2,
                    label=f"{sname.title()}")

        # Total FE
        if region_filter is None:
            ghim_fe = [df[df["year"] == y]["total_energy_ej"].sum()
                       for y in model_years_plot]
            gcam_fe = [sum(get_gcam("fe_total", r, y) for r in regions)
                       for y in gcam_years]
        else:
            sub = df[df["region"] == region_filter]
            ghim_fe = [sub[sub["year"] == y]["total_energy_ej"].values[0]
                       for y in model_years_plot]
            gcam_fe = [get_gcam("fe_total", region_filter, y) for y in gcam_years]

        ax.plot(gcam_years, gcam_fe, "s--", color="gray", ms=3, lw=1.5, alpha=0.6,
                label="Total (GCAM)")
        ax.plot(model_years_plot, ghim_fe, "-", color="black", lw=2,
                label="Total (GHIM)")

        ax.set_title(title, fontweight="bold", color=ACCENT, pad=8)
        ax.set_ylabel("EJ/yr")
        ax.set_xlim(1975, 2105)
        ax.legend(fontsize=7, ncol=2)
        ax.grid(True, alpha=0.4)

    fig.tight_layout()
    fig.savefig(OUT / "val_fe_sector_2p.png", dpi=DPI)
    plt.close(fig)
    print("  saved val_fe_sector_2p.png")


# ── Chart 3: FE by Carrier (3 panels: Industry, Buildings, Transport) ─
def chart_fe_carrier():
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    carrier_colors = {
        "electricity": "#2471A3", "gas": "#E8832A", "liquids": "#8B4513",
        "coal": "#2C3E50", "biomass": ACCENT, "h2": "#9B59B6",
        "heat": "#C0392B", "biofuel": "#27AE60",
    }

    for ax, title, region_filter in [
        (axes[0], "Global", None),
        (axes[1], "South Korea", "South Korea"),
    ]:
        # Get carrier shares from GCAM
        all_carriers = set()
        for y in gcam_years:
            if region_filter is None:
                for r in regions:
                    all_carriers.update(get_gcam_dict("fe_carrier_shares", r, y).keys())
            else:
                all_carriers.update(
                    get_gcam_dict("fe_carrier_shares", region_filter, y).keys())

        for carrier in sorted(all_carriers):
            if carrier not in carrier_colors:
                continue
            gcam_shares = []
            for y in gcam_years:
                if region_filter is None:
                    # Weighted average share across regions
                    total_fe = sum(get_gcam("fe_total", r, y) for r in regions)
                    if total_fe > 0:
                        wt_share = sum(
                            get_gcam_dict("fe_carrier_shares", r, y).get(carrier, 0)
                            * get_gcam("fe_total", r, y)
                            for r in regions
                        ) / total_fe
                    else:
                        wt_share = 0
                else:
                    wt_share = get_gcam_dict(
                        "fe_carrier_shares", region_filter, y).get(carrier, 0)
                gcam_shares.append(wt_share)

            if max(gcam_shares) > 0.01:  # skip negligible carriers
                ax.plot(gcam_years, gcam_shares, "o--", ms=2, lw=1,
                        color=carrier_colors[carrier], alpha=0.7,
                        label=f"{carrier}")

        # Model carrier shares from CSV
        carrier_cols = [c for c in df.columns if c.startswith("demand_") and c.endswith("_ej")]
        for col in carrier_cols:
            carrier = col.replace("demand_", "").replace("_ej", "")
            if carrier not in carrier_colors:
                continue
            if region_filter is None:
                model_demand = [df[df["year"] == y][col].sum() for y in model_years_plot]
                model_total = [df[df["year"] == y]["total_energy_ej"].sum()
                               for y in model_years_plot]
            else:
                sub = df[df["region"] == region_filter]
                model_demand = [sub[sub["year"] == y][col].values[0]
                                for y in model_years_plot]
                model_total = [sub[sub["year"] == y]["total_energy_ej"].values[0]
                               for y in model_years_plot]

            model_shares = [d / t if t > 0 else 0
                            for d, t in zip(model_demand, model_total)]
            if max(model_shares) > 0.01:
                ax.plot(model_years_plot, model_shares, "-", lw=1.8,
                        color=carrier_colors[carrier])

        ax.set_title(title, fontweight="bold", color=ACCENT, pad=8)
        ax.set_ylabel("Share")
        ax.set_xlim(1975, 2105)
        ax.set_ylim(0, None)
        ax.legend(fontsize=6, ncol=2, title="dashed=GCAM, solid=GHIM",
                  title_fontsize=6)
        ax.grid(True, alpha=0.4)

    fig.tight_layout()
    fig.savefig(OUT / "val_fe_carrier_2p.png", dpi=DPI)
    plt.close(fig)
    print("  saved val_fe_carrier_2p.png")


if __name__ == "__main__":
    print("Generating 2-panel validation charts (GCAM, 1975-2100)...")
    chart_gdp()
    chart_fe_sector()
    chart_fe_carrier()

    # Compute metrics on overlap
    ghim_g = [df[df["year"] == y]["gdp_billion_usd"].sum() for y in overlap]
    gcam_g = [sum(get_gcam("gdp", r, y) for r in regions) for y in overlap]
    cc, mae = cc_mae(gcam_g, ghim_g)
    print(f"  GDP: CC={cc:.6f}, MAE={mae:.1f}")

    ghim_fe = [df[df["year"] == y]["total_energy_ej"].sum() for y in overlap]
    gcam_fe = [sum(get_gcam("fe_total", r, y) for r in regions) for y in overlap]
    cc2, mae2 = cc_mae(gcam_fe, ghim_fe)
    print(f"  FE:  CC={cc2:.6f}, MAE={mae2:.1f} EJ")
    print("Done.")
