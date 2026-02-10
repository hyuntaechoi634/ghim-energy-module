"""Build GHIM Energy Module proposal slide deck (.pptx).

Usage:
    python slides/build_slides.py

Requires: python-pptx, figures in slides/figures/ (run proposal_plots.ipynb first).
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SLIDES_DIR = Path(__file__).resolve().parent
FIGURES_DIR = SLIDES_DIR / "figures"
OUTPUT_PATH = SLIDES_DIR / "ghim_proposal.pptx"

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------
TITLE_COLOR = RGBColor(0x1A, 0x23, 0x7E)  # dark indigo
ACCENT_COLOR = RGBColor(0x21, 0x96, 0xF3)  # blue
TEXT_COLOR = RGBColor(0x33, 0x33, 0x33)
SUBTLE_COLOR = RGBColor(0x75, 0x75, 0x75)
WARN_COLOR = RGBColor(0xE6, 0x51, 0x00)    # deep orange for issues/improvements
BG_COLOR = RGBColor(0xFF, 0xFF, 0xFF)

TITLE_SIZE = Pt(28)
SUBTITLE_SIZE = Pt(18)
HEADING_SIZE = Pt(24)
SUBHEADING_SIZE = Pt(18)
BODY_SIZE = Pt(14)
SMALL_SIZE = Pt(11)

SLIDE_WIDTH = Inches(13.333)  # widescreen 16:9
SLIDE_HEIGHT = Inches(7.5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def set_slide_bg(slide, color=BG_COLOR):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_textbox(slide, left, top, width, height, text, *,
                font_size=BODY_SIZE, bold=False, color=TEXT_COLOR,
                alignment=PP_ALIGN.LEFT, font_name="Calibri"):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = font_size
    p.font.bold = bold
    p.font.color.rgb = color
    p.font.name = font_name
    p.alignment = alignment
    return tf


def add_title_bar(slide, title_text):
    """Add a colored title bar at the top of a content slide."""
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE.RECTANGLE
        Inches(0), Inches(0), SLIDE_WIDTH, Inches(0.08)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = ACCENT_COLOR
    shape.line.fill.background()

    add_textbox(slide, Inches(0.8), Inches(0.3), Inches(11), Inches(0.7),
                title_text, font_size=HEADING_SIZE, bold=True, color=TITLE_COLOR)


def add_bullets(slide, left, top, width, height, items, *,
                font_size=BODY_SIZE, color=TEXT_COLOR, bold_prefix=True):
    """Add bullet-point text box. Items can be strings or (bold_part, rest) tuples."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True

    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(4)
        p.space_before = Pt(2)

        if isinstance(item, tuple):
            bold_part, rest = item
            run_b = p.add_run()
            run_b.text = bold_part
            run_b.font.size = font_size
            run_b.font.bold = True
            run_b.font.color.rgb = color
            run_b.font.name = "Calibri"
            run_r = p.add_run()
            run_r.text = rest
            run_r.font.size = font_size
            run_r.font.bold = False
            run_r.font.color.rgb = color
            run_r.font.name = "Calibri"
        else:
            run = p.add_run()
            run.text = f"\u2022  {item}"
            run.font.size = font_size
            run.font.color.rgb = color
            run.font.name = "Calibri"
    return tf


def add_figure(slide, filename, left, top, width=None, height=None):
    """Add a figure from the figures directory."""
    path = FIGURES_DIR / filename
    if not path.exists():
        add_textbox(slide, left, top, Inches(4), Inches(0.5),
                    f"[Figure: {filename}]", font_size=SMALL_SIZE, color=SUBTLE_COLOR)
        return
    kwargs = {}
    if width:
        kwargs["width"] = width
    if height:
        kwargs["height"] = height
    slide.shapes.add_picture(str(path), left, top, **kwargs)


# ---------------------------------------------------------------------------
# Slide builders
# ---------------------------------------------------------------------------

def slide_0_claude_code(prs):
    """Slide 0: Claude Code Experience."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    set_slide_bg(slide)
    add_title_bar(slide, "Claude Code Experience")

    items = [
        ("\u2022  Quota: ", "Opus 4 via Max plan ($200/mo); typical session uses 30\u201360 tool calls; "
         "multi-file edits, model runs, and test suites within a single conversation"),
        ("\u2022  Environment: ", "WSL2 Ubuntu + conda (ghim, Python 3.11) + editable install; "
         "Claude Code hooks for Telegram notifications (alert bot for milestones, "
         "tracker bot for all tool calls); session context files in context/ "
         "for cross-session continuity; auto-memory in .claude/projects/ for persistent knowledge"),
    ]

    add_bullets(slide, Inches(0.8), Inches(1.3), Inches(11), Inches(5.5),
                items, font_size=Pt(15))


def slide_1_title(prs):
    """Slide 1: Title slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    set_slide_bg(slide)

    shape = slide.shapes.add_shape(
        1, Inches(0), Inches(2.8), SLIDE_WIDTH, Inches(0.06)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = ACCENT_COLOR
    shape.line.fill.background()

    add_textbox(slide, Inches(1), Inches(1.5), Inches(11), Inches(1.2),
                "GHIM Energy Module",
                font_size=Pt(40), bold=True, color=TITLE_COLOR,
                alignment=PP_ALIGN.CENTER)

    add_textbox(slide, Inches(1), Inches(2.3), Inches(11), Inches(0.6),
                "A Recursive-Dynamic Energy-Economy Model",
                font_size=SUBTITLE_SIZE, color=SUBTLE_COLOR,
                alignment=PP_ALIGN.CENTER)

    add_textbox(slide, Inches(1), Inches(3.2), Inches(11), Inches(0.5),
                "10 AR6 Regions  \u00b7  2000\u20132150  \u00b7  5-year timesteps",
                font_size=Pt(16), color=SUBTLE_COLOR,
                alignment=PP_ALIGN.CENTER)

    add_textbox(slide, Inches(1), Inches(5.0), Inches(11), Inches(0.5),
                "Hyuntae Choi  \u00b7  February 2026",
                font_size=Pt(15), color=SUBTLE_COLOR,
                alignment=PP_ALIGN.CENTER)


def slide_2_motivation(prs):
    """Slide 2: Motivation & Model Identity."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide)
    add_title_bar(slide, "Motivation & Model Identity")

    items = [
        "GHIM: independent energy module, not a GCAM fork \u2014 own solver, architecture, and codebase",
        "Python-first for rapid iteration, transparency, and reproducibility",
        "Leverages GCAM data infrastructure (fossil supply curves, calibration) while redesigning the modeling approach",
        "Hybrid design: DICE/WITCH macro-economics + GCAM technology detail + MERGE preference factors",
        "Target: integration into the full GHIM integrated model (energy + land use + water + climate)",
    ]
    add_bullets(slide, Inches(0.8), Inches(1.3), Inches(11.5), Inches(5.5), items)


def slide_3_framework(prs):
    """Slide 3: Model Framework — Regions, Periods, Optimization."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide)
    add_title_bar(slide, "Model Framework \u2014 Regions, Periods, Solution Method")

    # ---- LEFT COLUMN: Current implementation ----
    add_textbox(slide, Inches(0.8), Inches(1.2), Inches(5.5), Inches(0.5),
                "Current Implementation", font_size=SUBHEADING_SIZE, bold=True, color=ACCENT_COLOR)

    current = [
        ("Regions: ", "10 AR6 R10 macro-regions (Africa, Asia-Pacific Dev., Eastern Asia, Eurasia, "
         "Europe, Latin America, Middle East, North America, SE Asia & dev. Pacific, Southern Asia)"),
        ("Time horizon: ", "2000\u20132150, 5-year timesteps (31 periods)"),
        ("Calibration: ", "Historical period 2000\u20132020 (SSP Historical Reference); "
         "model is calibrated at 2020 (TFP, capital stock, technology shares, preference factors)"),
        ("Projection: ", "2025\u20132150 forward-solved with endogenous GDP, trade, technology choice"),
        ("Solution method: ", "Recursive-dynamic (period-by-period, myopic expectations) \u2014 "
         "each period solves given current state without anticipating future prices or policies"),
    ]
    add_bullets(slide, Inches(0.8), Inches(1.7), Inches(5.5), Inches(4.0),
                current, font_size=Pt(12))

    # ---- RIGHT COLUMN: Improvement directions ----
    add_textbox(slide, Inches(7.0), Inches(1.2), Inches(5.5), Inches(0.5),
                "Improvement Directions", font_size=SUBHEADING_SIZE, bold=True, color=WARN_COLOR)

    improvements = [
        ("R10 \u2192 Country-level: ", "Current R10 aggregation loses within-region heterogeneity "
         "(e.g., India vs. Bangladesh in Southern Asia). Country-level resolution would allow "
         "direct calibration to national IEA data and policy analysis at country scale. "
         "Requires: country-level SSP data (available), demand calibration, trade matrix expansion."),
        ("5-year \u2192 1-year timesteps: ", "Finer temporal resolution improves: (a) stock turnover "
         "realism (15-yr vehicle fleet \u2192 3 period steps vs 15), (b) policy phase-in smoothness, "
         "(c) investment timing. Trade-off: 6\u00d7 more periods, solver runtime scales linearly."),
        ("Recursive-dynamic \u2192 Foresight: ", "Current myopic solver cannot optimize over time. "
         "Options: (a) Perfect foresight (full intertemporal optimization, computationally expensive), "
         "(b) Imperfect / rolling limited foresight (e.g., 20-year lookahead window, "
         "re-solve each period) \u2014 captures investment anticipation without full optimization. "
         "Key benefit: agents can anticipate carbon price ramps and invest in clean tech earlier."),
    ]
    add_bullets(slide, Inches(7.0), Inches(1.7), Inches(5.8), Inches(5.2),
                improvements, font_size=Pt(12))


def slide_4_klem(prs):
    """Slide 4: KLEM — Homogeneous GE with Energy Cost Feedback."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide)
    add_title_bar(slide, "Economic Core \u2014 KLEM Production & General Equilibrium")

    # ---- LEFT COLUMN: Model description ----
    add_textbox(slide, Inches(0.8), Inches(1.2), Inches(5.5), Inches(0.5),
                "Homogeneous GE with Energy Cost Feedback",
                font_size=Pt(15), bold=True, color=ACCENT_COLOR)

    desc = [
        ("Production function: ", "Y = A(t) \u00b7 K(t)\u1d45 \u00b7 L(t)\u00b9\u207b\u1d45  "
         "(\u03b1 = 0.3, Cobb-Douglas)"),
        ("Single representative agent: ", "Each region has one aggregate production function \u2014 "
         "homogeneous general equilibrium, not multi-sector CGE"),
        ("Energy as a cost: ", "Net output = Gross output \u2212 Energy cost; energy cost = "
         "\u03a3(carrier_demand_EJ \u00d7 carrier_price_$/GJ)"),
        ("Capital dynamics: ", "I = s \u00b7 Y_net (s=0.22), K(t+1) = (1\u2212\u03b4)\u2075 \u00b7 K(t) + I \u00b7 5; "
         "energy cost shock \u2192 lower net Y \u2192 lower I \u2192 lower future K \u2192 lower future GDP"),
        ("TFP calibration: ", "A(t) calibrated from SSP GDP path via backward K solve (2020\u21922000) "
         "then forward calibration (2020\u21922150). TFP held fixed during projection \u2014 GDP deviates "
         "from SSP only through energy cost feedback."),
        ("KLEM-sector coupling: ", "KLEM total energy sets the macro envelope; "
         "sector demands (industry/buildings/transport) set relative shares; "
         "klem_scale = klem_total / sector_sum, clamped to [0.5, 2.0]"),
    ]
    add_bullets(slide, Inches(0.8), Inches(1.7), Inches(5.5), Inches(4.5),
                desc, font_size=Pt(11))

    # ---- RIGHT COLUMN: GDP figure + capital issue ----
    add_figure(slide, "gdp_trajectory.png",
               Inches(6.8), Inches(1.2), width=Inches(5.8))

    # Capital inconsistency callout
    add_textbox(slide, Inches(6.8), Inches(4.6), Inches(5.8), Inches(0.4),
                "Known Issue: Capital Layer Inconsistency",
                font_size=Pt(13), bold=True, color=WARN_COLOR)

    issue_items = [
        ("Macro K vs. Sector K: ", "The KLEM aggregate capital stock K (used in Y = AK\u1d45L\u00b9\u207b\u1d45) "
         "is a single number per region. But each technology has its own capital_cost ($/kW) "
         "embedded in LCOE calculations. These two capital concepts are disconnected."),
        ("No adding-up: ", "\u03a3(tech capital stocks) \u2260 K_macro. The macro K governs GDP and "
         "investment, while tech-level capex only affects relative costs in the logit. "
         "A power plant investment does not draw down from the macro K pool."),
        ("Consequence: ", "Energy sector investment can expand without crowding out non-energy "
         "capital. This overstates the economy's ability to simultaneously grow GDP and "
         "invest in clean energy. A proper fix requires either a multi-sector CGE with "
         "capital allocation, or an investment budget constraint linking macro I to sector capex."),
    ]
    add_bullets(slide, Inches(6.8), Inches(5.0), Inches(5.8), Inches(2.2),
                issue_items, font_size=Pt(10), color=TEXT_COLOR)


def slide_5_demand(prs):
    """Slide 5: Primary Energy Demand — Derived Demand by Sectors."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide)
    add_title_bar(slide, "Primary Energy Demand \u2014 Derived Demand by Sectors")

    # ---- Intro explanation ----
    add_textbox(slide, Inches(0.8), Inches(1.2), Inches(11.5), Inches(0.8),
                "Primary energy demand is not demanded directly \u2014 it is derived from final sector "
                "demands for energy services. Sectors demand energy carriers (electricity, refined liquids, "
                "gas, etc.), and these are traced back through transformation sectors "
                "(power generation, refining, hydrogen production) to primary fuel requirements.",
                font_size=Pt(13), color=TEXT_COLOR)

    # ---- LEFT: Demand tree structure ----
    add_textbox(slide, Inches(0.8), Inches(2.2), Inches(5.8), Inches(0.4),
                "Nested Demand Tree (per region)", font_size=Pt(15), bold=True, color=ACCENT_COLOR)

    tree_items = [
        ("Final demand sectors ", "(GDP-driven total, income elasticity):"),
        ("  Industry ", "(\u03b5=0.6): heavy (coal/gas/elec), light (elec/gas), data centers (100% elec)"),
        ("  Buildings ", "(\u03b5=0.5): residential (elec/gas/biomass), commercial (elec/gas)"),
        ("  Transport ", "(\u03b5=0.7): passenger (ref. liquids/elec), freight (ref. liquids/gas)"),
        ("", ""),
        ("Carrier choices via logit: ", "At each tree node, children compete via "
         "relative-preference logit with stock turnover. s\u1d62 = \u03b1\u1d62\u00b7exp(\u2212k\u00b7P\u1d62)\u00b7C\u1d62\u1d5d / \u03a3"),
        ("6 energy carriers: ", "coal, refined liquids, gas, electricity, biomass, hydrogen"),
    ]
    add_bullets(slide, Inches(0.8), Inches(2.6), Inches(5.8), Inches(3.0),
                tree_items, font_size=Pt(11))

    # ---- RIGHT: Derivation to primary ----
    add_textbox(slide, Inches(7.0), Inches(2.2), Inches(5.8), Inches(0.4),
                "From Final Demand to Primary Fuel", font_size=Pt(15), bold=True, color=ACCENT_COLOR)

    deriv_items = [
        ("Step 1 \u2014 Sector totals: ", "Each sector's total demand scales with GDP: "
         "E_sector = E_base \u00d7 (GDP/GDP_base)^(\u03b5). KLEM coupling then rescales "
         "all sectors so their sum matches the macro energy envelope."),
        ("Step 2 \u2014 Carrier allocation: ", "Within each sector/subsector, logit + stock turnover "
         "determines the split across 6 carriers. Result: carrier_demand_EJ per region."),
        ("Step 3 \u2014 Secondary transformation: ",
         "\u2022 Electricity demand \u2192 8-tech generation mix (coal, gas CC, oil, nuclear, "
         "hydro, wind, solar, biomass) \u2192 fuel inputs via efficiency\n"
         "\u2022 Refined liquids demand \u2192 oil refining (\u03b7=0.85) \u2192 crude oil input\n"
         "\u2022 Hydrogen demand \u2192 SMR (gas) + electrolysis (elec) \u2192 gas/elec inputs"),
        ("Step 4 \u2014 Primary fuel aggregation: ",
         "Sum all fuel inputs across final demand + electricity + refining + hydrogen:\n"
         "  coal = direct_coal + elec_coal_input\n"
         "  oil = refining_oil_input + elec_oil_input\n"
         "  gas = direct_gas + elec_gas_input + h2_smr_gas_input"),
    ]
    add_bullets(slide, Inches(7.0), Inches(2.6), Inches(5.8), Inches(4.2),
                deriv_items, font_size=Pt(11))


def slide_6_supply(prs):
    """Slide 6: Primary Energy Supply — Resource Curves & Trade."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide)
    add_title_bar(slide, "Primary Energy Supply \u2014 Resource Curves & Trade Clearing")

    # ---- LEFT: Supply curve structure ----
    add_textbox(slide, Inches(0.8), Inches(1.2), Inches(5.8), Inches(0.4),
                "Grade-Based Supply Curves (per region, per fuel)",
                font_size=Pt(15), bold=True, color=ACCENT_COLOR)

    supply_items = [
        ("GCAM supply curves: ", "Fossil fuels (coal, oil, gas) modeled as multi-grade "
         "supply curves with increasing extraction cost. Each grade has a resource amount (EJ) "
         "and an extraction cost ($/GJ). Original data from GCAM R32 regions."),
        ("Aggregation pipeline: ", "R32 grades \u2192 country-level (GDP-share downscaling) "
         "\u2192 R10 aggregation. Result: ~3\u20135 grades per fuel per R10 region."),
        ("Piecewise-linear supply: ", "production_at_price(p) ramps linearly between grade "
         "boundaries (first grade ramps from p=0). This eliminates step-function "
         "discontinuities that cause solver oscillation."),
        ("Production cap: ", "max_annual_production = 3\u00d7 base-year production per region. "
         "Prevents unrealistic instantaneous scaling."),
        ("Renewables: ", "Wind, solar, hydro, biomass \u2014 no resource depletion. "
         "Cost determined entirely by technology capital cost + learning curves. "
         "Supply is effectively unlimited at the technology's LCOE."),
    ]
    add_bullets(slide, Inches(0.8), Inches(1.6), Inches(5.8), Inches(3.5),
                supply_items, font_size=Pt(11))

    # ---- RIGHT: Trade mechanism ----
    add_textbox(slide, Inches(7.0), Inches(1.2), Inches(5.8), Inches(0.4),
                "Global Market Clearing (coal, oil, gas)",
                font_size=Pt(15), bold=True, color=ACCENT_COLOR)

    trade_items = [
        ("Bisection algorithm: ", "For each fuel, find world price p* such that "
         "\u03a3_r supply_r(p*) = \u03a3_r demand_r(p*). Price search over "
         "[FLOOR=0.1, CEILING=50] $/GJ, tolerance 0.01 $/GJ."),
        ("Calibration rents: ", "At base year, observed price often exceeds the "
         "supply-curve clearing price (market power, transport costs, taxes). "
         "Rent = observed \u2212 cleared, locked at 2025, passed as price_adder into bisection. "
         "Supply evaluated at extraction_cost + rent; world_price includes rent."),
        ("Stabilization mechanisms: ",
         "\u2022 Inter-period price clamping: max 30% price change per 5-year period\n"
         "\u2022 Production inertia: max 30% decline per region per period (growth unconstrained)\n"
         "\u2022 Demand-trade iteration: up to 10 rounds with 50% damping per period\n"
         "\u2022 Warm-start: previous period's cleared prices seed next period's bisection"),
        ("Net exports: ", "net_exports_r = production_r(p*) \u2212 demand_r. "
         "Positive = exporter, negative = importer."),
    ]
    add_bullets(slide, Inches(7.0), Inches(1.6), Inches(5.8), Inches(3.5),
                trade_items, font_size=Pt(11))

    # ---- Bottom: two trade figures ----
    add_figure(slide, "trade_world_prices.png",
               Inches(0.8), Inches(5.0), width=Inches(5.5))

    add_figure(slide, "trade_net_exports.png",
               Inches(7.0), Inches(5.0), width=Inches(5.5))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build():
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    slide_0_claude_code(prs)    # Slide 0: Claude Code Experience
    slide_1_title(prs)          # Slide 1: Title
    slide_2_motivation(prs)     # Slide 2: Motivation
    slide_3_framework(prs)      # Slide 3: Framework (regions, periods, optimization)
    slide_4_klem(prs)           # Slide 4: KLEM / GE / capital issue
    slide_5_demand(prs)         # Slide 5: Primary energy demand (derived)
    slide_6_supply(prs)         # Slide 6: Primary energy supply & trade

    prs.save(str(OUTPUT_PATH))
    print(f"Saved {OUTPUT_PATH} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    build()
