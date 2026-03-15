"""Load GCAM v8.2 Reference scenario data and map to GHIM calibration targets.

Data source: BaseX query on GCAM v8.2 SSP2-Reference output database.
Files: ghim/data/external/gcam_ref/*.parquet

GCAM regions are native R32 (32 geopolitical regions) — no downscaling needed.

Units:
  - GCAM monetary: million 1990$ → converted to billion US$2010
  - GCAM population: thousand persons → converted to million
  - GCAM energy: EJ (kept as-is)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from ghim.config import GHIM_DATA_EXT
from ghim.regions_r32 import R32_REGIONS


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

# BEA GDP deflator: 1990$ → 2010$  (89.632 / 59.305)
GDP_1990_TO_2010: float = 1.5114


# ---------------------------------------------------------------------------
# GCAM → GHIM mapping dictionaries
# ---------------------------------------------------------------------------

GCAM_FUEL_TO_GHIM: dict[str, str] = {
    "delivered coal": "coal",
    "delivered gas": "gas",
    "wholesale gas": "gas",
    "refined liquids enduse": "liquids",
    "refined liquids industrial": "liquids",
    "elect_td_bld": "electricity",
    "elect_td_ind": "electricity",
    "elect_td_trn": "electricity",
    "district heat": "heat",
    "delivered biomass": "biomass",
    "traditional biomass": "biomass",
    "regional woodpulp for energy": "biomass",
    "H2 retail delivery": "h2",
    "H2 retail dispensing": "h2",
    "H2 wholesale delivery": "h2",
    "H2 wholesale dispensing": "h2",
    "H2 industrial": "h2",
}
# Excluded: alumina, scrap, global solar resource, seawater, water_td_*

GCAM_ELEC_TECH_TO_GHIM: dict[str, str] = {
    "coal (conv pul)": "coal",
    "coal (IGCC)": "coal",
    "gas (CC)": "gas_cc",
    "gas (steam/CT)": "gas_cc",
    "Gen_II_LWR": "nuclear",
    "Gen_III": "nuclear",
    "hydro": "hydro",
    "wind": "wind",
    "wind_offshore": "wind_offshore",
    "wind_storage": "wind",
    "PV": "solar",
    "PV_storage": "solar",
    "CSP": "solar_csp",
    "CSP_storage": "solar_csp",
    "rooftop_pv": "solar",
    "geothermal": "geothermal",
    "biomass (conv)": "biomass",
    "biomass (IGCC)": "biomass",
    "refined liquids (CC)": "oil",
    "refined liquids (steam/CT)": "oil",
}

# Near-zero placeholder techs not in GCAM baseline
_PLACEHOLDER_ELEC_TECHS = ("ocean", "h2_turbine", "ammonia",
                            "coal_ccs", "gas_cc_ccs", "biomass_ccs")

# Water/non-energy sectors to exclude
_EXCLUDED_SECTOR_KEYWORDS = ("water", "desalinated", "wastewater")


def _classify_gcam_sector(sector: str) -> str | None:
    """Map GCAM final_energy sector name to GHIM sector."""
    if sector.startswith("resid") or sector.startswith("comm"):
        return "buildings"
    if sector.startswith("trn_"):
        return "transport"
    if sector == "agricultural energy use":
        return "agriculture"
    if any(kw in sector for kw in _EXCLUDED_SECTOR_KEYWORDS):
        return None
    return "industry"


def _classify_gcam_bld_subsector(sector: str) -> str | None:
    """Map GCAM buildings sector to GHIM subsector name.

    GCAM structure:  resid {cooling,heating,others} {modern,TradBio,coal}_d{1-10}
                     comm  {cooling,heating,others}
    GHIM structure:  {residential,commercial}.{heating,cooling,other}
    """
    if sector.startswith("resid"):
        bld_type = "residential"
    elif sector.startswith("comm"):
        bld_type = "commercial"
    else:
        return None

    if "cooling" in sector:
        service = "cooling"
    elif "heating" in sector:
        service = "heating"
    elif "others" in sector or "other" in sector:
        service = "other"
    else:
        return None

    return f"{bld_type}.{service}"


# ---------------------------------------------------------------------------
# Parquet loading (cached)
# ---------------------------------------------------------------------------

_GCAM_DIR = GHIM_DATA_EXT / "gcam_ref"


@lru_cache(maxsize=8)
def _load_parquet(name: str) -> pd.DataFrame:
    """Load a GCAM parquet file, raising if not found."""
    path = _GCAM_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"GCAM data not found at {path}. "
            "Extract from BaseX first."
        )
    return pd.read_parquet(path)


def gcam_available() -> bool:
    """Check whether GCAM reference data files exist."""
    return all(
        (_GCAM_DIR / f"{f}.parquet").exists()
        for f in ("electricity_gen", "final_energy",
                   "national_accounts", "population")
    )


def gcam_years() -> list[int]:
    """Return sorted list of years available in GCAM national accounts."""
    if not gcam_available():
        return []
    na = _load_parquet("national_accounts")
    return sorted(na["year"].unique().tolist())


# ---------------------------------------------------------------------------
# Per-variable extraction (all return R32-level data)
# ---------------------------------------------------------------------------

def get_gcam_gdp(year: int, region: str) -> float:
    """GDP in billion US$2010 (converted from GCAM million 1990$)."""
    na = _load_parquet("national_accounts")
    row = na.loc[
        (na["region"] == region) & (na["year"] == year)
        & (na["variable"] == "GDP"),
        "value",
    ]
    if row.empty:
        return 0.0
    return float(row.iloc[0]) * GDP_1990_TO_2010 / 1000.0


def get_gcam_population(year: int, region: str) -> float:
    """Population in million (converted from thousand)."""
    pop = _load_parquet("population")
    row = pop.loc[
        (pop["region"] == region) & (pop["year"] == year),
        "population_thous",
    ]
    if row.empty:
        return 0.0
    return float(row.iloc[0]) / 1000.0


def get_gcam_capital_stock(year: int, region: str) -> float:
    """Capital stock in billion US$2010."""
    na = _load_parquet("national_accounts")
    row = na.loc[
        (na["region"] == region) & (na["year"] == year)
        & (na["variable"] == "capital-stock"),
        "value",
    ]
    if row.empty:
        return 0.0
    return float(row.iloc[0]) * GDP_1990_TO_2010 / 1000.0


def get_gcam_factor_shares(year: int, region: str) -> dict[str, float]:
    """Factor income shares (capital, labor, energy)."""
    na = _load_parquet("national_accounts")
    mask = (na["region"] == region) & (na["year"] == year)
    result: dict[str, float] = {}
    for var, key in [
        ("fac-share-capital", "capital"),
        ("fac-share-labor", "labor"),
        ("fac-share-energy", "energy"),
    ]:
        row = na.loc[mask & (na["variable"] == var), "value"]
        result[key] = float(row.iloc[0]) if not row.empty else 0.0
    return result


def get_gcam_elec_shares(year: int, region: str) -> dict[str, float]:
    """Electricity generation shares by GHIM tech name."""
    elec = _load_parquet("electricity_gen")
    df = elec.loc[(elec["region"] == region) & (elec["year"] == year)]
    if df.empty:
        return {}

    # Vectorized: map tech → GHIM, groupby sum
    mapped = df["technology"].map(GCAM_ELEC_TECH_TO_GHIM)
    valid = mapped.notna()
    if not valid.any():
        return {}

    gen = df.loc[valid, "generation_ej"].clip(lower=0)
    ghim_gen = gen.groupby(mapped[valid]).sum()
    total = ghim_gen.sum()
    if total <= 0:
        return {}

    shares = (ghim_gen / total).to_dict()

    for tech in _PLACEHOLDER_ELEC_TECHS:
        shares.setdefault(tech, 1e-6)

    total_s = sum(shares.values())
    return {k: v / total_s for k, v in shares.items()}


# ---------------------------------------------------------------------------
# Batch final-energy processing (vectorized for speed)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _build_fe_aggregates() -> pd.DataFrame:
    """Pre-compute all FE aggregates: region × year × ghim_sector × ghim_carrier.

    Returns a DataFrame with columns:
        region, year, ghim_sector, ghim_subsector, ghim_carrier, demand_ej
    Aggregated (summed) over GCAM subsectors/technologies.
    ``ghim_subsector`` is non-null only for buildings (e.g. "residential.heating").
    """
    fe = _load_parquet("final_energy")

    # Map fuel → GHIM carrier (vectorized)
    fe = fe.copy()
    fe["ghim_carrier"] = fe["fuel"].map(GCAM_FUEL_TO_GHIM)
    fe = fe.dropna(subset=["ghim_carrier"])

    # Map sector → GHIM sector (vectorized via apply, but only on unique sectors)
    sector_map = {s: _classify_gcam_sector(s) for s in fe["sector"].unique()}
    fe["ghim_sector"] = fe["sector"].map(sector_map)
    fe = fe.dropna(subset=["ghim_sector"])

    # Map sector → GHIM buildings subsector (only for buildings)
    subsector_map = {s: _classify_gcam_bld_subsector(s) for s in fe["sector"].unique()}
    fe["ghim_subsector"] = fe["sector"].map(subsector_map)

    # Clip negative demand
    fe["demand_ej"] = fe["demand_ej"].clip(lower=0)

    # Aggregate (include ghim_subsector)
    agg = (
        fe.groupby(
            ["region", "year", "ghim_sector", "ghim_subsector", "ghim_carrier"],
            as_index=False, dropna=False,
        )["demand_ej"].sum()
    )
    return agg


def get_gcam_total_final_energy(year: int, region: str) -> float:
    """Total final energy in EJ/yr (excluding water sectors)."""
    agg = _build_fe_aggregates()
    mask = (agg["region"] == region) & (agg["year"] == year)
    return float(agg.loc[mask, "demand_ej"].sum())


def get_gcam_sector_totals(year: int, region: str) -> dict[str, float]:
    """Final energy by GHIM sector (EJ/yr)."""
    agg = _build_fe_aggregates()
    mask = (agg["region"] == region) & (agg["year"] == year)
    sub = agg.loc[mask]
    if sub.empty:
        return {}
    return sub.groupby("ghim_sector")["demand_ej"].sum().to_dict()


def get_gcam_fe_carrier_shares(year: int, region: str) -> dict[str, float]:
    """Total FE carrier shares (across all demand sectors)."""
    agg = _build_fe_aggregates()
    mask = (agg["region"] == region) & (agg["year"] == year)
    sub = agg.loc[mask]
    if sub.empty:
        return {}
    carrier_abs = sub.groupby("ghim_carrier")["demand_ej"].sum()
    total = carrier_abs.sum()
    if total <= 0:
        return {}
    return (carrier_abs / total).to_dict()


def get_gcam_sector_carrier_shares(
    year: int,
    sector: str,
    region: str,
) -> dict[str, float]:
    """Carrier shares within a specific GHIM sector."""
    agg = _build_fe_aggregates()
    mask = (
        (agg["region"] == region) & (agg["year"] == year)
        & (agg["ghim_sector"] == sector)
    )
    sub = agg.loc[mask]
    if sub.empty:
        return {}

    carrier_abs = sub.groupby("ghim_carrier")["demand_ej"].sum()
    total = carrier_abs.sum()
    if total <= 0:
        return {}

    shares = (carrier_abs / total).to_dict()

    for c in ("h2", "biofuel"):
        shares.setdefault(c, 1e-6)
    total_s = sum(shares.values())
    return {k: v / total_s for k, v in shares.items()}


# ---------------------------------------------------------------------------
# Main loader: build CalibrationDataset (batch, vectorized)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4)
def load_gcam_calibration(
    source: str = "GCAM-v8.2",
    scenario: str = "SSP2-Ref",
    data_dir: Path | None = None,
) -> "CalibrationDataset":
    """Load GCAM reference data into a standardized CalibrationDataset.

    Parameters
    ----------
    source : str
        Model source label (e.g. "GCAM-v8.2").
    scenario : str
        Scenario label (e.g. "SSP2-Ref").
    data_dir : Path, optional
        Override data directory (default: ghim/data/external/gcam_ref/).

    Returns
    -------
    CalibrationDataset
        Standardized calibration targets at R32 resolution.
    """
    global _GCAM_DIR
    if data_dir is not None:
        _GCAM_DIR = data_dir
        _load_parquet.cache_clear()
        _build_fe_aggregates.cache_clear()

    from ghim.calibration import CalibrationDataset

    model_name = f"GHIM-{source}-{scenario}"
    years = gcam_years()
    available_regions = _get_available_regions()
    regions = [r for r in R32_REGIONS if r in available_regions]

    # --- Batch: national accounts ---
    na = _load_parquet("national_accounts")
    gdp: dict[str, dict[int, float]] = {}
    capital_stock: dict[str, dict[int, float]] = {}
    factor_shares: dict[str, dict[int, dict[str, float]]] = {}

    for region in regions:
        gdp[region] = {}
        capital_stock[region] = {}
        factor_shares[region] = {}
        na_r = na[na["region"] == region]

        for year in years:
            na_ry = na_r[na_r["year"] == year]
            if na_ry.empty:
                continue

            vals = dict(zip(na_ry["variable"], na_ry["value"]))

            g = vals.get("GDP", 0.0) * GDP_1990_TO_2010 / 1000.0
            if g > 0:
                gdp[region][year] = g

            k = vals.get("capital-stock", 0.0) * GDP_1990_TO_2010 / 1000.0
            if k > 0:
                capital_stock[region][year] = k

            fs = {
                "capital": vals.get("fac-share-capital", 0.0),
                "labor": vals.get("fac-share-labor", 0.0),
                "energy": vals.get("fac-share-energy", 0.0),
            }
            if any(v > 0 for v in fs.values()):
                factor_shares[region][year] = fs

    # --- Batch: population ---
    pop_df = _load_parquet("population")
    population: dict[str, dict[int, float]] = {}
    for region in regions:
        population[region] = {}
        pop_r = pop_df[pop_df["region"] == region]
        for _, row in pop_r.iterrows():
            p = row["population_thous"] / 1000.0
            if p > 0:
                population[region][int(row["year"])] = p

    # --- Batch: electricity ---
    elec_df = _load_parquet("electricity_gen")
    elec_df = elec_df.copy()
    elec_df["ghim_tech"] = elec_df["technology"].map(GCAM_ELEC_TECH_TO_GHIM)
    elec_df = elec_df.dropna(subset=["ghim_tech"])
    elec_df["generation_ej"] = elec_df["generation_ej"].clip(lower=0)
    elec_agg = (
        elec_df.groupby(["region", "year", "ghim_tech"], as_index=False)
        ["generation_ej"].sum()
    )

    elec_shares: dict[str, dict[int, dict[str, float]]] = {}
    for region in regions:
        elec_shares[region] = {}
        sub = elec_agg[elec_agg["region"] == region]
        for year in sub["year"].unique():
            yr_sub = sub[sub["year"] == year]
            total = yr_sub["generation_ej"].sum()
            if total <= 0:
                continue
            shares = dict(zip(yr_sub["ghim_tech"], yr_sub["generation_ej"] / total))
            for tech in _PLACEHOLDER_ELEC_TECHS:
                shares.setdefault(tech, 1e-6)
            total_s = sum(shares.values())
            elec_shares[region][int(year)] = {k: v / total_s for k, v in shares.items()}

    # --- Batch: final energy (pre-aggregated) ---
    fe_agg = _build_fe_aggregates()

    fe_total: dict[str, dict[int, float]] = {}
    fe_carrier_shares: dict[str, dict[int, dict[str, float]]] = {}
    sector_totals: dict[str, dict[int, dict[str, float]]] = {}
    sector_carrier_shares: dict[str, dict[int, dict[str, dict[str, float]]]] = {}

    for region in regions:
        fe_total[region] = {}
        fe_carrier_shares[region] = {}
        sector_totals[region] = {}
        sector_carrier_shares[region] = {}

        sub = fe_agg[fe_agg["region"] == region]

        for year in sub["year"].unique():
            yr = int(year)
            yr_sub = sub[sub["year"] == year]

            # FE total
            ft = yr_sub["demand_ej"].sum()
            if ft > 0:
                fe_total[region][yr] = float(ft)

            # FE carrier shares
            carrier_abs = yr_sub.groupby("ghim_carrier")["demand_ej"].sum()
            total_c = carrier_abs.sum()
            if total_c > 0:
                fe_carrier_shares[region][yr] = (carrier_abs / total_c).to_dict()

            # Sector totals
            sec_tot = yr_sub.groupby("ghim_sector")["demand_ej"].sum()
            if not sec_tot.empty:
                sector_totals[region][yr] = sec_tot.to_dict()

            # Sector × carrier shares
            scs: dict[str, dict[str, float]] = {}
            for sec in yr_sub["ghim_sector"].unique():
                sec_sub = yr_sub[yr_sub["ghim_sector"] == sec]
                sec_carrier = sec_sub.groupby("ghim_carrier")["demand_ej"].sum()
                sec_total = sec_carrier.sum()
                if sec_total > 0:
                    sc = (sec_carrier / sec_total).to_dict()
                    for c in ("h2", "biofuel"):
                        sc.setdefault(c, 1e-6)
                    sc_total = sum(sc.values())
                    scs[sec] = {k: v / sc_total for k, v in sc.items()}
            if scs:
                sector_carrier_shares[region][yr] = scs

    # --- Batch: heat / H2 production (derived from demand-side carrier totals) ---
    heat_production: dict[str, dict[int, float]] = {}
    h2_production: dict[str, dict[int, float]] = {}

    for region in regions:
        heat_production[region] = {}
        h2_production[region] = {}
        sub = fe_agg[fe_agg["region"] == region]

        for year in sub["year"].unique():
            yr = int(year)
            yr_sub = sub[sub["year"] == year]

            heat_ej = float(
                yr_sub.loc[yr_sub["ghim_carrier"] == "heat", "demand_ej"].sum()
            )
            if heat_ej > 0:
                heat_production[region][yr] = heat_ej

            h2_ej = float(
                yr_sub.loc[yr_sub["ghim_carrier"] == "h2", "demand_ej"].sum()
            )
            if h2_ej > 0:
                h2_production[region][yr] = h2_ej

    # --- Batch: buildings subsector-level (heating/cooling/other × resid/comm) ---
    subsector_totals: dict[str, dict[int, dict[str, float]]] = {}
    subsector_carrier_shares: dict[str, dict[int, dict[str, dict[str, float]]]] = {}

    bld_agg = fe_agg[fe_agg["ghim_subsector"].notna()]
    for region in regions:
        subsector_totals[region] = {}
        subsector_carrier_shares[region] = {}
        bld_r = bld_agg[bld_agg["region"] == region]

        for year in bld_r["year"].unique():
            yr = int(year)
            yr_sub = bld_r[bld_r["year"] == year]

            # Subsector totals
            sub_tot = yr_sub.groupby("ghim_subsector")["demand_ej"].sum()
            if not sub_tot.empty:
                subsector_totals[region][yr] = sub_tot.to_dict()

            # Subsector × carrier shares
            sscs: dict[str, dict[str, float]] = {}
            for subsec in yr_sub["ghim_subsector"].unique():
                ss_sub = yr_sub[yr_sub["ghim_subsector"] == subsec]
                ss_carrier = ss_sub.groupby("ghim_carrier")["demand_ej"].sum()
                ss_total = ss_carrier.sum()
                if ss_total > 0:
                    sc = (ss_carrier / ss_total).to_dict()
                    for c in ("h2", "biofuel"):
                        sc.setdefault(c, 1e-6)
                    sc_total = sum(sc.values())
                    sscs[subsec] = {k: v / sc_total for k, v in sc.items()}
            if sscs:
                subsector_carrier_shares[region][yr] = sscs

    # --- Batch: electricity generation totals (incl. T&D losses, own-use) ---
    elec_generation: dict[str, dict[int, float]] = {}
    elec_agg = elec_df.copy()
    elec_agg["ghim_tech"] = elec_agg["technology"].map(GCAM_ELEC_TECH_TO_GHIM)
    elec_agg = elec_agg.dropna(subset=["ghim_tech"])
    elec_agg["generation_ej"] = elec_agg["generation_ej"].clip(lower=0)
    elec_totals = elec_agg.groupby(["region", "year"])["generation_ej"].sum()

    for region in regions:
        elec_generation[region] = {}
        if region in elec_totals.index.get_level_values(0):
            for year, gen in elec_totals.loc[region].items():
                if gen > 0:
                    elec_generation[region][int(year)] = float(gen)

    return CalibrationDataset(
        model_name=model_name,
        source=source,
        scenario=scenario,
        years=years,
        regions=regions,
        gdp=gdp,
        population=population,
        capital_stock=capital_stock,
        factor_shares=factor_shares,
        elec_shares=elec_shares,
        fe_total=fe_total,
        fe_carrier_shares=fe_carrier_shares,
        sector_totals=sector_totals,
        sector_carrier_shares=sector_carrier_shares,
        subsector_totals=subsector_totals,
        subsector_carrier_shares=subsector_carrier_shares,
        elec_generation=elec_generation,
        heat_production=heat_production,
        h2_production=h2_production,
    )


@lru_cache(maxsize=1)
def _get_available_regions() -> set[str]:
    """Regions present in GCAM national accounts data."""
    na = _load_parquet("national_accounts")
    return set(na["region"].unique())
