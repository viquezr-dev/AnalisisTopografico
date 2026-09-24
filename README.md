# Topographic Analysis for QGIS

**Topographic Analysis** is a QGIS plugin for adjusting differential leveling
networks and performing two-dimensional Helmert coordinate transformations.
It provides data validation, least-squares adjustment, statistical quality
control, formatted reports, and GIS-ready result exports through a single
graphical interface.

The plugin is intended for surveying, geodesy, cartography, engineering, and
quality-control workflows in which observations must be checked before final
coordinates or elevations are produced.

**Official repository:**
[github.com/viquezr-dev/AnalisisTopografico](https://github.com/viquezr-dev/AnalisisTopografico)

## Main features

### Differential leveling

- Gauss-Markov least-squares adjustment.
- Observation weights based on inverse distance (`1 / distance`).
- Support for fixed benchmarks and unknown stations.
- Standard convention: `H_final - H_initial = dh`.
- Optional field convention: `H_initial - H_final = dh`.
- Automatic checks for missing fields, invalid observations, duplicate lines,
  disconnected networks, insufficient redundancy, and ill-conditioned normal
  matrices.
- Adjusted elevations, residuals, standard deviations, 95% confidence
  intervals, redundancy values, standardized residuals, and observation
  ranking.
- Chi-square consistency test and warnings for suspicious observations.

### Helmert transformations

- Four-parameter similarity transformation:
  - two translations;
  - one rotation;
  - one uniform scale factor.
- Six-parameter affine transformation:
  - two translations;
  - independent axis coefficients;
  - rotation, scale, and shear effects.
- Separate handling of control, verification, and transformation-only points.
- Validation of duplicated coordinates, non-finite values, insufficient
  control points, collinearity, rank, and matrix conditioning.
- Parameter covariance, residual statistics, transformed coordinates, and
  approximate error ellipses for control points.

### Reports and exports

- Detailed HTML reports.
- Optional SVG sketches embedded in reports.
- CSV output for adjusted results.
- GeoPackage output with categorized QGIS symbology.
- CSV export of adjustment matrices.
- Built-in example templates for both supported workflows.
- Automatic detection of the analysis mode from the input fields.

## Requirements

- QGIS 3.x.
- Python 3 as supplied with QGIS.
- NumPy.
- SciPy is optional. If it is unavailable, the plugin uses internal
  approximations for the statistical critical values.

The plugin source follows Flake8 style requirements.

## Installation

### From the QGIS Plugin Repository

1. Open QGIS.
2. Select **Plugins > Manage and Install Plugins**.
3. Search for **Topographic Analysis**.
4. Select the plugin and click **Install Plugin**.

### Manual installation

1. Download the plugin ZIP file from the
   [GitHub repository](https://github.com/viquezr-dev/AnalisisTopografico)
   or its
   [Releases page](https://github.com/viquezr-dev/AnalisisTopografico/releases).
2. In QGIS, open **Plugins > Manage and Install Plugins**.
3. Select **Install from ZIP**.
4. Choose the downloaded ZIP file and click **Install Plugin**.
5. Open the plugin from the QGIS Plugins menu or its toolbar button.

Do not rename or remove the plugin's Python modules after installation. The
main interface imports the Helmert calculation module from the same plugin
directory.

## Input data

Input data may be loaded in QGIS as a vector layer or a table without geometry.
Field matching is case-insensitive.

### Leveling fields

| Field | Description | Required |
| --- | --- | --- |
| `EST` | Observation or line identifier | Yes |
| `C_FIJA` | Known elevation associated with the initial station | Yes |
| `C_INICIAL` | Initial station identifier | Yes |
| `C_FINAL` | Final station identifier | Yes |
| `DIF_COTA` | Observed elevation difference in metres | Yes |
| `DIST` | Observation distance in metres; must be greater than zero | Yes |
| `X`, `Y` | Optional station coordinates used for mapping | No |

The network must be connected and must contain enough redundant observations
to produce positive degrees of freedom. At least one fixed elevation must be
provided.

### Helmert fields

| Field | Description | Required |
| --- | --- | --- |
| `PUNTO` | Point identifier | Yes |
| `X_ORIGEN` | Source X coordinate | Yes |
| `Y_ORIGEN` | Source Y coordinate | Yes |
| `X_DESTINO` | Known target X coordinate | For control and verification points |
| `Y_DESTINO` | Known target Y coordinate | For control and verification points |
| `USO` | Point role: `Control` or `Verification` | Recommended |

Point behavior is determined as follows:

| Role and coordinates | Behavior |
| --- | --- |
| `Control` with target coordinates | Included in the transformation adjustment |
| `Verification` with target coordinates | Excluded from the adjustment and used for independent validation |
| `Control` with empty target coordinates | Transformed after the parameters are calculated |
| Empty `USO` value | Treated as `Control` |

The four-parameter model requires at least two control points. The
six-parameter model requires at least three non-collinear control points.
Additional control points are recommended so that residuals and adjustment
quality can be evaluated statistically.

## Basic workflow

1. Load the input table or vector layer in QGIS.
2. Open **Topographic Analysis**.
3. Select **Leveling** or **Helmert** mode.
4. Select the input layer.
5. Configure the adjustment tolerances and report options.
6. For Helmert processing, select the four- or six-parameter model.
7. Click **Verify Data** and review the activity log.
8. Click **Calculate Adjustment**.
9. Generate the HTML report or export the results to GeoPackage, CSV, or
   matrix CSV files.

If you are preparing a dataset for the first time, use **Generate Example CSV
Templates** in the plugin interface.

## Output and quality control

Depending on the selected mode, the plugin reports:

- adjusted elevations or transformed coordinates;
- residuals and standardized residuals;
- posterior variance factor;
- degrees of freedom;
- covariance and standard-deviation information;
- matrix condition diagnostics;
- chi-square test results;
- warnings for observations that exceed the configured tolerances;
- independent verification-point differences;
- transformation parameters and control-point error ellipses.

Results should always be reviewed by a qualified surveying or geospatial
professional before they are used in operational or legal work.

## Source files

- `nivelacion.py`: QGIS interface, leveling adjustment, validation, reporting,
  and export functions.
- `helmert.py`: numerical engine for four- and six-parameter transformations.

The filenames inside the final plugin package should match the imports and the
module names declared in the plugin package.

## Development and validation

To check the Python files locally:

```bash
python -m py_compile nivelacion.py helmert.py
flake8 nivelacion.py helmert.py
```

Testing should also be performed inside a supported QGIS installation because
the graphical interface depends on PyQGIS and Qt components.

## Contributing

Bug reports, improvement proposals, and pull requests are welcome. Use the
[GitHub issue tracker](https://github.com/viquezr-dev/AnalisisTopografico/issues)
to report a problem. Include:

- QGIS version;
- operating system;
- selected analysis mode and model;
- input field structure;
- steps needed to reproduce the issue;
- relevant error messages, without confidential project data.

## License

This project is licensed under the **GNU General Public License v3.0**. See the
`LICENSE` file for the complete license text.

## Author

**Raul Viquez**

## Disclaimer

This software is provided without warranty. Users are responsible for
verifying input data, adjustment settings, numerical results, coordinate
reference systems, and final deliverables.
