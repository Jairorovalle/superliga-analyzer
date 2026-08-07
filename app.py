
import re
from io import StringIO
import requests
import pandas as pd
import streamlit as st

URL = "https://www.futbolgol.com/superliga/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
}

st.set_page_config(page_title="Superliga Analyzer", page_icon="⚽", layout="wide")
st.title("⚽ Superliga Analyzer")
st.caption("Datos de FutbolGol • actualización bajo demanda")

def clean(df):
    df = df.copy()
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df.dropna(how="all").reset_index(drop=True)

def get_table():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(StringIO(r.text))
    for t in tables:
        t = clean(t)
        cols = " ".join(map(str, t.columns)).upper()
        if "EQUIPO" in cols and ("PJ" in cols or "PG" in cols):
            return t
    raise RuntimeError("No encontré la tabla de clasificación.")

def normalize(df):
    df = clean(df)
    # Numeric conversion
    for c in df.columns:
        x = pd.to_numeric(df[c].astype(str).str.replace(",", ".", regex=False), errors="coerce")
        if x.notna().sum() >= max(2, int(len(df) * .6)):
            df[c] = x

    upper = {str(c).upper(): c for c in df.columns}
    gf, gc = upper.get("GF"), upper.get("GC")
    pg, pe = upper.get("PG"), upper.get("PE")
    pj = upper.get("PJ")
    pts = upper.get("PTS") or upper.get("PUNTOS")

    if gf and gc:
        df["DG"] = pd.to_numeric(df[gf], errors="coerce").fillna(0) - pd.to_numeric(df[gc], errors="coerce").fillna(0)
    if not pts and pg and pe:
        df["PTS"] = pd.to_numeric(df[pg], errors="coerce").fillna(0)*3 + pd.to_numeric(df[pe], errors="coerce").fillna(0)

    if pj:
        pjv = pd.to_numeric(df[pj], errors="coerce").replace(0, pd.NA)
        if gf:
            df["GF/PJ"] = (pd.to_numeric(df[gf], errors="coerce") / pjv).round(2)
        if gc:
            df["GC/PJ"] = (pd.to_numeric(df[gc], errors="coerce") / pjv).round(2)
        if "PTS" in df:
            df["Pts/PJ"] = (pd.to_numeric(df["PTS"], errors="coerce") / pjv).round(2)

    sort = [c for c in ["PTS", "DG", "GF"] if c in df.columns]
    if sort:
        df = df.sort_values(sort, ascending=[False]*len(sort), na_position="last")
    df.insert(0, "Pos", range(1, len(df)+1))
    return df

if st.button("🔄 Actualizar datos de FutbolGol", type="primary"):
    st.cache_data.clear()

try:
    with st.spinner("Consultando FutbolGol..."):
        table = normalize(get_table())

    st.success(f"Tabla actualizada: {len(table)} equipos.")

    team = st.selectbox("Selecciona tu equipo", ["— Seleccionar —"] + table.iloc[:, 1].astype(str).tolist())

    if team != "— Seleccionar —":
        row = table[table.iloc[:, 1].astype(str) == team].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Posición", int(row["Pos"]))
        if "PTS" in table: c2.metric("Puntos", int(row["PTS"]))
        if "PJ" in table: c3.metric("PJ", int(row["PJ"]))
        if "DG" in table: c4.metric("Diferencia", int(row["DG"]))

    st.subheader("Clasificación")
    st.dataframe(table, use_container_width=True, hide_index=True)

    csv = table.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Descargar tabla CSV", csv, "superliga_clasificacion.csv", "text/csv")

except Exception as e:
    st.error("No fue posible leer automáticamente FutbolGol desde el servidor.")
    st.write("Detalle:", str(e))
    st.info("Si FutbolGol bloquea solicitudes automáticas o cambia su estructura, podemos añadir una carga manual por captura/Excel como respaldo.")
