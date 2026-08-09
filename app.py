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


def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def clean_table(df):
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(str(x) for x in c if str(x) != "nan").strip()
            for c in df.columns
        ]
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df.dropna(how="all").reset_index(drop=True)


def get_standings():
    tables = pd.read_html(StringIO(get_html(BASE_URL)))
    best, score_best = None, -1
    for t in tables:
        t = clean_table(t)
        cols = " ".join(str(c).lower() for c in t.columns)
        score = sum(x in cols for x in
                    ["equipo", "pj", "pg", "pe", "pp", "gf", "gc", "pts"])
        if score > score_best:
            best, score_best = t, score
    if best is None:
        raise RuntimeError("No se encontró la tabla de posiciones.")
    return best


def find_candidate_links():
    html = get_html(BASE_URL)
    links = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    host = urlparse(BASE_URL).netloc
    keywords = (
        "galeria", "gallery", "jugadores", "jugador", "plantilla",
        "players", "player", "roster", "equipo", "team"
    )
    rows, seen = [], set()

    for href in links:
        url = urljoin(BASE_URL, href)
        if urlparse(url).netloc != host or url in seen:
            continue
        low = url.lower()
        matches = [k for k in keywords if k in low]
        if matches:
            seen.add(url)
            rows.append({"Enlace encontrado": url, "Tipo": matches[0]})

    return pd.DataFrame(rows)


def extract_visible_age_text(html):
    patterns = [
        r'(?i)\bedad\s*[:\-]?\s*(\d{1,2})',
        r'(?i)\b(\d{1,2})\s*años\b',
        r'(?i)\bage\s*[:\-]?\s*(\d{1,2})',
    ]
    ages = []
    for pattern in patterns:
        ages.extend(int(x) for x in re.findall(pattern, html))
    return sorted(set(a for a in ages if 16 <= a <= 80))


def inspect_links(df):
    results = []
    for _, row in df.iterrows():
        url = row["Enlace encontrado"]
        try:
            html = get_html(url)
            ages = extract_visible_age_text(html)
            title_match = re.search(
                r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S
            )
            title = (
                re.sub(r"<.*?>", "", title_match.group(1)).strip()
                if title_match else ""
            )
            results.append({
                "URL": url,
                "Título": title,
                "Edades visibles": ", ".join(map(str, ages)) if ages else "No visibles",
                "Cantidad edades": len(ages),
                "HTML recibido": "Sí",
            })
        except Exception as e:
            results.append({
                "URL": url,
                "Título": "",
                "Edades visibles": "Error",
                "Cantidad edades": 0,
                "HTML recibido": str(e),
            })
    return pd.DataFrame(results)


tab1, tab2 = st.tabs(["📊 Clasificación", "👥 Galería de jugadores"])

with tab1:
    st.subheader("📊 Clasificación")
    if st.button("🔄 Actualizar clasificación", type="primary"):
        try:
            st.session_state["standings"] = get_standings()
        except Exception as e:
            st.error(f"No fue posible leer la clasificación: {e}")

    if "standings" in st.session_state:
        st.dataframe(
            st.session_state["standings"],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Pulsa «Actualizar clasificación» para consultar FutbolGol.")


with tab2:
    st.subheader("👥 Análisis de galerías de jugadores")
    st.write(
        "Primero mostramos los enlaces reales que encuentra FutbolGol. "
        "Después identificaremos la fuente dinámica de las edades."
    )

    if st.button("🔎 Buscar galerías y mostrar enlaces", type="primary"):
        with st.spinner("Buscando enlaces de galerías en FutbolGol..."):
            try:
                candidates = find_candidate_links()
                st.session_state["candidate_links"] = candidates
                if candidates.empty:
                    st.warning(
                        "No se encontraron enlaces explícitos de galerías en el HTML."
                    )
                else:
                    st.success(
                        f"Se encontraron {len(candidates)} enlaces candidatos."
                    )
            except Exception as e:
                st.error(f"No fue posible buscar los enlaces: {e}")

    candidates = st.session_state.get("candidate_links", pd.DataFrame())

    if not candidates.empty:
        st.subheader("🔗 Enlaces encontrados por el Analyzer")
        st.dataframe(
            candidates,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Enlace encontrado": st.column_config.LinkColumn(
                    "Enlace encontrado"
                )
            },
        )

        if st.button("🧪 Inspeccionar edades visibles"):
            with st.spinner("Inspeccionando las páginas encontradas..."):
                st.session_state["inspection"] = inspect_links(candidates)

    inspection = st.session_state.get("inspection", pd.DataFrame())

    if not inspection.empty:
        st.subheader("🧪 Resultado de la inspección")
        st.dataframe(
            inspection,
            use_container_width=True,
            hide_index=True,
            column_config={"URL": st.column_config.LinkColumn("URL")},
        )

        if inspection["Edades visibles"].eq("No visibles").any():
            st.warning(
                "Las páginas responden, pero las edades no aparecen en el HTML "
                "inicial. Esto confirma que debemos localizar el contenido dinámico "
                "o la fuente de datos que FutbolGol utiliza para cargar las edades."
            )
        else:
            st.success(
                "Se encontraron edades directamente en las páginas."
            )
