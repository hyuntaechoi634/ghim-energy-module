#!/usr/bin/env python3
"""Generate GCAM 32-region world map for presentation slides."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import geopandas as gpd
import pandas as pd
from shapely.geometry import box, MultiPolygon
from shapely.ops import unary_union
from pathlib import Path

ACCENT = "#2C5F2D"
BG = "#FAFAF8"
TEXT = "#4A4A4A"
DPI = 200
OUT_DIR = Path(__file__).resolve().parent
GCAMDATA = Path(__file__).resolve().parents[2] / "input" / "gcamdata" / "inst" / "extdata" / "common"

# 32 distinct colors — grouped by geography for visual coherence
REGION_COLORS = {
    "USA": "#1f77b4",
    "Canada": "#4a90d9",
    "Mexico": "#6baed6",
    "Central America and Caribbean": "#9ecae1",
    "Brazil": "#2ca02c",
    "Argentina": "#5cb85c",
    "Colombia": "#78c679",
    "South America_Northern": "#a1d99b",
    "South America_Southern": "#c7e9c0",
    "EU-15": "#d62728",
    "EU-12": "#e6550d",
    "European Free Trade Association": "#fd8d3c",
    "Europe_Non_EU": "#fdae6b",
    "Ukraine": "#fdd0a2",
    "Russia": "#9467bd",
    "Central Asia": "#c5b0d5",
    "Africa_Northern": "#8c564b",
    "Africa_Eastern": "#c49c94",
    "Africa_Western": "#bcbd22",
    "Africa_Southern": "#dbdb8d",
    "South Africa": "#e7ba52",
    "Middle East": "#e7969c",
    "India": "#ff7f0e",
    "Pakistan": "#ffbb78",
    "South Asia": "#ffc966",
    "China": "#b2182b",
    "Japan": "#17becf",
    "South Korea": "#FFD700",
    "Taiwan": "#76c7c0",
    "Indonesia": "#7f7f7f",
    "Southeast Asia": "#c7c7c7",
    "Australia_NZ": "#393b79",
}

# EU-15 members (ISO alpha-3 lowercase)
EU15 = {
    "aut", "bel", "dnk", "fin", "fra", "deu", "grc", "irl",
    "ita", "lux", "nld", "prt", "esp", "swe", "gbr",
}

# EU-12 members (2004/2007/2013 accession)
EU12 = {
    "bgr", "cyp", "cze", "est", "hrv", "hun", "ltu", "lva",
    "mlt", "pol", "rou", "svk", "svn",
}


def load_gcam_mapping():
    """Load ISO→GCAM region mapping."""
    regions = pd.read_csv(GCAMDATA / "GCAM_region_names.csv", comment="#")
    iso_map = pd.read_csv(GCAMDATA / "iso_GCAM_regID.csv", comment="#")
    merged = iso_map.merge(regions, on="GCAM_region_ID")
    # iso codes are lowercase alpha-3
    return dict(zip(merged["iso"], merged["region"]))


def gen_r32_map():
    """Generate world map colored by GCAM 32 regions."""
    iso_to_region = load_gcam_mapping()

    ne_url = "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"
    world = gpd.read_file(ne_url)
    # naturalearth uses uppercase ISO_A3; some entries are "-99" for disputed
    world["iso_lower"] = world["ISO_A3_EH"].str.lower()

    # Manual fixes for naturalearth quirks
    fixes = {
        "France": "fra", "Norway": "nor", "N. Cyprus": "cyp",
        "Somaliland": "som", "Kosovo": "xkx",
    }
    for name, iso in fixes.items():
        mask = world["NAME"] == name
        if mask.any():
            world.loc[mask, "iso_lower"] = iso

    # Split France: European part stays EU-15, overseas territories get their own regions
    fra_idx = world.index[world["iso_lower"] == "fra"]
    if len(fra_idx):
        fra_row = world.loc[fra_idx[0]]
        europe_clip = box(-10, 40, 15, 55)  # metropolitan France
        fra_europe = fra_row.geometry.intersection(europe_clip)
        fra_overseas = fra_row.geometry.difference(europe_clip)
        # Replace France with European part only
        world.loc[fra_idx[0], "geometry"] = fra_europe
        # Add French Guiana (overseas part) as South America_Northern
        if not fra_overseas.is_empty:
            overseas_row = fra_row.copy()
            overseas_row["geometry"] = fra_overseas
            overseas_row["iso_lower"] = "guf"
            world = pd.concat([world, pd.DataFrame([overseas_row])], ignore_index=True)

    world["gcam_region"] = world["iso_lower"].map(iso_to_region)
    world["color"] = world["gcam_region"].map(REGION_COLORS)
    world.loc[world["color"].isna(), "color"] = "#E8E8E8"  # unmapped = light gray

    fig, ax = plt.subplots(1, 1, figsize=(14, 6.5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    world.plot(
        ax=ax,
        color=world["color"],
        edgecolor="white",
        linewidth=0.3,
    )

    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 85)
    ax.axis("off")

    # Legend — two columns, sorted by region ID
    regions_df = pd.read_csv(GCAMDATA / "GCAM_region_names.csv", comment="#")
    patches = []
    for _, row in regions_df.iterrows():
        name = row["region"]
        color = REGION_COLORS.get(name, "#E8E8E8")
        # Shorten long names for legend
        short = name.replace("_", " ").replace("European Free Trade Association", "EFTA")
        short = short.replace("Central America and Caribbean", "C. America & Carib.")
        short = short.replace("South America Northern", "S. America N.")
        short = short.replace("South America Southern", "S. America S.")
        short = short.replace("Africa Eastern", "Africa E.")
        short = short.replace("Africa Western", "Africa W.")
        short = short.replace("Africa Northern", "Africa N.")
        short = short.replace("Africa Southern", "Africa S.")
        short = short.replace("Europe Non EU", "Europe Non-EU")
        short = short.replace("Australia NZ", "Australia/NZ")
        patches.append(mpatches.Patch(color=color, label=short))

    ax.legend(
        handles=patches,
        loc="lower left",
        bbox_to_anchor=(0.0, -0.02),
        ncol=4,
        fontsize=5.5,
        frameon=False,
        handlelength=1.0,
        handletextpad=0.4,
        columnspacing=0.8,
        labelcolor=TEXT,
    )

    out = OUT_DIR / "r32_world_map.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    gen_r32_map()
