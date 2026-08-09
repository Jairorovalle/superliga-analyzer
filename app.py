import re
from io import StringIO
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser

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
st.caption("Clasificación + análisis de galerías de jugadores")

TEAM_RE = re.compile(r"/equipo/([^/?#]+)/?", re.I)
PLAYER_RE = re.compile(r"/(?:jugador|player|jugadores|players)/([^/?#]+)/?", re.I)
AGE_RE = re.compile(r"(?i)(?:edad|age)\s*[:\-]?\s*(\d{1,2})\b")

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.href = None
        self.anchor = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.anchor = []

    def handle_data(self, data):
        self.parts.append(data)
        if self.href is not None:
            self.anchor.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href is not None:
            self.links.append((self.href, " ".join(self.anchor).strip()))
            self.href = None
            self.anchor = []

def get(url, timeout=30):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text, r.headers.get("content-type", "")

def html_text(html):
    p = TextExtractor()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()

def page_links(html, page_url):
    p = TextExtractor()
    p.feed(html)
    return [(urljoin(page_url, h), t) for h, t in p.links if h]

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
    html, _ = get(BASE_URL)
    tables = pd.read_html(StringIO(html))
    best, score_best = None, -1
    for t in tables:
        t = clean_table(t)
        cols = " ".join(str(c).lower() for c in t.columns)
        score = sum(x in cols for x in ["equipo","pj","pg","pe","pp","gf","gc","pts"])
        if score > score_best:
            best, score_best = t, score
    if best is None:
        raise RuntimeError("No se encontró la tabla de posiciones.")
    return best

def team_links_from_superliga():
    html, _ = get(BASE_URL)
    found = {}
    for href, _ in page_links(html, BASE_URL):
        m = TEAM_RE.search(urlparse(href).path)
        if m:
            slug = m.group(1).lower()
            found[slug] = href.rstrip("/") + "/"
    return found

def find_player_links(team_url, team_html):
    found = {}
    for href, anchor in page_links(team_html, team_url):
        if PLAYER_RE.search(urlparse(href).path):
            found[href.rstrip("/") + "/"] = anchor.strip()
    # Also catch absolute links embedded in HTML/script blocks.
    for href in re.findall(r'https?://[^"\'\s<>]+futbolgol\.com[^"\'\s<>]+', team_html, re.I):
        if PLAYER_RE.search(urlparse(href).path):
            found[href.rstrip("/") + "/"] = found.get(href.rstrip("/") + "/", "")
    return found

def extract_player_record(player_url, fallback_name=""):
    html, _ = get(player_url, timeout=25)
    text = html_text(html)

    age = None
    m = AGE_RE.search(text)
    if m:
        n = int(m.group(1))
        if 15 <= n <= 80:
            age = n

    if age is None:
        for pat in [
            r'(?i)["\'](?:edad|age)["\']\s*[:=]\s*["\']?(\d{1,2})',
            r'(?i)\b(?:edad|age)\b[^0-9]{0,40}(\d{1,2})\b',
        ]:
            m = re.search(pat, html)
            if m:
                n = int(m.group(1))
                if 15 <= n <= 80:
                    age = n
                    break

    name = fallback_name.strip()
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if h1:
        candidate = re.sub(r"<[^>]+>", " ", h1.group(1))
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if 2 <= len(candidate) <= 100:
            name = candidate

    if not name:
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if title:
            name = re.sub(r"<[^>]+>", " ", title.group(1))
            name = re.sub(r"\s*[-|]\s*FutbolGol.*$", "", name, flags=re.I).strip()

    return {
        "Jugador": name or player_url.rstrip("/").split("/")[-1].replace("-", " ").title(),
        "Edad": age,
        "URL jugador": player_url,
    }

def analyze_team(slug, team_url):
    team_html, _ = get(team_url)
    player_links = find_player_links(team_url, team_html)
    records, errors = [], 0

    for player_url, anchor in player_links.items():
        try:
            rec = extract_player_record(player_url, anchor)
            if rec["Edad"] is not None:
                records.append(rec)
            else:
                errors += 1
        except Exception:
            errors += 1

    return records, len(player_links), errors


# ---------------- UI ----------------
tab1, tab2 = st.tabs(["📊 Clasificación", "👥 Galería de jugadores"])

with tab1:
    st.subheader("📊 Clasificación")
    if st.button("🔄 Actualizar clasificación", type="primary"):
        try:
            st.session_state["standings"] = get_standings()
        except Exception as e:
            st.error(f"No fue posible leer la clasificación: {e}")
    if "standings" in st.session_state:
        st.dataframe(st.session_state["standings"], use_container_width=True, hide_index=True)
    else:
        st.info("Pulsa «Actualizar clasificación» para consultar FutbolGol.")

with tab2:
    st.subheader("👥 Análisis de galerías")
    st.write(
        "La app ahora entra en las fichas individuales de los jugadores. "
        "FutbolGol muestra allí la edad, aunque no esté en el HTML inicial de la página del equipo."
    )

    if st.button("🚀 Analizar galerías de todos los equipos", type="primary"):
        try:
            teams = team_links_from_superliga()
            st.info(f"Se identificaron {len(teams)} páginas de equipos. Ahora se revisarán sus jugadores.")
            all_rows, diagnostics = [], []
            progress = st.progress(0)

            for i, (slug, url) in enumerate(teams.items(), start=1):
                team_name = slug.replace("-", " ").title()
                try:
                    records, player_links, errors = analyze_team(slug, url)
                    diagnostics.append({
                        "Equipo": team_name,
                        "Jugadores encontrados": player_links,
                        "Jugadores con edad": len(records),
                        "Sin edad / error": errors,
                        "URL": url,
                    })
                    for rec in records:
                        all_rows.append({"Equipo": team_name, **rec})
                except Exception as e:
                    diagnostics.append({
                        "Equipo": team_name,
                        "Jugadores encontrados": 0,
                        "Jugadores con edad": 0,
                        "Sin edad / error": 0,
                        "URL": url,
                        "Error": str(e),
                    })
                progress.progress(i / max(len(teams), 1))

            st.session_state["players"] = pd.DataFrame(all_rows)
            st.session_state["diagnostics"] = pd.DataFrame(diagnostics)
        except Exception as e:
            st.error(f"No fue posible iniciar el análisis: {e}")

    players = st.session_state.get("players", pd.DataFrame())
    diagnostics = st.session_state.get("diagnostics", pd.DataFrame())

    if not diagnostics.empty:
        st.subheader("🔎 Diagnóstico por equipo")
        st.dataframe(
            diagnostics,
            use_container_width=True,
            hide_index=True,
            column_config={"URL": st.column_config.LinkColumn("URL")},
        )

    if not players.empty:
        st.success(f"Se recuperaron {len(players)} jugadores con edad.")
        st.subheader("🏆 Comparación de edades por equipo")

        summary = (
            players.groupby("Equipo")
            .agg(
                Jugadores=("Jugador", "count"),
                Edad_promedio=("Edad", "mean"),
                Edad_min=("Edad", "min"),
                Edad_max=("Edad", "max"),
            )
            .reset_index()
            .sort_values("Edad_promedio")
        )
        summary["Edad_promedio"] = summary["Edad_promedio"].round(1)

        st.dataframe(summary, use_container_width=True, hide_index=True)

        if len(summary):
            youngest = summary.iloc[0]
            oldest = summary.iloc[-1]
            c1, c2 = st.columns(2)
            with c1:
                st.metric("👶 Equipo más joven", f"{youngest['Equipo']} — {youngest['Edad_promedio']:.1f} años")
            with c2:
                st.metric("👴 Equipo más veterano", f"{oldest['Equipo']} — {oldest['Edad_promedio']:.1f} años")

        st.subheader("👤 Jugadores")
        st.dataframe(
            players.sort_values(["Equipo", "Edad", "Jugador"]),
            use_container_width=True,
            hide_index=True,
            column_config={"URL jugador": st.column_config.LinkColumn("Ficha del jugador")},
        )

        st.download_button(
            "⬇️ Descargar jugadores y edades (CSV)",
            players.to_csv(index=False).encode("utf-8-sig"),
            "superliga_jugadores_edades.csv",
            "text/csv",
        )
    elif not diagnostics.empty:
        st.warning(
            "Se encontraron páginas de equipos, pero no jugadores con edad. "
            "Revisa «Jugadores encontrados» para ver si FutbolGol está exponiendo las fichas."
        )
