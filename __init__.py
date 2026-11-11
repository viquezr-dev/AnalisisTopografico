# -*- coding: utf-8 -*-
"""
Análisis Topográfico — plugin de QGIS
Inicializa el complemento y expone classFactory().
"""


def classFactory(iface):
    from .nivelacion import AnalisisTopografico
    return AnalisisTopografico(iface)
