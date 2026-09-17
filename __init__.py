# -*- coding: utf-8 -*-
"""
Módulo de inicialización del plugin Analisis Nivelacion.
QGIS busca esta función al cargar el complemento.
"""

def classFactory(iface):
    """Punto de entrada del plugin. QGIS llama a esta función."""
    from .nivelacion import AnalisisNivelacion
    return AnalisisNivelacion(iface)