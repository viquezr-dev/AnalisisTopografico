# -*- coding: utf-8 -*-
"""
Plugin: Análisis de Nivelación  ·  v2.2
Autor:  Tu Nombre
Licencia: GPL v3

Ajuste de nivelación topográfica por mínimos cuadrados (Gaus-Markov).
- Detecta coordenadas UTM opcionales en la tabla de entrada.
- Genera reporte HTML, GeoPackage y CSV.
- Interfaz compacta con paleta pastel.
- v2.2: corrige var-cov de residuos (Q_vv), manejo de observaciones fija-fija.
"""

import os
import math
import webbrowser
from datetime import datetime

import numpy as np

from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QTextEdit,
    QGroupBox, QMessageBox, QFileDialog, QDoubleSpinBox, QSpinBox,
    QProgressBar, QCheckBox
)
from qgis.PyQt.QtGui import QIcon, QFont, QColor
from qgis.PyQt.QtCore import Qt, QVariant

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsFields, QgsVectorFileWriter,
    QgsCoordinateTransformContext, QgsMarkerSymbol,
    QgsCategorizedSymbolRenderer, QgsRendererCategory,
    QgsCoordinateReferenceSystem
)


# ============================================================
#  UTILIDADES NUMÉRICAS
# ============================================================
def _to_float(s):
    if s is None: return None
    s = str(s).strip()
    if s == "" or s.upper() in ("NULL", "NA", "N/A"): return None
    try:    return float(s.replace(",", "."))
    except: return None

def _to_int(s):
    v = _to_float(s)
    return int(v) if v is not None else None


# Estadísticas (con fallback)
try:
    from scipy.stats import t as _t, chi2 as _chi2
    def t_95(gl):         return float(_t.ppf(0.975, gl))
    def chi2_crit(gl):    return float(_chi2.ppf(0.95, gl))
    def chi2_pval(x, gl): return float(1 - _chi2.cdf(x, gl))
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False
    _TABLA_T = {1:12.706, 2:4.303, 3:3.182, 4:2.776, 5:2.571,
                6:2.447, 7:2.365, 8:2.306, 9:2.262, 10:2.228,
                12:2.179, 15:2.131, 20:2.086, 30:2.042,
                60:2.000, 120:1.980}
    def t_95(gl):
        if gl in _TABLA_T: return _TABLA_T[gl]
        for k in sorted(_TABLA_T):
            if gl <= k: return _TABLA_T[k]
        return 1.960
    def chi2_crit(gl):
        z = 1.645
        return gl * (1 - 2/(9*gl) + z*math.sqrt(2/(9*gl)))**3
    def chi2_pval(x, gl):
        return 0.05 if x > chi2_crit(gl) else 0.5


# ============================================================
#  HOJA DE ESTILOS (pastel)
# ============================================================
QSS = """
QDialog {
    background: #f7f9fc;
    font-family: 'Segoe UI', 'Calibri', sans-serif;
    font-size: 12px;
    color: #2c3e50;
}
QLabel { color: #2c3e50; background: transparent; }
QLabel#titulo {
    font-size: 14px; font-weight: bold; color: #3a6d8c;
    padding: 6px 0;
}
QLabel#info_ok {
    color: #1e8449;
    font-size: 11px;
    background: #eafaf1;
    border: 1px solid #a9dfbf;
    border-radius: 4px;
    padding: 4px 8px;
}
QLabel#info_warn {
    color: #b9770e;
    font-size: 11px;
    background: #fef9e7;
    border: 1px solid #f7dc6f;
    border-radius: 4px;
    padding: 4px 8px;
}
QLabel#info_err {
    color: #922b21;
    font-size: 11px;
    background: #fdedec;
    border: 1px solid #f5b7b1;
    border-radius: 4px;
    padding: 4px 8px;
}
QGroupBox {
    background: #eaf2f8;
    border: 1px solid #b8d0e0;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 8px;
    font-weight: bold;
    color: #3a6d8c;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    background: #f7f9fc;
}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #c5d5e0;
    border-radius: 4px;
    padding: 4px 6px;
    min-height: 22px;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #7fb3d5;
}
QPushButton {
    background: #d6eaf8;
    border: 1px solid #a9cce3;
    border-radius: 4px;
    padding: 6px 10px;
    color: #2c3e50;
    font-weight: 500;
}
QPushButton:hover   { background: #aed6f1; }
QPushButton:pressed { background: #85c1e9; }
QPushButton:disabled {
    background: #ecf0f1;
    color: #95a5a6;
    border-color: #d5dbdb;
}
QPushButton#primary {
    background: #a9cce3; font-weight: bold;
}
QPushButton#primary:hover { background: #7fb3d5; }
QPushButton#success {
    background: #d5f5e3; border-color: #a9dfbf; font-weight: bold;
}
QPushButton#success:hover { background: #abebc6; }
QPushButton#neutral {
    background: #e8e8e8; border-color: #cccccc;
}
QTextEdit {
    background: #fdfefe;
    border: 1px solid #d5dbdb;
    border-radius: 4px;
}
QProgressBar {
    background: #ecf0f1;
    border: 1px solid #d5dbdb;
    border-radius: 4px;
    text-align: center;
    height: 14px;
}
QProgressBar::chunk {
    background: #a9cce3;
    border-radius: 3px;
}
QCheckBox { spacing: 6px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #a9cce3;
    border-radius: 3px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #7fb3d5;
    border: 1px solid #5dade2;
}
"""


# ============================================================
#  PLUGIN
# ============================================================
class AnalisisNivelacion:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, "Análisis de Nivelación",
                              self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.action.setStatusTip("Ajuste de nivelación por mínimos cuadrados")
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Análisis de Nivelación", self.action)

    def unload(self):
        self.iface.removePluginMenu("&Análisis de Nivelación", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dialog:
            self.dialog.close()
            self.dialog = None

    def run(self):
        if self.dialog is None:
            self.dialog = DialogoNivelacion(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()


# ============================================================
#  DIÁLOGO
# ============================================================
class DialogoNivelacion(QDialog):

    CAMPOS_REQ = ["EST", "C_FIJA", "C_INICIAL", "C_FINAL", "DIF_COTA", "DIST"]

    COLS_X = ["COORD_X", "UTM_X", "X_UTM", "COORDENADA_X",
              "ESTE", "EAST", "X", "E"]
    COLS_Y = ["COORD_Y", "UTM_Y", "Y_UTM", "COORDENADA_Y",
              "NORTE", "NORTH", "Y", "N"]

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Análisis de Nivelación  ·  v2.2")
        self.setStyleSheet(QSS)
        self.setMinimumWidth(540)
        self.setMaximumWidth(600)

        self.obs               = None
        self.res               = None
        self.autor             = ""
        self.capa_src          = None
        self.col_x             = None
        self.col_y             = None
        self.coords_estaciones = {}

        self._construir_ui()
        self._cargar_capas()

    # --------------------------------------------------------
    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        titulo = QLabel("ANÁLISIS DE NIVELACIÓN")
        titulo.setObjectName("titulo")
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)

        # ============ 1 · Entrada ============
        grp1 = QGroupBox("1 · Datos de entrada")
        v1 = QVBoxLayout(grp1)

        h_capa = QHBoxLayout()
        h_capa.addWidget(QLabel("Capa:"))
        self.cmb_capa = QComboBox()
        h_capa.addWidget(self.cmb_capa, 1)
        btn_ref = QPushButton("↻")
        btn_ref.setFixedWidth(30)
        btn_ref.setToolTip("Refrescar capas del proyecto")
        btn_ref.clicked.connect(self._cargar_capas)
        h_capa.addWidget(btn_ref)
        v1.addLayout(h_capa)

        self.lbl_info = QLabel("—")
        self.lbl_info.setObjectName("info_warn")
        self.lbl_info.setWordWrap(True)
        v1.addWidget(self.lbl_info)

        h_autor = QHBoxLayout()
        h_autor.addWidget(QLabel("Autor:"))
        self.txt_autor = QLineEdit()
        self.txt_autor.setPlaceholderText("Nombre de quien realiza el cálculo")
        h_autor.addWidget(self.txt_autor, 1)
        v1.addLayout(h_autor)

        h_crs = QHBoxLayout()
        h_crs.addWidget(QLabel("CRS de salida:"))
        self.cmb_crs = QComboBox()
        self.cmb_crs.setEditable(True)
        self._cargar_crs_comunes()
        h_crs.addWidget(self.cmb_crs, 1)
        v1.addLayout(h_crs)

        layout.addWidget(grp1)

        # ============ 2 · Tolerancias ============
        grp2 = QGroupBox("2 · Tolerancias y opciones")
        v2 = QVBoxLayout(grp2)

        g_tol = QGridLayout()
        g_tol.addWidget(QLabel("σ₀ (m):"),        0, 0)
        self.sp_sigma = QDoubleSpinBox()
        self.sp_sigma.setDecimals(5); self.sp_sigma.setRange(0.00001, 1.0)
        self.sp_sigma.setSingleStep(0.0005); self.sp_sigma.setValue(0.003)
        g_tol.addWidget(self.sp_sigma, 0, 1)

        g_tol.addWidget(QLabel("Resid. (m):"),    0, 2)
        self.sp_resid = QDoubleSpinBox()
        self.sp_resid.setDecimals(5); self.sp_resid.setRange(0.00001, 1.0)
        self.sp_resid.setSingleStep(0.0005); self.sp_resid.setValue(0.005)
        g_tol.addWidget(self.sp_resid, 0, 3)

        g_tol.addWidget(QLabel("v-estand.:"),     1, 0)
        self.sp_vstd = QDoubleSpinBox()
        self.sp_vstd.setDecimals(2); self.sp_vstd.setRange(1.0, 10.0)
        self.sp_vstd.setSingleStep(0.5); self.sp_vstd.setValue(3.0)
        g_tol.addWidget(self.sp_vstd, 1, 1)

        v2.addLayout(g_tol)

        h_chk = QHBoxLayout()
        self.chk_croquis = QCheckBox("Croquis SVG en HTML")
        self.chk_croquis.setChecked(True)
        h_chk.addWidget(self.chk_croquis)

        self.chk_abrirlo = QCheckBox("Abrir HTML al terminar")
        self.chk_abrirlo.setChecked(True)
        h_chk.addWidget(self.chk_abrirlo)
        h_chk.addStretch()
        v2.addLayout(h_chk)

        layout.addWidget(grp2)

        # ============ 3 · Acciones ============
        grp3 = QGroupBox("3 · Acciones")
        g3 = QGridLayout(grp3)
        g3.setSpacing(6)

        self.btn_verif = QPushButton("1 · Verificar datos")
        self.btn_calc  = QPushButton("2 · Calcular ajuste")
        self.btn_html  = QPushButton("3 · Generar HTML")
        self.btn_gpkg  = QPushButton("Exportar GeoPackage")
        self.btn_csv   = QPushButton("Exportar CSV")
        self.btn_abrir = QPushButton("Abrir carpeta de reportes")
        self.btn_limpiar = QPushButton("Limpiar")

        self.btn_calc.setObjectName("primary")
        self.btn_html.setObjectName("success")
        self.btn_limpiar.setObjectName("neutral")

        for b in (self.btn_verif, self.btn_calc, self.btn_html):
            b.setMinimumHeight(30)

        self.btn_calc.setEnabled(False)
        self.btn_html.setEnabled(False)
        self.btn_gpkg.setEnabled(False)
        self.btn_csv.setEnabled(False)

        g3.addWidget(self.btn_verif, 0, 0)
        g3.addWidget(self.btn_calc,  0, 1)
        g3.addWidget(self.btn_html,  1, 0)
        g3.addWidget(self.btn_gpkg,  1, 1)
        g3.addWidget(self.btn_csv,   2, 0)
        g3.addWidget(self.btn_abrir, 2, 1)
        g3.addWidget(self.btn_limpiar, 3, 0, 1, 2)

        layout.addWidget(grp3)

        # ============ 4 · Log ============
        grp4 = QGroupBox("4 · Registro de actividad")
        v4 = QVBoxLayout(grp4)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 9))
        self.txt_log.setFixedHeight(160)
        v4.addWidget(self.txt_log)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        v4.addWidget(self.progress)

        layout.addWidget(grp4)

        hb = QHBoxLayout()
        hb.addStretch()
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setObjectName("neutral")
        btn_cerrar.clicked.connect(self.close)
        hb.addWidget(btn_cerrar)
        layout.addLayout(hb)

        # Conexiones
        self.btn_verif.clicked.connect(self._verificar_datos)
        self.btn_calc.clicked.connect(self._calcular)
        self.btn_html.clicked.connect(self._generar_html)
        self.btn_gpkg.clicked.connect(self._exportar_gpkg)
        self.btn_csv.clicked.connect(self._exportar_csv)
        self.btn_abrir.clicked.connect(self._abrir_carpeta_reportes)
        self.btn_limpiar.clicked.connect(self._limpiar)
        self.cmb_capa.currentIndexChanged.connect(self._on_capa_cambio)

    def _cargar_crs_comunes(self):
        opciones = [
            ("EPSG:32617", "WGS 84 / UTM zone 17N (Panamá)"),
            ("EPSG:32616", "WGS 84 / UTM zone 16N"),
            ("EPSG:32618", "WGS 84 / UTM zone 18N"),
            ("EPSG:32619", "WGS 84 / UTM zone 19N"),
            ("EPSG:32615", "WGS 84 / UTM zone 15N"),
            ("EPSG:32620", "WGS 84 / UTM zone 20N"),
            ("EPSG:4326",  "WGS 84 (lat/lon)"),
            ("EPSG:5367",  "CRTM05 Costa Rica"),
        ]
        for codigo, nombre in opciones:
            self.cmb_crs.addItem(f"{codigo} — {nombre}", codigo)
        self.cmb_crs.setCurrentIndex(0)

    def _crs_seleccionado(self):
        data = self.cmb_crs.currentData()
        if data:
            return data
        txt = self.cmb_crs.currentText().strip()
        if "—" in txt:
            txt = txt.split("—")[0].strip()
        return txt or "EPSG:32617"

    # --------------------------------------------------------
    def _log(self, msg, color=None):
        ts = datetime.now().strftime("%H:%M:%S")
        if color:
            self.txt_log.append(
                f'<span style="color:{color};">[{ts}] {msg}</span>')
        else:
            self.txt_log.append(f"[{ts}] {msg}")
        self.txt_log.verticalScrollBar().setValue(
            self.txt_log.verticalScrollBar().maximum())

    def _set_progress(self, val):
        self.progress.setValue(val)

    # --------------------------------------------------------
    def _detectar_coordenadas(self, capa):
        nombres = [f.name().upper() for f in capa.fields()]
        col_x = next((c for c in self.COLS_X if c in nombres), None)
        col_y = next((c for c in self.COLS_Y if c in nombres), None)
        if col_x is None or col_y is None:
            return None, None
        return col_x, col_y

    # --------------------------------------------------------
    def _cargar_capas(self):
        self.cmb_capa.clear()
        for capa in QgsProject.instance().mapLayers().values():
            if isinstance(capa, QgsVectorLayer):
                self.cmb_capa.addItem(capa.name(), capa.id())
        if self.cmb_capa.count() == 0:
            self.lbl_info.setText("⚠ No hay capas vectoriales cargadas.")
            self.lbl_info.setObjectName("info_warn")
            self.lbl_info.setStyleSheet("")
        else:
            self._on_capa_cambio()

    def _on_capa_cambio(self):
        capa = self._capa_actual()
        if capa is None:
            self.lbl_info.setText("—")
            return

        campos = [f.name().upper() for f in capa.fields()]
        faltan = [c for c in self.CAMPOS_REQ if c not in campos]
        n = capa.featureCount()

        if faltan:
            self.lbl_info.setText(
                f'⚠ Capa "{capa.name()}" ({n} filas) — '
                f'faltan campos: {", ".join(faltan)}')
            self.lbl_info.setObjectName("info_err")
            self.lbl_info.setStyleSheet("")
            return

        col_x, col_y = self._detectar_coordenadas(capa)
        if col_x and col_y:
            self.lbl_info.setText(
                f'✓ "{capa.name()}" ({n} filas) — '
                f'coordenadas detectadas: {col_x}/{col_y}')
            self.lbl_info.setObjectName("info_ok")
        else:
            self.lbl_info.setText(
                f'✓ "{capa.name()}" ({n} filas) — '
                f'SIN coordenadas (se calculará sin mapa)')
            self.lbl_info.setObjectName("info_warn")
        self.lbl_info.setStyleSheet("")

    def _capa_actual(self):
        lid = self.cmb_capa.currentData()
        if not lid: return None
        return QgsProject.instance().mapLayer(lid)

    # --------------------------------------------------------
    # 1 · Verificar datos
    # --------------------------------------------------------
    def _verificar_datos(self):
        self._log("Iniciando verificación de datos...")
        self._set_progress(10)

        capa = self._capa_actual()
        if capa is None:
            QMessageBox.warning(self, "Sin capa",
                                "Debe seleccionar una capa de entrada.")
            return

        campos = [f.name().upper() for f in capa.fields()]
        faltan = [c for c in self.CAMPOS_REQ if c not in campos]
        if faltan:
            self._log(f"✗ Faltan campos: {faltan}", "red")
            QMessageBox.critical(self, "Campos faltantes",
                                 f"Faltan campos: {', '.join(faltan)}")
            return
        self._log("✓ Campos requeridos presentes.", "#1e8449")
        self._set_progress(20)

        self.col_x, self.col_y = self._detectar_coordenadas(capa)
        if self.col_x and self.col_y:
            self._log(f"✓ Coordenadas UTM detectadas: "
                      f"X={self.col_x}, Y={self.col_y}", "#1e8449")
        else:
            self._log("ℹ Sin columnas de coordenadas. "
                      "El ajuste se ejecutará igual, sin mapa.",
                      "#b9770e")
        self._set_progress(35)

        try:
            obs = self._leer_capa(capa)
        except Exception as e:
            self._log(f"✗ Error leyendo capa: {e}", "red")
            return
        if not obs:
            self._log("✗ No hay observaciones válidas.", "red")
            return
        self._log(f"✓ {len(obs)} observaciones válidas leídas.", "#1e8449")
        self._set_progress(55)

        cotas_fijas = {o["est"]: o["cota_fija"]
                       for o in obs if o["cota_fija"] is not None}
        if not cotas_fijas:
            self._log("✗ No hay cotas fijas.", "red")
            return
        self._log(f"✓ Cotas fijas: {sorted(cotas_fijas.keys())}", "#1e8449")

        estaciones = set()
        for o in obs:
            estaciones.add(o["ini"]); estaciones.add(o["fin"])
        incognitas = sorted(e for e in estaciones if e not in cotas_fijas)
        self._log(f"  Estaciones: {len(estaciones)}  ·  "
                  f"Fijas: {len(cotas_fijas)}  ·  "
                  f"Incógnitas: {len(incognitas)}")

        # Conectividad (BFS)
        grafo = {}
        for o in obs:
            grafo.setdefault(o["ini"], set()).add(o["fin"])
            grafo.setdefault(o["fin"], set()).add(o["ini"])
        visitados, pila = set(), [next(iter(estaciones))]
        while pila:
            nodo = pila.pop()
            if nodo in visitados: continue
            visitados.add(nodo)
            pila.extend(grafo.get(nodo, []))
        if visitados != estaciones:
            self._log("⚠ La red está desconectada.", "#b9770e")
        else:
            self._log("✓ Red conectada.", "#1e8449")
        self._set_progress(80)

        pares = [(o["ini"], o["fin"]) for o in obs]
        dups = len(pares) - len(set(pares))
        if dups > 0:
            self._log(f"⚠ {dups} observaciones duplicadas.", "#b9770e")
        else:
            self._log("✓ Sin duplicados.", "#1e8449")

        n_coords = len(self.coords_estaciones)
        if self.col_x and self.col_y:
            self._log(f"  Coordenadas leídas para {n_coords} estaciones.",
                      "#1e8449")

        self.obs = obs
        self.capa_src = capa
        self.btn_calc.setEnabled(True)
        self._set_progress(100)
        self._log("Verificación completada.", "#1e8449")

    # --------------------------------------------------------
    def _leer_capa(self, capa):
        nombres = [f.name().upper() for f in capa.fields()]
        def col(n): return nombres.index(n.upper())

        i_est  = col("EST");       i_fija = col("C_FIJA")
        i_ini  = col("C_INICIAL"); i_fin  = col("C_FINAL")
        i_dh   = col("DIF_COTA");  i_dist = col("DIST")

        col_x, col_y = self._detectar_coordenadas(capa)
        i_x = nombres.index(col_x) if col_x else None
        i_y = nombres.index(col_y) if col_y else None

        coords = {}
        obs = []
        for f in capa.getFeatures():
            a = f.attributes()
            est = _to_int(a[i_est]); ini = _to_int(a[i_ini]); fin = _to_int(a[i_fin])
            dh  = _to_float(a[i_dh]); dis = _to_float(a[i_dist])
            cf  = _to_float(a[i_fija])

            if est is None or ini is None or fin is None: continue
            if dh is None or dis is None or dis <= 0: continue

            if i_x is not None and i_y is not None:
                x_val = _to_float(a[i_x])
                y_val = _to_float(a[i_y])
                if x_val is not None and y_val is not None:
                    coords[est] = (x_val, y_val)

            obs.append({"est": est, "cota_fija": cf,
                        "ini": ini, "fin": fin,
                        "dh": dh, "dist": dis})

        obs.sort(key=lambda x: x["est"])
        self.coords_estaciones = coords
        return obs

    # --------------------------------------------------------
    # 2 · Calcular
    # --------------------------------------------------------
    def _calcular(self):
        if not self.obs:
            QMessageBox.warning(self, "Sin datos",
                                "Ejecute primero la verificación.")
            return

        self.autor = self.txt_autor.text().strip() or "Usuario QGIS"
        self._log(f"Calculando ajuste (autor: {self.autor})...")
        self._set_progress(20)

        try:
            self.res = self._ajustar(self.obs)
        except Exception as e:
            import traceback
            self._log(f"✗ Error en ajuste: {e}", "red")
            self._log(traceback.format_exc(), "red")
            QMessageBox.critical(self, "Error", f"Error en el ajuste:\n{e}")
            return

        self._set_progress(100)
        self._log("✓ Ajuste completado.", "#1e8449")
        self._log(f"  σ₀ = {self.res['sigma']:.6f} m")
        self._log(f"  Test χ²: {'✓ OK' if self.res['test_ok'] else '✗ Revisar'}")
        for k, e in enumerate(self.res["incognitas"]):
            self._log(f"  Estación {e}: {self.res['X'][k]:.4f} m  "
                      f"± {self.res['desv'][k]:.6f}")

        self.btn_html.setEnabled(True)
        self.btn_gpkg.setEnabled(True)
        self.btn_csv.setEnabled(True)

    def _ajustar(self, obs):
        tol_sigma = self.sp_sigma.value()
        tol_resid = self.sp_resid.value()
        tol_vstd  = self.sp_vstd.value()

        cotas_fijas = {o["est"]: o["cota_fija"]
                       for o in obs if o["cota_fija"] is not None}
        estaciones = set()
        for o in obs:
            estaciones.add(o["ini"]); estaciones.add(o["fin"])
        incognitas = sorted(e for e in estaciones if e not in cotas_fijas)
        idx = {e: k for k, e in enumerate(incognitas)}
        n, u = len(obs), len(incognitas)
        gl = n - u

        P = np.zeros((n, n)); A = np.zeros((n, u)); fv = np.zeros(n)
        for i, o in enumerate(obs):
            P[i, i] = 1.0 / o["dist"]
            if o["fin"] in idx: A[i, idx[o["fin"]]] =  1.0
            if o["ini"] in idx: A[i, idx[o["ini"]]] = -1.0
            c_ini = cotas_fijas.get(o["ini"], 0.0)
            c_fin = cotas_fijas.get(o["fin"], 0.0)
            fv[i] = o["dh"] - c_fin + c_ini

        ATPA    = A.T @ P @ A
        ATPF    = A.T @ P @ fv
        INVATPA = np.linalg.inv(ATPA)
        X       = INVATPA @ ATPF

        V      = A @ X - fv
        VTPV   = float(V.T @ P @ V)
        sigma2 = VTPV / gl
        sigma  = float(np.sqrt(sigma2))

        Sigma_XX = sigma2 * INVATPA
        desv     = np.sqrt(np.diag(Sigma_XX))

        # ===== MATRICES DE VARIANZA-COVARIANZA =====
        # Q      = P^-1  (cofactor de las observaciones)
        # N^-1   = INVATPA
        #
        # Q_vv   = Q - A·N⁻¹·A'·Q   →  cofactor de RESIDUOS
        # Q_lhat = A·N⁻¹·A'·Q        →  cofactor de observables AJUSTADOS
        Q          = np.linalg.inv(P)
        A_Ninv_AtQ = A @ INVATPA @ A.T @ Q

        Q_vv   = sigma2 * (Q - A_Ninv_AtQ)    # residuos
        Q_lhat = sigma2 * A_Ninv_AtQ           # observables ajustados

        # Redundancia r_i
        H_ii = np.diag(A @ INVATPA @ A.T @ P)
        r_i  = 1.0 - H_ii

        # ===== Residuo estandarizado =====
        # v_i / sqrt(Q_vv_ii)  — se usa Q_vv (residuos), NO Q_lhat
        sd_V = np.sqrt(np.diag(Q_vv))
        # Las observaciones fija-fija (r_i=1) tienen varianza ~0 → NaN
        sd_V = np.where(sd_V > 1e-15, sd_V, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            v_std = V / sd_V

        chi2_obs = VTPV
        chi2_tab = chi2_crit(gl)
        p_valor  = chi2_pval(chi2_obs, gl)
        test_ok  = chi2_obs <= chi2_tab

        tcrit = t_95(gl)
        IC95  = tcrit * desv

        # ===== Estado por observación =====
        #   ✓  residuo normal
        #   ?  residuo moderado (> tol_vstd)
        #   ⚠  residuo crítico (> 3.29, test de Baarda)
        #   —  no aplica (observación de control puro fija-fija)
        estado = []
        for i in range(n):
            vs = v_std[i]
            if np.isnan(vs):
                estado.append("—")
            elif abs(vs) > 3.29:
                estado.append("⚠")
            elif abs(vs) > tol_vstd:
                estado.append("?")
            else:
                estado.append("✓")

        cotas_fin = dict(cotas_fijas)
        for e, k in idx.items():
            cotas_fin[e] = float(X[k])

        dh_ajust = np.array([o["dh"] for o in obs]) + V

        return dict(
            n=n, u=u, gl=gl,
            incognitas=incognitas, idx=idx,
            cotas_fijas=cotas_fijas, cotas_finales=cotas_fin,
            P=P, A=A, AT=A.T, f=fv,
            ATPA=ATPA, INVATPA=INVATPA, ATPF=ATPF,
            X=X, V=V, VTPV=VTPV, dh_ajust=dh_ajust,
            sigma2=sigma2, sigma=sigma,
            Sigma_XX=Sigma_XX, desv=desv,
            Q=Q, Q_vv=Q_vv, Q_lhat=Q_lhat,
            r_i=r_i, v_std=v_std,
            chi2_obs=chi2_obs, chi2_tab=chi2_tab,
            p_valor=p_valor, test_ok=test_ok,
            tcrit=tcrit, IC95=IC95,
            estado=estado,
            cond=np.linalg.cond(ATPA),
            tol_sigma=tol_sigma, tol_resid=tol_resid, tol_vstd=tol_vstd,
        )

    # --------------------------------------------------------
    def _capa_ajustada(self):
        res = self.res
        crs = self._crs_seleccionado()

        capa = QgsVectorLayer(f"Point?crs={crs}",
                              "nivelacion_ajustada", "memory")
        if not capa.isValid():
            raise ValueError(f"No se pudo crear capa con CRS '{crs}'. "
                             "Verifique el código EPSG.")

        prov = capa.dataProvider()

        campos = QgsFields()
        campos.append(QgsField("est",   QVariant.Int))
        campos.append(QgsField("cota",  QVariant.Double, "double", 12, 4))
        campos.append(QgsField("desv",  QVariant.Double, "double", 12, 8))
        campos.append(QgsField("ic95",  QVariant.Double, "double", 12, 8))
        campos.append(QgsField("tipo",  QVariant.String, "string", 12))
        prov.addAttributes(campos)
        capa.updateFields()

        idx_map = res["idx"]
        tiene_coords = bool(self.col_x and self.col_y and
                            self.coords_estaciones)

        for est, cota in res["cotas_finales"].items():
            f = QgsFeature(capa.fields())
            f["est"]  = int(est)
            f["cota"] = float(cota)
            # Conversión explícita para evitar sentinel -999... en GPKG
            f["desv"] = float(res["desv"][idx_map[est]]) if est in idx_map else 0.0
            f["ic95"] = float(res["IC95"][idx_map[est]]) if est in idx_map else 0.0
            f["tipo"] = "fija" if est in res["cotas_fijas"] else "incognita"

            if tiene_coords and est in self.coords_estaciones:
                x, y = self.coords_estaciones[est]
                pt = QgsPointXY(float(x), float(y))
            else:
                pt = QgsPointXY(float(est), float(cota))
            f.setGeometry(QgsGeometry.fromPointXY(pt))
            prov.addFeature(f)

        capa.updateExtents()
        self._aplicar_simbologia(capa)
        return capa

    def _aplicar_simbologia(self, capa):
        cat_fija = QgsRendererCategory(
            "fija",
            QgsMarkerSymbol.createSimple({
                "name": "circle", "size": "3.5",
                "color": "150, 220, 170, 220",
                "outline_color": "60, 130, 80", "outline_width": "0.6"}),
            "Cota fija")
        cat_inc = QgsRendererCategory(
            "incognita",
            QgsMarkerSymbol.createSimple({
                "name": "circle", "size": "3.5",
                "color": "150, 190, 230, 220",
                "outline_color": "60, 100, 150", "outline_width": "0.6"}),
            "Incógnita")
        renderer = QgsCategorizedSymbolRenderer("tipo", [cat_fija, cat_inc])
        capa.setRenderer(renderer)

    # --------------------------------------------------------
    # 3 · HTML
    # --------------------------------------------------------
    def _generar_html(self):
        if not self.res:
            QMessageBox.warning(self, "Sin resultados",
                                "Ejecute primero el cálculo.")
            return

        try:
            proy_dir = os.path.dirname(QgsProject.instance().fileName())
            if not proy_dir:
                proy_dir = os.path.expanduser("~")
        except Exception:
            proy_dir = os.path.expanduser("~")
        carpeta = os.path.join(proy_dir, "reportes_nivelacion")
        os.makedirs(carpeta, exist_ok=True)

        nombre = f"nivelacion_{datetime.now():%Y%m%d_%H%M%S}.html"
        ruta = os.path.join(carpeta, nombre)

        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte HTML", ruta, "HTML (*.html)")
        if not ruta:
            return

        try:
            html = self._construir_html(self.res, self.obs, self.autor)
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(html)
            self._log(f"✓ HTML guardado: {ruta}", "#1e8449")
            if self.chk_abrirlo.isChecked():
                webbrowser.open(f"file:///{ruta.replace(os.sep, '/')}")
            QMessageBox.information(self, "Reporte generado",
                                    f"Guardado en:\n{ruta}")
        except Exception as e:
            import traceback
            self._log(f"✗ Error HTML: {e}", "red")
            self._log(traceback.format_exc(), "red")

    # --------------------------------------------------------
    # 4 · GeoPackage
    # --------------------------------------------------------
    def _exportar_gpkg(self):
        if not self.res:
            QMessageBox.warning(self, "Sin resultados",
                                "Ejecute primero el cálculo.")
            return

        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar GeoPackage", "nivelacion_ajustada.gpkg",
            "GeoPackage (*.gpkg)")
        if not ruta:
            return
        if not ruta.lower().endswith(".gpkg"):
            ruta += ".gpkg"
        if os.path.exists(ruta):
            try:    os.remove(ruta)
            except: pass

        try:
            capa = self._capa_ajustada()
            crs_str = self._crs_seleccionado()

            self._log(f"Exportando con CRS: {crs_str}...")

            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.layerName  = "nivelacion_ajustada"
            opts.fileEncoding = "UTF-8"
            opts.actionOnExistingFile = (
                QgsVectorFileWriter.CreateOrOverwriteFile)

            resultado = QgsVectorFileWriter.writeAsVectorFormatV3(
                capa, ruta, QgsCoordinateTransformContext(), opts)

            err_code = resultado[0] if isinstance(resultado, tuple) else resultado
            err_msg  = resultado[1] if isinstance(resultado, tuple) and len(resultado) > 1 else ""

            if err_code == QgsVectorFileWriter.NoError:
                self._log(f"✓ GeoPackage exportado: {ruta}", "#1e8449")
                self._log(f"  CRS aplicado: {crs_str}", "#1e8449")

                capa_cargada = QgsVectorLayer(
                    f"{ruta}|layername=nivelacion_ajustada",
                    "nivelacion_ajustada", "ogr")
                if capa_cargada.isValid():
                    QgsProject.instance().addMapLayer(capa_cargada)
                    self._log(
                        f"✓ Capa añadida al proyecto "
                        f"(CRS: {capa_cargada.crs().authid()})",
                        "#1e8449")
                else:
                    self._log("⚠ No se pudo cargar la capa al proyecto.",
                              "#b9770e")

                QMessageBox.information(
                    self, "GeoPackage generado",
                    f"Exportado en:\n{ruta}\n\nCRS: {crs_str}")
            else:
                self._log(f"✗ Error GPKG ({err_code}): {err_msg}", "red")
                QMessageBox.critical(self, "Error",
                                     f"No se pudo exportar.\n{err_msg}")
        except Exception as e:
            import traceback
            self._log(f"✗ Excepción GPKG: {e}", "red")
            self._log(traceback.format_exc(), "red")

    # --------------------------------------------------------
    # 5 · CSV
    # --------------------------------------------------------
    def _exportar_csv(self):
        if not self.res:
            QMessageBox.warning(self, "Sin resultados",
                                "Ejecute primero el cálculo.")
            return

        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar CSV", "nivelacion_ajustada.csv",
            "CSV (*.csv)")
        if not ruta:
            return
        if not ruta.lower().endswith(".csv"):
            ruta += ".csv"

        try:
            res = self.res
            idx_map = res["idx"]
            tiene_coords = bool(self.col_x and self.col_y and
                                self.coords_estaciones)

            cab = ["EST", "COTA_AJUSTADA", "DESVIACION",
                   "IC95_INF", "IC95_SUP", "TIPO"]
            if tiene_coords:
                cab += ["X_UTM", "Y_UTM"]

            lineas = [",".join(cab)]
            for est in sorted(res["cotas_finales"].keys()):
                cota = res["cotas_finales"][est]
                desv = res["desv"][idx_map[est]] if est in idx_map else 0.0
                ic95 = res["IC95"][idx_map[est]] if est in idx_map else 0.0
                tipo = "FIJA" if est in res["cotas_fijas"] else "INCÓGNITA"

                fila = [
                    str(est),
                    f"{cota:.4f}",
                    f"{desv:.6f}",
                    f"{cota-ic95:.4f}",
                    f"{cota+ic95:.4f}",
                    tipo,
                ]
                if tiene_coords and est in self.coords_estaciones:
                    x, y = self.coords_estaciones[est]
                    fila += [f"{x:.3f}", f"{y:.3f}"]
                elif tiene_coords:
                    fila += ["", ""]
                lineas.append(",".join(fila))

            meta = [
                f"# Reporte de Nivelación",
                f"# Fecha: {datetime.now():%Y-%m-%d %H:%M:%S}",
                f"# Autor: {self.autor}",
                f"# Capa: {self.capa_src.name() if self.capa_src else 'N/A'}",
                f"# Ecuaciones: {res['n']}  Incógnitas: {res['u']}  "
                f"GL: {res['gl']}",
                f"# Sigma0 = {res['sigma']:.6f} m",
                f"# Test chi2: {'OK' if res['test_ok'] else 'REVISAR'}",
            ]

            with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(meta) + "\n")
                fh.write("\n".join(lineas) + "\n")

            self._log(f"✓ CSV exportado: {ruta}", "#1e8449")
            QMessageBox.information(self, "CSV generado",
                                    f"Exportado en:\n{ruta}")
        except Exception as e:
            import traceback
            self._log(f"✗ Excepción CSV: {e}", "red")
            self._log(traceback.format_exc(), "red")

    # --------------------------------------------------------
    def _abrir_carpeta_reportes(self):
        try:
            proy_dir = os.path.dirname(QgsProject.instance().fileName())
            if not proy_dir:
                proy_dir = os.path.expanduser("~")
        except Exception:
            proy_dir = os.path.expanduser("~")
        carpeta = os.path.join(proy_dir, "reportes_nivelacion")
        os.makedirs(carpeta, exist_ok=True)
        webbrowser.open(f"file:///{carpeta.replace(os.sep, '/')}")

    def _limpiar(self):
        self.obs = None
        self.res = None
        self.coords_estaciones = {}
        self.col_x = self.col_y = None
        self.txt_log.clear()
        self.progress.setValue(0)
        self.btn_calc.setEnabled(False)
        self.btn_html.setEnabled(False)
        self.btn_gpkg.setEnabled(False)
        self.btn_csv.setEnabled(False)
        self._log("Estado limpiado.")

    # ========================================================
    #  HTML
    # ========================================================
    def _construir_html(self, res, obs, autor):
        n, u, gl = res["n"], res["u"], res["gl"]
        n_fijas = len(res["cotas_fijas"])
        n_total = n_fijas + u

        capa = self.capa_src
        crs_src = capa.crs().authid() if capa else ""
        crs_out = self._crs_seleccionado()
        crs = crs_src if crs_src else f"{crs_out} (salida)"
        proy_path = QgsProject.instance().fileName() or "(sin guardar)"
        proy = os.path.basename(proy_path) if proy_path and proy_path != "(sin guardar)" else proy_path

        tiene_coords = bool(self.col_x and self.col_y)

        # ===== Semáforo (con nanmax para no romper con NaN) =====
        sem = []
        sem.append(("σ₀ = " + f"{res['sigma']*1000:.3f} mm",
                    "ok" if res['sigma'] < res["tol_sigma"] else "alerta"))
        vmax = float(np.max(np.abs(res["V"])))
        sem.append(("Residuo máx = " + f"{vmax*1000:.3f} mm",
                    "ok" if vmax < res["tol_resid"] else "alerta"))

        v_std_valid = res["v_std"][~np.isnan(res["v_std"])]
        if len(v_std_valid) > 0:
            vsmax = float(np.max(np.abs(v_std_valid)))
            sem.append(("Resid. estand. máx = " + f"{vsmax:.2f}",
                        "ok" if vsmax < res["tol_vstd"] else "alerta"))
        else:
            sem.append(("Resid. estand. máx = n/a", "ok"))

        sem.append(("Test χ² global",
                    "ok" if res["test_ok"] else "alerta"))
        cond = res["cond"]
        sem.append(("Cond. matriz = " + f"{cond:.1e}",
                    "ok" if cond < 1e10 else "alerta"))

        def f_num(v, dec=4):
            if v is None: return ""
            if abs(v) < 1e-15: return "0." + "0"*dec
            return f"{v:.{dec}f}"

        def f_sci(v):
            if v is None: return ""
            if v == 0: return "0.00E+00"
            return f"{v:.2E}"

        def tabla(M, dec=4, ciencia=False, con_indices=True):
            M = np.atleast_2d(M)
            filas, cols = M.shape
            out = ['<table class="matriz">']
            if con_indices:
                # Cabecera de columnas (1..n)
                out.append('<tr><th class="idx"></th>')
                for j in range(cols):
                    out.append(f'<th class="idx">{j+1}</th>')
                out.append('</tr>')
            for i in range(filas):
                out.append("<tr>")
                if con_indices:
                    out.append(f'<th class="idx">{i+1}</th>')
                for j in range(cols):
                    v = M[i, j]
                    txt = f_sci(v) if ciencia else f_num(v, dec)
                    cls = "cero" if abs(v) < 1e-15 else "val"
                    out.append(f'<td class="{cls}">{txt}</td>')
                out.append("</tr>")
            out.append("</table>")
            return "\n".join(out)

        def croquis_svg():
            if not self.chk_croquis.isChecked():
                return ""
            ids = sorted(res["cotas_finales"].keys())
            nn = len(ids)

            tiene_coords_ok = bool(self.col_x and self.col_y and
                                   self.coords_estaciones and
                                   all(e in self.coords_estaciones for e in ids))

            if tiene_coords_ok:
                # ===== Usar coordenadas UTM reales (croquis a escala) =====
                xs = [self.coords_estaciones[e][0] for e in ids]
                ys = [self.coords_estaciones[e][1] for e in ids]
                xmin, xmax = min(xs), max(xs)
                ymin, ymax = min(ys), max(ys)
                dx = (xmax - xmin) or 1.0
                dy = (ymax - ymin) or 1.0
                # margen del 12%
                xmin -= dx*0.12; xmax += dx*0.12
                ymin -= dy*0.12; ymax += dy*0.12

                W, H = 640, 640
                M = 40  # margen interno
                ancho = xmax - xmin
                alto  = ymax - ymin
                escala = min((W-2*M)/ancho, (H-2*M)/alto)

                def proy(x, y):
                    px = M + (x - xmin) * escala
                    py = H - M - (y - ymin) * escala   # Y invertida
                    return px, py

                pos = {e: proy(*self.coords_estaciones[e]) for e in ids}
            else:
                # ===== Fallback: croquis circular sin coordenadas =====
                cx, cy, R = 320, 320, 210
                pos = {}
                for i, e in enumerate(ids):
                    ang = -math.pi/2 + 2*math.pi*i/nn
                    pos[e] = (cx + R*math.cos(ang), cy + R*math.sin(ang))

            svg = ['<svg xmlns="http://www.w3.org/2000/svg" '
                   'width="640" height="640" '
                   'style="border:1px solid #ccc; background:#fafafa;">']

            # Aristas
            for o in obs:
                if o["ini"] not in pos or o["fin"] not in pos:
                    continue
                x1, y1 = pos[o["ini"]]; x2, y2 = pos[o["fin"]]
                svg.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" '
                           f'x2="{x2:.1f}" y2="{y2:.1f}" '
                           f'stroke="#888" stroke-width="1.4"/>')
                xm, ym = (x1+x2)/2, (y1+y2)/2
                svg.append(f'<text x="{xm:.1f}" y="{ym:.1f}" '
                           f'text-anchor="middle" fill="#444" font-size="9">'
                           f'{o["dh"]:+.2f}</text>')

            # Nodos
            for e in ids:
                if e not in pos: continue
                x, y = pos[e]
                fija = e in res["cotas_fijas"]
                color = "#8ecf9e" if fija else "#96bfe6"
                cota = res["cotas_finales"][e]
                svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="16" '
                           f'fill="{color}" stroke="#fff" stroke-width="2"/>')
                svg.append(f'<text x="{x:.1f}" y="{y+4:.1f}" '
                           f'text-anchor="middle" fill="#2c3e50" '
                           f'font-size="11" font-weight="bold">{e}</text>')
                svg.append(f'<text x="{x:.1f}" y="{y-22:.1f}" '
                           f'text-anchor="middle" fill="#333" '
                           f'font-size="10">{cota:.3f} m</text>')

            # Leyenda "a escala"
            if tiene_coords_ok:
                svg.append('<text x="10" y="20" fill="#666" font-size="10">'
                           'Croquis a escala · UTM</text>')
            else:
                svg.append('<text x="10" y="20" fill="#666" font-size="10">'
                           'Croquis esquemático (sin coordenadas)</text>')

            svg.append('</svg>')
            return "\n".join(svg)

        H = []
        H.append(f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<title>Resultado de la Nivelación</title>
<style>
  body {{ font-family: Calibri, Arial, sans-serif; margin:30px; color:#222; }}
  h1 {{ font-size:22px; text-decoration:underline; margin:0 0 5px 0; }}
  h2 {{ font-size:15px; text-decoration:underline; margin:26px 0 8px 0; }}
  .info {{ background:#f2f2f2; padding:10px 16px; border-radius:6px;
    display:inline-block; margin-bottom:15px; font-size:13px;
    border-left:4px solid #7fb3d5; }}
  .info b {{ display:inline-block; min-width:160px; }}
  table.resumen, table.matriz, table.datos {{
    border-collapse:collapse; font-size:12px; margin-bottom:12px; }}
  table.resumen td, table.resumen th,
  table.datos td, table.datos th {{
    border:1px solid #888; padding:4px 10px; text-align:center; }}
  table.resumen th, table.datos th {{ background:#d9d9d9; }}
  table.matriz td {{ border:1px solid #888; padding:3px 8px;
    text-align:center; font-family:Consolas, monospace; min-width:72px; }}
    table.matriz td.cero {{ color:#aaa; }}
  table.matriz td.val  {{ background:#e8e8e8; }}
  table.matriz th.idx  {{ background:#eaeaea; color:#666;
    font-family:Consolas, monospace; font-size:10px;
    padding:2px 6px; min-width:28px; font-weight:normal; }}
  .meta {{ background:#fafbfc; border:1px solid #d5dbdb;
    border-radius:6px; padding:12px 16px; font-size:12px;
    font-family:Consolas, monospace; color:#333;
    line-height:1.7; max-width:680px; }}
  .sigma {{ background:#fff8dc; padding:8px 15px;
    border-left:4px solid #d4a017; display:inline-block;
    margin:5px 0; font-family:Consolas, monospace; }}
  .semaforo {{ padding:6px 14px; border-radius:4px; margin:4px 6px 4px 0;
    display:inline-block; font-size:13px; font-weight:bold; }}
  .semaforo.ok     {{ background:#e8f5e9; color:#2e7d32; }}
  .semaforo.alerta {{ background:#ffebee; color:#c62828; }}
  .badge-ok  {{ color:#2e7d32; font-weight:bold; }}
  .badge-rev {{ color:#e65100; font-weight:bold; }}
  .badge-mal {{ color:#c62828; font-weight:bold; }}
  .badge-na  {{ color:#888;    font-weight:bold; }}
  a.inicio {{ display:inline-block; margin-top:20px; color:#0645ad;
    font-weight:bold; text-decoration:none; }}
  .footer {{ margin-top:40px; font-size:11px; color:#888;
    border-top:1px solid #ccc; padding-top:8px; }}
</style></head><body id="inicio">

<h1>RESULTADO DE LA NIVELACIÓN</h1>
<div class="info">
  <b>Calculado por:</b> {autor}<br>
  <b>Fecha:</b> {datetime.now():%Y-%m-%d %H:%M:%S}<br>
  <b>Proyecto:</b> <span title="{proy_path}">{proy}</span><br>
  <b>Sistema de referencia:</b> {crs}<br>
  <b>Capa fuente:</b> {capa.name() if capa else 'N/A'}
  ({capa.featureCount() if capa else 0} filas)<br>
  <b>Coordenadas UTM:</b>
  {'Sí (' + self.col_x + '/' + self.col_y + ')' if tiene_coords else 'No disponibles'}<br>
  <b>Generado por:</b> Plugin Análisis de Nivelación v2.2
</div>

<h2>RESUMEN</h2>
<table class="resumen">
  <tr><th>Concepto</th><th>Valor</th></tr>
  <tr><td>Número de ecuaciones</td><td>{n}</td></tr>
  <tr><td>Número de incógnitas</td><td>{u}</td></tr>
  <tr><td>Grados de confianza</td><td>{gl}</td></tr>
  <tr><td>Cotas fijas</td><td>{n_fijas}</td></tr>
  <tr><td>Total de cotas medidas</td><td>{n_total}</td></tr>
</table>

<h2>SEMÁFORO DE CONTROL DE CALIDAD</h2>
<div>""")

        for txt, cls in sem:
            H.append(f'<div class="semaforo {cls}">{txt}</div>')
        H.append(f"""</div>
<div style="font-size:12px;color:#666;">
  Criterios: σ₀ ≤ {res['tol_sigma']*1000:.0f} mm ·
  residuo ≤ {res['tol_resid']*1000:.0f} mm ·
  resid. estand. ≤ {res['tol_vstd']} · test χ² al 95%
</div>""")

        svg = croquis_svg()
        if svg:
            H.append('<h2>CROQUIS DE LA RED</h2>')
            H.append(svg)
            H.append('<p style="font-size:11px;color:#666;">'
                     '🟢 Cota fija &nbsp; 🔵 Incógnita &nbsp;| '
                     'Aristas etiquetadas con el desnivel medido (m)</p>')

        # ===== Tabla de observaciones con manejo de NaN =====
        H.append('<h2>OBSERVACIONES Y RESIDUOS</h2>')
        H.append('<table class="datos">'
                 '<tr><th>Obs</th><th>Ini</th><th>Fin</th>'
                 '<th>dh medido</th><th>dh ajustado</th>'
                 '<th>Residuo (m)</th><th>r<sub>i</sub></th>'
                 '<th>v estand.</th><th>Estado</th></tr>')

        cls_map = {"✓": "badge-ok", "?": "badge-rev",
                   "⚠": "badge-mal", "—": "badge-na"}

        for i, o in enumerate(obs):
            est = res["estado"][i]
            cls = cls_map.get(est, "")
            if np.isnan(res["v_std"][i]):
                vstd_txt = "—"
            else:
                vstd_txt = f"{res['v_std'][i]:+.2f}"
            H.append(
                f'<tr><td>{o["est"]}</td><td>{o["ini"]}</td><td>{o["fin"]}</td>'
                f'<td>{o["dh"]:.4f}</td>'
                f'<td>{res["dh_ajust"][i]:.4f}</td>'
                f'<td>{res["V"][i]:+.6f}</td>'
                f'<td>{res["r_i"][i]:.3f}</td>'
                f'<td>{vstd_txt}</td>'
                f'<td class="{cls}">{est}</td></tr>')
        H.append('</table>')

        # Matrices básicas
        H.append(f'<h2>MATRIZ DE PESOS P ({n} × {n})</h2>' + tabla(res["P"], 4))
        H.append(f'<h2>MATRIZ DE DISEÑO A ({n} × {u})</h2>' + tabla(res["A"], 4))
        H.append(f'<h2>MATRIZ DE DISEÑO F ({n} × 1)</h2>'
                 + tabla(res["f"].reshape(-1,1), 4))
        H.append(f'<h2>MATRIZ TRASPUESTA DE A (AT) ({u} × {n})</h2>'
                 + tabla(res["AT"], 4))
        H.append(f'<h2>MATRIZ AT(PA) ({u} × {u})</h2>' + tabla(res["ATPA"], 4))
        H.append(f'<h2>MATRIZ INVERSA (ATPA) ({u} × {u})</h2>'
                 + tabla(res["INVATPA"], 4))
        H.append(f'<h2>MATRIZ (ATPF) ({u} × 1)</h2>'
                 + tabla(res["ATPF"].reshape(-1,1), 4))

        # ===== Tabla completa: fijas + incógnitas =====
        H.append('<h2>RESUMEN DE COTAS FINALES</h2>'
                 '<table class="datos">'
                 '<tr><th>Est</th><th>Cota final (m)</th>'
                 '<th>± σ (m)</th><th>± IC95%</th>'
                 '<th>Tipo</th><th>Fuente</th></tr>')

        # Incógnitas primero (ajustadas)
        for k, e in enumerate(res["incognitas"]):
            H.append(f'<tr><td>{e}</td>'
                     f'<td>{f_num(res["X"][k],4)}</td>'
                     f'<td>{f_sci(res["desv"][k])}</td>'
                     f'<td>{f_sci(res["IC95"][k])}</td>'
                     f'<td>Incógnita</td>'
                     f'<td>Ajustada</td></tr>')

        # Luego las fijas
        for e in sorted(res["cotas_fijas"].keys()):
            H.append(f'<tr><td>{e}</td>'
                     f'<td>{f_num(res["cotas_fijas"][e],4)}</td>'
                     f'<td>—</td>'
                     f'<td>—</td>'
                     f'<td>Fija</td>'
                     f'<td>Dato</td></tr>')
        H.append('</table>')

        H.append('<h2>VECTOR DE RESIDUOS V</h2>'
                 + tabla(res["V"].reshape(-1,1), 8))

        H.append('<h2>CONTROL ESTADÍSTICO</h2>'
                 f'<div class="sigma"><b>σ₀² </b> = {f_sci(res["sigma2"])}</div><br>'
                 f'<div class="sigma"><b>σ₀  </b> = {f_sci(res["sigma"])}</div><br>'
                 f'<div class="sigma"><b>t<sub>95,{gl}</sub></b> = '
                 f'{res["tcrit"]:.4f}</div>')
        H.append(f'<div style="font-size:13px;margin-top:8px;">'
                 f'<b>Test χ² global</b> &nbsp; '
                 f'χ²<sub>obs</sub> = {res["chi2_obs"]:.4e} &nbsp;|&nbsp; '
                 f'χ²<sub>tab(95%)</sub> = {res["chi2_tab"]:.4e} &nbsp;|&nbsp; '
                 f'p-valor ≈ {res["p_valor"]:.3f} &nbsp;→&nbsp; '
                 f'<b>{"✓ Aceptable" if res["test_ok"] else "✗ Revisar"}</b>'
                 f'</div>')

        # ===== Matriz var-cov de parámetros =====
        H.append(f'<h2>MATRIZ VARIANZA-COVARIANZA DE PARÁMETROS '
                 f'({u} × {u})</h2>' + tabla(res["Sigma_XX"], ciencia=True))

        # ===== Cotas ajustadas con IC95 =====
        H.append('<h2>COTAS AJUSTADAS CON INTERVALO DE CONFIANZA 95%</h2>'
                 '<table class="datos">'
                 '<tr><th>Estación</th><th>Cota (m)</th>'
                 '<th>± σ</th><th>± IC95%</th>'
                 '<th>Intervalo de confianza</th></tr>')
        for k, e in enumerate(res["incognitas"]):
            c = res["cotas_finales"][e]
            s = res["desv"][k]
            ic = res["IC95"][k]
            H.append(f'<tr><td>Estación {e}</td>'
                     f'<td>{f_num(c,4)}</td>'
                     f'<td>{f_sci(s)}</td>'
                     f'<td>{f_sci(ic)}</td>'
                     f'<td>[{c-ic:.4f} , {c+ic:.4f}]</td></tr>')
        H.append('</table>')

        # ===== Matrices var-cov (con nombres correctos) =====
        H.append(f'<h2>MATRIZ VARIANZA-COVARIANZA DE OBSERVABLES '
                 f'AJUSTADOS (Q<sub>l̂l̂</sub>) ({n} × {n})</h2>'
                 + tabla(res["Q_lhat"], ciencia=True))
        H.append(f'<h2>MATRIZ VARIANZA-COVARIANZA DE RESIDUOS '
                 f'(Q<sub>vv</sub>) ({n} × {n})</h2>'
                 + tabla(res["Q_vv"], ciencia=True))

        H.append('<h2>DESVIACIONES TÍPICAS POR ESTACIÓN</h2>'
                 '<table class="resumen">'
                 '<tr><th>Estación</th><th>± σ (m)</th></tr>')
        for k, e in enumerate(res["incognitas"]):
            H.append(f'<tr><td>Est: {e}</td>'
                     f'<td>{f_num(res["desv"][k],6)}</td></tr>')
        H.append('</table>')

                # ===== Metadatos técnicos =====
        H.append('<h2>METADATOS TÉCNICOS</h2>')
        H.append('<div class="meta">')
        H.append(f'<b>Método:</b> Gaus-Markov con pesos 1/distancia<br>')
        H.append(f'<b>Ecuaciones:</b> {n} · '
                 f'<b>Incógnitas:</b> {u} · '
                 f'<b>Redundancia total:</b> {gl}<br>')
        H.append(f'<b>σ₀²</b> = {f_sci(res["sigma2"])} · '
                 f'<b>σ₀</b> = {f_sci(res["sigma"])} m<br>')
        H.append(f'<b>Test χ²:</b> '
                 f'χ²<sub>obs</sub> = {res["chi2_obs"]:.4e} vs '
                 f'χ²<sub>tab(95%)</sub> = {res["chi2_tab"]:.4e} '
                 f'→ {"✓ Aceptable" if res["test_ok"] else "✗ Revisar"}<br>')
        H.append(f'<b>Condición de ATPA:</b> {res["cond"]:.2e}<br>')
        H.append(f'<b>Observaciones con residuo > 3σ:</b> '
                 f'{int(np.sum(np.abs(v_std_valid) > 3.0)) if len(v_std_valid) > 0 else 0}<br>')
        H.append(f'<b>Fecha de procesamiento:</b> '
                 f'{datetime.now():%Y-%m-%d %H:%M:%S}<br>')
        H.append(f'<b>Autor:</b> {autor}')
        H.append('</div>')

        H.append(f"""
<h2>FIN DEL PROCESO</h2>
<a class="inicio" href="#inicio">↑ IR AL INICIO</a>
<div class="footer">
  Generado con QGIS + Python · Plugin Análisis de Nivelación v2.2 ·
  Ajuste Gaus-Markov · {datetime.now():%Y-%m-%d %H:%M:%S}
</div>
</body></html>""")

        return "\n".join(H)
