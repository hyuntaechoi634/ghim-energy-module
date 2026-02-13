"""Sphinx configuration for GHIM documentation."""

project = "GHIM Energy Module"
author = "Hyuntae Choi"
copyright = "2025, Hyuntae Choi"
release = "0.1.0"

extensions = [
    "myst_parser",
    "sphinx.ext.mathjax",
    "sphinx_copybutton",
    "sphinx_design",
]

myst_enable_extensions = [
    "dollarmath",
    "colon_fence",
    "fieldlist",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "sphinx_book_theme"
html_theme_options = {
    "repository_url": "https://github.com/hyuntae-choi/ghim-energy-module",
    "use_repository_button": True,
    "show_toc_level": 2,
    "navigation_with_keys": True,
}
html_title = "GHIM Energy Module"
html_static_path = ["_static"]

# MyST settings
myst_heading_anchors = 3

# MathJax: pin to v3 (well-tested with MyST + Sphinx)
mathjax_path = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"
mathjax3_config = {
    "tex": {
        "inlineMath": [["\\(", "\\)"]],
        "displayMath": [["\\[", "\\]"]],
    },
}
