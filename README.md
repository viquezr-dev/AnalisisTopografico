# Leveling Analysis — QGIS Plugin

[![QGIS](https://img.shields.io/badge/QGIS-3.16%2B-green.svg)](https://qgis.org)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Version](https://img.shields.io/badge/version-2.2.0-orange.svg)]()

A professional QGIS plugin for adjusting **topographic leveling networks** by the
**least squares method (Gaus-Markov)**, with full quality control and a
publication-quality HTML report.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Input Data Format](#input-data-format)
- [Usage](#usage)
- [Output Files](#output-files)
- [Methodology](#methodology)
- [Quality Control](#quality-control)
- [Changelog](#changelog)
- [License](#license)
- [Author](#author)

---

## Features

- **Least squares adjustment (Gaus-Markov)** with weights `1 / distance`.
- **Input validation** before processing:
  - Required field detection.
  - Network connectivity check (BFS).
  - Duplicate observation detection.
  - Fixed elevation presence.
- **Optional UTM coordinates detection** (multiple aliases supported:
  `X`, `Y`, `E`, `N`, `ESTE`, `NORTE`, `EAST`, `NORTH`, `UTM_X`, `UTM_Y`,
  `COORD_X`, `COORD_Y`, etc.).
- **Full statistical report**:
  - Posteriori variance `σ₀²` and unit deviation `σ₀`.
  - Global chi-square test (`χ²` at 95% confidence).
  - Confidence intervals at 95% (Student's t).
  - Redundancy number per observation (`rᵢ`).
  - Standardized residuals (Baarda's data snooping, `|w| > 3.29`).
  - Full variance-covariance matrices (`Q_vv` and `Q_lhat`).
- **Professional HTML report**:
  - Quality-control traffic light (semaphore).
  - **Scaled network sketch in UTM coordinates** (or schematic circular
    layout if no coordinates available).
  - All design matrices (P, A, F, AT, ATPA, inverse of ATPA, ATPF).
  - Residuals vector and complete final elevations table.
  - Technical metadata block.
- **Export options**:
  - **GeoPackage** (`.gpkg`) with categorized styling (fixed = green,
    unknown = blue).
  - **CSV** with adjusted elevations, standard deviations, confidence
    intervals, and UTM coordinates.
- **Compact, professional interface** with pastel palette.
- **No external dependencies** — works with the standard QGIS Python stack
  (`numpy`). Optional `scipy` for more precise statistical tests (falls back
  to an internal table if not available).

---

## Requirements

- **QGIS ≥ 3.16** (tested up to 3.99).
- `numpy` (bundled with QGIS).
- `scipy` — **optional**, improves the accuracy of `χ²` and `t` distributions.
  The plugin works without it using internal lookup tables.

---

## Installation

### Method 1 — QGIS Plugin Manager (once published)

1. In QGIS: `Plugins → Manage and Install Plugins`.
2. Search for **"Leveling Analysis"**.
3. Click **Install**.

### Method 2 — Manual installation (development)

1. Copy the folder `analisis_nivelacion/` to:

   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

2. Restart QGIS.
3. Enable the plugin in `Plugins → Manage and Install Plugins → Installed`.

You will see a **Δ icon** in the toolbar and a menu entry under
**Leveling Analysis**.

---

## Input Data Format

The plugin reads a **CSV table** imported into QGIS as a vector/text layer.
All fields must be **String type**. The table must contain at least the
following columns:

| Field | Description |
|-------|-------------|
| `EST` | Station number (row identifier). The fixed elevation in `C_FIJA` belongs to this station. |
| `C_FIJA` | Fixed elevation (in meters). Leave empty if the station is unknown. |
| `C_INICIAL` | Origin station of the observation. |
| `C_FINAL` | Target station of the observation. |
| `DIF_COTA` | Measured elevation difference (in meters). |
| `DIST` | Distance (in km) used to compute the weight. |

### Optional coordinate columns

If your table also contains coordinates, the plugin will detect them
automatically. Supported names (case-insensitive):

| Coordinate X | Coordinate Y |
|--------------|--------------|
| `COORD_X`, `UTM_X`, `X_UTM`, `COORDENADA_X`, `ESTE`, `EAST`, `X`, `E` | `COORD_Y`, `UTM_Y`, `Y_UTM`, `COORDENADA_Y`, `NORTE`, `NORTH`, `Y`, `N` |

When coordinates are present, the plugin will:
- Use them to place stations on the map.
- Draw the network sketch in the HTML report **to scale**.

### Example CSV

```csv
EST,C_FIJA,C_INICIAL,C_FINAL,DIF_COTA,DIST,X,Y
1,,1,2,5.507,0.327,500100.25,1100250.40
2,54.808,2,3,1.728,0.460,500145.10,1100280.85
3,,3,4,-6.798,0.496,500190.75,1100310.60
4,49.738,4,5,-0.588,0.509,500235.10,1100340.20
5,,5,6,5.081,0.519,500280.00,1100369.30
6,54.232,7,6,-0.920,0.646,500200.40,1100420.10
7,,1,7,5.851,0.383,500130.85,1100390.55
8,52.637,8,4,-2.898,1.609,500050.20,1100300.75
9,47.049,8,1,-3.335,0.501,500055.60,1100240.90
10,,3,6,-2.304,0.381,500250.35,1100380.45
11,,9,1,2.252,2.732,500090.10,1100215.30
