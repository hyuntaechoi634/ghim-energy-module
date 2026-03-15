"""Multi-gas emission result dataclass."""

from __future__ import annotations

from dataclasses import dataclass

from ghim.core.carrier import GWP100


@dataclass
class EmissionResult:
    """Anthropogenic emissions by gas from a single source.  Units: Mt per gas.

    co2 can be NEGATIVE for BECCS (captured biogenic carbon).
    lulucf is the anthropogenic land-use component (EDGAR):
      positive = deforestation, negative = managed forest regrowth.

    Natural sinks (ocean, CO2 fertilization) are NOT included here --
    they are irrelevant for UNFCCC Net-Zero accounting.
    Phase 2+ Climate module can track them separately for concentration.
    """

    co2: float = 0.0        # MtCO2 (can be negative for BECCS)
    ch4: float = 0.0        # MtCH4
    n2o: float = 0.0        # MtN2O
    f_gases: float = 0.0    # MtCO2eq (already in CO2eq)
    lulucf: float = 0.0     # MtCO2 (anthropogenic: deforestation - managed regrowth)

    @property
    def co2eq(self) -> float:
        """Total anthropogenic GHG in MtCO2eq (= UNFCCC Net-Zero target)."""
        return (self.co2
                + self.ch4 * GWP100["ch4"]
                + self.n2o * GWP100["n2o"]
                + self.f_gases
                + self.lulucf)

    @property
    def co2eq_excl_lulucf(self) -> float:
        """Anthropogenic GHG excluding LULUCF."""
        return (self.co2
                + self.ch4 * GWP100["ch4"]
                + self.n2o * GWP100["n2o"]
                + self.f_gases)

    def __add__(self, other: EmissionResult) -> EmissionResult:
        return EmissionResult(
            co2=self.co2 + other.co2,
            ch4=self.ch4 + other.ch4,
            n2o=self.n2o + other.n2o,
            f_gases=self.f_gases + other.f_gases,
            lulucf=self.lulucf + other.lulucf,
        )

    def __radd__(self, other: object) -> EmissionResult:
        # Support sum() which starts with 0
        if other == 0:
            return self
        if isinstance(other, EmissionResult):
            return other.__add__(self)
        return NotImplemented
