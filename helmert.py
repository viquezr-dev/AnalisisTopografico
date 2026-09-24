# -*- coding: utf-8 -*-
"""Transformaciones Helmert 2D (similitud 4p y afín 6p) · v3.1."""

import math
import numpy as np

_COND_MAX = 1.0e12
_EPS = 1.0e-15


def _entradas(x_src, y_src, x_dst, y_dst, minimo, pesos=None):
    vectores = [np.asarray(v, dtype=float).reshape(-1)
                for v in (x_src, y_src, x_dst, y_dst)]
    if len({len(v) for v in vectores}) != 1:
        raise ValueError(
            "x_src, y_src, x_dst e y_dst deben tener la misma longitud")
    n = len(vectores[0])
    if n < minimo:
        raise ValueError(f"Se necesitan al menos {minimo} puntos de control")
    if not all(np.all(np.isfinite(v)) for v in vectores):
        raise ValueError("Las coordenadas contienen valores NaN o infinitos")
    origen = np.column_stack(vectores[:2])
    destino = np.column_stack(vectores[2:])
    if len(np.unique(origen, axis=0)) != n:
        raise ValueError("Existen coordenadas de origen duplicadas")
    if len(np.unique(destino, axis=0)) != n:
        raise ValueError("Existen coordenadas de destino duplicadas")
    if pesos is None:
        w = np.ones(n, dtype=float)
    else:
        w = np.asarray(pesos, dtype=float).reshape(-1)
        if len(w) != n:
            raise ValueError(
                "pesos debe tener la misma longitud que los puntos")
        if not np.all(np.isfinite(w)) or np.any(w <= 0):
            raise ValueError(
                "Todos los pesos deben ser finitos y mayores que cero")
    return (*vectores, w)


def _resolver(A, L, pesos, parametros):
    p_diag = np.repeat(pesos, 2)
    raiz_p = np.sqrt(p_diag)
    escalas = np.linalg.norm(A * raiz_p[:, None], axis=0)
    escalas[escalas < _EPS] = 1.0
    A_esc = A / escalas
    Aw = A_esc * raiz_p[:, None]
    Lw = L * raiz_p
    X_esc, _, rango, singulares = np.linalg.lstsq(Aw, Lw, rcond=None)
    if rango < parametros:
        raise ValueError(
            "Geometría degenerada: la matriz de diseño tiene rango "
            f"{rango}; se requieren {parametros} parámetros")
    condicion = float(np.linalg.cond(Aw))
    if not np.isfinite(condicion) or condicion > _COND_MAX:
        raise ValueError(
            "Geometría mal condicionada "
            f"(condición escalada={condicion:.3e})")

    X = X_esc / escalas
    V = A @ X - L
    P = np.diag(p_diag)
    ATPA = A.T @ P @ A
    ATPL = A.T @ P @ L
    INV_ATPA = np.linalg.pinv(ATPA, rcond=1.0e-15, hermitian=True)
    VTPV = float(V.T @ P @ V)
    gl = len(L) - parametros
    sigma2 = VTPV / gl if gl > 0 else 0.0
    sigma = math.sqrt(max(sigma2, 0.0))
    param_cov = sigma2 * INV_ATPA
    param_desv = np.sqrt(np.clip(np.diag(param_cov), 0.0, None))

    if gl > 0 and sigma2 > 0:
        Q = np.diag(1.0 / p_diag)
        Q_vv = sigma2 * (Q - A @ INV_ATPA @ A.T)
        var_v = np.clip(np.diag(Q_vv), 0.0, None)
        sd_v = np.sqrt(var_v)
        sd_v[sd_v < _EPS] = np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            v_std = V / sd_v
    else:
        var_v = np.full(len(L), np.nan)
        v_std = np.full(len(L), np.nan)

    return {
        "A": A, "L": L, "X": X, "P": P,
        "ATPA": ATPA, "INV_ATPA": INV_ATPA, "ATPL": ATPL,
        "V": V.reshape(-1, 2), "VTPV": VTPV,
        "sigma2": sigma2, "sigma": sigma, "gl": gl,
        "param_cov": param_cov, "param_desv": param_desv,
        "v_std": v_std.reshape(-1, 2),
        "Q_vv_diag": var_v.reshape(-1, 2),
        "rank": int(rango), "cond": condicion,
        "singular_values": singulares,
    }


def helmert_4p(x_src, y_src, x_dst, y_dst, pesos=None):
    """Ajusta similitud 2D: rotación, escala y dos traslaciones."""
    x_src, y_src, x_dst, y_dst, w = _entradas(
        x_src, y_src, x_dst, y_dst, 2, pesos)
    n = len(x_src)
    A = np.zeros((2 * n, 4), dtype=float)
    L = np.empty(2 * n, dtype=float)
    A[0::2, 0], A[0::2, 1], A[0::2, 2] = x_src, -y_src, 1.0
    A[1::2, 0], A[1::2, 1], A[1::2, 3] = y_src, x_src, 1.0
    L[0::2], L[1::2] = x_dst, y_dst
    res = _resolver(A, L, w, 4)
    a, b, Tx, Ty = res["X"]
    angulo = math.atan2(b, a)
    res.update({"a": a, "b": b, "Tx": Tx, "Ty": Ty,
                "s": math.hypot(a, b), "theta_rad": angulo,
                "theta_deg": math.degrees(angulo), "n": n, "tipo": "4p"})
    return res


def transformar_4p(x_src, y_src, params):
    x, y = _coordenadas_nuevas(x_src, y_src)
    return (params["a"] * x - params["b"] * y + params["Tx"],
            params["b"] * x + params["a"] * y + params["Ty"])


def helmert_6p(x_src, y_src, x_dst, y_dst, pesos=None):
    """Ajusta una transformación afín 2D de seis parámetros."""
    x_src, y_src, x_dst, y_dst, w = _entradas(
        x_src, y_src, x_dst, y_dst, 3, pesos)
    n = len(x_src)
    A = np.zeros((2 * n, 6), dtype=float)
    L = np.empty(2 * n, dtype=float)
    A[0::2, 0], A[0::2, 1], A[0::2, 2] = x_src, y_src, 1.0
    A[1::2, 3], A[1::2, 4], A[1::2, 5] = x_src, y_src, 1.0
    L[0::2], L[1::2] = x_dst, y_dst
    res = _resolver(A, L, w, 6)
    a1, a2, Tx, b1, b2, Ty = res["X"]
    res.update({"a1": a1, "a2": a2, "Tx": Tx,
                "b1": b1, "b2": b2, "Ty": Ty,
                "n": n, "tipo": "6p"})
    return res


def transformar_6p(x_src, y_src, params):
    x, y = _coordenadas_nuevas(x_src, y_src)
    return (params["a1"] * x + params["a2"] * y + params["Tx"],
            params["b1"] * x + params["b2"] * y + params["Ty"])


def _coordenadas_nuevas(x_src, y_src):
    x = np.asarray(x_src, dtype=float)
    y = np.asarray(y_src, dtype=float)
    if x.shape != y.shape:
        raise ValueError("x_src e y_src deben tener la misma forma")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Las coordenadas contienen valores NaN o infinitos")
    return x, y


def resumen_4p(res, nombres=None):
    lineas = [f"Puntos de control: {res['n']}",
              f"Grados de libertad: {res['gl']}",
              f"Factor de escala  s = {res['s']:.10f}",
              f"Rotación θ = {res['theta_deg']:.8f}°",
              f"Traslación Tx = {res['Tx']:.4f} m",
              f"Traslación Ty = {res['Ty']:.4f} m",
              f"σ₀ = {res['sigma']:.6f} m", "",
              "Desviaciones típicas de los parámetros:"]
    etiquetas = nombres or ["a", "b", "Tx", "Ty"]
    lineas.extend(f"  σ({nom}) = {desv:.6e}"
                  for nom, desv in zip(etiquetas, res["param_desv"]))
    return "\n".join(lineas)


def elipses_por_punto(res, nombres=None):
    """Calcula elipses de error aproximadas en puntos de control."""
    salida = []
    for i in range(int(res["n"])):
        A_i = res["A"][2 * i:2 * i + 2, :]
        cov = res["sigma2"] * A_i @ res["INV_ATPA"] @ A_i.T
        cov = (cov + cov.T) / 2.0
        valores, vectores = np.linalg.eigh(cov)
        orden = np.argsort(valores)
        valores = np.clip(valores[orden], 0.0, None)
        vector = vectores[:, orden[-1]]
        azimut = math.atan2(vector[0], vector[1]) % (2 * math.pi)
        salida.append({"n": i,
                       "name": nombres[i] if nombres else f"P{i + 1}",
                       "a": math.sqrt(valores[-1]),
                       "b": math.sqrt(valores[0]),
                       "az_deg": math.degrees(azimut)})
    return salida
