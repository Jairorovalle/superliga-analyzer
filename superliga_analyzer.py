
import re
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

URL = "https://www.futbolgol.com/superliga/"
OUTPUT = Path("superliga_datos.xlsx")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}


def download_page(url=URL):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.text


def clean_columns(df):
    df = df.copy()
    df.columns = [
        re.sub(r"\s+", " ", str(c)).strip()
        for c in df.columns
    ]
    return df.dropna(how="all").reset_index(drop=True)


def find_classification_table(html):
    tables = pd.read_html(StringIO(html))
    if not tables:
        raise RuntimeError("No se encontraron tablas en la página.")

    # Buscar la tabla que contiene columnas típicas de clasificación.
    for t in tables:
        t = clean_columns(t)
        cols = " ".join(map(str, t.columns)).upper()
        if "EQUIPO" in cols and ("PJ" in cols or "PG" in cols):
            return t

    # Fallback: devolver la tabla más grande.
    return max(tables, key=lambda x: x.shape[0] * x.shape[1])


def normalize_table(df):
    df = clean_columns(df)

    # A veces pandas interpreta una fila de encabezado como datos.
    if len(df) and all(str(x).strip().lower() in {"equipo", "pj", "pg", "pe", "pp", "gf", "gc", "gd", "pts", "puntos"} 
                       for x in df.iloc[0].astype(str).tolist()):
        df = df.iloc[1:].reset_index(drop=True)

    # Convertir columnas numéricas cuando sea posible.
    for c in df.columns:
        s = df[c].astype(str).str.replace(",", ".", regex=False)
        numeric = pd.to_numeric(s, errors="coerce")
        if numeric.notna().sum() >= max(2, len(df) * 0.6):
            df[c] = numeric

    # Crear diferencia de goles y puntos si no existen y están disponibles.
    colmap = {str(c).upper(): c for c in df.columns}
    gf = colmap.get("GF")
    gc = colmap.get("GC")

    if "DG" not in colmap and "GD" not in colmap and gf and gc:
        df["DG"] = df[gf] - df[gc]

    if "PTS" not in colmap and "PUNTOS" not in colmap:
        pg = colmap.get("PG")
        pe = colmap.get("PE")
        if pg and pe:
            df["PTS"] = df[pg].fillna(0) * 3 + df[pe].fillna(0)

    return df


def add_power_metrics(df):
    df = df.copy()
    cols = {str(c).upper(): c for c in df.columns}

    def num(name):
        c = cols.get(name)
        return pd.to_numeric(df[c], errors="coerce").fillna(0) if c else None

    pj, gf, gc, pts = num("PJ"), num("GF"), num("GC"), num("PTS")
    if pj is not None:
        df["GF/PJ"] = (gf / pj.replace(0, pd.NA)).round(2) if gf is not None else pd.NA
        df["GC/PJ"] = (gc / pj.replace(0, pd.NA)).round(2) if gc is not None else pd.NA
        df["Pts/PJ"] = (pts / pj.replace(0, pd.NA)).round(2) if pts is not None else pd.NA

    if gf is not None and gc is not None:
        df["DG"] = gf - gc

    return df


def main():
    print(f"Descargando: {URL}")
    html = download_page()
    print("Página descargada.")

    table = find_classification_table(html)
    table = normalize_table(table)
    table = add_power_metrics(table)

    # Ordenar por puntos y diferencia de goles cuando existen.
    sort_cols = [c for c in ["PTS", "DG", "GF"] if c in table.columns]
    if sort_cols:
        table = table.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last")

    # Añadir posición.
    table.insert(0, "Posición", range(1, len(table) + 1))

    with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="Clasificacion", index=False)

        info = pd.DataFrame({
            "Dato": [
                "Fuente",
                "URL",
                "Fecha de consulta",
                "Equipos detectados",
            ],
            "Valor": [
                "FutbolGol",
                URL,
                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                len(table),
            ],
        })
        info.to_excel(writer, sheet_name="Info", index=False)

    print(f"\nListo. Archivo generado: {OUTPUT.resolve()}")
    print("\nVista rápida:")
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
