"""Oil refining sector model.

Converts crude oil to refined liquid fuels with fixed efficiency.
"""

from __future__ import annotations

from ghim.energy.technology import Technology, default_refining_techs


class RefiningSector:
    """Oil refining for a single region."""

    def __init__(self, techs: list[Technology] | None = None):
        self.techs = techs or default_refining_techs()
        self.total_output_ej = 0.0

    @property
    def primary_tech(self) -> Technology:
        return self.techs[0]

    def compute_supply(
        self,
        demand_ej: float,
        oil_price: float,
    ) -> dict[str, float]:
        """Compute refined liquids supply.

        Parameters
        ----------
        demand_ej : float
            Demand for refined liquids (EJ).
        oil_price : float
            Crude oil price ($/GJ).

        Returns
        -------
        dict with keys: "output_ej", "oil_input_ej", "cost_per_gj", "emissions_mtc"
        """
        t = self.primary_tech
        self.total_output_ej = demand_ej

        oil_input = demand_ej / t.efficiency if t.efficiency > 0 else 0.0
        cost = t.levelized_cost(oil_price)
        emissions = t.annual_emissions_tc(demand_ej)

        return {
            "output_ej": demand_ej,
            "oil_input_ej": oil_input,
            "cost_per_gj": cost,
            "emissions_mtc": emissions,
        }
