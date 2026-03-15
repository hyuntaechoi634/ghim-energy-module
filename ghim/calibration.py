"""Calibration pipeline — preference weight computation from target data.

A ``CalibrationDataset`` (R32 resolution, common units) is wrapped in a
``Calibrator`` that provides target shares and inverse-logit preference
factors.  Default dataset: GCAM-v8.2 SSP2-Ref (1975-2100).

``CalibrationConfig`` controls:
- calibrate: bool (True = run calibration, False = load saved params)
- model_name / scenario: identify the calibration source
- cal_start / cal_end: calibration year range (auto-detected from dataset)
- run_end: model run endpoint (default = cal_end, can extend to 2150+)

Usage
-----
    from ghim.calibration import CalibrationConfig, make_calibrator

    # Default: GCAM-v8.2 SSP2-Ref, 1975-2100
    config = CalibrationConfig()
    calibrator, time_cfg = make_calibrator(config)

    # Custom dataset
    config = CalibrationConfig(
        model_name="MyModel", scenario="Baseline",
        dataset_path="path/to/data/",
    )

    # No calibration (load saved params)
    config = CalibrationConfig(calibrate=False, params_file="params.json")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from ghim.energy.logit import preference_calibrate
from ghim.config import ELEC_LOGIT_EXP, PREF_LOGIT_SCALE


# ---------------------------------------------------------------------------
# CalibrationDataset — standardized calibration targets
# ---------------------------------------------------------------------------

@dataclass
class CalibrationDataset:
    """Standardized calibration targets at R32 resolution.

    All monetary values in billion US$2010.
    All energy values in EJ/yr.
    Population in million.

    This is a *target-only* container: it holds what the model should match,
    not input parameters (costs, learning rates, etc.) which remain in the
    model's configuration.  A future extension may add an ``InputDataset``
    for user-provided cost/tech data.
    """

    model_name: str          # e.g. "GHIM-GCAM-v8.2-SSP2-Ref"
    source: str              # e.g. "GCAM-v8.2"
    scenario: str            # e.g. "SSP2-Ref"
    years: list[int] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)

    # Scalar targets: region → year → float
    gdp: dict[str, dict[int, float]] = field(default_factory=dict)
    population: dict[str, dict[int, float]] = field(default_factory=dict)
    capital_stock: dict[str, dict[int, float]] = field(default_factory=dict)
    fe_total: dict[str, dict[int, float]] = field(default_factory=dict)

    # Dict targets: region → year → dict[key → float]
    factor_shares: dict[str, dict[int, dict[str, float]]] = field(default_factory=dict)
    elec_shares: dict[str, dict[int, dict[str, float]]] = field(default_factory=dict)
    fe_carrier_shares: dict[str, dict[int, dict[str, float]]] = field(default_factory=dict)
    sector_totals: dict[str, dict[int, dict[str, float]]] = field(default_factory=dict)

    # Nested: region → year → sector → dict[carrier → share]
    sector_carrier_shares: dict[str, dict[int, dict[str, dict[str, float]]]] = field(
        default_factory=dict,
    )

    # Buildings subsector detail: region → year → subsector → value
    # subsector names: "residential.heating", "residential.cooling", "residential.other",
    #                  "commercial.heating", "commercial.cooling", "commercial.other"
    subsector_totals: dict[str, dict[int, dict[str, float]]] = field(
        default_factory=dict,
    )
    subsector_carrier_shares: dict[str, dict[int, dict[str, dict[str, float]]]] = field(
        default_factory=dict,
    )

    # Electricity generation totals: region → year → EJ
    # (includes T&D losses, own-use — larger than FE electricity demand)
    elec_generation: dict[str, dict[int, float]] = field(default_factory=dict)

    # Buildings subsector income elasticity: region → subsector → float
    # Derived from GCAM trajectory: α = ln(d_end/d_base) / ln(GDP_end/GDP_base)
    bld_sub_income_elas: dict[str, dict[str, float]] = field(default_factory=dict)

    # Electricity T&D+ownuse combined loss rate: region → year → fraction
    # loss_rate = 1 - (FE_electricity / generation)
    # Applied as: generation = FE_demand / (1 - loss_rate)
    elec_td_loss: dict[str, dict[int, float]] = field(default_factory=dict)

    # Transformation sector production: region → year → EJ
    # Derived from demand-side data: Σ(sector_total × carrier_share) across sectors
    heat_production: dict[str, dict[int, float]] = field(default_factory=dict)
    h2_production: dict[str, dict[int, float]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper: interpolate AR6 data at 5-year model years
# ---------------------------------------------------------------------------

def _interpolate_shares(
    shares_by_year: dict[int, dict[str, float]],
    target_year: int,
) -> dict[str, float]:
    """Linearly interpolate AR6 shares at a non-AR6 year."""
    years = sorted(shares_by_year.keys())
    if target_year in shares_by_year:
        return shares_by_year[target_year]
    if target_year <= years[0]:
        return shares_by_year[years[0]]
    if target_year >= years[-1]:
        return shares_by_year[years[-1]]

    # Find bracketing years
    lo = max(y for y in years if y <= target_year)
    hi = min(y for y in years if y >= target_year)
    if lo == hi:
        return shares_by_year[lo]

    alpha = (target_year - lo) / (hi - lo)
    lo_shares = shares_by_year[lo]
    hi_shares = shares_by_year[hi]
    all_techs = set(lo_shares) | set(hi_shares)
    interp = {}
    for tech in all_techs:
        v0 = lo_shares.get(tech, 0.0)
        v1 = hi_shares.get(tech, 0.0)
        interp[tech] = v0 + alpha * (v1 - v0)
    # Renormalize
    total = sum(interp.values())
    if total > 0:
        interp = {k: v / total for k, v in interp.items()}
    return interp


def _interpolate_scalar(
    values_by_year: dict[int, float],
    target_year: int,
) -> float | None:
    """Linearly interpolate a scalar AR6 quantity at a model year."""
    if not values_by_year:
        return None
    years = sorted(values_by_year.keys())
    if target_year in values_by_year:
        return values_by_year[target_year]
    if target_year <= years[0]:
        return values_by_year[years[0]]
    if target_year >= years[-1]:
        return values_by_year[years[-1]]

    lo = max(y for y in years if y <= target_year)
    hi = min(y for y in years if y >= target_year)
    if lo == hi:
        return values_by_year[lo]
    alpha = (target_year - lo) / (hi - lo)
    return values_by_year[lo] + alpha * (values_by_year[hi] - values_by_year[lo])


def _expand_carrier_shares_to_techs(
    carrier_shares: dict[str, float],
    techs: list[Any],
    costs: np.ndarray,
    logit_scale: float,
) -> np.ndarray:
    """Expand carrier-level target shares to tech-level.

    When multiple techs share the same carrier (e.g., ICE and HEV both use
    liquids), the carrier share is split using within-carrier cost competition.
    """
    n = len(techs)
    tech_shares = np.zeros(n)

    # Group techs by carrier
    groups: dict[str, list[int]] = {}
    for i, tech in enumerate(techs):
        groups.setdefault(tech.carrier, []).append(i)

    for carrier, indices in groups.items():
        c_share = carrier_shares.get(carrier, 1e-6)
        if len(indices) == 1:
            tech_shares[indices[0]] = c_share
        else:
            # Within-carrier: split by cost-based softmax (cheaper → more share)
            subset_costs = costs[indices]
            log_unnorm = -logit_scale * subset_costs
            log_unnorm -= log_unnorm.max()
            unnorm = np.exp(log_unnorm)
            within = unnorm / unnorm.sum()
            for j, idx in enumerate(indices):
                tech_shares[idx] = c_share * within[j]

    tech_shares = np.maximum(tech_shares, 1e-6)
    tech_shares /= tech_shares.sum()
    return tech_shares


# ---------------------------------------------------------------------------
# CalibrationConfig — user-facing configuration
# ---------------------------------------------------------------------------

class PostCalMode(str, Enum):
    """Post-calibration preference weight behavior."""
    DECAY = "decay"    # linear decay to 0 by run_end (default)
    HOLD = "hold"      # keep cal_end values constant


@dataclass
class CalibrationConfig:
    """Configuration for the calibration pipeline.

    Parameters
    ----------
    calibrate : bool
        True = run calibration against dataset. False = load saved params.
    model_name : str or None
        Name of the reference model (e.g. "GCAM-v8.2"). Required when
        providing a custom dataset.
    scenario : str or None
        Scenario name (e.g. "SSP2-Ref"). Required when providing a
        custom dataset.
    cal_start : int or None
        First calibration year. Auto-detected from dataset if None.
    cal_end : int or None
        Last calibration year. Auto-detected from dataset if None.
    run_end : int or None
        Last model year. Default = cal_end. Set to 2150 for projection.
    post_cal_mode : PostCalMode
        What to do with preference weights after cal_end.
        DECAY = linear decay to 0 by run_end (default).
        HOLD = keep cal_end values constant.
    dataset_path : str or None
        Path to custom calibration data directory. If None, uses
        built-in GCAM-v8.2 SSP2-Ref.
    params_file : str or None
        Path to saved calibrated params (for calibrate=False).
    """
    calibrate: bool = True
    model_name: str | None = None
    scenario: str | None = None
    cal_start: int | None = None
    cal_end: int | None = None
    run_end: int | None = None
    post_cal_mode: PostCalMode = PostCalMode.DECAY
    dataset_path: str | None = None
    params_file: str | None = None


def make_calibrator(
    config: CalibrationConfig | None = None,
) -> tuple["Calibrator", dict[str, int]]:
    """Create a Calibrator from configuration.

    Returns
    -------
    calibrator : Calibrator
    time_info : dict with keys cal_start, cal_end, run_end
    """
    if config is None:
        config = CalibrationConfig()

    if not config.calibrate:
        # Load saved params (Phase C — placeholder)
        if config.params_file is None:
            raise ValueError("calibrate=False requires params_file")
        raise NotImplementedError("Saved params loading not yet implemented")

    # Load dataset
    if config.dataset_path is not None:
        # Custom dataset — require model_name and scenario
        if config.model_name is None or config.scenario is None:
            raise ValueError(
                "When providing a custom dataset, both model_name and "
                "scenario must be specified."
            )
        # TODO: generic dataset loader for user-provided data
        raise NotImplementedError(
            f"Custom dataset loading from {config.dataset_path} "
            "not yet implemented. Use built-in GCAM-v8.2 SSP2-Ref."
        )
    else:
        # Default: GCAM-v8.2 SSP2-Ref
        from ghim.data.gcam_cal import load_gcam_calibration
        source = config.model_name or "GCAM-v8.2"
        scenario = config.scenario or "SSP2-Ref"
        dataset = load_gcam_calibration(source=source, scenario=scenario)

    calibrator = Calibrator(dataset)

    # Auto-detect time range from dataset
    all_years = set()
    for region_years in dataset.gdp.values():
        all_years |= set(region_years.keys())
    sorted_years = sorted(all_years)

    cal_start = config.cal_start or (sorted_years[0] if sorted_years else 1975)
    cal_end = config.cal_end or (sorted_years[-1] if sorted_years else 2100)
    run_end = config.run_end or cal_end

    time_info = {
        "cal_start": cal_start,
        "cal_end": cal_end,
        "post_cal_mode": config.post_cal_mode.value,
        "run_end": run_end,
    }

    return calibrator, time_info


# AR6Calibrator removed — use Calibrator + CalibrationConfig
# ---------------------------------------------------------------------------

class Calibrator:
    """General-purpose calibrator backed by a ``CalibrationDataset``.

    Same public interface as ``AR6Calibrator`` but works with any
    standardized calibration data at native R32 resolution (no R5→R32
    downscaling needed).

    Parameters
    ----------
    dataset : CalibrationDataset
        Standardized calibration targets.
    scale_k : float
        Logit sensitivity parameter.
    logit_exp : float
        Relative cost exponent (electricity sector).
    """

    native_r32: bool = True

    def __init__(
        self,
        dataset: CalibrationDataset,
        scale_k: float = PREF_LOGIT_SCALE,
        logit_exp: float = ELEC_LOGIT_EXP,
    ) -> None:
        self.dataset = dataset
        self.scale_k = scale_k
        self.logit_exp = logit_exp

    @property
    def available(self) -> bool:
        return len(self.dataset.years) > 0

    @property
    def model_name(self) -> str:
        return self.dataset.model_name

    # ---- Electricity targets ----

    def get_elec_target_shares(
        self,
        year: int,
        region_r32: str,
    ) -> dict[str, float] | None:
        year_data = self.dataset.elec_shares.get(region_r32, {})
        if not year_data:
            return None
        return _interpolate_shares(year_data, year)

    def get_fe_target_shares(
        self,
        year: int,
        region_r32: str,
    ) -> dict[str, float] | None:
        year_data = self.dataset.fe_carrier_shares.get(region_r32, {})
        if not year_data:
            return None
        return _interpolate_shares(year_data, year)

    # ---- Demand sector targets ----

    def get_sector_total(
        self,
        year: int,
        sector: str,
        region_r32: str,
    ) -> float | None:
        """Sector total FE (EJ/yr) — already at R32 resolution."""
        year_data = self.dataset.sector_totals.get(region_r32, {})
        if not year_data:
            return None
        sector_by_year = {
            y: d.get(sector, 0.0)
            for y, d in year_data.items()
            if sector in d
        }
        return _interpolate_scalar(sector_by_year, year)

    def get_fe_total(
        self,
        year: int,
        region_r32: str,
    ) -> float | None:
        year_data = self.dataset.fe_total.get(region_r32, {})
        return _interpolate_scalar(year_data, year)

    def get_gdp(
        self,
        year: int,
        region_r32: str,
    ) -> float | None:
        """GDP in billion US$2010."""
        year_data = self.dataset.gdp.get(region_r32, {})
        return _interpolate_scalar(year_data, year)

    def get_population(
        self,
        year: int,
        region_r32: str,
    ) -> float | None:
        year_data = self.dataset.population.get(region_r32, {})
        return _interpolate_scalar(year_data, year)

    def get_sector_carrier_shares(
        self,
        year: int,
        sector: str,
        region_r32: str,
    ) -> dict[str, float] | None:
        """Carrier shares within a sector — full sector×carrier detail."""
        region_data = self.dataset.sector_carrier_shares.get(region_r32, {})
        if not region_data:
            return None
        # Build year → shares for this sector
        sector_by_year: dict[int, dict[str, float]] = {}
        for y, sectors in region_data.items():
            if sector in sectors:
                sector_by_year[y] = sectors[sector]
        if not sector_by_year:
            return None
        return _interpolate_shares(sector_by_year, year)

    # ---- Bonus: GCAM national accounts ----

    def get_factor_shares(
        self,
        year: int,
        region_r32: str,
    ) -> dict[str, float] | None:
        year_data = self.dataset.factor_shares.get(region_r32, {})
        if not year_data:
            return None
        # Interpolate each share component
        keys = set()
        for d in year_data.values():
            keys |= d.keys()
        result: dict[str, float] = {}
        for key in keys:
            scalar_by_year = {y: d.get(key, 0.0) for y, d in year_data.items()}
            val = _interpolate_scalar(scalar_by_year, year)
            if val is not None:
                result[key] = val
        return result if result else None

    # ---- Buildings subsector targets ----

    def get_subsector_total(
        self,
        year: int,
        subsector: str,
        region_r32: str,
    ) -> float | None:
        """Subsector FE total (EJ/yr) — e.g. 'residential.heating'."""
        year_data = self.dataset.subsector_totals.get(region_r32, {})
        if not year_data:
            return None
        sub_by_year = {
            y: d.get(subsector, 0.0)
            for y, d in year_data.items()
            if subsector in d
        }
        return _interpolate_scalar(sub_by_year, year)

    def get_subsector_carrier_shares(
        self,
        year: int,
        subsector: str,
        region_r32: str,
    ) -> dict[str, float] | None:
        """Carrier shares within a buildings subsector."""
        region_data = self.dataset.subsector_carrier_shares.get(region_r32, {})
        if not region_data:
            return None
        sub_by_year: dict[int, dict[str, float]] = {}
        for y, subsectors in region_data.items():
            if subsector in subsectors:
                sub_by_year[y] = subsectors[subsector]
        if not sub_by_year:
            return None
        return _interpolate_shares(sub_by_year, year)

    def get_elec_generation(
        self,
        year: int,
        region_r32: str,
    ) -> float | None:
        """Target electricity generation (EJ/yr), incl. T&D losses."""
        year_data = self.dataset.elec_generation.get(region_r32, {})
        return _interpolate_scalar(year_data, year)

    def get_elec_td_loss(
        self,
        year: int,
        region_r32: str,
    ) -> float:
        """T&D+ownuse combined loss rate (fraction, 0-1)."""
        year_data = self.dataset.elec_td_loss.get(region_r32, {})
        val = _interpolate_scalar(year_data, year)
        return val if val is not None else 0.1  # default 10%

    def get_heat_production(
        self,
        year: int,
        region_r32: str,
    ) -> float | None:
        """Target district heat production (EJ/yr)."""
        year_data = self.dataset.heat_production.get(region_r32, {})
        return _interpolate_scalar(year_data, year)

    def get_h2_production(
        self,
        year: int,
        region_r32: str,
    ) -> float | None:
        """Target hydrogen production (EJ/yr)."""
        year_data = self.dataset.h2_production.get(region_r32, {})
        return _interpolate_scalar(year_data, year)

    def get_capital_stock(
        self,
        year: int,
        region_r32: str,
    ) -> float | None:
        year_data = self.dataset.capital_stock.get(region_r32, {})
        return _interpolate_scalar(year_data, year)

    # ---- Electricity preference calibration ----

    def electricity_prefs(
        self,
        year: int,
        techs: list[Any],
        fuel_prices: dict[str, float],
        region_r32: str = "USA",
        carbon_price: float = 0.0,
    ) -> np.ndarray | None:
        target = self.get_elec_target_shares(year, region_r32)
        if target is None:
            return None

        shares = np.array([target.get(t.name, 1e-6) for t in techs])
        shares = np.maximum(shares, 1e-6)
        shares /= shares.sum()

        costs = np.array([
            t.lcoe(fuel_prices, carbon_price=carbon_price) for t in techs
        ])

        return preference_calibrate(
            shares, costs, self.scale_k, logit_exp=self.logit_exp,
        )

    # ---- Demand carrier preference calibration ----

    def demand_carrier_prefs(
        self,
        year: int,
        subsector: Any,
        carrier_prices: dict[str, float],
        sector_name: str,
        region_r32: str = "USA",
    ) -> np.ndarray | None:
        target = self.get_sector_carrier_shares(year, sector_name, region_r32)
        if target is None:
            return None

        if len(subsector.techs) <= 1:
            return None

        from ghim.core.technology import Powertrain
        costs = np.array([
            t.lcot(carrier_prices.get(t.carrier, 5.0))
            if isinstance(t, Powertrain)
            else t.levelized_cost(carrier_prices.get(t.carrier, 5.0))
            for t in subsector.techs
        ])

        tech_shares = _expand_carrier_shares_to_techs(
            target, subsector.techs, costs, subsector.logit_scale,
        )

        return preference_calibrate(
            tech_shares, costs, subsector.logit_scale,
        )

    # ---- Summary ----

    def summary(
        self,
        region_r32: str = "USA",
        years: list[int] | None = None,
    ) -> str:
        if years is None:
            years = sorted(self.dataset.years)[:6]

        lines = [f"{self.model_name} targets for {region_r32}"]
        lines.append("")

        lines.append("Electricity generation shares:")
        for year in years:
            shares = self.get_elec_target_shares(year, region_r32)
            if shares is None:
                lines.append(f"  {year}: no data")
                continue
            top5 = sorted(shares.items(), key=lambda x: -x[1])[:5]
            parts = [f"{k}={v:.3f}" for k, v in top5]
            lines.append(f"  {year}: {', '.join(parts)}")

        lines.append("")
        lines.append("Sector totals (EJ/yr):")
        for year in years:
            parts = []
            for s in ["industry", "buildings", "transport"]:
                val = self.get_sector_total(year, s, region_r32)
                parts.append(f"{s}={val:.1f}" if val is not None else f"{s}=?")
            lines.append(f"  {year}: {', '.join(parts)}")

        return "\n".join(lines)  # end Calibrator.summary


# ---------------------------------------------------------------------------
# SectorScore / CalibrationResult — bottom-up validation
# ---------------------------------------------------------------------------

@dataclass
class SectorScore:
    """CC + MAE for one sector×region×period."""
    sector: str
    region: str
    year: int
    cc: float
    mae: float
    weight: float = 1.0  # EJ for weighted aggregation

    @staticmethod
    def from_shares(
        target: dict[str, float], model: dict[str, float],
        sector: str, region: str, year: int, weight: float = 1.0,
    ) -> "SectorScore":
        keys = sorted(set(list(target) + list(model)))
        t = np.array([target.get(k, 0) for k in keys])
        m = np.array([model.get(k, 0) for k in keys])
        mae = float(np.mean(np.abs(t - m)))
        if np.std(t) > 0 and np.std(m) > 0:
            cc = float(np.corrcoef(t, m)[0, 1])
        else:
            cc = 1.0 if np.allclose(t, m) else 0.0
        return SectorScore(sector, region, year, cc, mae, weight)


@dataclass
class CalibrationResult:
    """Bottom-up CC + MAE aggregated from sector → region → global.

    Hierarchy::

        Global
        └── Region (×32)
            ├── electricity         (tech shares)
            ├── industry            (carrier shares)
            ├── buildings           (carrier shares, aggregate)
            │   ├── residential.heating / cooling / other
            │   └── commercial.heating / cooling / other
            └── transport           (carrier shares)

    Usage::

        result = CalibrationResult.from_run(calibrator, results)
        print(result.summary())       # one-line
        print(result.sector_table())  # per-sector
        print(result.region_table())  # per-region
        print(result.detail("South Korea"))
    """

    scores: list[SectorScore]
    model_name: str = ""

    @classmethod
    def from_run(cls, calibrator: "Calibrator", results: list,
                 periods: list[int] | None = None) -> "CalibrationResult":
        from ghim.core.config import FUTURE_YEARS
        if periods is None:
            periods = FUTURE_YEARS[:len(results)]
        regions = list(results[0].regions.keys())
        bld_subs = [
            "residential.heating", "residential.cooling", "residential.other",
            "commercial.heating", "commercial.cooling", "commercial.other",
        ]
        scores: list[SectorScore] = []
        for i, period in enumerate(periods):
            for region in regions:
                rs = results[i].regions[region]
                # Electricity
                tgt = calibrator.get_elec_target_shares(period, region) or {}
                gen = rs.generation.get("electricity", {})
                gt = sum(gen.values()) if isinstance(gen, dict) else 0
                mdl = {k: v / gt for k, v in gen.items()} if gt > 0 else {}
                if tgt and mdl:
                    scores.append(SectorScore.from_shares(
                        tgt, mdl, "electricity", region, period, weight=gt))
                # Demand sectors
                for sec in ("industry", "buildings", "transport"):
                    tgt = calibrator.get_sector_carrier_shares(period, sec, region) or {}
                    sd = rs.sector_demand.get(sec, {})
                    st = sum(sd.values())
                    mdl = {k: v / st for k, v in sd.items()} if st > 0 else {}
                    if tgt and mdl:
                        scores.append(SectorScore.from_shares(
                            tgt, mdl, sec, region, period, weight=st))
                # Buildings subsectors
                for sub in bld_subs:
                    tgt = calibrator.get_subsector_carrier_shares(period, sub, region)
                    if tgt is None:
                        continue
                    st = calibrator.get_subsector_total(period, sub, region) or 0
                    if st > 0:
                        sd = rs.sector_demand.get("buildings", {})
                        bt = sum(sd.values())
                        mdl = {k: v / bt for k, v in sd.items()} if bt > 0 else {}
                        if mdl:
                            scores.append(SectorScore.from_shares(
                                tgt, mdl, f"buildings.{sub}", region, period, weight=st))
        return cls(scores=scores, model_name=calibrator.model_name)

    def _agg(self, scores: list[SectorScore]) -> tuple[float, float]:
        if not scores:
            return 0.0, 0.0
        w = np.array([s.weight for s in scores])
        if w.sum() <= 0:
            w = np.ones(len(scores))
        return (float(np.average([s.cc for s in scores], weights=w)),
                float(np.average([s.mae for s in scores], weights=w)))

    def global_score(self) -> tuple[float, float]:
        return self._agg(self.scores)

    def sector_table(self) -> str:
        lines = [f"{'Sector':>25s}  {'CC':>7s}  {'MAE':>7s}  {'n':>5s}"]
        for sec in ["electricity", "industry", "buildings", "transport"]:
            ss = [s for s in self.scores if s.sector == sec]
            cc, mae = self._agg(ss)
            lines.append(f"{sec:>25s}  {cc:>7.4f}  {mae:>7.4f}  {len(ss):>5d}")
        for sub in sorted(set(s.sector for s in self.scores if s.sector.startswith("buildings."))):
            ss = [s for s in self.scores if s.sector == sub]
            cc, mae = self._agg(ss)
            lines.append(f"{sub:>25s}  {cc:>7.4f}  {mae:>7.4f}  {len(ss):>5d}")
        cc, mae = self.global_score()
        lines.append(f"{'ALL':>25s}  {cc:>7.4f}  {mae:>7.4f}  {len(self.scores):>5d}")
        return "\n".join(lines)

    def region_table(self) -> str:
        regions = sorted(set(s.region for s in self.scores))
        stats = [(r, *self._agg([s for s in self.scores if s.region == r])) for r in regions]
        stats.sort(key=lambda x: -x[1])
        lines = [f"{'Region':>30s}  {'CC':>7s}  {'MAE':>7s}"]
        for r, cc, mae in stats:
            lines.append(f"{r:>30s}  {cc:>7.4f}  {mae:>7.4f}")
        return "\n".join(lines)

    def detail(self, region: str) -> str:
        ss = [s for s in self.scores if s.region == region]
        sectors = sorted(set(s.sector for s in ss))
        years = sorted(set(s.year for s in ss))
        show = years[::max(1, len(years) // 6)][:6]
        lines = [f"{region} — CC/MAE"]
        lines.append(f"{'Sector':>25s}" + "".join(f"  {y:>12d}" for y in show))
        for sec in sectors:
            parts = [f"{sec:>25s}"]
            for y in show:
                m = [s for s in ss if s.sector == sec and s.year == y]
                parts.append(f"  {m[0].cc:.3f}/{m[0].mae:.4f}" if m else f"  {'—':>12s}")
            lines.append("".join(parts))
        return "\n".join(lines)

    def summary(self) -> str:
        cc, mae = self.global_score()
        nr = len(set(s.region for s in self.scores))
        ny = len(set(s.year for s in self.scores))
        return f"{self.model_name}: CC={cc:.4f}, MAE={mae:.4f} ({nr} regions, {ny} periods)"
