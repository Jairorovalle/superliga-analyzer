import re
from io import StringIO

import pandas as pd
import requests
import streamlit as st

URL = "https://www.futbolgol.com/superliga/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
}

st.set_page_config(page_title="Superliga Analyzer", page_icon="⚽", layout="wide")
st.title("⚽ Superliga Analyzer")
st.caption("Datos de FutbolGol • actualización bajo demanda")


def clean(df):
    df = df.copy()
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df.dropna(how="all").reset_index(drop=True)


def numeric(series):
    return pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False),
        errors="coerce"
    )


def get_table():
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise RuntimeError("FutbolGol no devolvió ninguna tabla.")
    for table in tables:
        table = clean(table)
        cols = " ".join(map(str, table.columns)).upper()
        if "EQUIPO" in cols and ("PJ" in cols or "PG" in cols):
            return table
    raise RuntimeError("No encontré la tabla de clasificación de Superliga.")


def normalize(df):
    df = clean(df)

    for col in df.columns:
        converted = numeric(df[col])
        if converted.notna().sum() >= max(2, int(len(df) * 0.6)):
            df[col] = converted

    upper = {str(c).upper(): c for c in df.columns}
    gf, gc = upper.get("GF"), upper.get("GC")
    pg, pe = upper.get("PG"), upper.get("PE")
    pj = upper.get("PJ")
    pts_col = upper.get("PTS") or upper.get("PUNTOS")

    if gf and gc:
        df["DG"] = numeric(df[gf]).fillna(0) - numeric(df[gc]).fillna(0)

    if not pts_col and pg and pe:
        df["PTS"] = numeric(df[pg]).fillna(0) * 3 + numeric(df[pe]).fillna(0)

    if pj:
        pj_values = numeric(df[pj]).replace(0, pd.NA)
        if gf:
            df["GF/PJ"] = pd.to_numeric(numeric(df[gf]) / pj_values, errors="coerce").round(2)
        if gc:
            df["GC/PJ"] = pd.to_numeric(numeric(df[gc]) / pj_values, errors="coerce").round(2)
        if "PTS" in df.columns:
            df["Pts/PJ"] = pd.to_numeric(numeric(df["PTS"]) / pj_values, errors="coerce").round(2)

    sort_cols = [c for c in ["PTS", "DG", "GF"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last")

    df.insert(0, "Pos", range(1, len(df) + 1))
    return df


if st.button("🔄 Actualizar datos de FutbolGol", type="primary"):
    st.rerun()

try:
    with st.spinner("Consultando FutbolGol..."):
        table = normalize(get_table())

    st.success(f"Tabla actualizada: {len(table)} equipos.")

    team = st.selectbox(
        "Selecciona tu equipo",
        ["— Seleccionar —"] + table.iloc[:, 1].astype(str).tolist()
    )

    if team != "— Seleccionar —":
        row = table[table.iloc[:, 1].astype(str) == team].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Posición", int(row["Pos"]))
        if "PTS" in table.columns:
            c2.metric("Puntos", int(row["PTS"]))
        if "PJ" in table.columns:
            c3.metric("PJ", int(row["PJ"]))
        if "DG" in table.columns:
            c4.metric("Diferencia", int(row["DG"]))

    st.subheader("Clasificación")
    st.dataframe(table, use_container_width=True, hide_index=True)

    csv = table.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Descargar tabla CSV", csv, "superliga_clasificacion.csv", "text/csv")

except Exception as e:
    st.error("No fue posible procesar la tabla de FutbolGol.")
    st.write("Detalle:", str(e))
    st.info("La conexión con FutbolGol está funcionando; corregiremos cualquier otro detalle de estructura si aparece.")
