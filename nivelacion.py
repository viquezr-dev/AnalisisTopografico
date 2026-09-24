# -*- coding: utf-8 -*-
"""
Plugin: Análisis Topográfico  ·  v3.1
Autor:  Raul Viquez
Licencia: GPL v3

Dos modos en un solo plugin:
  · Nivelación  — ajuste Gaus-Markov con pesos 1/dist
  · Helmert     — transformación 4p (similaridad) o 6p (afín)

Detección informativa del modo según los campos de la capa:
  · Nivelación → EST, C_FIJA, C_INICIAL, C_FINAL, DIF_COTA, DIST
  · Helmert    → PUNTO, X_ORIGEN, Y_ORIGEN, X_DESTINO, Y_DESTINO, USO
"""

import os
import math
import webbrowser
from datetime import datetime

import numpy as np

from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QTextEdit,
    QGroupBox, QMessageBox, QFileDialog, QDoubleSpinBox,
    QProgressBar, QCheckBox, QWidget, QRadioButton,
    QButtonGroup, QSizePolicy, QFrame, QTabWidget
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt, QVariant

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsField, QgsFields, QgsVectorFileWriter,
    QgsCoordinateTransformContext, QgsMarkerSymbol,
    QgsCategorizedSymbolRenderer, QgsRendererCategory
)

# Importación del motor matemático (mismo directorio)
try:
    from . import helmert
except ImportError:
    import helmert


# ============================================================
#  UTILIDADES NUMÉRICAS
# ============================================================
def _to_float(s):
    if s is None:
        return None
    s = str(s).strip()
    if s == "" or s.upper() in ("NULL", "NA", "N/A"):
        return None
    try:
        return float(s.replace(",", "."))
    except BaseException:
        return None


def _to_int(s):
    v = _to_float(s)
    return int(v) if v is not None else None


def _to_id(s):
    """
    Devuelve el identificador de estación como string limpio.
    Acepta números (1, 2, 3) o strings (BM_A, P1, T-01).
    """
    if s is None:
        return None
    s = str(s).strip()
    if s == "" or s.upper() in ("NULL", "NA", "N/A"):
        return None
    return s


# Estadísticas (con fallback)
try:
    from scipy.stats import t as _t, chi2 as _chi2
    def t_95(gl): return float(_t.ppf(0.975, gl))
    def chi2_crit(gl): return float(_chi2.ppf(0.95, gl))
    def chi2_pval(x, gl): return float(1 - _chi2.cdf(x, gl))
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False
    _TABLA_T = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
                6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
                12: 2.179, 15: 2.131, 20: 2.086, 30: 2.042,
                60: 2.000, 120: 1.980}

    def t_95(gl):
        if gl in _TABLA_T:
            return _TABLA_T[gl]
        for k in sorted(_TABLA_T):
            if gl <= k:
                return _TABLA_T[k]
        return 1.960

    def chi2_crit(gl):
        z = 1.645
        return gl * (1 - 2 / (9 * gl) + z * math.sqrt(2 / (9 * gl)))**3

    def chi2_pval(x, gl):
        return None


# ============================================================
#  HOJA DE ESTILOS (pastel, con QTabWidget)
# ============================================================
QSS = """
/* ============================================================
   BASE
   ============================================================ */
QDialog {
    background: #f3f6f8;
    font-family: 'Segoe UI', 'Calibri', sans-serif;
    font-size: 12px;
    color: #243746;
}
QLabel {
    color: #2c3e50;
    background: transparent;
}

/* ============================================================
   ENCABEZADO
   ============================================================ */
QLabel#titulo {
    font-size: 16px;
    font-weight: 700;
    color: #1b4f72;
    padding: 7px;
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #e9f5f7, stop:1 #d4eaee);
    border: 1px solid #9fcbd3;
    border-radius: 6px;
}
QLabel#subtitulo {
    color: #7f8c8d;
    font-size: 10px;
    padding: 2px;
}

/* ============================================================
   QGroupBox — tarjetas blancas con borde suave
   ============================================================ */
QGroupBox {
    font-weight: 600;
    color: #1b4f72;
    background: #ffffff;
    border: 1px solid #e1e8ed;
    border-radius: 7px;
    margin-top: 9px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #1b4f72;
    background: #f7f8fa;
}

/* ============================================================
   PESTAÑAS
   ============================================================ */
QTabWidget::pane {
    border: 1px solid #e1e8ed;
    border-radius: 6px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: #ecf0f1;
    color: #7f8c8d;
    border: 1px solid #e1e8ed;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 13px;
    min-width: 86px;
    font-weight: 600;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #1b4f72;
    border-bottom: 2px solid #a9cce3;
}
QTabBar::tab:hover:!selected {
    background: #f4f8fb;
    color: #5499c7;
}

/* ============================================================
   CAMPOS DE ENTRADA
   ============================================================ */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #d5dbdb;
    border-radius: 4px;
    padding: 3px 7px;
    min-height: 22px;
    color: #2c3e50;
    selection-background-color: #a9cce3;
    selection-color: #1b4f72;
}
QLineEdit:focus, QComboBox:focus,
QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #5499c7;
    background: #fbfdfe;
}
QLineEdit:disabled, QComboBox:disabled,
QDoubleSpinBox:disabled, QSpinBox:disabled {
    background: #f7f8fa;
    color: #95a5a6;
    border-color: #e1e8ed;
}
QComboBox::drop-down {
    width: 24px;
    border-left: 1px solid #e1e8ed;
    background: #fbfdfe;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}
QComboBox::down-arrow {
    width: 10px;
    height: 10px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #a9cce3;
    border-radius: 4px;
    selection-background-color: #d6eaf8;
    selection-color: #1b4f72;
    padding: 4px;
}

/* ============================================================
   BOTONES
   ============================================================ */
QPushButton {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #d6eaf8, stop:1 #a9cce3);
    color: #1b4f72;
    border: 1px solid #a9cce3;
    border-radius: 5px;
    padding: 5px 11px;
    font-weight: 600;
    min-height: 27px;
}
QPushButton:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #a9cce3, stop:1 #7fb3d5);
    color: #ffffff;
}
QPushButton:pressed {
    background: #5499c7;
    color: #ffffff;
}
QPushButton:disabled {
    background: #ecf0f1;
    color: #b0b8bf;
    border-color: #e1e8ed;
}

/* Botón de refresh (↻) — solo el icono, compacto */
QPushButton#refresh {
    background: #ecf0f1;
    color: #5499c7;
    font-size: 16px;
    padding: 0;
    border: 1px solid #d5dbdb;
}
QPushButton#refresh:hover {
    background: #a9cce3;
    color: #ffffff;
}

/* Botón éxito (Calcular, Generar HTML) */
QPushButton#success {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #d5f5e3, stop:1 #a9dfbf);
    color: #186a3b;
    border: 1px solid #a9dfbf;
}
QPushButton#success:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #a9dfbf, stop:1 #7dcea0);
    color: #ffffff;
}
QPushButton#success:disabled {
    background: #ecf0f1;
    color: #b0b8bf;
    border-color: #e1e8ed;
}

/* Botón neutral (Limpiar, GeoPackage, CSV…) */
QPushButton#neutral {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #f4f6f7, stop:1 #e5e8e8);
    color: #5d6d7e;
    border: 1px solid #d5dbdb;
}
QPushButton#neutral:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #e5e8e8, stop:1 #d5dbdb);
    color: #2c3e50;
}

/* Botón peligro (Cerrar) */
QPushButton#danger {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #fadbd8, stop:1 #f5b7b1);
    color: #922b21;
    border: 1px solid #f5b7b1;
}
QPushButton#danger:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #f5b7b1, stop:1 #ec7063);
    color: #ffffff;
}

/* ============================================================
   ÁREA DE TEXTO (log)
   ============================================================ */
QTextEdit {
    background: #ffffff;
    color: #2c3e50;
    border: 1px solid #d5dbdb;
    border-radius: 5px;
    padding: 6px;
    font-family: 'Consolas', 'Cascadia Mono', monospace;
    font-size: 11px;
    selection-background-color: #a9cce3;
    selection-color: #1b4f72;
}
QTextEdit:focus {
    border: 1px solid #5499c7;
}

/* ============================================================
   BARRA DE PROGRESO
   ============================================================ */
QProgressBar {
    background: #ecf0f1;
    border: 1px solid #d5dbdb;
    border-radius: 5px;
    height: 18px;
    text-align: center;
    color: #2c3e50;
    font-weight: 600;
    font-size: 11px;
}
QProgressBar::chunk {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #a9dfbf, stop:1 #7dcea0);
    border-radius: 4px;
}

/* ============================================================
   CHECKBOX
   ============================================================ */
QCheckBox {
    spacing: 8px;
    padding: 3px 0;
    color: #2c3e50;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #a9cce3;
    border-radius: 3px;
    background: #ffffff;
}
QCheckBox::indicator:hover {
    border: 1px solid #5499c7;
}
QCheckBox::indicator:checked {
    background: #a9cce3;
    border: 1px solid #5499c7;
}

/* ============================================================
   RADIOBUTTON
   ============================================================ */
QRadioButton {
    spacing: 8px;
    padding: 4px 8px;
    font-size: 12px;
    font-weight: 600;
    color: #2c3e50;
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #a9cce3;
    border-radius: 9px;
    background: #ffffff;
}
QRadioButton::indicator:hover {
    border: 2px solid #5499c7;
}
QRadioButton::indicator:checked {
    background: #5499c7;
    border: 4px solid #d6eaf8;
}

/* ============================================================
   SEPARADORES Y ETIQUETAS ESPECIALES
   ============================================================ */
QFrame#linea {
    background: #e1e8ed;
    max-height: 1px;
    border: none;
}
QLabel#sectionLabel {
    color: #1b4f72;
    font-weight: 700;
    font-size: 12px;
}
QLabel#helper {
    color: #7f8c8d;
    background: #f4f8fb;
    border: 1px solid #e1e8ed;
    border-radius: 5px;
    padding: 8px 10px;
    font-size: 11px;
}

/* Info de la capa — 3 estados */
QLabel#info_ok {
    color: #186a3b;
    background: #eafaf1;
    border: 1px solid #a9dfbf;
    border-radius: 5px;
    padding: 7px 10px;
}
QLabel#info_warn {
    color: #7d6608;
    background: #fef9e7;
    border: 1px solid #f9e79f;
    border-radius: 5px;
    padding: 7px 10px;
}
QLabel#info_err {
    color: #922b21;
    background: #fdedec;
    border: 1px solid #f5b7b1;
    border-radius: 5px;
    padding: 7px 10px;
}

/* ============================================================
   TOOLTIPS
   ============================================================ */
QToolTip {
    background: #2c3e50;
    color: #ffffff;
    border: 1px solid #1b4f72;
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 11px;
}

/* ============================================================
   SCROLLBARS — sutiles y profesionales
   ============================================================ */
QScrollBar:vertical {
    background: #f7f8fa;
    width: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: #c8d6e0;
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #a9cce3;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: #f7f8fa;
    height: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #c8d6e0;
    border-radius: 5px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #a9cce3;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
}
"""


# ============================================================
#  PLUGIN
# ============================================================
class AnalisisTopografico:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, "Análisis Topográfico",
                              self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.action.setStatusTip(
            "Ajuste topográfico: nivelación y transformación Helmert")
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Análisis Topográfico", self.action)

    def unload(self):
        self.iface.removePluginMenu("&Análisis Topográfico", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dialog:
            self.dialog.close()
            self.dialog = None

    def run(self):
        if self.dialog is None:
            self.dialog = DialogoTopografico(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()


# ============================================================
#  DIÁLOGO PRINCIPAL
# ============================================================
class DialogoTopografico(QDialog):

    # --- Campos por modo ---
    CAMPOS_NIVEL = ["EST", "C_FIJA", "C_INICIAL", "C_FINAL",
                    "DIF_COTA", "DIST"]
    CAMPOS_HELM = ["PUNTO", "X_ORIGEN", "Y_ORIGEN",
                   "X_DESTINO", "Y_DESTINO", "USO"]

    COLS_X_NIVEL = ["COORD_X", "UTM_X", "X_UTM", "COORDENADA_X",
                    "ESTE", "EAST", "X", "E"]
    COLS_Y_NIVEL = ["COORD_Y", "UTM_Y", "Y_UTM", "COORDENADA_Y",
                    "NORTE", "NORTH", "Y", "N"]

    MODO_NIVEL = "nivelacion"
    MODO_HELM = "helmert"

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Análisis Topográfico  ·  v3.1")
        self.setStyleSheet(QSS)
        self.setMinimumWidth(640)
        self.setMaximumWidth(780)
        self.resize(680, 700)
        self.setMinimumHeight(600)

        # ---- Estado ----
        self.modo = self.MODO_NIVEL
        self.obs = None       # nivelación
        self.res = None       # nivelación
        self.pts_control = None
        self.pts_verificacion = None
        self.pts_a_transf = None
        self.res_helmert = None       # helmert: resultado del ajuste

        self.autor = ""
        self.capa_src = None
        self.col_x = None       # nivelación
        self.col_y = None
        self.coords_estaciones = {}         # nivelación
        self.cotas_huerfanas = {}

        # ---- Construcción ----
        self._construir_ui()
        self._cargar_capas()

    # --------------------------------------------------------
    #  CONSTRUCCIÓN DE LA UI
    # --------------------------------------------------------
    def _construir_ui(self):
        """Construye la interfaz. La lógica de cálculo no se modifica."""
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(5)

        # ----------------------------------------------------
        # Encabezado
        # ----------------------------------------------------
        titulo = QLabel("ANÁLISIS TOPOGRÁFICO")
        titulo.setObjectName("titulo")
        titulo.setAlignment(Qt.AlignCenter)
        root.addWidget(titulo)

        subtitulo = QLabel("v3.1 · Nivelación y Transformación Helmert")
        subtitulo.setObjectName("subtitulo")
        subtitulo.setAlignment(Qt.AlignCenter)
        root.addWidget(subtitulo)

        # ----------------------------------------------------
        # Modo de cálculo: se conserva exactamente la lógica
        # de los radio buttons originales.
        # ----------------------------------------------------
        grp_modo = QGroupBox("Modo de cálculo")
        h_modo = QHBoxLayout(grp_modo)
        h_modo.setContentsMargins(8, 7, 8, 6)

        self.radio_nivel = QRadioButton("Nivelación")
        self.radio_helm = QRadioButton("Transformación Helmert")
        self.radio_nivel.setChecked(True)

        self.grupo_modo = QButtonGroup(self)
        self.grupo_modo.addButton(self.radio_nivel)
        self.grupo_modo.addButton(self.radio_helm)

        h_modo.addWidget(self.radio_nivel)
        h_modo.addStretch()
        h_modo.addWidget(self.radio_helm)
        root.addWidget(grp_modo)

        # ----------------------------------------------------
        # Pestañas
        # ----------------------------------------------------
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        root.addWidget(self.tabs, 1)

        # ====================================================
        # PESTAÑA 1 — DATOS
        # ====================================================
        tab_datos = QWidget()
        datos = QVBoxLayout(tab_datos)
        datos.setContentsMargins(7, 7, 7, 7)
        datos.setSpacing(5)

        grp_capa = QGroupBox("Selección de tabla / capa de entrada")
        v_capa = QVBoxLayout(grp_capa)
        v_capa.setContentsMargins(10, 14, 10, 10)
        v_capa.setSpacing(7)

        fila_capa = QHBoxLayout()
        lbl_capa = QLabel("Tabla / capa:")
        self.cmb_capa = QComboBox()
        self.cmb_capa.setEditable(True)
        self.cmb_capa.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_capa.setMinimumHeight(30)
        self.cmb_capa.setToolTip(
            "Seleccione la tabla o capa vectorial que contiene los datos "
            "del ajuste."
        )

        btn_ref = QPushButton("↻")
        btn_ref.setObjectName("refresh")
        btn_ref.setFixedSize(36, 32)
        btn_ref.setToolTip("Actualizar tablas y capas del proyecto")
        btn_ref.clicked.connect(self._cargar_capas)

        fila_capa.addWidget(lbl_capa)
        fila_capa.addWidget(self.cmb_capa, 1)
        fila_capa.addWidget(btn_ref)
        v_capa.addLayout(fila_capa)

        self.lbl_info = QLabel("—")
        self.lbl_info.setObjectName("info_warn")
        self.lbl_info.setWordWrap(True)
        v_capa.addWidget(self.lbl_info)
        datos.addWidget(grp_capa)
        grp_plantillas = QGroupBox("¿Primera vez usando el plugin?")
        v_plant = QVBoxLayout(grp_plantillas)
        v_plant.setContentsMargins(10, 14, 10, 10)
        v_plant.setSpacing(7)

        lbl_plant = QLabel(
            "Genera dos archivos CSV de ejemplo con los campos correctos "
            "para nivelación y para Helmert. Ábrelos con Excel, "
            "rellena tus datos y cárgalos en QGIS."
        )
        lbl_plant.setWordWrap(True)
        lbl_plant.setObjectName("helper")
        v_plant.addWidget(lbl_plant)

        self.btn_plantillas = QPushButton(
            "📥 Generar plantillas CSV de ejemplo")
        self.btn_plantillas.setMinimumHeight(36)
        self.btn_plantillas.setToolTip(
            "Genera dos archivos CSV con los campos correctos:\n"
            "  · plantilla_nivelacion.csv\n"
            "  · plantilla_coordenadas.csv"
        )
        self.btn_plantillas.setObjectName("neutral")
        v_plant.addWidget(self.btn_plantillas)

        datos.addWidget(grp_plantillas)

        grp_meta = QGroupBox("Metadatos")
        meta = QFormLayout(grp_meta)
        meta.setContentsMargins(10, 14, 10, 10)
        meta.setSpacing(7)

        self.txt_autor = QLineEdit()
        self.txt_autor.setPlaceholderText("Nombre de quien realiza el cálculo")
        meta.addRow("Autor:", self.txt_autor)

        self.cmb_crs = QComboBox()
        self.cmb_crs.setEditable(True)
        self.cmb_crs.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_crs.setMinimumHeight(30)
        self._cargar_crs_comunes()
        meta.addRow("CRS de salida:", self.cmb_crs)

        datos.addWidget(grp_meta)
        datos.addStretch(1)
        self.tabs.addTab(tab_datos, "① Datos")

        # ====================================================
        # PESTAÑA 2 — PARÁMETROS
        # ====================================================
        tab_param = QWidget()
        param = QVBoxLayout(tab_param)
        param.setContentsMargins(7, 7, 7, 7)
        param.setSpacing(5)

        self.grp_params = QGroupBox("Parámetros del ajuste")
        vp = QVBoxLayout(self.grp_params)
        vp.setContentsMargins(10, 14, 10, 10)
        vp.setSpacing(8)

        f_tol = QFormLayout()
        f_tol.setSpacing(7)

        self.sp_sigma = QDoubleSpinBox()
        self.sp_sigma.setDecimals(5)
        self.sp_sigma.setRange(0.00001, 10.0)
        self.sp_sigma.setSingleStep(0.0005)
        self.sp_sigma.setValue(0.003)
        self.sp_sigma.setSuffix(" m")
        f_tol.addRow("σ₀:", self.sp_sigma)

        self.sp_resid = QDoubleSpinBox()
        self.sp_resid.setDecimals(5)
        self.sp_resid.setRange(0.00001, 10.0)
        self.sp_resid.setSingleStep(0.0005)
        self.sp_resid.setValue(0.005)
        self.sp_resid.setSuffix(" m")
        f_tol.addRow("Residuo máximo:", self.sp_resid)

        self.sp_vstd = QDoubleSpinBox()
        self.sp_vstd.setDecimals(2)
        self.sp_vstd.setRange(1.0, 10.0)
        self.sp_vstd.setSingleStep(0.5)
        self.sp_vstd.setValue(3.0)
        self.sp_vstd.setSuffix(" σ")
        f_tol.addRow("Residuo estandarizado:", self.sp_vstd)

        vp.addLayout(f_tol)

        # ---- Nivelación
        self.bloque_nivel = QWidget()
        vn = QVBoxLayout(self.bloque_nivel)
        vn.setContentsMargins(0, 6, 0, 0)
        vn.setSpacing(5)

        self.chk_invertir = QCheckBox(
            "Convención de campo (atrás − adelante)"
        )
        self.chk_invertir.setChecked(False)
        self.chk_invertir.setToolTip(
            "Desactivado: H_final − H_inicial = dh (estándar)\n"
            "Activado: H_inicial − H_final = dh (campo)"
        )
        vn.addWidget(self.chk_invertir)
        vn.addWidget(QLabel(
            "Estándar → H_final − H_inicial = dh\n"
            "Campo → H_inicial − H_final = dh"
        ))
        vp.addWidget(self.bloque_nivel)

        # ---- Helmert
        self.bloque_helm = QWidget()
        vh = QVBoxLayout(self.bloque_helm)
        vh.setContentsMargins(0, 6, 0, 0)
        vh.setSpacing(5)

        f_helm = QFormLayout()
        f_helm.setSpacing(7)

        self.cmb_modelo_helm = QComboBox()
        self.cmb_modelo_helm.addItem(
            "4 parámetros — Similaridad (rot + escala + trasl.)", 4
        )
        self.cmb_modelo_helm.addItem(
            "6 parámetros — Afín (escala X/Y + shear)", 6
        )
        self.cmb_modelo_helm.setMinimumHeight(30)
        f_helm.addRow("Modelo:", self.cmb_modelo_helm)
        vh.addLayout(f_helm)

        vh.addWidget(QLabel(
            "Puntos de control: USO = Control\n"
            "Puntos a transformar: USO = Control y destino vacío"
        ))
        vp.addWidget(self.bloque_helm)
        self.bloque_helm.setVisible(False)

        # ---- Reporte
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("linea")
        vp.addWidget(sep)

        lbl_rep = QLabel("Opciones de reporte")
        lbl_rep.setObjectName("sectionLabel")
        vp.addWidget(lbl_rep)

        self.chk_croquis = QCheckBox("Incluir croquis SVG en el HTML")
        self.chk_croquis.setChecked(True)
        vp.addWidget(self.chk_croquis)

        self.chk_abrirlo = QCheckBox("Abrir el HTML al terminar")
        self.chk_abrirlo.setChecked(True)
        vp.addWidget(self.chk_abrirlo)

        param.addWidget(self.grp_params)
        param.addStretch(1)
        self.tabs.addTab(tab_param, "② Parámetros")

        # ====================================================
        # PESTAÑA 3 — PROCESO
        # ====================================================
        tab_proc = QWidget()
        proc = QVBoxLayout(tab_proc)
        proc.setContentsMargins(7, 7, 7, 7)
        proc.setSpacing(5)

        grp_proceso = QGroupBox("Proceso de cálculo")
        gp = QGridLayout(grp_proceso)
        gp.setContentsMargins(10, 14, 10, 10)
        gp.setSpacing(7)

        self.btn_verif = QPushButton("1 · Verificar datos")
        self.btn_calc = QPushButton("2 · Calcular ajuste")
        self.btn_verif.setMinimumHeight(36)
        self.btn_calc.setMinimumHeight(36)
        self.btn_calc.setObjectName("success")
        self.btn_calc.setEnabled(False)

        gp.addWidget(self.btn_verif, 0, 0)
        gp.addWidget(self.btn_calc, 0, 1)

        proc.addWidget(grp_proceso)

        grp_log = QGroupBox("Registro de actividad")
        vlog = QVBoxLayout(grp_log)
        vlog.setContentsMargins(10, 14, 10, 10)
        vlog.setSpacing(6)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMinimumHeight(145)
        self.txt_log.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        vlog.addWidget(self.txt_log, 1)

        # --- Limpieza exclusiva del registro de actividad ---
        h_limpiar = QHBoxLayout()
        h_limpiar.setSpacing(6)

        self.btn_limpiar_log = QPushButton("Limpiar pantalla")
        self.btn_limpiar_log.setObjectName("neutral")
        self.btn_limpiar_log.setMinimumHeight(32)
        self.btn_limpiar_log.setToolTip(
            "Borra solo el contenido del registro de actividad.")
        h_limpiar.addWidget(self.btn_limpiar_log)

        vlog.addLayout(h_limpiar)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        vlog.addWidget(self.progress)

        proc.addWidget(grp_log, 1)
        self.tabs.addTab(tab_proc, "③ Proceso")

        # ====================================================
        # PESTAÑA 4 — RESULTADOS
        # ====================================================
        tab_res = QWidget()
        res_layout = QVBoxLayout(tab_res)
        res_layout.setContentsMargins(7, 7, 7, 7)
        res_layout.setSpacing(5)

        grp_result = QGroupBox("Resultados y exportación")
        vgr = QVBoxLayout(grp_result)
        vgr.setContentsMargins(10, 14, 10, 10)
        vgr.setSpacing(7)

        # --- Botón Generar HTML (ancho completo) ---
        self.btn_html = QPushButton("3 · Generar HTML")
        self.btn_html.setObjectName("success")
        self.btn_html.setMinimumHeight(38)
        self.btn_html.setEnabled(False)
        vgr.addWidget(self.btn_html)

        # --- Fila: GeoPackage + CSV ---
        h_exp = QHBoxLayout()
        h_exp.setSpacing(7)

        self.btn_gpkg = QPushButton("GeoPackage")
        self.btn_gpkg.setMinimumHeight(34)
        self.btn_gpkg.setEnabled(False)
        h_exp.addWidget(self.btn_gpkg)

        self.btn_csv = QPushButton("CSV")
        self.btn_csv.setMinimumHeight(34)
        self.btn_csv.setEnabled(False)
        h_exp.addWidget(self.btn_csv)

        vgr.addLayout(h_exp)

        # --- Botón matrices (ancho completo) ---
        self.btn_matrices = QPushButton("Exportar matrices (CSV)")
        self.btn_matrices.setMinimumHeight(34)
        self.btn_matrices.setEnabled(False)
        vgr.addWidget(self.btn_matrices)

        # --- Botón Abrir reportes (ancho completo) ---
        self.btn_abrir = QPushButton("Abrir reportes")
        self.btn_abrir.setMinimumHeight(34)
        vgr.addWidget(self.btn_abrir)

        res_layout.addWidget(grp_result)

        info_res = QLabel(
            "Después del cálculo podrá generar el informe HTML o "
            "exportar los resultados a GeoPackage y CSV."
        )
        info_res.setWordWrap(True)
        info_res.setObjectName("helper")
        res_layout.addWidget(info_res)
        res_layout.addStretch(1)

        self.tabs.addTab(tab_res, "④ Resultados")

        # ====================================================
        # Acciones generales siempre visibles
        # ====================================================
        hb = QHBoxLayout()

        self.btn_limpiar_todo = QPushButton("🧹 Limpiar todo")
        self.btn_limpiar_todo.setObjectName("neutral")
        self.btn_limpiar_todo.setMinimumWidth(130)
        self.btn_limpiar_todo.setMinimumHeight(32)
        self.btn_limpiar_todo.setToolTip(
            "Borra el registro, resetea el estado del ajuste y "
            "deshabilita los botones de cálculo.")
        hb.addWidget(self.btn_limpiar_todo)

        hb.addStretch()
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setObjectName("danger")
        btn_cerrar.setMinimumWidth(110)
        btn_cerrar.setMinimumHeight(32)
        btn_cerrar.clicked.connect(self.close)
        hb.addWidget(btn_cerrar)
        root.addLayout(hb)

        # ----------------------------------------------------
        # Conexiones: se conservan los nombres y métodos
        # originales para no tocar la lógica.
        # ----------------------------------------------------
        self.radio_nivel.toggled.connect(self._on_modo_cambiado)
        self.cmb_capa.currentIndexChanged.connect(self._on_capa_cambio)
        self.cmb_capa.editTextChanged.connect(self._on_capa_cambio)
        self.cmb_modelo_helm.currentIndexChanged.connect(
            lambda _index: self._invalidar_resultados())
        self.btn_limpiar_log.clicked.connect(self.txt_log.clear)
        self.btn_limpiar_todo.clicked.connect(self._limpiar)
        self.btn_verif.clicked.connect(self._verificar_datos)
        self.btn_plantillas.clicked.connect(self._generar_plantillas)
        self.btn_calc.clicked.connect(self._calcular)
        self.btn_html.clicked.connect(self._generar_html)
        self.btn_gpkg.clicked.connect(self._exportar_gpkg)
        self.btn_csv.clicked.connect(self._exportar_csv)
        self.btn_abrir.clicked.connect(self._abrir_carpeta_reportes)

        self.btn_matrices.clicked.connect(self._exportar_matrices_csv)

        # --------------------------------------------------------
    def _cargar_crs_comunes(self):
        opciones = [
            ("EPSG:32617", "WGS 84 / UTM zone 17N (Panamá)"),
            ("EPSG:32616", "WGS 84 / UTM zone 16N"),
            ("EPSG:32618", "WGS 84 / UTM zone 18N"),
            ("EPSG:32619", "WGS 84 / UTM zone 19N"),
            ("EPSG:32615", "WGS 84 / UTM zone 15N"),
            ("EPSG:32620", "WGS 84 / UTM zone 20N"),
            ("EPSG:4326", "WGS 84 (lat/lon)"),
            ("EPSG:5367", "CRTM05 Costa Rica"),
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
    #  LOG Y PROGRESO
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

    def _invalidar_resultados(self):
        """Descarta verificaciones/cálculos que ya no corresponden a la UI."""
        self.obs = None
        self.res = None
        self.res_helmert = None
        self.pts_control = None
        self.pts_verificacion = None
        self.pts_a_transf = None
        self.capa_src = None
        self.coords_estaciones = {}
        self.cotas_huerfanas = {}
        self.col_x = self.col_y = None
        self.btn_calc.setEnabled(False)
        self.btn_html.setEnabled(False)
        self.btn_gpkg.setEnabled(False)
        self.btn_csv.setEnabled(False)
        self.btn_matrices.setEnabled(False)
        self.progress.setValue(0)

    # --------------------------------------------------------
    #  MODO
    # --------------------------------------------------------
    def _on_modo_cambiado(self):
        self._invalidar_resultados()
        if self.radio_helm.isChecked():
            self.modo = self.MODO_HELM
        else:
            self.modo = self.MODO_NIVEL

        es_helm = (self.modo == self.MODO_HELM)
        self.bloque_nivel.setVisible(not es_helm)
        self.bloque_helm.setVisible(es_helm)

        if es_helm:
            self.sp_sigma.setValue(0.010)
            self.sp_resid.setValue(0.020)
        else:
            self.sp_sigma.setValue(0.003)
            self.sp_resid.setValue(0.005)

        self._log(f"Modo cambiado a: "
                  f"{'Helmert' if es_helm else 'Nivelación'}")
        self._on_capa_cambio()

    def _detectar_modo_por_campos(self, capa):
        """Devuelve MODO_NIVEL, MODO_HELM o None."""
        nombres = {f.name().upper() for f in capa.fields()}
        if all(c in nombres for c in self.CAMPOS_HELM):
            return self.MODO_HELM
        if all(c in nombres for c in self.CAMPOS_NIVEL):
            return self.MODO_NIVEL
        return None

    # --------------------------------------------------------
    #  CAPAS
    # --------------------------------------------------------
    def _cargar_capas(self):
        self.cmb_capa.clear()
        for capa in QgsProject.instance().mapLayers().values():
            if isinstance(capa, QgsVectorLayer):
                # Mostrar nombre + CRS + nº de entidades (igual estilo que CRS)
                nombre = capa.name()
                crs_id = capa.crs().authid() if capa.crs().isValid() else "—"
                n = capa.featureCount()
                etiqueta = f"{nombre} — {crs_id} ({n} filas)"
                self.cmb_capa.addItem(etiqueta, capa.id())
        if self.cmb_capa.count() == 0:
            self.lbl_info.setText("⚠ No hay capas vectoriales cargadas.")
            self.lbl_info.setObjectName("info_warn")
            self.lbl_info.setStyleSheet("")
        else:
            self._on_capa_cambio()

    def _capa_actual(self):
        # Si el combo es editable y el usuario escribió texto libre,
        # currentData() puede ser None. En ese caso, buscar por nombre.
        lid = self.cmb_capa.currentData()
        if lid:
            capa = QgsProject.instance().mapLayer(lid)
            if capa is not None:
                return capa

        # Fallback: buscar por texto exacto
        texto = self.cmb_capa.currentText().strip()
        if not texto:
            return None
        for capa in QgsProject.instance().mapLayers().values():
            if isinstance(capa, QgsVectorLayer):
                etiqueta = self.cmb_capa.itemText(
                    self.cmb_capa.findData(capa.id()))
                if etiqueta == texto or capa.name() == texto:
                    return capa
        return None

    def _detectar_coordenadas_nivel(self, capa):
        nombres = [f.name().upper() for f in capa.fields()]
        col_x = next((c for c in self.COLS_X_NIVEL if c in nombres), None)
        col_y = next((c for c in self.COLS_Y_NIVEL if c in nombres), None)
        if col_x is None or col_y is None:
            return None, None
        return col_x, col_y

    def _on_capa_cambio(self):
        self._invalidar_resultados()
        capa = self._capa_actual()
        if capa is None:
            self.lbl_info.setText("—")
            return

        # Detección automática del modo (informativa)
        detectado = self._detectar_modo_por_campos(capa)
        es_helm = (self.modo == self.MODO_HELM)
        campos_req = self.CAMPOS_HELM if es_helm else self.CAMPOS_NIVEL

        nombres = [f.name().upper() for f in capa.fields()]
        faltan = [c for c in campos_req if c not in nombres]
        n = capa.featureCount()

        if faltan:
            self.lbl_info.setText(
                f'⚠ Capa "{capa.name()}" ({n} filas) — '
                f'faltan campos para modo '
                f'{"Helmert" if es_helm else "Nivelación"}: '
                f'{", ".join(faltan)}')
            self.lbl_info.setObjectName("info_err")
            self.lbl_info.setStyleSheet("")
            return

        # Aviso si el modo detectado no coincide con el elegido
        aviso_modo = ""
        if detectado and detectado != self.modo:
            nombre_modo = (
                "Helmert" if detectado == self.MODO_HELM else "Nivelación"
            )
            aviso_modo = f'  [ℹ Detectado como {nombre_modo}]'

        if es_helm:
            self.lbl_info.setText(
                f'✓ "{capa.name()}" ({n} filas) — modo Helmert '
                f'(con X_DST/Y_DST = control, sin = a transformar)'
                f'{aviso_modo}')
        else:
            col_x, col_y = self._detectar_coordenadas_nivel(capa)
            if col_x and col_y:
                self.lbl_info.setText(
                    f'✓ "{capa.name()}" ({n} filas) — '
                    f'coords: {col_x}/{col_y}{aviso_modo}')
            else:
                self.lbl_info.setText(
                    f'✓ "{capa.name()}" ({n} filas) — '
                    f'SIN coordenadas (cálculo igual){aviso_modo}')

        self.lbl_info.setObjectName("info_ok")
        self.lbl_info.setStyleSheet("")

    # --------------------------------------------------------
    #  VERIFICACIÓN DE DATOS (despacha por modo)
    # --------------------------------------------------------
    def _verificar_datos(self):
        if self.modo == self.MODO_HELM:
            self._verificar_helmert()
        else:
            self._verificar_nivelacion()

    # ========================================================
    #  VERIFICACIÓN — NIVELACIÓN
    # ========================================================
    def _verificar_nivelacion(self):
        self._log("Iniciando verificación (Nivelación)...")
        self._set_progress(10)

        capa = self._capa_actual()
        if capa is None:
            QMessageBox.warning(self, "Sin capa",
                                "Debe seleccionar una capa de entrada.")
            return

        nombres = [f.name().upper() for f in capa.fields()]
        faltan = [c for c in self.CAMPOS_NIVEL if c not in nombres]
        if faltan:
            self._log(f"✗ Faltan campos: {faltan}", "red")
            QMessageBox.critical(self, "Campos faltantes",
                                 f"Faltan campos: {', '.join(faltan)}")
            return
        self._log("✓ Campos requeridos presentes.", "#1e8449")
        self._set_progress(20)

        self.col_x, self.col_y = self._detectar_coordenadas_nivel(capa)
        if self.col_x and self.col_y:
            self._log(f"✓ Coordenadas UTM detectadas: "
                      f"X={self.col_x}, Y={self.col_y}", "#1e8449")
        else:
            self._log("ℹ Sin columnas de coordenadas. "
                      "El ajuste se ejecutará igual, sin mapa.",
                      "#b9770e")
        self._set_progress(35)

        try:
            obs = self._leer_capa_nivel(capa)
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

        huerfanas_usadas = []
        for est_huerfana, cota in self.cotas_huerfanas.items():
            if est_huerfana not in cotas_fijas:
                cotas_fijas[est_huerfana] = cota
                huerfanas_usadas.append(est_huerfana)

        if huerfanas_usadas:
            self._log(
                f"ℹ Cotas huérfanas recuperadas: {sorted(huerfanas_usadas)}",
                "#b9770e")

        if not cotas_fijas:
            self._log("✗ No hay cotas fijas.", "red")
            return

        self._log(f"✓ Cotas fijas: {sorted(cotas_fijas.keys())}", "#1e8449")

        estaciones = set()
        for o in obs:
            estaciones.add(o["ini"])
            estaciones.add(o["fin"])
        incognitas = sorted(e for e in estaciones if e not in cotas_fijas)
        self._log(f"  Estaciones: {len(estaciones)}  ·  "
                  f"Fijas: {len(cotas_fijas)}  ·  "
                  f"Incógnitas: {len(incognitas)}")

        gl = len(obs) - len(incognitas)
        if gl <= 0:
            self._log(
                f"✗ Grados de libertad insuficientes (GL={gl}).", "red")
            QMessageBox.critical(
                self, "Sin redundancia",
                "La red no tiene observaciones redundantes suficientes para "
                "evaluar estadísticamente el ajuste.\n\n"
                f"Observaciones: {len(obs)}\n"
                f"Incógnitas: {len(incognitas)}\nGL: {gl}")
            return

        if self.chk_invertir.isChecked():
            self._log(
                "⚙ Convención de campo ACTIVA: 'de A a B' ⇒ H_A − H_B = dh",
                "#b9770e")
        else:
            self._log("⚙ Convención estándar: H_final − H_inicial = dh.",
                      "#1e8449")

        # Conectividad (BFS)
        grafo = {}
        for o in obs:
            grafo.setdefault(o["ini"], set()).add(o["fin"])
            grafo.setdefault(o["fin"], set()).add(o["ini"])
        visitados, pila = set(), [next(iter(estaciones))]
        while pila:
            nodo = pila.pop()
            if nodo in visitados:
                continue
            visitados.add(nodo)
            pila.extend(grafo.get(nodo, []))
        if visitados != estaciones:
            faltantes = sorted(estaciones - visitados)
            self._log(
                f"✗ Red desconectada. Estaciones fuera del componente: "
                f"{faltantes}", "red")
            QMessageBox.critical(
                self, "Red desconectada",
                "La red contiene componentes separados. Conecte todas las "
                "estaciones antes de calcular.\n\n"
                f"Estaciones desconectadas: {', '.join(faltantes)}")
            self.btn_calc.setEnabled(False)
            return
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
    def _leer_capa_nivel(self, capa):
        nombres = [f.name().upper() for f in capa.fields()]
        def col(n): return nombres.index(n.upper())

        i_est = col("EST")
        i_fija = col("C_FIJA")
        i_ini = col("C_INICIAL")
        i_fin = col("C_FINAL")
        i_dh = col("DIF_COTA")
        i_dist = col("DIST")

        col_x, col_y = self._detectar_coordenadas_nivel(capa)
        i_x = nombres.index(col_x) if col_x else None
        i_y = nombres.index(col_y) if col_y else None

        invertir = self.chk_invertir.isChecked()

        coords = {}
        obs = []
        cotas_huerfanas = {}

        for f in capa.getFeatures():
            a = f.attributes()
            est = _to_id(a[i_est])
            ini = _to_id(a[i_ini])
            fin = _to_id(a[i_fin])
            dh = _to_float(a[i_dh])
            dis = _to_float(a[i_dist])
            cf = _to_float(a[i_fija])

            # La cota fija se asocia a la estación C_INICIAL (la que
            # "tiene" el BM en esa fila). Esto permite que la fila
            # T-01 (BM_A → P1) declare la cota fija de BM_A.
            if ini is not None and cf is not None:
                cotas_huerfanas[ini] = cf

            # Si no hay C_INICIAL pero hay EST y C_FIJA, se asocia a EST
            # (compatibilidad con tablas antiguas sin C_INICIAL).
            if ini is None and est is not None and cf is not None:
                cotas_huerfanas[est] = cf

            if ini is None or fin is None:
                continue
            if dh is None or dis is None or dis <= 0:
                continue

            if i_x is not None and i_y is not None:
                x_val = _to_float(a[i_x])
                y_val = _to_float(a[i_y])
                if x_val is not None and y_val is not None:
                    coords[est] = (x_val, y_val)

            if invertir:
                ini, fin = fin, ini

            obs.append({"est": est, "cota_fija": cf,
                        "ini": ini, "fin": fin,
                        "dh": dh, "dist": dis})

        obs.sort(key=lambda x: x["est"])
        self.coords_estaciones = coords
        self.cotas_huerfanas = cotas_huerfanas
        return obs

    # ========================================================
    #  VERIFICACIÓN — HELMERT
    # ========================================================
    def _verificar_helmert(self):
        self._log("Iniciando verificación (Helmert)...")
        self._set_progress(10)

        capa = self._capa_actual()
        if capa is None:
            QMessageBox.warning(self, "Sin capa",
                                "Debe seleccionar una capa de entrada.")
            return

        nombres = [f.name().upper() for f in capa.fields()]
        faltan = [c for c in self.CAMPOS_HELM if c not in nombres]
        if faltan:
            self._log(f"✗ Faltan campos: {faltan}", "red")
            QMessageBox.critical(self, "Campos faltantes",
                                 f"Faltan campos: {', '.join(faltan)}")
            return
        self._log("✓ Campos requeridos presentes.", "#1e8449")
        self._set_progress(30)

        try:
            pc, verificacion, a_transf = self._leer_capa_helm(capa)
        except Exception as e:
            self._log(f"✗ Error leyendo capa: {e}", "red")
            return

        if not pc:
            self._log("✗ No hay puntos de control con X_DESTINO/Y_DESTINO.",
                      "red")
            QMessageBox.critical(
                self, "Sin puntos de control",
                "Se necesita al menos 2 puntos con USO=Control y "
                "X_DESTINO/Y_DESTINO llenos para el ajuste Helmert 4p "
                "(3 para 6p).")
            return

        self._log(f"✓ {len(pc)} puntos de control (entran al ajuste).",
                  "#1e8449")
        if verificacion:
            self._log(f"✓ {len(verificacion)} puntos de verificación "
                      f"(NO entran al ajuste, solo validan).", "#1e8449")
        if a_transf:
            self._log(f"✓ {len(a_transf)} puntos a transformar "
                      f"(sin X_DESTINO/Y_DESTINO).", "#1e8449")

        # Validación de modelo
        modelo = self.cmb_modelo_helm.currentData()
        if modelo == 6 and len(pc) < 3:
            self._log("✗ Modelo 6p requiere ≥3 puntos de control.", "red")
            QMessageBox.critical(
                self, "Puntos insuficientes",
                "El modelo afín (6p) requiere al menos 3 puntos de control.")
            return

        if modelo == 4 and len(pc) < 2:
            self._log("✗ Modelo 4p requiere ≥2 puntos de control.", "red")
            QMessageBox.critical(
                self, "Puntos insuficientes",
                "El modelo de similitud (4p) requiere al menos 2 puntos.")
            return

        # Geometría: coordenadas finitas, puntos repetidos y rango suficiente.
        src = np.array([(p["x_src"], p["y_src"]) for p in pc], dtype=float)
        dst = np.array([(p["x_dst"], p["y_dst"]) for p in pc], dtype=float)
        if not np.all(np.isfinite(src)) or not np.all(np.isfinite(dst)):
            QMessageBox.critical(self, "Coordenadas inválidas",
                                 "Hay coordenadas NaN o infinitas.")
            return
        if len(np.unique(src, axis=0)) != len(src):
            QMessageBox.critical(self, "Puntos duplicados",
                                 "Hay coordenadas de origen duplicadas.")
            return
        if modelo == 6:
            centrados = src - src.mean(axis=0)
            if np.linalg.matrix_rank(centrados, tol=1e-10) < 2:
                QMessageBox.critical(
                    self, "Geometría degenerada",
                    "El modelo afín requiere puntos no colineales.")
                return

        gl_helm = 2 * len(pc) - modelo
        if gl_helm == 0:
            self._log(
                "⚠ Ajuste exacto (GL=0): se calculan parámetros, pero no "
                "pueden evaluarse estadísticamente los residuos.", "#b9770e")

        self._log(f"  Modelo seleccionado: Helmert {modelo}p", "#1e8449")
        for p in pc:
            self._log(
                f"    {p['name']:<8} ORI=({p['x_src']:.3f},"
                f"{p['y_src']:.3f})  DST=({p['x_dst']:.3f},"
                f"{p['y_dst']:.3f})")
        for p in verificacion:
            self._log(f"    {p['name']:<8} ORI=({p['x_src']:.3f},"
                      f"{p['y_src']:.3f})  [verificación]")
        for p in a_transf:
            self._log(f"    {p['name']:<8} ORI=({p['x_src']:.3f},"
                      f"{p['y_src']:.3f})  [a transformar]")

        self.pts_control = pc
        self.pts_verificacion = verificacion
        self.pts_a_transf = a_transf
        self.capa_src = capa
        self.btn_calc.setEnabled(True)
        self._set_progress(100)
        self._log("Verificación completada.", "#1e8449")

    # --------------------------------------------------------
    def _leer_capa_helm(self, capa):
        """
        Lee la capa Helmert.

        Estructura esperada de la tabla:
            PUNTO, X_ORIGEN, Y_ORIGEN, X_DESTINO, Y_DESTINO, USO

        USO:
          - Control      → entra al ajuste (requiere X_DESTINO/Y_DESTINO)
          - Verificación → no entra al ajuste, se usa para validar
          - (vacío)      → se asume Control
          - Control sin X_DESTINO/Y_DESTINO → se transforma pero no ajusta

        Devuelve (pc, verificacion, a_transf):
          pc            = puntos de control (entran al ajuste)
          verificacion  = puntos de verificación (comparan contra el ajuste)
          a_transf      = puntos a transformar (solo origen)
        """
        nombres = [f.name().upper() for f in capa.fields()]

        def col(n):
            return nombres.index(n.upper()) if n.upper() in nombres else None

        i_punto = col("PUNTO")
        i_xo = col("X_ORIGEN")
        i_yo = col("Y_ORIGEN")
        i_xd = col("X_DESTINO")
        i_yd = col("Y_DESTINO")
        i_uso = col("USO")

        if i_punto is None:
            raise ValueError("Falta el campo obligatorio PUNTO")
        if i_xo is None or i_yo is None:
            raise ValueError(
                "Faltan los campos obligatorios X_ORIGEN / Y_ORIGEN")

        pc = []
        verificacion = []
        a_transf = []

        for f in capa.getFeatures():
            a = f.attributes()

            punto = (str(a[i_punto]).strip() if i_punto is not None
                     and a[i_punto] is not None else "")
            x_origen = _to_float(a[i_xo])
            y_origen = _to_float(a[i_yo])
            x_destino = _to_float(a[i_xd]) if i_xd is not None else None
            y_destino = _to_float(a[i_yd]) if i_yd is not None else None
            uso_raw = (str(a[i_uso]).strip() if i_uso is not None
                       and a[i_uso] is not None else "")

            if not punto:
                punto = f"P{len(pc) + len(verificacion) + len(a_transf) + 1}"

            if x_origen is None or y_origen is None:
                self._log(f"⚠ '{punto}' sin X_ORIGEN/Y_ORIGEN — omitido.",
                          "#b9770e")
                continue

            # Normalizar USO
            uso_norm = uso_raw.lower().strip()
            if uso_norm in ("", "control", "ctrl", "c"):
                uso = "control"
            elif uso_norm in ("verificación", "verificacion",
                              "verif", "v", "comprobación", "comprobacion"):
                uso = "verificacion"
            else:
                self._log(
                    f"⚠ '{punto}': USO='{uso_raw}' no reconocido "
                    f"— se asume Control.", "#b9770e")
                uso = "control"

            tiene_destino = (x_destino is not None and y_destino is not None)

            if uso == "control" and tiene_destino:
                pc.append({
                    "name": punto, "est": None, "cota": None,
                    "x_src": x_origen, "y_src": y_origen,
                    "x_dst": x_destino, "y_dst": y_destino,
                })
            elif uso == "verificacion" and tiene_destino:
                verificacion.append({
                    "name": punto,
                    "x_src": x_origen, "y_src": y_origen,
                    "x_dst": x_destino, "y_dst": y_destino,
                })
            elif uso == "verificacion" and not tiene_destino:
                self._log(
                    f"⚠ '{punto}': USO=Verificación sin X_DESTINO/Y_DESTINO "
                    f"— omitido.", "#b9770e")
            else:
                # control sin destino → solo transformar
                a_transf.append({
                    "name": punto, "est": None, "cota": None,
                    "x_src": x_origen, "y_src": y_origen,
                })

        return pc, verificacion, a_transf

    # --------------------------------------------------------
    #  2 · Calcular (despacha según modo)
    # --------------------------------------------------------
    def _calcular(self):
        if self.modo == self.MODO_HELM:
            self._calcular_helmert()
        else:
            self._calcular_nivelacion()

    # --------------------------------------------------------
    #  2a · Calcular — Nivelación
    # --------------------------------------------------------
    def _calcular_nivelacion(self):
        if not self.obs:
            QMessageBox.warning(self, "Sin datos",
                                "Ejecute primero la verificación.")
            return

        self.autor = self.txt_autor.text().strip() or "Usuario QGIS"
        self._log(f"Calculando ajuste de nivelación (autor: {self.autor})...")
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
        self._log(f"  Test χ²: "
                  f"{'✓ OK' if self.res['test_ok'] else '✗ Revisar'}")
        for k, e in enumerate(self.res["incognitas"]):
            self._log(f"  Estación {e}: {self.res['X'][k]:.4f} m  "
                      f"± {self.res['desv'][k]:.6f}")

        self.btn_html.setEnabled(True)
        self.btn_gpkg.setEnabled(True)
        self.btn_csv.setEnabled(True)
        self.btn_matrices.setEnabled(True)

    # --------------------------------------------------------
    #  2b · Calcular — Helmert
    # --------------------------------------------------------
    def _calcular_helmert(self):
        if not self.pts_control or len(self.pts_control) < 2:
            QMessageBox.warning(self, "Sin datos",
                                "Ejecute primero la verificación.")
            return

        self.autor = self.txt_autor.text().strip() or "Usuario QGIS"

        # El combo guarda 4 o 6 (int); convertir a "4p" / "6p"
        modelo = self.cmb_modelo_helm.currentData()
        tipo = "6p" if modelo == 6 else "4p"

        self._log(f"Calculando transformación Helmert ({tipo}) "
                  f"(autor: {self.autor})...")
        self._set_progress(20)

        try:
            self.res_helmert = self._ajustar_helmert(self.pts_control, tipo)
        except Exception as e:
            import traceback
            self._log(f"✗ Error en ajuste Helmert: {e}", "red")
            self._log(traceback.format_exc(), "red")
            QMessageBox.critical(self, "Error",
                                 f"Error en el ajuste Helmert:\n{e}")
            return

        res = self.res_helmert
        self._set_progress(100)
        self._log("✓ Ajuste Helmert completado.", "#1e8449")

        if tipo == "4p":
            self._log(f"  s  = {res['s']:.10f}")
            self._log(f"  θ  = {res['theta_deg']:.8f}° "
                      f"({res['theta_deg'] * 3600:.4f}\")")
            self._log(f"  Tx = {res['Tx']:.4f} m")
            self._log(f"  Ty = {res['Ty']:.4f} m")
        else:
            self._log(f"  a1 = {res['a1']:.10f}  a2 = {res['a2']:.10f}")
            self._log(f"  b1 = {res['b1']:.10f}  b2 = {res['b2']:.10f}")
            self._log(f"  Tx = {res['Tx']:.4f} m")
            self._log(f"  Ty = {res['Ty']:.4f} m")
        self._log(f"  σ₀ = {res['sigma']:.6f} m")
        self._log(f"  GL = {res['gl']}")

        # Resumen de verificación externa
        if self.pts_verificacion and len(res["_nombres_ver"]) > 0:
            dX = res["_x_ver_dst_calc"] - res["_x_ver_dst_obs"]
            dY = res["_y_ver_dst_calc"] - res["_y_ver_dst_obs"]
            dX_mm = dX * 1000.0
            dY_mm = dY * 1000.0
            self._log("  --- Verificación externa ---")
            for i, n in enumerate(res["_nombres_ver"]):
                self._log(f"    {n:<8} dX={dX_mm[i]:+.3f} mm  "
                          f"dY={dY_mm[i]:+.3f} mm")
            rms_x = float(np.sqrt(np.mean(dX_mm**2)))
            rms_y = float(np.sqrt(np.mean(dY_mm**2)))
            rms_2d = float(np.sqrt(rms_x**2 + rms_y**2))
            self._log(f"    RMS X = {rms_x:.3f} mm")
            self._log(f"    RMS Y = {rms_y:.3f} mm")
            self._log(f"    RMS 2D = {rms_2d:.3f} mm")

        self.btn_html.setEnabled(True)
        self.btn_gpkg.setEnabled(True)
        self.btn_csv.setEnabled(True)
        self.btn_matrices.setEnabled(True)

    # --------------------------------------------------------
    #  Ajuste — Nivelación (Gaus-Markov)
    # --------------------------------------------------------
    def _ajustar(self, obs):
        tol_sigma = self.sp_sigma.value()
        tol_resid = self.sp_resid.value()
        tol_vstd = self.sp_vstd.value()

        cotas_fijas = {o["est"]: o["cota_fija"]
                       for o in obs if o["cota_fija"] is not None}

        # Fusionar cotas huérfanas
        for est_h, cota in self.cotas_huerfanas.items():
            if est_h not in cotas_fijas:
                cotas_fijas[est_h] = cota

        estaciones = set()
        for o in obs:
            estaciones.add(o["ini"])
            estaciones.add(o["fin"])

        incognitas = sorted(e for e in estaciones if e not in cotas_fijas)
        idx = {e: k for k, e in enumerate(incognitas)}
        n, u = len(obs), len(incognitas)
        gl = n - u
        if gl <= 0:
            raise ValueError(
                f"Grados de libertad insuficientes: n={n}, u={u}, GL={gl}.")

        P = np.zeros((n, n))
        A = np.zeros((n, u))
        fv = np.zeros(n)
        for i, o in enumerate(obs):
            P[i, i] = 1.0 / o["dist"]
            if o["fin"] in idx:
                A[i, idx[o["fin"]]] = 1.0
            if o["ini"] in idx:
                A[i, idx[o["ini"]]] = -1.0
            c_ini = cotas_fijas.get(o["ini"], 0.0)
            c_fin = cotas_fijas.get(o["fin"], 0.0)
            fv[i] = o["dh"] - c_fin + c_ini

        ATPA = A.T @ P @ A
        ATPF = A.T @ P @ fv
        condicion = float(np.linalg.cond(ATPA))
        if not np.isfinite(condicion) or condicion > 1e12:
            raise ValueError(
                "La matriz normal es singular o está mal condicionada "
                f"(condición={condicion:.3e}). Revise la geometría de la red.")
        INVATPA = np.linalg.inv(ATPA)
        X = np.linalg.solve(ATPA, ATPF)

        V = A @ X - fv
        VTPV = float(V.T @ P @ V)
        sigma2 = VTPV / gl if gl > 0 else 0.0
        sigma = float(np.sqrt(sigma2)) if sigma2 > 0 else 0.0

        vtpv_i = V * np.diag(P) * V
        vtpv_pct = ((vtpv_i / VTPV * 100) if VTPV > 0
                    else np.zeros_like(vtpv_i))

        ranking = np.argsort(-np.abs(V))
        Sigma_XX = sigma2 * INVATPA
        desv = np.sqrt(np.diag(Sigma_XX))

        Q = np.linalg.inv(P)
        A_Ninv_AtQ = A @ INVATPA @ A.T @ Q
        Q_vv = sigma2 * (Q - A_Ninv_AtQ)
        Q_lhat = sigma2 * A_Ninv_AtQ

        H_ii = np.diag(A @ INVATPA @ A.T @ P)
        r_i = 1.0 - H_ii

        sd_V = np.sqrt(np.diag(Q_vv))
        sd_V = np.where(sd_V > 1e-15, sd_V, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            v_std = V / sd_V

        chi2_obs = VTPV
        chi2_tab = chi2_crit(gl) if gl > 0 else 0.0
        p_valor = chi2_pval(chi2_obs, gl) if gl > 0 else 0.0
        test_ok = chi2_obs <= chi2_tab

        tcrit = t_95(gl) if gl > 0 else 0.0
        IC95 = tcrit * desv

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
            cond=condicion,
            tol_sigma=tol_sigma, tol_resid=tol_resid, tol_vstd=tol_vstd,
            vtpv_i=vtpv_i, vtpv_pct=vtpv_pct, ranking=ranking,
        )

    # --------------------------------------------------------
    #  Ajuste — Helmert
    # --------------------------------------------------------
    def _ajustar_helmert(self, control, tipo):
        x_src = np.array([p["x_src"] for p in control], dtype=float)
        y_src = np.array([p["y_src"] for p in control], dtype=float)
        x_dst = np.array([p["x_dst"] for p in control], dtype=float)
        y_dst = np.array([p["y_dst"] for p in control], dtype=float)

        if tipo == "6p":
            res = helmert.helmert_6p(x_src, y_src, x_dst, y_dst)
            res["tipo"] = "6p"
        else:
            res = helmert.helmert_4p(x_src, y_src, x_dst, y_dst)
            res["tipo"] = "4p"

        # Guardar arrays de control para el HTML y exportaciones
        res["_x_src"] = x_src
        res["_y_src"] = y_src
        res["_x_dst"] = x_dst
        res["_y_dst"] = y_dst
        res["_nombres"] = [p["name"] for p in control]

        # ---- Puntos a transformar (solo origen) ----
        if self.pts_a_transf:
            x_no = np.array([p["x_src"] for p in self.pts_a_transf],
                            dtype=float)
            y_no = np.array([p["y_src"] for p in self.pts_a_transf],
                            dtype=float)
            if tipo == "6p":
                xd_no, yd_no = helmert.transformar_6p(x_no, y_no, res)
            else:
                xd_no, yd_no = helmert.transformar_4p(x_no, y_no, res)
            res["_x_no_src"] = x_no
            res["_y_no_src"] = y_no
            res["_x_no_dst"] = xd_no
            res["_y_no_dst"] = yd_no
            res["_nombres_no"] = [p["name"] for p in self.pts_a_transf]
        else:
            res["_x_no_src"] = np.array([])
            res["_y_no_src"] = np.array([])
            res["_x_no_dst"] = np.array([])
            res["_y_no_dst"] = np.array([])
            res["_nombres_no"] = []

        # ---- Puntos de verificación: transformar y comparar ----
        if self.pts_verificacion:
            x_v = np.array([p["x_src"] for p in self.pts_verificacion],
                           dtype=float)
            y_v = np.array([p["y_src"] for p in self.pts_verificacion],
                           dtype=float)
            xd_obs = np.array([p["x_dst"] for p in self.pts_verificacion],
                              dtype=float)
            yd_obs = np.array([p["y_dst"] for p in self.pts_verificacion],
                              dtype=float)
            if tipo == "6p":
                xd_calc, yd_calc = helmert.transformar_6p(x_v, y_v, res)
            else:
                xd_calc, yd_calc = helmert.transformar_4p(x_v, y_v, res)
            res["_x_ver_src"] = x_v
            res["_y_ver_src"] = y_v
            res["_x_ver_dst_obs"] = xd_obs
            res["_y_ver_dst_obs"] = yd_obs
            res["_x_ver_dst_calc"] = xd_calc
            res["_y_ver_dst_calc"] = yd_calc
            res["_nombres_ver"] = [p["name"] for p in self.pts_verificacion]
        else:
            res["_x_ver_src"] = np.array([])
            res["_y_ver_src"] = np.array([])
            res["_x_ver_dst_obs"] = np.array([])
            res["_y_ver_dst_obs"] = np.array([])
            res["_x_ver_dst_calc"] = np.array([])
            res["_y_ver_dst_calc"] = np.array([])
            res["_nombres_ver"] = []

        return res

    # --------------------------------------------------------
    #  3 · Generar HTML (despacha según modo)
    # --------------------------------------------------------
    def _generar_html(self):
        if self.modo == self.MODO_HELM:
            if not self.res_helmert:
                QMessageBox.warning(self, "Sin resultados",
                                    "Ejecute primero el cálculo.")
                return
        else:
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
        carpeta = os.path.join(proy_dir, "reportes_topografia")
        os.makedirs(carpeta, exist_ok=True)

        prefijo = "helmert" if self.modo == self.MODO_HELM else "nivelacion"
        nombre = f"{prefijo}_{datetime.now():%Y%m%d_%H%M%S}.html"
        ruta = os.path.join(carpeta, nombre)

        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte HTML", ruta, "HTML (*.html)")
        if not ruta:
            return

        try:
            if self.modo == self.MODO_HELM:
                html = self._construir_html_helmert(self.res_helmert,
                                                    self.autor)
            else:
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
            QMessageBox.critical(self, "Error HTML",
                                 f"No se pudo generar el HTML:\n{e}")

    # --------------------------------------------------------
    #  Capa ajustada — Nivelación
    # --------------------------------------------------------
    def _capa_ajustada(self):
        res = self.res
        crs = self._crs_seleccionado()

        capa = QgsVectorLayer(f"Point?crs={crs}",
                              "nivelacion_ajustada", "memory")
        if not capa.isValid():
            raise ValueError(f"No se pudo crear capa con CRS '{crs}'.")

        prov = capa.dataProvider()
        campos = QgsFields()
        campos.append(QgsField("est", QVariant.String, "string", 32))
        campos.append(QgsField("cota", QVariant.Double, "double", 12, 4))
        campos.append(QgsField("desv", QVariant.Double, "double", 12, 8))
        campos.append(QgsField("ic95", QVariant.Double, "double", 12, 8))
        campos.append(QgsField("tipo", QVariant.String, "string", 12))
        prov.addAttributes(campos)
        capa.updateFields()

        idx_map = res["idx"]
        tiene_coords = bool(self.col_x and self.col_y and
                            self.coords_estaciones)

        for est, cota in res["cotas_finales"].items():
            f = QgsFeature(capa.fields())
            f["est"] = str(est)
            f["cota"] = float(cota)
            f["desv"] = (float(res["desv"][idx_map[est]])
                         if est in idx_map else 0.0)
            f["ic95"] = (float(res["IC95"][idx_map[est]])
                         if est in idx_map else 0.0)
            f["tipo"] = "fija" if est in res["cotas_fijas"] else "incognita"

            if tiene_coords and est in self.coords_estaciones:
                x, y = self.coords_estaciones[est]
                pt = QgsPointXY(float(x), float(y))
            else:
                # Sin coordenadas: usar índice ordinal como pseudo-X
                orden = list(res["cotas_finales"].keys())
                idx_est = orden.index(est) if est in orden else 0
                pt = QgsPointXY(float(idx_est), float(cota))
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
                "outline_color": "60, 130, 80",
                "outline_width": "0.6"}),
            "Cota fija")
        cat_inc = QgsRendererCategory(
            "incognita",
            QgsMarkerSymbol.createSimple({
                "name": "circle", "size": "3.5",
                "color": "150, 190, 230, 220",
                "outline_color": "60, 100, 150",
                "outline_width": "0.6"}),
            "Incógnita")
        renderer = QgsCategorizedSymbolRenderer("tipo", [cat_fija, cat_inc])
        capa.setRenderer(renderer)

    # --------------------------------------------------------
    #  Capa ajustada — Helmert
    # --------------------------------------------------------
    def _capa_ajustada_helmert(self):
        res = self.res_helmert
        crs = self._crs_seleccionado()

        capa = QgsVectorLayer(f"Point?crs={crs}",
                              "helmert_ajustada", "memory")
        if not capa.isValid():
            raise ValueError(f"No se pudo crear capa con CRS '{crs}'.")

        prov = capa.dataProvider()
        campos = QgsFields()
        campos.append(QgsField("punto", QVariant.String, "string", 32))
        campos.append(QgsField("tipo", QVariant.String, "string", 20))
        campos.append(QgsField("x_orig", QVariant.Double, "double", 16, 4))
        campos.append(QgsField("y_orig", QVariant.Double, "double", 16, 4))
        campos.append(QgsField("x_dest", QVariant.Double, "double", 16, 4))
        campos.append(QgsField("y_dest", QVariant.Double, "double", 16, 4))
        campos.append(QgsField("dx_mm", QVariant.Double, "double", 12, 3))
        campos.append(QgsField("dy_mm", QVariant.Double, "double", 12, 3))
        prov.addAttributes(campos)
        capa.updateFields()

        # --- Puntos de control ---
        for i, p in enumerate(self.pts_control):
            xc = float(res["_x_src"][i])
            yc = float(res["_y_src"][i])
            xd = float(res["_x_dst"][i])
            yd = float(res["_y_dst"][i])
            if res.get("tipo") == "6p":
                x_calc, y_calc = helmert.transformar_6p([xc], [yc], res)
            else:
                x_calc, y_calc = helmert.transformar_4p([xc], [yc], res)
            dx = (float(x_calc[0]) - xd) * 1000.0
            dy = (float(y_calc[0]) - yd) * 1000.0

            f = QgsFeature(capa.fields())
            f["punto"] = p["name"]
            f["tipo"] = "CONTROL"
            f["x_orig"] = xc
            f["y_orig"] = yc
            f["x_dest"] = xd
            f["y_dest"] = yd
            f["dx_mm"] = dx
            f["dy_mm"] = dy
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(xd, yd)))
            prov.addFeature(f)

        # --- Puntos de verificación ---
        for i, p in enumerate(self.pts_verificacion or []):
            xo = float(res["_x_ver_src"][i])
            yo = float(res["_y_ver_src"][i])
            xd_o = float(res["_x_ver_dst_obs"][i])
            yd_o = float(res["_y_ver_dst_obs"][i])
            xd_c = float(res["_x_ver_dst_calc"][i])
            yd_c = float(res["_y_ver_dst_calc"][i])
            dx = (xd_c - xd_o) * 1000.0
            dy = (yd_c - yd_o) * 1000.0

            f = QgsFeature(capa.fields())
            f["punto"] = p["name"]
            f["tipo"] = "VERIFICACION"
            f["x_orig"] = xo
            f["y_orig"] = yo
            f["x_dest"] = xd_o
            f["y_dest"] = yd_o
            f["dx_mm"] = dx
            f["dy_mm"] = dy
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(xd_o, yd_o)))
            prov.addFeature(f)

        # --- Puntos a transformar ---
        for i, p in enumerate(self.pts_a_transf or []):
            xo = float(res["_x_no_src"][i])
            yo = float(res["_y_no_src"][i])
            xd = float(res["_x_no_dst"][i])
            yd = float(res["_y_no_dst"][i])

            f = QgsFeature(capa.fields())
            f["punto"] = p["name"]
            f["tipo"] = "TRANSFORMADO"
            f["x_orig"] = xo
            f["y_orig"] = yo
            f["x_dest"] = xd
            f["y_dest"] = yd
            f["dx_mm"] = None
            f["dy_mm"] = None
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(xd, yd)))
            prov.addFeature(f)

        capa.updateExtents()
        self._aplicar_simbologia_helmert(capa)
        return capa

    def _aplicar_simbologia_helmert(self, capa):
        cat_ctrl = QgsRendererCategory(
            "CONTROL",
            QgsMarkerSymbol.createSimple({
                "name": "circle", "size": "3.8",
                "color": "150, 220, 170, 230",
                "outline_color": "60, 130, 80",
                "outline_width": "0.7"}),
            "Punto de control")
        cat_ver = QgsRendererCategory(
            "VERIFICACION",
            QgsMarkerSymbol.createSimple({
                "name": "star", "size": "4.0",
                "color": "250, 220, 150, 230",
                "outline_color": "180, 130, 40",
                "outline_width": "0.7"}),
            "Punto de verificación")
        cat_trans = QgsRendererCategory(
            "TRANSFORMADO",
            QgsMarkerSymbol.createSimple({
                "name": "triangle", "size": "3.5",
                "color": "200, 210, 240, 230",
                "outline_color": "100, 120, 180",
                "outline_width": "0.7"}),
            "Punto transformado")
        renderer = QgsCategorizedSymbolRenderer(
            "tipo", [cat_ctrl, cat_ver, cat_trans])
        capa.setRenderer(renderer)

    # --------------------------------------------------------
    #  4 · Exportar GeoPackage (despacha según modo)
    # --------------------------------------------------------
    def _exportar_gpkg(self):
        if self.modo == self.MODO_HELM:
            if not self.res_helmert:
                QMessageBox.warning(self, "Sin resultados",
                                    "Ejecute primero el cálculo.")
                return
            nombre_def = "helmert_ajustada.gpkg"
            nombre_capa = "helmert_ajustada"
        else:
            if not self.res:
                QMessageBox.warning(self, "Sin resultados",
                                    "Ejecute primero el cálculo.")
                return
            nombre_def = "nivelacion_ajustada.gpkg"
            nombre_capa = "nivelacion_ajustada"

        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar GeoPackage", nombre_def, "GeoPackage (*.gpkg)")
        if not ruta:
            return
        if not ruta.lower().endswith(".gpkg"):
            ruta += ".gpkg"
        if os.path.exists(ruta):
            try:
                os.remove(ruta)
            except Exception:
                pass

        try:
            capa = (self._capa_ajustada_helmert()
                    if self.modo == self.MODO_HELM
                    else self._capa_ajustada())
            crs_str = self._crs_seleccionado()
            self._log(f"Exportando con CRS: {crs_str}...")

            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.layerName = nombre_capa
            opts.fileEncoding = "UTF-8"
            opts.actionOnExistingFile = (
                QgsVectorFileWriter.CreateOrOverwriteFile)

            resultado = QgsVectorFileWriter.writeAsVectorFormatV3(
                capa, ruta, QgsCoordinateTransformContext(), opts)

            err_code = (resultado[0] if isinstance(resultado, tuple)
                        else resultado)
            err_msg = (resultado[1]
                       if isinstance(resultado, tuple) and len(resultado) > 1
                       else "")

            if err_code == QgsVectorFileWriter.NoError:
                self._log(f"✓ GeoPackage exportado: {ruta}", "#1e8449")
                self._log(f"  CRS aplicado: {crs_str}", "#1e8449")

                capa_cargada = QgsVectorLayer(
                    f"{ruta}|layername={nombre_capa}",
                    nombre_capa, "ogr")
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
            QMessageBox.critical(self, "Error GPKG", str(e))

    # --------------------------------------------------------
    #  5 · Exportar CSV (despacha según modo)
    # --------------------------------------------------------
    def _exportar_csv(self):
        if self.modo == self.MODO_HELM:
            self._exportar_csv_helmert()
        else:
            self._exportar_csv_nivelacion()

    def _exportar_csv_nivelacion(self):
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
                    f"{cota - ic95:.4f}",
                    f"{cota + ic95:.4f}",
                    tipo,
                ]
                if tiene_coords and est in self.coords_estaciones:
                    x, y = self.coords_estaciones[est]
                    fila += [f"{x:.3f}", f"{y:.3f}"]
                elif tiene_coords:
                    fila += ["", ""]
                lineas.append(",".join(fila))

            meta = [
                "# Reporte de Nivelación",
                f"# Fecha: {datetime.now():%Y-%m-%d %H:%M:%S}",
                f"# Autor: {self.autor}",
                f"# Capa: "
                f"{self.capa_src.name() if self.capa_src else 'N/A'}",
                f"# Ecuaciones: {res['n']}  Incógnitas: {res['u']}  "
                f"GL: {res['gl']}",
                f"# Sigma0 = {res['sigma']:.6f} m",
                f"# Test chi2: "
                f"{'OK' if res['test_ok'] else 'REVISAR'}",
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

    def _exportar_csv_helmert(self):
        if not self.res_helmert:
            QMessageBox.warning(self, "Sin resultados",
                                "Ejecute primero el cálculo.")
            return

        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar CSV", "helmert_ajustada.csv", "CSV (*.csv)")
        if not ruta:
            return
        if not ruta.lower().endswith(".csv"):
            ruta += ".csv"

        try:
            res = self.res_helmert
            tipo = res.get("tipo", "4p")

            cab = ["PUNTO", "TIPO", "X_ORIGEN", "Y_ORIGEN",
                   "X_DESTINO", "Y_DESTINO", "DX_MM", "DY_MM"]
            lineas = [",".join(cab)]

            # Control
            for i, p in enumerate(self.pts_control):
                xc = float(res["_x_src"][i])
                yc = float(res["_y_src"][i])
                xd = float(res["_x_dst"][i])
                yd = float(res["_y_dst"][i])
                if tipo == "6p":
                    x_calc, y_calc = helmert.transformar_6p([xc], [yc], res)
                else:
                    x_calc, y_calc = helmert.transformar_4p([xc], [yc], res)
                dx_mm = (float(x_calc[0]) - xd) * 1000.0
                dy_mm = (float(y_calc[0]) - yd) * 1000.0
                lineas.append(",".join([
                    p["name"], "CONTROL",
                    f"{xc:.4f}", f"{yc:.4f}",
                    f"{xd:.4f}", f"{yd:.4f}",
                    f"{dx_mm:+.3f}", f"{dy_mm:+.3f}"]))

            # Verificación
            for i, p in enumerate(self.pts_verificacion or []):
                xo = float(res["_x_ver_src"][i])
                yo = float(res["_y_ver_src"][i])
                xd_o = float(res["_x_ver_dst_obs"][i])
                yd_o = float(res["_y_ver_dst_obs"][i])
                xd_c = float(res["_x_ver_dst_calc"][i])
                yd_c = float(res["_y_ver_dst_calc"][i])
                dx_mm = (xd_c - xd_o) * 1000.0
                dy_mm = (yd_c - yd_o) * 1000.0
                lineas.append(",".join([
                    p["name"], "VERIFICACION",
                    f"{xo:.4f}", f"{yo:.4f}",
                    f"{xd_o:.4f}", f"{yd_o:.4f}",
                    f"{dx_mm:+.3f}", f"{dy_mm:+.3f}"]))

            # Transformados
            for i, p in enumerate(self.pts_a_transf or []):
                xs = float(res["_x_no_src"][i])
                ys = float(res["_y_no_src"][i])
                xd = float(res["_x_no_dst"][i])
                yd = float(res["_y_no_dst"][i])
                lineas.append(",".join([
                    p["name"], "TRANSFORMADO",
                    f"{xs:.4f}", f"{ys:.4f}",
                    f"{xd:.4f}", f"{yd:.4f}",
                    "", ""]))

            meta = [
                "# Reporte de Transformación Helmert",
                f"# Fecha: {datetime.now():%Y-%m-%d %H:%M:%S}",
                f"# Autor: {self.autor}",
                f"# Capa: {self.capa_src.name() if self.capa_src else 'N/A'}",
                f"# Modelo: {tipo}",
                f"# Control: {len(self.pts_control)}",
                f"# Verificación: {len(self.pts_verificacion or [])}",
                f"# Transformados: {len(self.pts_a_transf or [])}",
                f"# GL: {res['gl']}  sigma0 = {res['sigma']:.6f} m",
            ]
            if tipo == "4p":
                meta.append(f"# s = {res['s']:.10f}")
                meta.append(f"# theta_deg = {res['theta_deg']:.8f}")
            meta.append(f"# Tx = {res['Tx']:.4f} m")
            meta.append(f"# Ty = {res['Ty']:.4f} m")

            with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(meta) + "\n")
                fh.write("\n".join(lineas) + "\n")

            self._log(f"✓ CSV exportado: {ruta}", "#1e8449")
            QMessageBox.information(self, "CSV generado",
                                    f"Exportado en:\n{ruta}")
        except Exception as e:
            import traceback
            self._log(f"✗ Excepción CSV Helmert: {e}", "red")
            self._log(traceback.format_exc(), "red")

    # ========================================================
    #  DIAGNÓSTICO AUTOMÁTICO (Nivelación)
    # ========================================================
    def _diagnosticar(self, res, obs):
        """
        Diagnóstico automático.

        Criterios de severidad (basados solo en residuo estandarizado):
          - |v_std| > 3.29  → CRÍTICO (test de Baarda)
          - |v_std| > 2.50  → Revisar
          - |v_std| > 2.00  → Menor
          - |v_std| <= 2.00 → OK

        La contribución al VTPV se reporta como información adicional
        pero NO se usa como criterio de severidad por sí sola.
        """
        V = res["V"]
        v_std = res["v_std"]
        r_i = res["r_i"]
        vtpv_pct = res["vtpv_pct"]
        n = len(obs)

        sospechosas = []
        for i in range(n):
            vs = v_std[i] if not np.isnan(v_std[i]) else 0.0
            motivos = []
            sev = 0

            # Criterio principal: residuo estandarizado (Baarda)
            if abs(vs) > 3.29:
                motivos.append(
                    f"residuo estandarizado |w|={abs(vs):.2f} > 3.29")
                sev = max(sev, 3)
            elif abs(vs) > 2.50:
                motivos.append(
                    f"residuo estandarizado |w|={abs(vs):.2f} > 2.50")
                sev = max(sev, 2)
            elif abs(vs) > 2.00:
                motivos.append(
                    f"residuo estandarizado |w|={abs(vs):.2f}")
                sev = max(sev, 1)

            # Criterio secundario: redundancia muy baja (solo si no hay otro)
            if sev == 0 and r_i[i] < 0.05:
                motivos.append(
                    f"redundancia muy baja (r={r_i[i]:.2f})")
                sev = max(sev, 1)

            # Si ya está marcada y además aporta mucho al VTPV,
            # lo mencionamos como información adicional.
            if sev > 0 and vtpv_pct[i] > 20:
                motivos.append(
                    f"aporta {vtpv_pct[i]:.1f}% del VTPV")

            if motivos:
                sospechosas.append({
                    "obs": i,
                    "est": obs[i]["est"],
                    "ini": obs[i]["ini"],
                    "fin": obs[i]["fin"],
                    "dh": obs[i]["dh"],
                    "v_mm": V[i] * 1000,
                    "vs": vs,
                    "vtpv_pct": vtpv_pct[i],
                    "r_i": r_i[i],
                    "motivos": motivos,
                    "severidad": sev,
                })

        sospechosas.sort(key=lambda x: -x["severidad"])
        resumen = self._generar_sugerencias(res, obs, sospechosas)
        return {"sospechosas": sospechosas, "resumen": resumen}

    def _generar_sugerencias(self, res, obs, sospechosas):
        n_sosp = len(sospechosas)
        criticas = [s for s in sospechosas if s["severidad"] == 3]
        revisar = [s for s in sospechosas if s["severidad"] == 2]
        leves = [s for s in sospechosas if s["severidad"] == 1]

        lineas = []
        if not sospechosas:
            lineas.append(
                "✓ No se detectan observaciones problemáticas. "
                "El ajuste es estadísticamente consistente.")
            return lineas

        lineas.append(
            f"Se detectaron <b>{n_sosp}</b> observaciones para revisar "
            f"({len(criticas)} críticas, {len(revisar)} a revisar, "
            f"{len(leves)} menores).")

        top = sospechosas[:3]
        if top:
            lineas.append("<b>Revisar primero:</b>")
            for s in top:
                lineas.append(
                    f"  • Obs {s['est']} ({s['ini']}→{s['fin']}, "
                    f"dh={s['dh']:+.4f} m): "
                    + "; ".join(s["motivos"]))

        sigma_mm = res["sigma"] * 1000
        if sigma_mm > 50:
            lineas.append(
                f"⚠ σ₀ es muy alto ({sigma_mm:.1f} mm). "
                "Verifica los datos de campo y las cotas fijas.")
        elif sigma_mm > 10:
            lineas.append(
                f"σ₀ es alto ({sigma_mm:.1f} mm). "
                "Probablemente hay errores de transcripción.")

        return lineas

    # ========================================================
    #  HTML — NIVELACIÓN
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
        proy = (os.path.basename(proy_path)
                if proy_path and proy_path != "(sin guardar)"
                else proy_path)

        tiene_coords = bool(self.col_x and self.col_y)

        sem = []
        sem.append(("σ₀ = " + f"{res['sigma'] * 1000:.3f} mm",
                    "ok" if res['sigma'] < res["tol_sigma"] else "alerta"))
        vmax = float(np.max(np.abs(res["V"])))
        sem.append(("Residuo máx = " + f"{vmax * 1000:.3f} mm",
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
            if v is None:
                return ""
            if abs(v) < 1e-15:
                return "0." + "0" * dec
            return f"{v:.{dec}f}"

        def f_sci(v):
            if v is None:
                return ""
            if v == 0:
                return "0.00E+00"
            return f"{v:.2E}"

        def tabla(M, dec=4, ciencia=False, con_indices=True):
            M = np.atleast_2d(M)
            filas, cols = M.shape
            out = ['<table class="matriz">']
            if con_indices:
                out.append('<tr><th class="idx"></th>')
                for j in range(cols):
                    out.append(f'<th class="idx">{j + 1}</th>')
                out.append('</tr>')
            for i in range(filas):
                out.append("<tr>")
                if con_indices:
                    out.append(f'<th class="idx">{i + 1}</th>')
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

            tiene_coords_ok = bool(
                self.col_x and self.col_y and
                self.coords_estaciones and
                all(e in self.coords_estaciones for e in ids))

            if tiene_coords_ok:
                xs = [self.coords_estaciones[e][0] for e in ids]
                ys = [self.coords_estaciones[e][1] for e in ids]
                xmin, xmax = min(xs), max(xs)
                ymin, ymax = min(ys), max(ys)
                dx = (xmax - xmin) or 1.0
                dy = (ymax - ymin) or 1.0
                xmin -= dx * 0.12
                xmax += dx * 0.12
                ymin -= dy * 0.12
                ymax += dy * 0.12

                W, H = 640, 640
                M = 40
                ancho = xmax - xmin
                alto = ymax - ymin
                escala = min((W - 2 * M) / ancho, (H - 2 * M) / alto)

                def proy(x, y):
                    px = M + (x - xmin) * escala
                    py = H - M - (y - ymin) * escala
                    return px, py

                pos = {e: proy(*self.coords_estaciones[e]) for e in ids}
            else:
                cx, cy, R = 320, 320, 210
                pos = {}
                for i, e in enumerate(ids):
                    ang = -math.pi / 2 + 2 * math.pi * i / nn
                    pos[e] = (cx + R * math.cos(ang),
                              cy + R * math.sin(ang))

            svg = ['<svg xmlns="http://www.w3.org/2000/svg" '
                   'width="640" height="640" '
                   'style="border:1px solid #ccc; background:#fafafa;">']

            for o in obs:
                if o["ini"] not in pos or o["fin"] not in pos:
                    continue
                x1, y1 = pos[o["ini"]]
                x2, y2 = pos[o["fin"]]
                svg.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" '
                           f'x2="{x2:.1f}" y2="{y2:.1f}" '
                           f'stroke="#888" stroke-width="1.4"/>')
                xm, ym = (x1 + x2) / 2, (y1 + y2) / 2
                svg.append(f'<text x="{xm:.1f}" y="{ym:.1f}" '
                           f'text-anchor="middle" fill="#444" '
                           f'font-size="9">{o["dh"]:+.2f}</text>')

            for e in ids:
                if e not in pos:
                    continue
                x, y = pos[e]
                fija = e in res["cotas_fijas"]
                color = "#8ecf9e" if fija else "#96bfe6"
                cota = res["cotas_finales"][e]
                svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="16" '
                           f'fill="{color}" stroke="#fff" '
                           f'stroke-width="2"/>')
                svg.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" '
                           f'text-anchor="middle" fill="#2c3e50" '
                           f'font-size="11" font-weight="bold">{e}</text>')
                svg.append(f'<text x="{x:.1f}" y="{y - 22:.1f}" '
                           f'text-anchor="middle" fill="#333" '
                           f'font-size="10">{cota:.3f} m</text>')

            if tiene_coords_ok:
                svg.append('<text x="10" y="20" fill="#666" '
                           'font-size="10">Croquis a escala · UTM</text>')
            else:
                svg.append('<text x="10" y="20" fill="#666" '
                           'font-size="10">Croquis esquemático '
                           '(sin coordenadas)</text>')

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
    line-height:1.7; max-width:680px; display:inline-block; }}
  .diagnostico {{ background:#fff9e6; border:1px solid #f5d97a;
    border-left:3px solid #d4a017; border-radius:4px;
    padding:8px 12px; margin-bottom:8px; font-size:11px;
    line-height:1.35; color:#5c4813;
    display:inline-block; max-width:100%; }}
  .sigma {{ background:#fff8dc; padding:8px 15px;
    border-left:4px solid #d4a017; display:inline-block;
    margin:5px 0; font-family:Consolas, monospace; }}
  .semaforo {{ padding:6px 14px; border-radius:4px;
    margin:4px 6px 4px 0; display:inline-block;
    font-size:13px; font-weight:bold; }}
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
  {'Sí (' + self.col_x + '/' + self.col_y + ')'
            if tiene_coords else 'No disponibles'}<br>
  <b>Convención usada:</b>
  {'Campo — H_ini − H_fin = dh (swap automático)'
            if self.chk_invertir.isChecked()
            else 'Estándar — H_fin − H_ini = dh'}<br>
  <b>Generado por:</b> Plugin Análisis Topográfico v3.1
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

        diag = self._diagnosticar(res, obs)

        H.append('<h2>🔍 DIAGNÓSTICO AUTOMÁTICO</h2>')
        H.append('<div class="diagnostico">')
        for linea in diag["resumen"]:
            H.append(f'<p>{linea}</p>')
        H.append('</div>')

        if diag["sospechosas"]:
            H.append('<h3 style="font-size:12px; margin:10px 0 4px 0;">'
                     'Observaciones sospechosas</h3>')
            H.append('<table class="datos">'
                     '<tr><th>Obs</th><th>Ini</th><th>Fin</th>'
                     '<th>dh (m)</th><th>Residuo (mm)</th>'
                     '<th>v estand.</th><th>r<sub>i</sub></th>'
                     '<th>% VTPV</th><th>Severidad</th>'
                     '<th>Motivos</th></tr>')
            for s in diag["sospechosas"]:
                sev = s["severidad"]
                if sev == 3:
                    cls, etiqueta = "badge-mal", "🔴 CRÍTICA"
                elif sev == 2:
                    cls, etiqueta = "badge-rev", "🟠 Revisar"
                else:
                    cls, etiqueta = "badge-na", "🟡 Menor"
                motivos_txt = " · ".join(s["motivos"])
                H.append(
                    f'<tr><td>{s["est"]}</td>'
                    f'<td>{s["ini"]}</td><td>{s["fin"]}</td>'
                    f'<td>{s["dh"]:+.4f}</td>'
                    f'<td>{s["v_mm"]:+.3f}</td>'
                    f'<td>{s["vs"]:+.2f}</td>'
                    f'<td>{s["r_i"]:.3f}</td>'
                    f'<td>{s["vtpv_pct"]:.1f}%</td>'
                    f'<td class="{cls}">{etiqueta}</td>'
                    f'<td style="text-align:left; font-size:11px;">'
                    f'{motivos_txt}</td></tr>')
            H.append('</table>')

        H.append('<h3 style="font-size:12px; margin:10px 0 4px 0;">'
                 'Contribución al VTPV por observación</h3>')
        H.append('<table class="matriz">'
                 '<tr><th class="idx">Obs</th>'
                 '<th class="idx">v (mm)</th>'
                 '<th class="idx">P</th>'
                 '<th class="idx">v²·P</th>'
                 '<th class="idx">% total</th>'
                 '<th class="idx">acum.</th></tr>')

        orden = np.argsort(-res["vtpv_pct"])
        acum = 0.0
        for i in orden:
            acum += res["vtpv_pct"][i]
            pct = res["vtpv_pct"][i]
            cls = "val" if pct > 40 else "cero"
            H.append(
                f'<tr><th class="idx">{obs[i]["est"]}</th>'
                f'<td class="{cls}">{res["V"][i] * 1000:+.3f}</td>'
                f'<td class="{cls}">{res["P"][i, i]:.4f}</td>'
                f'<td class="{cls}">{res["vtpv_i"][i]:.6e}</td>'
                f'<td class="{cls}">{pct:.2f}%</td>'
                f'<td class="{cls}">{acum:.2f}%</td></tr>')
        H.append('</table>')

        H.append(
            '<p style="font-size:11px;color:#666;">'
            'El <b>VTPV</b> es la suma ponderada de residuos al cuadrado: '
            '<code>VᵀPV = Σ vᵢ² · Pᵢ</code>. '
            'Una observación que aporta &gt;40% del VTPV total es muy '
            'probable que contenga un error grosero.'
            '</p>')

        for txt, cls in sem:
            H.append(f'<div class="semaforo {cls}">{txt}</div>')
        H.append(f"""</div>
<div style="font-size:12px;color:#666;">
  Criterios: σ₀ ≤ {res['tol_sigma'] * 1000:.0f} mm ·
  residuo ≤ {res['tol_resid'] * 1000:.0f} mm ·
  resid. estand. ≤ {res['tol_vstd']} · test χ² al 95%
</div>""")

        svg = croquis_svg()
        if svg:
            H.append('<h2>CROQUIS DE LA RED</h2>')
            H.append(svg)
            H.append('<p style="font-size:11px;color:#666;">'
                     '🟢 Cota fija &nbsp; 🔵 Incógnita &nbsp;| '
                     'Aristas etiquetadas con el desnivel medido (m)</p>')

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
                f'<tr><td>{o["est"]}</td>'
                f'<td>{o["ini"]}</td><td>{o["fin"]}</td>'
                f'<td>{o["dh"]:.4f}</td>'
                f'<td>{res["dh_ajust"][i]:.4f}</td>'
                f'<td>{res["V"][i]:+.6f}</td>'
                f'<td>{res["r_i"][i]:.3f}</td>'
                f'<td>{vstd_txt}</td>'
                f'<td class="{cls}">{est}</td></tr>')
        H.append('</table>')

        UMBRAL_MATRICES = 15
        omitir_grandes = (n > UMBRAL_MATRICES)

        if omitir_grandes:
            H.append(
                f'<h2>MATRICES GRANDES — OMITIDAS</h2>'
                f'<div class="diagnostico">'
                f'<p>El ajuste tiene <b>{n}</b> observaciones '
                f'(supera el umbral de {UMBRAL_MATRICES}). '
                f'Las siguientes matrices se omitieron del reporte '
                f'para mantenerlo legible:</p>'
                f'<ul style="margin:6px 0 6px 20px; font-size:12px;">'
                f'<li>Matriz de pesos <b>P</b> ({n} × {n})</li>'
                f'<li>Matriz de diseño <b>A</b> ({n} × {u})</li>'
                f'<li>Matriz transpuesta <b>AT</b> ({u} × {n})</li>'
                f'<li>Matriz <b>Q_l̂l̂</b> ({n} × {n})</li>'
                f'<li>Matriz <b>Q_vv</b> ({n} × {n})</li>'
                f'</ul>'
                f'<p><b>Estas matrices no se han perdido.</b> Para '
                f'generarlas, vaya a la pestaña <b>④ Resultados</b> y pulse '
                f'<b>Exportar matrices (CSV)</b>.</p>'
                f'</div>')

        # Matrices siempre visibles (pequeñas)
        H.append(f'<h2>MATRIZ DE DISEÑO F ({n} × 1)</h2>'
                 + tabla(res["f"].reshape(-1, 1), 4))
        if not omitir_grandes:
            H.append(f'<h2>MATRIZ TRASPUESTA DE A (AT) ({u} × {n})</h2>'
                     + tabla(res["AT"], 4))
        H.append(f'<h2>MATRIZ AT(PA) ({u} × {u})</h2>'
                 + tabla(res["ATPA"], 4))
        H.append(f'<h2>MATRIZ INVERSA (ATPA) ({u} × {u})</h2>'
                 + tabla(res["INVATPA"], 4))
        H.append(f'<h2>MATRIZ (ATPF) ({u} × 1)</h2>'
                 + tabla(res["ATPF"].reshape(-1, 1), 4))

        H.append('<h2>RESUMEN DE COTAS FINALES</h2>'
                 '<table class="datos">'
                 '<tr><th>Est</th><th>Cota final (m)</th>'
                 '<th>± σ (m)</th><th>± IC95%</th>'
                 '<th>Tipo</th><th>Fuente</th></tr>')
        for k, e in enumerate(res["incognitas"]):
            H.append(f'<tr><td>{e}</td>'
                     f'<td>{f_num(res["X"][k], 4)}</td>'
                     f'<td>{f_sci(res["desv"][k])}</td>'
                     f'<td>{f_sci(res["IC95"][k])}</td>'
                     f'<td>Incógnita</td>'
                     f'<td>Ajustada</td></tr>')
        for e in sorted(res["cotas_fijas"].keys()):
            H.append(f'<tr><td>{e}</td>'
                     f'<td>{f_num(res["cotas_fijas"][e], 4)}</td>'
                     f'<td>—</td><td>—</td>'
                     f'<td>Fija</td><td>Dato</td></tr>')
        H.append('</table>')

        H.append('<h2>VECTOR DE RESIDUOS V</h2>'
                 + tabla(res["V"].reshape(-1, 1), 8))

        H.append('<h2>CONTROL ESTADÍSTICO</h2>'
                 f'<div class="sigma"><b>σ₀² </b> = '
                 f'{f_sci(res["sigma2"])}</div><br>'
                 f'<div class="sigma"><b>σ₀  </b> = '
                 f'{f_sci(res["sigma"])}</div><br>'
                 f'<div class="sigma"><b>t<sub>95,{gl}</sub></b> = '
                 f'{res["tcrit"]:.4f}</div>')
        p_texto = (f'{res["p_valor"]:.3f}'
                   if res["p_valor"] is not None else 'no disponible')
        H.append(f'<div style="font-size:13px;margin-top:8px;">'
                 f'<b>Test χ² global</b> &nbsp; '
                 f'χ²<sub>obs</sub> = {res["chi2_obs"]:.4e} &nbsp;|&nbsp; '
                 f'χ²<sub>tab(95%)</sub> = {res["chi2_tab"]:.4e} '
                 f'&nbsp;|&nbsp; p-valor: {p_texto} '
                 f'&nbsp;→&nbsp; '
                 f'<b>{"✓ Aceptable" if res["test_ok"] else "✗ Revisar"}</b>'
                 f'</div>')

        H.append(f'<h2>MATRIZ VARIANZA-COVARIANZA DE PARÁMETROS '
                 f'({u} × {u})</h2>' + tabla(res["Sigma_XX"], ciencia=True))

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
                     f'<td>{f_num(c, 4)}</td>'
                     f'<td>{f_sci(s)}</td>'
                     f'<td>{f_sci(ic)}</td>'
                     f'<td>[{c - ic:.4f} , {c + ic:.4f}]</td></tr>')
        H.append('</table>')

        if not omitir_grandes:
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
                     f'<td>{f_num(res["desv"][k], 6)}</td></tr>')
        H.append('</table>')

        H.append('<h2>METADATOS TÉCNICOS</h2>')
        H.append('<div class="meta">')
        H.append('<b>Método:</b> Gaus-Markov con pesos 1/distancia<br>')
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
        residuos_altos = (
            int(np.sum(np.abs(v_std_valid) > 3.0))
            if len(v_std_valid) > 0
            else 0
        )
        H.append(
            f'<b>Observaciones con residuo > 3σ:</b> '
            f'{residuos_altos}<br>')
        H.append(f'<b>Fecha de procesamiento:</b> '
                 f'{datetime.now():%Y-%m-%d %H:%M:%S}<br>')
        H.append(f'<b>Autor:</b> {autor}<br>')
        convencion = (
            "Campo (A→B ⇒ H_A − H_B)"
            if self.chk_invertir.isChecked()
            else "Estándar (H_final − H_inicial)"
        )
        H.append(
            f'<b>Convención de observaciones:</b> {convencion}<br>')
        H.append('</div>')

        H.append(f"""
<h2>FIN DEL PROCESO</h2>
<a class="inicio" href="#inicio">↑ IR AL INICIO</a>
<div class="footer">
  Generado con QGIS + Python · Plugin Análisis Topográfico v3.1 ·
  Ajuste Gaus-Markov · {datetime.now():%Y-%m-%d %H:%M:%S}
</div>
</body></html>""")

        return "\n".join(H)

    # ========================================================
    #  HTML — HELMERT
    # ========================================================
    def _construir_html_helmert(self, res, autor):
        tipo = res.get("tipo", "4p")
        n = int(res["n"])      # ← forzar a entero
        gl = int(res["gl"])    # ← forzar a entero

        capa = self.capa_src
        crs_src = capa.crs().authid() if capa else ""
        crs_out = self._crs_seleccionado()
        crs = crs_src if crs_src else f"{crs_out} (salida)"
        proy_path = QgsProject.instance().fileName() or "(sin guardar)"
        proy = (os.path.basename(proy_path)
                if proy_path and proy_path != "(sin guardar)"
                else proy_path)

        def f_num(v, dec=4):
            if v is None:
                return ""
            if abs(v) < 1e-15:
                return "0." + "0" * dec
            return f"{v:.{dec}f}"

        def f_sci(v):
            if v is None:
                return ""
            if v == 0:
                return "0.00E+00"
            return f"{v:.2E}"

        def tabla(M, dec=4, ciencia=False, con_indices=True):
            M = np.atleast_2d(M)
            filas, cols = M.shape
            out = ['<table class="matriz">']
            if con_indices:
                out.append('<tr><th class="idx"></th>')
                for j in range(cols):
                    out.append(f'<th class="idx">{j + 1}</th>')
                out.append('</tr>')
            for i in range(filas):
                out.append("<tr>")
                if con_indices:
                    out.append(f'<th class="idx">{i + 1}</th>')
                for j in range(cols):
                    v = M[i, j]
                    txt = f_sci(v) if ciencia else f_num(v, dec)
                    cls = "cero" if abs(v) < 1e-15 else "val"
                    out.append(f'<td class="{cls}">{txt}</td>')
                out.append("</tr>")
            out.append("</table>")
            return "\n".join(out)

        # ---- Semáforo ----
        sem = []
        sem.append(("σ₀ = " + f"{res['sigma'] * 1000:.3f} mm",
                    "ok" if res['sigma'] < self.sp_sigma.value()
                    else "alerta"))
        vmax = float(np.max(np.abs(res["V"]))) if res["V"].size else 0.0
        sem.append(("Residuo máx = " + f"{vmax * 1000:.3f} mm",
                    "ok" if vmax < self.sp_resid.value() else "alerta"))
        try:
            # El motor v3.1 devuelve la condición de la matriz escalada,
            # más representativa para coordenadas UTM grandes.
            cond = float(res.get("cond", np.linalg.cond(res["ATPA"])))
        except Exception:
            cond = float("nan")
        sem.append(("Cond. ATPA = " + f"{cond:.1e}",
                    "ok" if np.isfinite(cond) and cond < 1e10
                    else "alerta"))
        # χ² (4p: gl = 2n-4, 6p: gl = 2n-6)
        try:
            chi2_obs = res["VTPV"]
            chi2_tab = chi2_crit(gl) if gl > 0 else 0.0
            test_ok = chi2_obs <= chi2_tab
        except Exception:
            chi2_obs = 0.0
            chi2_tab = 0.0
            test_ok = True
        sem.append(("Test χ² global", "ok" if test_ok else "alerta"))

        # ---- Diagnóstico automático Helmert ----
        diagnostico_helm = []
        alertas_helm = 0
        sigma_mm = float(res["sigma"]) * 1000.0
        vmax_mm = vmax * 1000.0

        if gl <= 0:
            alertas_helm += 1
            diagnostico_helm.append(
                "⚠ <b>Ajuste exacto sin redundancia (GL=0).</b> Los "
                "parámetros pueden calcularse, pero no es posible evaluar "
                "estadísticamente los residuos. Agregue puntos de control.")
        else:
            diagnostico_helm.append(
                f"✓ El ajuste dispone de <b>{gl} grados de libertad</b>.")

        if sigma_mm <= self.sp_sigma.value() * 1000.0:
            diagnostico_helm.append(
                f"✓ La precisión global es aceptable: σ₀ = "
                f"<b>{sigma_mm:.3f} mm</b>.")
        else:
            alertas_helm += 1
            diagnostico_helm.append(
                f"⚠ σ₀ = <b>{sigma_mm:.3f} mm</b> supera la tolerancia "
                f"configurada ({self.sp_sigma.value() * 1000:.3f} mm).")

        if vmax_mm <= self.sp_resid.value() * 1000.0:
            diagnostico_helm.append(
                f"✓ El residuo máximo ({vmax_mm:.3f} mm) está dentro "
                f"de la tolerancia.")
        else:
            alertas_helm += 1
            diagnostico_helm.append(
                f"⚠ El residuo máximo es <b>{vmax_mm:.3f} mm</b> y "
                "supera la tolerancia "
                f"({self.sp_resid.value() * 1000:.3f} mm).")

        if res["V"].size and len(res.get("_nombres", [])):
            modulos = np.hypot(res["V"][:, 0], res["V"][:, 1])
            i_peor = int(np.argmax(modulos))
            diagnostico_helm.append(
                f"• El punto de control con mayor residuo combinado es "
                f"<b>{res['_nombres'][i_peor]}</b> "
                f"({modulos[i_peor] * 1000:.3f} mm).")

        if np.isfinite(cond) and cond < 1e10:
            diagnostico_helm.append(
                f"✓ La geometría numérica es estable "
                f"(condición escalada = {cond:.2e}).")
        else:
            alertas_helm += 1
            diagnostico_helm.append(
                f"⚠ La matriz presenta condición elevada ({cond:.2e}). "
                f"Revise la distribución de los puntos de control.")

        if gl > 0:
            if test_ok:
                diagnostico_helm.append("✓ El test χ² global es aceptable.")
            else:
                alertas_helm += 1
                diagnostico_helm.append(
                    "⚠ El test χ² global recomienda revisar el modelo, "
                    "los pesos o posibles errores en las coordenadas.")

        if len(res.get("_nombres_ver", [])) > 0:
            dx_ver = (res["_x_ver_dst_calc"] -
                      res["_x_ver_dst_obs"]) * 1000.0
            dy_ver = (res["_y_ver_dst_calc"] -
                      res["_y_ver_dst_obs"]) * 1000.0
            mod_ver = np.hypot(dx_ver, dy_ver)
            rms_ver = float(np.sqrt(np.mean(mod_ver**2)))
            peor_ver = int(np.argmax(mod_ver))
            diagnostico_helm.append(
                f"• Verificación externa: RMS 2D = <b>{rms_ver:.3f} "
                f"mm</b>; mayor diferencia en "
                f"<b>{res['_nombres_ver'][peor_ver]}</b> "
                f"({mod_ver[peor_ver]:.3f} mm).")
            if rms_ver > self.sp_resid.value() * 1000.0:
                alertas_helm += 1
                diagnostico_helm.append(
                    "⚠ La verificación externa supera la tolerancia de "
                    "residuos. Revise esos puntos antes de aplicar la "
                    "transformación a otros datos.")
        else:
            diagnostico_helm.append(
                "ℹ No se proporcionaron puntos de verificación externa.")

        conclusion_helm = (
            "✓ <b>Conclusión:</b> ajuste consistente con los criterios "
            "configurados."
            if alertas_helm == 0 else
            f"⚠ <b>Conclusión:</b> se detectaron {alertas_helm} "
            f"aspectos que requieren revisión.")

        # ---- Tabla de parámetros ----
        H = []
        H.append(f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<title>Resultado de la Transformación Helmert</title>
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
    line-height:1.7; max-width:680px; display:inline-block; }}
  .sigma {{ background:#fff8dc; padding:8px 15px;
    border-left:4px solid #d4a017; display:inline-block;
    margin:5px 0; font-family:Consolas, monospace; }}
  .semaforo {{ padding:6px 14px; border-radius:4px;
    margin:4px 6px 4px 0; display:inline-block;
    font-size:13px; font-weight:bold; }}
  .semaforo.ok     {{ background:#e8f5e9; color:#2e7d32; }}
  .semaforo.alerta {{ background:#ffebee; color:#c62828; }}
  .badge-ok  {{ color:#2e7d32; font-weight:bold; }}
  .badge-rev {{ color:#e65100; font-weight:bold; }}
  .badge-mal {{ color:#c62828; font-weight:bold; }}
  a.inicio {{ display:inline-block; margin-top:20px; color:#0645ad;
    font-weight:bold; text-decoration:none; }}
  .footer {{ margin-top:40px; font-size:11px; color:#888;
    border-top:1px solid #ccc; padding-top:8px; }}
</style></head><body id="inicio">

<h1>RESULTADO DE LA TRANSFORMACIÓN HELMERT</h1>
<div class="info">
  <b>Calculado por:</b> {autor}<br>
  <b>Fecha:</b> {datetime.now():%Y-%m-%d %H:%M:%S}<br>
  <b>Proyecto:</b> <span title="{proy_path}">{proy}</span><br>
  <b>Sistema de referencia (salida):</b> {crs}<br>
  <b>Capa fuente:</b> {capa.name() if capa else 'N/A'}
  ({capa.featureCount() if capa else 0} filas)<br>
  <b>Modelo:</b>
  {'Helmert 4 parámetros (similaridad)'
            if tipo == '4p' else 'Helmert 6 parámetros (afín)'}<br>
  <b>Puntos de control:</b> {n} (con X_DST/Y_DST)<br>
  <b>Puntos de verificación:</b> {len(self.pts_verificacion)}
  (no usados en el ajuste)<br>
  <b>Puntos transformados:</b> {len(self.pts_a_transf)} (sin X_DST/Y_DST)<br>
  <b>Total de puntos procesados:</b>
  {int(n) + len(self.pts_verificacion) + len(self.pts_a_transf)}<br>
  <b>Generado por:</b> Plugin Análisis Topográfico v3.1
</div>

<h2>RESUMEN</h2>
<table class="resumen">
  <tr><th>Concepto</th><th>Valor</th></tr>
  <tr><td>Ecuaciones (2n)</td><td>{2 * int(n)}</td></tr>
  <tr><td>Parámetros</td><td>{'4' if tipo == '4p' else '6'}</td></tr>
  <tr><td>Grados de libertad</td><td>{gl}</td></tr>
  <tr><td>Puntos de control</td><td>{n}</td></tr>
  <tr><td>Puntos de verificación</td><td>{len(self.pts_verificacion)}</td></tr>
  <tr><td>Puntos transformados</td><td>{len(self.pts_a_transf)}</td></tr>
  <tr><td><b>Total de puntos</b></td><td><b>
  {int(n) + len(self.pts_verificacion) + len(self.pts_a_transf)}
  </b></td></tr>
</table>

<h2>PARÁMETROS DE LA TRANSFORMACIÓN</h2>
<table class="datos">
  <tr><th>Parámetro</th><th>Valor</th><th>Unidad</th></tr>""")

        if tipo == "4p":
            H.append(f'<tr><td>a (s·cosθ)</td>'
                     f'<td>{res["a"]:.10f}</td><td>—</td></tr>')
            H.append(f'<tr><td>b (s·senθ)</td>'
                     f'<td>{res["b"]:.10f}</td><td>—</td></tr>')
            H.append(f'<tr><td>s (escala)</td>'
                     f'<td>{res["s"]:.10f}</td><td>—</td></tr>')
            H.append(f'<tr><td>θ (rotación)</td>'
                     f'<td>{res["theta_deg"]:.8f}</td><td>°</td></tr>')
            H.append(f'<tr><td>θ (rotación)</td>'
                     f'<td>{res["theta_deg"] * 3600:.4f}</td><td>"</td></tr>')
        else:
            H.append(f'<tr><td>a1</td>'
                     f'<td>{res["a1"]:.10f}</td><td>—</td></tr>')
            H.append(f'<tr><td>a2</td>'
                     f'<td>{res["a2"]:.10f}</td><td>—</td></tr>')
            H.append(f'<tr><td>b1</td>'
                     f'<td>{res["b1"]:.10f}</td><td>—</td></tr>')
            H.append(f'<tr><td>b2</td>'
                     f'<td>{res["b2"]:.10f}</td><td>—</td></tr>')
        H.append(f'<tr><td>Tx</td>'
                 f'<td>{res["Tx"]:.4f}</td><td>m</td></tr>')
        H.append(f'<tr><td>Ty</td>'
                 f'<td>{res["Ty"]:.4f}</td><td>m</td></tr>')
        H.append('</table>')

        # ---- Índice completo: ningún punto queda oculto ----
        H.append('<h2>LISTADO COMPLETO DE PUNTOS PROCESADOS</h2>')
        H.append('<table class="datos">'
                 '<tr><th>PUNTO</th><th>CLASIFICACIÓN</th>'
                 '<th>USO EN EL PROCESO</th></tr>')
        for nombre in res.get("_nombres", []):
            H.append(f'<tr><td>{nombre}</td><td>Control</td>'
                     f'<td>Usado para calcular los parámetros</td></tr>')
        for nombre in res.get("_nombres_ver", []):
            H.append(f'<tr><td>{nombre}</td><td>Verificación</td>'
                     '<td>Validación independiente; '
                     'no entra al ajuste</td></tr>')
        for nombre in res.get("_nombres_no", []):
            H.append(f'<tr><td>{nombre}</td><td>Transformado</td>'
                     f'<td>Coordenadas destino calculadas</td></tr>')
        H.append('</table>')

        H.append('<h2>SEMÁFORO DE CONTROL DE CALIDAD</h2><div>')
        for txt, cls in sem:
            H.append(f'<div class="semaforo {cls}">{txt}</div>')
        H.append('</div>')

        H.append('<h2>🔍 DIAGNÓSTICO AUTOMÁTICO</h2>')
        H.append('<div class="diagnostico">')
        H.append(f'<p>{conclusion_helm}</p>')
        for linea in diagnostico_helm:
            H.append(f'<p>{linea}</p>')
        H.append('</div>')

        # ---- Tabla de puntos de control con residuos ----
        H.append('<h2>PUNTOS DE CONTROL — COORDENADAS Y RESIDUOS</h2>')
        H.append('<table class="datos">'
                 '<tr><th>NAME</th>'
                 '<th>X_SRC</th><th>Y_SRC</th>'
                 '<th>X_DST obs</th><th>Y_DST obs</th>'
                 '<th>X_DST calc</th><th>Y_DST calc</th>'
                 '<th>dX (mm)</th><th>dY (mm)</th></tr>')

        for i in range(n):
            xc = float(res["_x_src"][i])
            yc = float(res["_y_src"][i])
            xd = float(res["_x_dst"][i])
            yd = float(res["_y_dst"][i])
            if tipo == "6p":
                x_calc, y_calc = helmert.transformar_6p([xc], [yc], res)
            else:
                x_calc, y_calc = helmert.transformar_4p([xc], [yc], res)
            dx_mm = (float(x_calc[0]) - xd) * 1000.0
            dy_mm = (float(y_calc[0]) - yd) * 1000.0
            name = res["_nombres"][i]
            H.append(
                f'<tr><td>{name}</td>'
                f'<td>{xc:.4f}</td><td>{yc:.4f}</td>'
                f'<td>{xd:.4f}</td><td>{yd:.4f}</td>'
                f'<td>{float(x_calc[0]):.4f}</td>'
                f'<td>{float(y_calc[0]):.4f}</td>'
                f'<td>{dx_mm:+.3f}</td>'
                f'<td>{dy_mm:+.3f}</td></tr>')
        H.append('</table>')

        # ---- Elipses de error por punto ----
        try:
            elipses = helmert.elipses_por_punto(res, res["_nombres"])
            H.append('<h2>ERROR CIRCULAR EN PUNTOS DE CONTROL</h2>')
            H.append('<table class="datos">'
                     '<tr><th>NAME</th><th>a (m)</th><th>b (m)</th>'
                     '<th>Azimut (°)</th><th>Nota</th></tr>')
            for el in elipses:
                nota = "circular" if abs(
                    el["a"] - el["b"]) < 1e-9 else "elíptico"
                H.append(f'<tr><td>{el["name"]}</td>'
                         f'<td>{el["a"] * 1000:.4f} mm</td>'
                         f'<td>{el["b"] * 1000:.4f} mm</td>'
                         f'<td>{el["az_deg"]:.3f}</td>'
                         f'<td>{nota}</td></tr>')
            H.append('</table>')
        except Exception:
            pass

        # ---- Tabla de puntos transformados (sin coordenadas de destino) ----
        if len(self.pts_a_transf) > 0:
            H.append('<h2>PUNTOS TRANSFORMADOS</h2>')
            H.append('<table class="datos">'
                     '<tr><th>PUNTO</th>'
                     '<th>X_ORIGEN</th><th>Y_ORIGEN</th>'
                     '<th>X_DESTINO</th><th>Y_DESTINO</th></tr>')
            for i, p in enumerate(self.pts_a_transf):
                xs = float(res["_x_no_src"][i])
                ys = float(res["_y_no_src"][i])
                xd = float(res["_x_no_dst"][i])
                yd = float(res["_y_no_dst"][i])
                H.append(f'<tr><td>{p["name"]}</td>'
                         f'<td>{xs:.4f}</td><td>{ys:.4f}</td>'
                         f'<td>{xd:.4f}</td><td>{yd:.4f}</td></tr>')
            H.append('</table>')

        # ---- Tabla de verificación externa ----
        if len(res.get("_nombres_ver", [])) > 0:
            dX = res["_x_ver_dst_calc"] - res["_x_ver_dst_obs"]
            dY = res["_y_ver_dst_calc"] - res["_y_ver_dst_obs"]
            dX_mm = dX * 1000.0
            dY_mm = dY * 1000.0
            rms_x = float(np.sqrt(np.mean(dX_mm**2)))
            rms_y = float(np.sqrt(np.mean(dY_mm**2)))
            rms_2d = float(np.sqrt(rms_x**2 + rms_y**2))

            H.append('<h2>VERIFICACIÓN EXTERNA '
                     '(puntos NO usados en el ajuste)</h2>')
            H.append(
                f'<div class="diagnostico">'
                f'<p>Estos puntos se reservaron para validar la '
                f'transformación de forma independiente. Se transforman '
                f'con los parámetros calculados y se comparan contra sus '
                f'coordenadas destino observadas.</p>'
                f'<p><b>RMS X = {rms_x:.3f} mm</b> &nbsp;·&nbsp; '
                f'<b>RMS Y = {rms_y:.3f} mm</b> &nbsp;·&nbsp; '
                f'<b>RMS 2D = {rms_2d:.3f} mm</b></p>'
                f'</div>')

            H.append('<table class="datos">'
                     '<tr><th>PUNTO</th>'
                     '<th>X_ORIGEN</th><th>Y_ORIGEN</th>'
                     '<th>X_DESTINO obs</th><th>Y_DESTINO obs</th>'
                     '<th>X_DESTINO calc</th><th>Y_DESTINO calc</th>'
                     '<th>dX (mm)</th><th>dY (mm)</th></tr>')
            for i, nombre in enumerate(res["_nombres_ver"]):
                xo = float(res["_x_ver_src"][i])
                yo = float(res["_y_ver_src"][i])
                xd_o = float(res["_x_ver_dst_obs"][i])
                yd_o = float(res["_y_ver_dst_obs"][i])
                xd_c = float(res["_x_ver_dst_calc"][i])
                yd_c = float(res["_y_ver_dst_calc"][i])
                H.append(f'<tr><td>{nombre}</td>'
                         f'<td>{xo:.4f}</td><td>{yo:.4f}</td>'
                         f'<td>{xd_o:.4f}</td><td>{yd_o:.4f}</td>'
                         f'<td>{xd_c:.4f}</td><td>{yd_c:.4f}</td>'
                         f'<td>{dX_mm[i]:+.3f}</td>'
                         f'<td>{dY_mm[i]:+.3f}</td></tr>')
            H.append('</table>')

        # ---- Croquis SVG ----
        if self.chk_croquis.isChecked():
            H.append('<h2>CROQUIS DE PUNTOS</h2>')
            H.append(self._croquis_svg_helmert(res))
            H.append('<p style="font-size:14px;color:#666;">'
                     '● Verde: control &nbsp; ■ Azul: verificación &nbsp; '
                     '▲ Naranja: transformado</p>')

        # ---- Matrices ----
        UMBRAL_MATRICES_HELM = 15
        omitir_grandes = (2 * int(n) > UMBRAL_MATRICES_HELM)

        if omitir_grandes:
            H.append(
                f'<h2>MATRICES GRANDES — OMITIDAS</h2>'
                f'<div class="diagnostico">'
                f'<p>El ajuste tiene <b>{2 * int(n)}</b> ecuaciones '
                f'(supera el umbral de {UMBRAL_MATRICES_HELM}). '
                f'Las siguientes matrices se omitieron del reporte '
                f'para mantenerlo legible:</p>'
                f'<ul style="margin:6px 0 6px 20px; font-size:12px;">'
                f'<li>Matriz de diseño <b>A</b> ({2 * int(n)} × '
                f'{"4" if tipo == "4p" else "6"})</li>'
                f'<li>Matriz de pesos <b>P</b> '
                f'({2 * int(n)} × {2 * int(n)})</li>'
                f'<li>Vector de observaciones <b>L</b> ({2 * int(n)} × 1)</li>'
                f'<li>Vector de residuos <b>V</b> ({2 * int(n)} × 1)</li>'
                f'</ul>'
                f'<p><b>Estas tablas no se han perdido.</b> Para generarlas, '
                f'vaya a la pestaña <b>④ Resultados</b> y pulse '
                f'<b>Exportar matrices (CSV)</b>.</p>'
                f'</div>')
        else:
            H.append(f'<h2>MATRIZ DE DISEÑO A ({2 * int(n)} × '
                     f'{"4" if tipo == "4p" else "6"})</h2>'
                     + tabla(res["A"], 4))

        if not omitir_grandes and "P" in res:
            H.append('<h2>MATRIZ DE PESOS P</h2>'
                     + tabla(res["P"], 4))
        if not omitir_grandes:
            H.append(f'<h2>VECTOR L ({2 * int(n)} × 1)</h2>'
                     + tabla(res["L"].reshape(-1, 1), 4))

        # Matrices siempre visibles
        if "ATPA" in res:
            m = 4 if tipo == "4p" else 6
            H.append(f'<h2>MATRIZ ATPA ({m} × {m})</h2>'
                     + tabla(res["ATPA"], 4))
            H.append(f'<h2>MATRIZ (ATPA)⁻¹ ({m} × {m})</h2>'
                     + tabla(res["INV_ATPA"], ciencia=True))
        if "ATPL" in res:
            H.append('<h2>VECTOR ATPL</h2>'
                     + tabla(res["ATPL"].reshape(-1, 1), 4))
        H.append('<h2>VECTOR DE PARÁMETROS X</h2>'
                 + tabla(res["X"].reshape(-1, 1), 6))

        if not omitir_grandes and "V" in res:
            V_flat = res["V"].flatten()
            H.append(f'<h2>VECTOR DE RESIDUOS V ({2 * int(n)} × 1)</h2>'
                     + tabla(V_flat.reshape(-1, 1), 8))

        # ---- Control estadístico ----
        H.append('<h2>CONTROL ESTADÍSTICO</h2>')
        H.append(f'<div class="sigma"><b>σ₀² </b> = '
                 f'{f_sci(res["sigma2"])}</div><br>')
        H.append(f'<div class="sigma"><b>σ₀  </b> = '
                 f'{f_sci(res["sigma"])}</div><br>')
        H.append(f'<div class="sigma"><b>VTPV</b> = '
                 f'{f_sci(res["VTPV"])}</div>')
        H.append(f'<div style="font-size:13px;margin-top:8px;">'
                 f'<b>Test χ² global</b> &nbsp; '
                 f'χ²<sub>obs</sub> = {chi2_obs:.4e} &nbsp;|&nbsp; '
                 f'χ²<sub>tab(95%)</sub> = {chi2_tab:.4e} &nbsp;→&nbsp; '
                 f'<b>{"✓ Aceptable" if test_ok else "✗ Revisar"}</b>'
                 f'</div>')

        H.append(f"""
<h2>FIN DEL PROCESO</h2>
<a class="inicio" href="#inicio">↑ IR AL INICIO</a>
<div class="footer">
  Generado con QGIS + Python · Plugin Análisis Topográfico v3.1 ·
  Transformación Helmert · {datetime.now():%Y-%m-%d %H:%M:%S}
</div>
</body></html>""")

        return "\n".join(H)

    def _croquis_svg_helmert(self, res):
        """
        Croquis SVG con controles, verificaciones y puntos transformados.
        Usa las coordenadas destino (X_DST/Y_DST) para el dibujo.
        """
        W, H = 640, 640
        M = 40

        # Recolectar puntos (x, y, name, tipo)
        pts = []
        for i in range(len(res["_nombres"])):
            pts.append((float(res["_x_dst"][i]),
                        float(res["_y_dst"][i]),
                        res["_nombres"][i], "CONTROL"))
        for i in range(len(res.get("_nombres_no", []))):
            pts.append((float(res["_x_no_dst"][i]),
                        float(res["_y_no_dst"][i]),
                        res["_nombres_no"][i], "TRANSFORMADO"))
        for i in range(len(res.get("_nombres_ver", []))):
            pts.append((float(res["_x_ver_dst_obs"][i]),
                        float(res["_y_ver_dst_obs"][i]),
                        res["_nombres_ver"][i], "VERIFICACION"))

        if not pts:
            return ""

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        dx = (xmax - xmin) or 1.0
        dy = (ymax - ymin) or 1.0
        xmin -= dx * 0.12
        xmax += dx * 0.12
        ymin -= dy * 0.12
        ymax += dy * 0.12

        ancho = xmax - xmin
        alto = ymax - ymin
        escala = min((W - 2 * M) / ancho, (H - 2 * M) / alto)

        def proy(x, y):
            px = M + (x - xmin) * escala
            py = H - M - (y - ymin) * escala
            return px, py

        svg = ['<svg xmlns="http://www.w3.org/2000/svg" '
               'width="640" height="640" '
               'style="border:1px solid #ccc; background:#fafafa;">']

        for x, y, name, tipo in pts:
            px, py = proy(x, y)
            if tipo == "CONTROL":
                color = "#8ecf9e"
                stroke = "#3a7d4d"
                forma = (f'<circle cx="{px:.1f}" cy="{py:.1f}" r="9" '
                         f'fill="{color}" stroke="{stroke}" '
                         f'stroke-width="1.6"/>')
            elif tipo == "TRANSFORMADO":
                color = "#f5cba7"
                stroke = "#b9770e"
                forma = (f'<polygon points="{px:.1f},{py - 9:.1f} '
                         f'{px + 9:.1f},{py + 7:.1f} '
                         f'{px - 9:.1f},{py + 7:.1f}" '
                         f'fill="{color}" stroke="{stroke}" '
                         f'stroke-width="1.6"/>')
            else:
                color = "#aed6f1"
                stroke = "#2874a6"
                forma = (f'<rect x="{px - 7:.1f}" y="{py - 7:.1f}" '
                         f'width="14" height="14" fill="{color}" '
                         f'stroke="{stroke}" stroke-width="1.6"/>')
            svg.append(forma)
            svg.append(f'<text x="{px:.1f}" y="{py - 13:.1f}" '
                       f'text-anchor="middle" fill="#2c3e50" '
                       f'font-size="10" font-weight="bold">{name}</text>')

        svg.append('<text x="10" y="20" fill="#666" font-size="10">'
                   'Croquis · coordenadas destino</text>')
        svg.append('</svg>')
        return "\n".join(svg)

    # --------------------------------------------------------
    #  Abrir carpeta de reportes
    # --------------------------------------------------------
    def _abrir_carpeta_reportes(self):
        try:
            proy_dir = os.path.dirname(QgsProject.instance().fileName())
            if not proy_dir:
                proy_dir = os.path.expanduser("~")
        except Exception:
            proy_dir = os.path.expanduser("~")
        carpeta = os.path.join(proy_dir, "reportes_topografia")
        os.makedirs(carpeta, exist_ok=True)
        webbrowser.open(f"file:///{carpeta.replace(os.sep, '/')}")

    # --------------------------------------------------------
    #  Limpiar estado
    # --------------------------------------------------------
    def _limpiar(self, silencioso=False):
        self.obs = None
        self.res = None
        self.res_helmert = None
        self.pts_control = None
        self.pts_verificacion = None
        self.pts_a_transf = None
        self.coords_estaciones = {}
        self.cotas_huerfanas = {}
        self.col_x = self.col_y = None

        if not silencioso:
            self.txt_log.clear()
            self.progress.setValue(0)

        self.btn_calc.setEnabled(False)
        self.btn_html.setEnabled(False)
        self.btn_gpkg.setEnabled(False)
        self.btn_csv.setEnabled(False)
        self.btn_matrices.setEnabled(False)

        if not silencioso:
            self._log("Estado limpiado.")

    def _exportar_matrices_csv(self):
        """Exporta a CSV las matrices grandes omitidas del HTML."""
        if self.modo == self.MODO_HELM:
            if not self.res_helmert:
                QMessageBox.warning(self, "Sin resultados",
                                    "Ejecute primero el cálculo.")
                return
        else:
            if not self.res:
                QMessageBox.warning(self, "Sin resultados",
                                    "Ejecute primero el cálculo.")
                return

        prefijo = (
            "helmert_matrices"
            if self.modo == self.MODO_HELM
            else "nivelacion_matrices"
        )
        nombre_def = f"{prefijo}.csv"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar matrices (CSV)", nombre_def, "CSV (*.csv)")
        if not ruta:
            return
        if not ruta.lower().endswith(".csv"):
            ruta += ".csv"

        try:
            lineas = []
            lineas.append("# Matrices del ajuste")
            lineas.append(f"# Fecha: {datetime.now():%Y-%m-%d %H:%M:%S}")
            lineas.append(f"# Autor: {self.autor}")
            lineas.append(
                "# Modo: "
                + ("Helmert" if self.modo == self.MODO_HELM else "Nivelación")
            )
            lineas.append("")

            def mat_a_csv(nombre, M):
                M = np.atleast_2d(M)
                lineas.append(
                    f"# ---- {nombre} ({M.shape[0]} x {M.shape[1]}) ----")
                for i in range(M.shape[0]):
                    fila = ",".join(
                        f"{M[i, j]:.10e}" for j in range(M.shape[1]))
                    lineas.append(fila)
                lineas.append("")

            if self.modo == self.MODO_HELM:
                res = self.res_helmert
                if "A" in res:
                    mat_a_csv("Matriz de diseño A", res["A"])
                if "P" in res:
                    mat_a_csv("Matriz de pesos P", res["P"])
                if "L" in res:
                    mat_a_csv("Vector de observaciones L",
                              res["L"].reshape(-1, 1))
                if "V" in res:
                    V_flat = res["V"].flatten()
                    mat_a_csv("Vector de residuos V (n x 1)",
                              V_flat.reshape(-1, 1))
                if "X" in res:
                    mat_a_csv("Vector de parámetros X (n x 1)",
                              res["X"].reshape(-1, 1))
                if "ATPA" in res:
                    mat_a_csv("Matriz normal ATPA", res["ATPA"])
                if "INV_ATPA" in res:
                    mat_a_csv("Matriz inversa de ATPA", res["INV_ATPA"])
                if "ATPL" in res:
                    mat_a_csv("Vector ATPL", res["ATPL"].reshape(-1, 1))
            else:
                res = self.res
                mat_a_csv("Matriz de pesos P", res["P"])
                mat_a_csv("Matriz de diseño A", res["A"])
                mat_a_csv("Matriz transpuesta AT", res["AT"])
                mat_a_csv("Matriz Q_lhat", res["Q_lhat"])
                mat_a_csv("Matriz Q_vv", res["Q_vv"])
                mat_a_csv("Vector de residuos V",
                          res["V"].reshape(-1, 1))
                mat_a_csv("Matriz Sigma_XX", res["Sigma_XX"])

            with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(lineas) + "\n")

            self._log(f"✓ Matrices exportadas: {ruta}", "#1e8449")
            QMessageBox.information(
                self, "Matrices exportadas",
                f"Exportado en:\n{ruta}\n\n"
                f"Formato: valores científicos (10 decimales), "
                f"una matriz tras otra, separadas por comentarios.")
        except Exception as e:
            import traceback
            self._log(f"✗ Excepción matrices CSV: {e}", "red")
            self._log(traceback.format_exc(), "red")
            QMessageBox.critical(self, "Error", str(e))

    def _generar_plantillas(self):
        """
        Genera dos CSV de plantilla con los campos correctos.

        Los archivos contienen solo el encabezado + 1 fila de ejemplo.
        Sin comentarios, listos para abrir en Excel y rellenar.
        """
        carpeta = QFileDialog.getExistingDirectory(
            self,
            "Selecciona carpeta donde guardar las plantillas",
            os.path.expanduser("~"))
        if not carpeta:
            return

        try:
            # --- Plantilla nivelación ---
            ruta_niv = os.path.join(carpeta, "plantilla_nivelacion.csv")
            lineas_niv = [
                "EST,C_FIJA,C_INICIAL,C_FINAL,DIF_COTA,DIST,X,Y",
                "T-01,100.000,BM_A,P1,1.2345,45.0,662400.000,998500.000",
                "T-02,,P1,P2,-0.5123,50.0,662450.000,998510.000",
                "T-03,102.500,BM_B,P2,2.1150,48.0,662500.000,998520.000",
                "T-04,,P2,P3,0.8500,55.0,662550.000,998530.000",
                "T-05,98.200,BM_C,P3,-1.1500,42.0,662600.000,998540.000",
            ]
            with open(ruta_niv, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(lineas_niv) + "\n")

            # --- Plantilla coordenadas (Helmert) ---
            ruta_helm = os.path.join(carpeta, "plantilla_coordenadas.csv")
            lineas_helm = [
                "PUNTO,X_ORIGEN,Y_ORIGEN,X_DESTINO,Y_DESTINO,USO",
                "H1,662412.000,998537.000,663885.5527,997732.7172,Control",
                "H2,662652.000,998525.000,664125.5620,997720.7266,Control",
                "H3,661436.233,997853.692,662909.7968,997049.3576,Control",
                "V1,662550.000,998400.000,664023.5000,997595.5000,"
                "Verificación",
                "V2,662700.000,998600.000,664174.5000,997795.5000,"
                "Verificación",
                "PT1,662480.666,998413.879,,,Control",
                "PT2,662543.662,998732.545,,,Control",
                "PT3,662154.764,998359.366,,,Control",
            ]
            with open(ruta_helm, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(lineas_helm) + "\n")

            self._log(f"✓ Plantillas generadas en: {carpeta}", "#1e8449")

            # --- Mensaje detallado con la descripción de columnas ---
            msg = (
                f"<b>✓ Plantillas generadas en:</b><br>"
                f"<code>{carpeta}</code><br><br>"

                f"<b>1) plantilla_nivelacion.csv</b><br>"
                f"Columnas:<br>"
                f"&nbsp;&nbsp;• <b>EST</b> — ID de línea (T-01, T-02...)<br>"
                f"&nbsp;&nbsp;• <b>C_FIJA</b> — cota fija si la estación de "
                f"<b>C_INICIAL</b> es un BM<br>"
                f"&nbsp;&nbsp;• <b>C_INICIAL</b> — estación origen "
                f"(BM_A, P1...)<br>"
                f"&nbsp;&nbsp;• <b>C_FINAL</b> — estación destino "
                f"(P1, P2...)<br>"
                f"&nbsp;&nbsp;• <b>DIF_COTA</b> — desnivel (m)<br>"
                f"&nbsp;&nbsp;• <b>DIST</b> — distancia (m)<br>"
                f"&nbsp;&nbsp;• <b>X</b>, <b>Y</b> — coords UTM (opcional)<br>"
                f"<i>La cota fija se asocia a C_INICIAL, no a EST.</i><br><br>"

                f"<b>2) plantilla_coordenadas.csv</b><br>"
                f"Columnas:<br>"
                f"&nbsp;&nbsp;• <b>PUNTO</b> — identificador del punto<br>"
                f"&nbsp;&nbsp;• <b>X_ORIGEN</b>, <b>Y_ORIGEN</b> — "
                f"sistema origen<br>"
                f"&nbsp;&nbsp;• <b>X_DESTINO</b>, <b>Y_DESTINO</b> — "
                f"sistema destino<br>"
                f"&nbsp;&nbsp;• <b>USO</b> — <i>Control</i> (entra al ajuste) "
                f"o <i>Verificación</i> (valida, no ajusta)<br>"
                f"&nbsp;&nbsp;&nbsp;&nbsp;Si X_DESTINO/Y_DESTINO están "
                f"vacíos → punto a transformar<br><br>"

                f"<b>Instrucciones:</b><br>"
                f"1. Abre cada archivo con Excel o bloc de notas.<br>"
                f"2. Borra las filas de ejemplo.<br>"
                f"3. Escribe tus datos respetando el orden de columnas.<br>"
                f"4. Guarda el archivo.<br>"
                f"5. Cárgalo en QGIS con <i>Capa → Añadir capa → "
                f"Añadir capa de texto delimitado</i>."
            )
            QMessageBox.information(self, "Plantillas generadas", msg)

            # Abrir carpeta en el explorador
            try:
                webbrowser.open(
                    f"file:///{carpeta.replace(os.sep, '/')}")
            except Exception:
                pass

        except Exception as e:
            import traceback
            self._log(f"✗ Error generando plantillas: {e}", "red")
            self._log(traceback.format_exc(), "red")
            QMessageBox.critical(
                self, "Error",
                f"No se pudieron generar las plantillas:\n{e}")
