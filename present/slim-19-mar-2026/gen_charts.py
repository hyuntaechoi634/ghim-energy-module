#!/usr/bin/env python3
"""Generate presentation charts for GHIM energy module slides."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

ACCENT = "#2C5F2D"
BG = "#FAFAF8"
TEXT = "#4A4A4A"
DPI = 200
OUT_DIR = Path(__file__).resolve().parent

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Calibri", "DejaVu Sans", "Arial", "Helvetica"],
    "axes.facecolor": BG,
    "figure.facecolor": BG,
    "savefig.facecolor": BG,
    "text.color": TEXT,
    "axes.labelcolor": TEXT,
    "xtick.color": TEXT,
    "ytick.color": TEXT,
    "axes.edgecolor": "#CCCCCC",
    "grid.color": "#E0E0E0",
    "grid.linewidth": 0.6,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9,
    "legend.framealpha": 0.9,
})


def chart_supply_curve():
    fig, ax = plt.subplots(figsize=(8, 4.5))
    grades = [(0, 0), (30, 4), (60, 8), (100, 12)]
    gx = [g[0] for g in grades]
    gy = [g[1] for g in grades]
    step_x = [0, 0, 30, 30, 60, 60, 100]
    step_y = [4, 4, 4, 8, 8, 12, 12]
    ax.plot(step_x, step_y, color="#999999", ls="--", lw=1.8,
            label="Naive step function", zorder=2)
    ax.plot(gx, gy, color="#1B4F72", lw=2.5,
            label="Piecewise-linear (GHIM)", zorder=3)
    for i, (x, y) in enumerate(grades[1:], start=1):
        ax.plot(x, y, "o", color="#C0392B", ms=8, zorder=4)
        ej = x - grades[i - 1][0]
        ax.annotate(
            f"Grade {i}\n({ej} EJ, ${y}/GJ)",
            xy=(x, y), xytext=(x - 8, y + 1.2),
            fontsize=8.5, color=TEXT, ha="center",
            arrowprops=dict(arrowstyle="->", color="#999999", lw=0.8),
        )
    ax.set_xlabel("Production (EJ)")
    ax.set_ylabel("Price ($/GJ)")
    ax.set_title("Grade-Based Supply Curve: Piecewise-Linear Interpolation",
                 fontsize=13, fontweight="bold", color=ACCENT, pad=12)
    ax.set_xlim(-2, 110)
    ax.set_ylim(-0.5, 15)
    ax.legend(loc="upper left", frameon=True, edgecolor="#CCCCCC")
    ax.grid(True, alpha=0.5)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "supply_curve.png", dpi=DPI)
    plt.close(fig)
    print("  saved supply_curve.png")


def chart_s_curve():
    fig, ax = plt.subplots(figsize=(8, 5))
    # GCAM A23.globaltech_retirement.csv — actual parameters
    # Same steepness=0.1, two lifetime groups + renewables hard cutoff
    techs = [
        ("Coal / Nuclear / Biomass", 60, 30,   0.1, "#2C3E50", "-"),
        ("Gas CC / Oil",             45, 22.5, 0.1, "#C0392B", "-"),
    ]
    ages = np.linspace(0, 75, 1500)
    for name, L, half, k, color, ls in techs:
        if half is not None:
            # S-curve + hard cutoff at lifetime (matches GCAM C++)
            s0 = 1.0 / (1.0 + np.exp(k * (0 - half)))
            surv = (1.0 / (1.0 + np.exp(k * (ages - half)))) / s0
            surv = np.clip(surv, 0, 1)
        else:
            # Pure hard cutoff (renewables — no S-curve in GCAM)
            surv = np.where(ages <= L, 1.0, 0.0)
        ax.plot(ages, surv, color=color, lw=2.5, ls=ls,
                label=f"{name}  (L={L}" + (f", t\u00bd={int(half)}" if half else "") + ")")
    ax.set_xlabel("Plant age (years)")
    ax.set_ylabel("Survival Fraction")
    ax.set_xlim(0, 75)
    ax.set_ylim(-0.02, 1.05)
    ax.legend(loc="lower left", frameon=True, edgecolor="#CCCCCC", fontsize=8.5)
    ax.grid(True, alpha=0.5)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "s_curve.png", dpi=DPI)
    plt.close(fig)
    print("  saved s_curve.png")


def chart_profit_shutdown():
    fig, ax = plt.subplots(figsize=(8, 5))
    median = -0.1
    steepness = 6
    pi = np.linspace(-0.8, 0.8, 600)
    p_pi = 1.0 / (1.0 + np.exp(-steepness * (pi - median)))
    ax.axvspan(-0.8, -0.1, color="#EAFAF1", alpha=0.7, zorder=0)
    ax.axvspan(-0.1, 0.3, color="#FEF9E7", alpha=0.7, zorder=0)
    ax.axvspan(0.3, 0.8, color="#FDEDEC", alpha=0.7, zorder=0)
    ax.text(-0.45, 0.92, "Profitable\n(most capacity runs)",
            fontsize=8.5, ha="center", va="top", color=ACCENT, fontstyle="italic")
    ax.text(0.10, 0.92, "Marginal",
            fontsize=8.5, ha="center", va="top", color="#B7950B", fontstyle="italic")
    ax.text(0.55, 0.92, "Uneconomic\n(capacity shuts down)",
            fontsize=8.5, ha="center", va="top", color="#C0392B", fontstyle="italic")
    ax.plot(-pi, p_pi, color="#1B4F72", lw=2.8, zorder=3)
    ax.plot(-median, 0.5, "o", color="#C0392B", ms=9, zorder=4)
    ax.annotate("m = \u22120.1 (50% shutdown)",
                xy=(-median, 0.5), xytext=(-median - 0.25, 0.35),
                fontsize=9, color=TEXT,
                arrowprops=dict(arrowstyle="->", color="#999999", lw=1))
    for xv in [-0.1, 0.3]:
        ax.axvline(xv, color="#CCCCCC", ls=":", lw=1, zorder=1)
    ax.set_xlabel("Profit rate \u03c0 = (revenue \u2212 var_cost) / |var_cost|")
    ax.set_ylabel("Survival Fraction  P(\u03c0)")
    ax.set_xlim(-0.8, 0.8)
    ax.set_ylim(-0.02, 1.05)
    ax.grid(True, alpha=0.4)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "profit_shutdown.png", dpi=DPI)
    plt.close(fig)
    print("  saved profit_shutdown.png")


if __name__ == "__main__":
    print("Generating charts...")
    chart_supply_curve()
    chart_s_curve()
    chart_profit_shutdown()
    print("Done.")
