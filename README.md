# Leveling Analysis — QGIS Plugin

[![QGIS](https://img.shields.io/badge/QGIS-3.16%2B-green.svg)](https://qgis.org)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Version](https://img.shields.io/badge/version-2.2.0-orange.svg)](https://github.com/viquezr-dev/analisis_nivelacion/releases)
[![GitHub](https://img.shields.io/badge/GitHub-viquezr--dev-blue.svg)](https://github.com/viquezr-dev/analisis_nivelacion)

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
```

---

## Usage

1. **Import the CSV** into QGIS:
   - `Layer → Add Layer → Add Delimited Text Layer`
   - Choose the CSV file, select **Tab** or **Comma** as separator.
   - Choose **"No geometry (attribute only table)"**.
   - Give the layer a name (any name; the plugin autodetects the required
     columns).

2. **Open the plugin**:
   - Click the **Δ** icon in the toolbar, or
   - Menu: `Leveling Analysis → Leveling Analysis`.

3. **Fill the form**:
   - **Layer**: select the imported table.
   - **Author**: your name (goes into the HTML report).
   - **CRS**: the output coordinate system (default `EPSG:32617` —
     WGS 84 / UTM zone 17N).

4. **Run the workflow**:
   - **1 · Verify data** → Validates fields, connectivity, duplicates.
   - **2 · Compute adjustment** → Runs least squares; results appear in
     the log.
   - **3 · Generate HTML** → Choose the output path; the report opens
     automatically in the browser.
   - **Export GeoPackage** → Saves the adjusted points as a spatial layer.
   - **Export CSV** → Saves the adjusted elevations with statistics.

5. **View results**:
   - The adjusted points are added to the QGIS map (green = fixed,
     blue = unknown).
   - The HTML report opens in the browser with the full statistical
     report.

---

## Output Files

### HTML Report

- Global summary (equations, unknowns, degrees of freedom, fixed
  elevations, total measured elevations).
- Quality-control semaphore (`σ₀`, max residual, max standardized
  residual, χ² test, matrix condition).
- **Scaled network sketch** in UTM.
- Observation and residual table with redundancy number, standardized
  residual, and quality flag.
- Design matrices (P, A, F, AT, ATPA, ATPA⁻¹, ATPF).
- Final elevations table (adjusted + fixed, with statistics).
- Residual vector V.
- Statistical control block (σ₀², σ₀, t₉₅, χ², p-value).
- Variance-covariance matrices (`Σₓₓ`, `Q_l̂l̂`, `Q_vv`).
- Standard deviations per station.
- **Technical metadata block** with method, redundancy, date, and author.

### GeoPackage (`.gpkg`)

- Point layer with fields: `est`, `cota`, `desv`, `ic95`, `tipo`.
- Categorized styling:
  - 🟢 Green = fixed elevation.
  - 🔵 Blue = adjusted (unknown) elevation.

### CSV (`.csv`)

- Columns: `EST`, `COTA_AJUSTADA`, `DESVIACION`, `IC95_INF`,
  `IC95_SUP`, `TIPO`, and optionally `X_UTM`, `Y_UTM`.
- Header comments with metadata (author, date, sigma, chi-square test).

---

## Methodology

The plugin implements the **Gaus-Markov model** for leveling networks:

### Observation equation

For each observation *i* connecting stations *a* and *b*:

```
Δh_i = H_b − H_a + v_i
```

### Weight matrix

```
P[i,i] = 1 / distance_i
```

### Least squares solution

```
X̂ = (Aᵀ P A)⁻¹ · Aᵀ P · f
```

Where:
- **A** is the design matrix (`+1` for target station, `−1` for origin).
- **f** is the reduced observation vector (`Δh − H_final + H_initial`).
- **X̂** is the vector of adjusted unknown elevations.

### Residuals and variance

```
V    = A · X̂ − f
σ₀²  = Vᵀ P V / (n − u)
```

Where *n* is the number of equations and *u* the number of unknowns.

### Variance-covariance matrices

```
Q_vv   = P⁻¹ − A · (AᵀPA)⁻¹ · Aᵀ · P⁻¹   (residuals)
Q_l̂l̂  = A · (AᵀPA)⁻¹ · Aᵀ · P⁻¹          (adjusted observations)
Σₓₓ    = σ₀² · (AᵀPA)⁻¹                  (parameters)
```

---

## Quality Control

The plugin performs the following statistical checks and displays them as
a colored semaphore:

| Indicator | Criterion | Meaning |
|-----------|-----------|---------|
| **σ₀** | ≤ 3 mm (configurable) | Global accuracy of the adjustment |
| **Max residual** | ≤ 5 mm (configurable) | Largest observation error |
| **Max standardized residual** | ≤ 3.0 (configurable) | Baarda's data snooping threshold |
| **Global χ² test** | χ²_obs ≤ χ²_tab (95%) | Model acceptability |
| **Matrix condition** | < 1e10 | Numerical stability of ATPA |

### Baarda's data snooping

Each observation is tested using the **standardized residual**:

```
w_i = v_i / (σ₀ · √q_vv_ii)
```

- `|w| ≤ 3.0` → ✓ OK
- `3.0 < |w| ≤ 3.29` → ⚠ Review
- `|w| > 3.29` → ⚠ Outlier (α = 0.001)

---

## Changelog

### 2.2.0

- **Fixed** variance-covariance matrices: `Q_vv` (residuals) and
  `Q_lhat` (adjusted observations) are now correctly computed and
  labeled.
- **Fixed** sentinel values in GeoPackage export (explicit `float()`
  conversion).
- **Added** UTM coordinate detection with multiple field aliases.
- **Added** scaled network sketch in the HTML report (uses real UTM
  coordinates when available; falls back to a schematic circular layout).
- **Added** GeoPackage export with categorized styling.
- **Added** CSV export with adjusted elevations, confidence intervals,
  and coordinates.
- **Added** interval of confidence at 95% for adjusted elevations.
- **Added** technical metadata block in HTML report.
- **Added** quality-control traffic light (semaphore).
- **Improved** HTML report layout: project name (short form),
  matrix indices, complete final elevation table (fixed + unknown),
  technical metadata.
- **Improved** plugin interface: compact layout, pastel palette,
  clear workflow buttons.

### 2.0.0

- First public release.
- Least squares adjustment for leveling networks.
- HTML report generation.
- Support for up to 50 observations and 50 stations.

---

## License

This plugin is licensed under the **GNU General Public License v3.0** —
see the [LICENSE](LICENSE) file for details.

---

## Author

**Raúl Víquez**
Email: viquezr@gmail.com

Repository: [https://github.com/viquezr-dev/analisis_nivelacion](https://github.com/viquezr-dev/analisis_nivelacion)

---

## Credits

Originally based on a VBA macro for Excel. Ported to Python/QGIS and
extended with modern statistical methods and reporting.

Special thanks to the QGIS community for the excellent API and
documentation.
