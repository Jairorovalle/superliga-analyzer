import re
from io import StringIO
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st

BASE_URL = "https://www.futbolgol.com/superliga/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                  "Mobile/15E148 Safari/604.1"
}

st.set_page_config(page_title="Superliga Analyzer", page_icon="⚽", layout="wide")
st.title("⚽ Superliga Analyzer")
st.caption("Tabla + análisis de galerías de jugadores")


def clean_table(df):
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(str(x) for x in col if str(x) != "nan").strip()
            for col in df.columns
        ]
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df.dropna(how="all").reset_index(drop=True)


def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def get_standings():
    tables = pd.read_html(StringIO(get_html(BASE_URL)))
    best, best_score = None, -1
    for t in tables:
        t = clean_table(t)
        cols = " ".join(str(c).lower() for c in t.columns)
        score = sum(x in cols for x in ["equipo", "pj", "pg", "pe", "pp", "gf", "gc", "pts"])
        if score > best_score:
            best, best_score = t, score
    if best is None:
        raise RuntimeError("No se encontró la tabla de posiciones.")
    return best


def find_gallery_links():
    html = get_html(BASE_URL)
    links = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    host = urlparse(BASE_URL).netloc
    keys = ("galeria", "gallery", "jugadores", "jugador", "plantilla",
            "players", "player", "equipo", "team", "roster")
    found = []
    for href in links:
        url = urljoin(BASE_URL, href)
        if urlparse(url).netloc == host and any(k in url.lower() for k in keys):
            if url not in found:
                found.append(url)
    return found


def parse_age(value):
    if pd.isna(value):
        return None
    m = re.search(r"\b(1[6-9]|[2-7][0-9]|80)\b", str(value))
    return int(m.group(1)) if m else None


def extract_players(table):
    table = clean_table(table)
    age_col = None
    name_col = None
    for col in table.columns:
        key = str(col).lower()
        if any(x in key for x in ["edad", "age", "años", "anos"]):
            age_col = col
        if any(x in key for x in ["jugador", "player", "nombre", "name"]):
            name_col = col
    if age_col is None:
        return pd.DataFrame()
    out = pd.DataFrame({"Edad": table[age_col].map(parse_age)})
    out["Jugador"] = table[name_col].astype(str) if name_col else ""
    return out.dropna(subset=["Edad"]).reset_index(drop=True)


def analyze_galleries():
    urls = find_gallery_links()
    records = []
    for url in urls[:100]:
        try:
            tables = pd.read_html(StringIO(get_html(url)))
            for table in tables:
                players = extract_players(table)
                if players.empty:
                    continue
                title = re.search(r"<title[^>]*>(.*?)</title>", get_html(url),
                                  flags=re.I | re.S)
                team = re.sub(r"<.*?>", "", title.group(1)).strip() if title else url
                players.insert(0, "Equipo", team)
                players["Fuente"] = url
                records.append(players)
        except Exception:
            continue
    return (pd.concat(records, ignore_index=True) if records else pd.DataFrame()), urls


tab1, tab2 = st.tabs(["📊 Clasificación", "👥 Galería de jugadores"])

with tab1:
    if st.button("🔄 Actualizar clasificación", type="primary"):
        try:
            st.session_state["standings"] = get_standings()
        except Exception as e:
            st.error(f"No fue posible leer la clasificación: {e}")
    if "standings" in st.session_state:
        st.dataframe(st.session_state["standings"], use_container_width=True, hide_index=True)
    else:
        st.info("Pulsa «Actualizar clasificación».")

with tab2:
    st.subheader("👥 Análisis de galerías")
    st.write("Busca páginas de jugadores/plantillas y calcula edades cuando FutbolGol las publica.")
    if st.button("🔎 Buscar galerías de jugadores", type="primary"):
        with st.spinner("Buscando galerías en FutbolGol..."):
            try:
                players, urls = analyze_galleries()
                st.session_state["players"] = players
                st.session_state["gallery_urls"] = urls
            except Exception as e:
                st.error(f"No fue posible analizar las galerías: {e}")

    players = st.session_state.get("players", pd.DataFrame())

    if not players.empty:
        summary = players.groupby("Equipo", dropna=False).agg(
            Jugadores=("Edad", "count"),
            Edad_promedio=("Edad", "mean"),
            Edad_mediana=("Edad", "median"),
            Edad_mínima=("Edad", "min"),
            Edad_máxima=("Edad", "max"),
        ).reset_index()
        summary["Edad_promedio"] = summary["Edad_promedio"].round(1)
        summary["Edad_mediana"] = summary["Edad_mediana"].round(1)
        summary = summary.sort_values("Edad_promedio").reset_index(drop=True)
        summary.insert(0, "Ranking joven", range(1, len(summary) + 1))

        st.subheader("🏆 Ranking por edad")
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.subheader("👤 Jugadores encontrados")
        st.dataframe(players, use_container_width=True, hide_index=True)

        nes = players[players["Equipo"].astype(str).str.contains("NES FC", case=False, na=False)]
        if not nes.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Jugadores NES FC", len(nes))
            c2.metric("Edad promedio NES FC", f"{nes['Edad'].mean():.1f}")
            c3.metric("Promedio muestra", f"{players['Edad'].mean():.1f}")
    else:
        st.info("Pulsa «Buscar galerías de jugadores».")
        if st.session_state.get("gallery_urls"):
            st.warning("Se encontraron enlaces, pero FutbolGol puede cargar las edades dinámicamente.")
