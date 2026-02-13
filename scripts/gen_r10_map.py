"""Generate R10 world map for presentation slides."""
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import MultiPolygon
import matplotlib.patheffects as pe
import os

rc = pd.read_csv("ghim/data/external/region_classification.tsv", sep="\t")
iso_to_r10 = dict(zip(rc["ISO"], rc["region_ar6_10"]))

print("Downloading shapefile...")
world = gpd.read_file("https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip")

# --- Split multi-polygon countries with overseas territories ---
# France: mainland Europe + French Guiana (South America) + others
# We split by longitude: parts with centroid.x < -10 are in the Americas
rows_to_add = []
for idx, row in world.iterrows():
    if row["ISO_A3_EH"] == "FRA" and row.geometry.geom_type == "MultiPolygon":
        europe_parts = []
        overseas_parts = []
        for poly in row.geometry.geoms:
            if poly.centroid.x < -10:  # French Guiana
                overseas_parts.append(poly)
            else:
                europe_parts.append(poly)
        if overseas_parts:
            world.at[idx, "geometry"] = MultiPolygon(europe_parts) if len(europe_parts) > 1 else europe_parts[0]
            for p in overseas_parts:
                new_row = row.copy()
                new_row["geometry"] = p
                new_row["ISO_A3"] = "GUF"
                new_row["ISO_A3_EH"] = "GUF"
                new_row["NAME"] = "French Guiana"
                rows_to_add.append(new_row)

if rows_to_add:
    world = pd.concat([world, gpd.GeoDataFrame(rows_to_add, crs=world.crs)], ignore_index=True)

# ISO_A3 is -99 for some countries (France, Norway); fall back to ISO_A3_EH
world["ISO"] = world["ISO_A3"].where(world["ISO_A3"] != "-99", world["ISO_A3_EH"])
# Manual fixes for territories not in naturalearth with standard codes
manual = {"N. Cyprus": "Europe", "Somaliland": "Africa", "Kosovo": "Europe"}
world["R10"] = world["ISO"].map(iso_to_r10)
world["R10"] = world["R10"].fillna(world["NAME"].map(manual))
# Drop Antarctica
world = world[world["ISO"] != "ATA"]

colors = {
    "Africa": "#e6194b",
    "Asia-Pacific Developed": "#3cb44b",
    "Eastern Asia": "#ffe119",
    "Eurasia": "#4363d8",
    "Europe": "#f58231",
    "Latin America and Caribbean": "#911eb4",
    "Middle East": "#42d4f4",
    "North America": "#f032e6",
    "South-East Asia and developing Pacific": "#bfef45",
    "Southern Asia": "#fabed4",
}

world["color"] = world["R10"].map(colors).fillna("#d3d3d3")

fig, ax = plt.subplots(1, 1, figsize=(14, 7))
world.plot(ax=ax, color=world["color"], edgecolor="white", linewidth=0.3)
ax.set_axis_off()
ax.set_xlim(-180, 180)
ax.set_ylim(-60, 85)

# --- Region labels as annotations on the map ---
region_labels = {
    "Africa":                               ( 28,   8),
    "Asia-Pacific\nDeveloped":              (135, -25),
    "Eastern Asia":                         ( 98,  36),
    "Eurasia":                              ( 85,  62),
    "Europe":                               ( 12,  47),
    "Latin America\nand Caribbean":         (-65, -15),
    "Middle East":                          ( 46,  26),
    "North America":                        (-108, 48),
    "South-East Asia\nand dev. Pacific":    (120,   0),
    "Southern Asia":                        ( 75,  20),
}

# Map display names back to color keys
label_to_key = {
    "Africa": "Africa",
    "Asia-Pacific\nDeveloped": "Asia-Pacific Developed",
    "Eastern Asia": "Eastern Asia",
    "Eurasia": "Eurasia",
    "Europe": "Europe",
    "Latin America\nand Caribbean": "Latin America and Caribbean",
    "Middle East": "Middle East",
    "North America": "North America",
    "South-East Asia\nand dev. Pacific": "South-East Asia and developing Pacific",
    "Southern Asia": "Southern Asia",
}

for label, (x, y) in region_labels.items():
    color_key = label_to_key[label]
    ax.annotate(
        label, xy=(x, y), fontsize=16, fontweight="bold",
        ha="center", va="center", color=colors[color_key],
        path_effects=[pe.withStroke(linewidth=4, foreground="white")],
    )

plt.tight_layout()
out = "present/shared/images/r10_world_map.png"
os.makedirs(os.path.dirname(out), exist_ok=True)
fig.savefig(out, dpi=200, bbox_inches="tight", transparent=False)
print(f"Saved to {out}")
print(f"File exists: {os.path.exists(out)}, size: {os.path.getsize(out)} bytes")
