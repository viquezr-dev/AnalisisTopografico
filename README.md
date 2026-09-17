# Análisis de Nivelación — Plugin QGIS

Plugin para ajustar redes de nivelación topográfica por el método de
**mínimos cuadrados (Gaus-Markov)** y generar un reporte HTML profesional.

## Características

- ✅ Lectura de tablas CSV importadas a QGIS (campos String)
- ✅ Validación previa de la estructura y datos
- ✅ Ajuste por mínimos cuadrados con pesos `1/distancia`
- ✅ Reporte HTML con formato idéntico al Excel original
- ✅ Test χ² global + p-valor
- ✅ Intervalos de confianza al 95 % (t de Student)
- ✅ Residuos estandarizados y test de Baarda
- ✅ Número de redundancia por observación
- ✅ Semáforo de control de calidad
- ✅ Croquis SVG de la red (verde = fija, rojo = incógnita)
- ✅ Exportación a GeoPackage
- ✅ Sin dependencia de scipy (fallback interno)

## Requisitos

- QGIS ≥ 3.16
- numpy (incluido en QGIS)
- scipy (opcional, mejora la precisión del test χ²)

## Estructura esperada de la tabla

La capa de entrada debe tener **6 campos tipo String**:

| Campo | Descripción |
|-------|-------------|
| EST | Número de la estación (fila) |
| C_FIJA | Cota fija (solo si la estación es fija) |
| C_INICIAL | Estación de origen de la observación |
| C_FINAL | Estación de destino de la observación |
| DIF_COTA | Desnivel medido (m) |
| DIST | Distancia (km) para el peso |

Ejemplo:
