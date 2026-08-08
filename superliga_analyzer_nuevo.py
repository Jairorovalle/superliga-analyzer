import re
from io import StringIO
import pandas as pd
import requests
import streamlit as st

URL = "https://www.futbolgol.com/superliga/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                  "Mobile/15E148 Safari/604.1"
}

st.set_page_config(page_title="Superliga Analyzer", page_icon="⚽", layout="wide")
st.title("⚽ Superliga Analyzer")
st.caption("Datos de FutbolGol • actualización bajo demanda")


def clean_dataframe(df):
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(str(x) for x in col if str(x) != "nan").strip()
            for col in df.columns
        ]
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df.dropna(how="all").reset_index(drop=True)


def get_tables():
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    return [clean_dataframe(t) for t in tables if not clean_dataframe(t).empty]


def find_standings(tables):
    keywords = {
        "pos", "pts", "pj", "pg", "pe", "pp", "gf", "gc", "dg",
        "equipo", "equipos", "team", "teams"
    }
    best, best_score = None, -1
    for table in tables:
        cols = {str(c).lower().strip() for c in table.columns}
        score = len(cols & keywords)
        if any("pts" in str(c).lower() for c in table.columns):
            score += 3
        if any(("equipo" in str(c).lower()) or ("team" in str(c).lower())
               for c in table.columns):
            score += 2
        if score > best_score:
            best, best_score = table, score
    return best


def add_position(df):
    df = df.copy()
    pos_cols = [c for c in df.columns if str(c).strip().lower() == "pos"]
    if pos_cols:
        df[pos_cols[0]] = range(1, len(df) + 1)
    else:
        df.insert(0, "Pos", range(1, len(df) + 1))
    return df


if st.button("🔄 Actualizar datos de FutbolGol", type="primary"):
    with st.spinner("Consultando FutbolGol..."):
        try:
            tables = get_tables()
            if not tables:
                st.error("FutbolGol no devolvió ninguna tabla.")
                st.stop()

            table = find_standings(tables)
            if table is None:
                st.error("No se encontró una tabla de posiciones.")
                st.stop()

            table = add_position(table)
            st.session_state["table"] = table

        except requests.RequestException as exc:
            st.error(f"No fue posible conectar con FutbolGol: {exc}")
        except Exception as exc:
            st.error(f"No fue posible procesar la información: {exc}")


if "table" in st.session_state:
    table = st.session_state["table"]
    st.success(f"Tabla actualizada correctamente: {len(table)} equipos.")
    st.dataframe(table, use_container_width=True, hide_index=True)

    team_cols = [
        c for c in table.columns
        if "equipo" in str(c).lower()
        or "team" in str(c).lower()
        or "club" in str(c).lower()
    ]

    if team_cols:
        team_col = team_cols[0]
        selected = st.selectbox(
            "Selecciona tu equipo",
            ["— Seleccionar —"] + table[team_col].astype(str).tolist()
        )
        if selected != "— Seleccionar —":
            st.subheader(f"Análisis: {selected}")
            st.dataframe(
                table[table[team_col].astype(str) == selected],
                use_container_width=True,
                hide_index=True,
            )
else:
    st.info("Pulsa «Actualizar datos de FutbolGol» para consultar la tabla.")
