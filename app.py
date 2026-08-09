import json
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
st.caption("Clasificación + análisis de galerías de jugadores")

TEAM_RE = re.compile(r"/equipo/([^/?#]+)/?", re.I)
AGE_RE = re.compile(
    r"(?i)(?:edad|age|años|years)[^0-9]{0,25}(\d{1,2})|"
    r"(\d{1,2})[^0-9]{0,5}(?:años|years)"
)

def get(url, timeout=30):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text, r.headers.get("content-type", "")

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
        score = sum(x in cols for x in
                    ["equipo", "pj", "pg", "pe", "pp", "gf", "gc", "pts"])
        if score > score_best:
            best, score_best = t, score
    if best is None:
        raise RuntimeError("No se encontró la tabla de posiciones.")
    return best

def team_links_from_superliga():
    html, _ = get(BASE_URL)
    links = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
    found = {}
    for href in links:
        u = urljoin(BASE_URL, href)
        m = TEAM_RE.search(urlparse(u).path)
        if m:
            slug = m.group(1).lower()
            found[slug] = u.rstrip("/") + "/"
    return found

def script_sources(html, page_url):
    out = []
    for src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I):
        out.append(urljoin(page_url, src))
    return list(dict.fromkeys(out))

def extract_json_like(text):
    blobs = []
    # Next.js / common embedded JSON
    for m in re.finditer(
        r'<script[^>]*(?:type=["\']application/json["\']|id=["\']__NEXT_DATA__["\'])[^>]*>(.*?)</script>',
        text, re.I | re.S
    ):
        blobs.append(m.group(1))
    # Common JS variables containing player/roster data
    for m in re.finditer(
        r'(?:players|jugadores|roster|plantilla|squad)[^=]{0,20}=\s*(\[[\s\S]{0,200000}?\])',
        text, re.I
    ):
        blobs.append(m.group(1))
    return blobs

def age_values(text):
    vals = []
    for m in AGE_RE.finditer(text):
        x = m.group(1) or m.group(2)
        if x:
            n = int(x)
            if 15 <= n <= 80:
                vals.append(n)
    return vals

def discover_dynamic_sources(team_url):
    html, _ = get(team_url)
    sources = []
    # APIs/JSON endpoints explicitly present in page or JS
    urls = re.findall(
        r'https?://[^"\'\s<>]+?(?:api|ajax|json|player|jugador|roster|plantilla)[^"\'\s<>]*',
        html, re.I
    )
    for u in urls:
        sources.append(u.rstrip("\\"))
    scripts = script_sources(html, team_url)
    script_texts = []
    for s in scripts[:40]:
        try:
            txt, _ = get(s, timeout=20)
            script_texts.append((s, txt))
            for u in re.findall(
                r'https?://[^"\'\s<>]+?(?:api|ajax|json|player|jugador|roster|plantilla)[^"\'\s<>]*',
                txt, re.I
            ):
                sources.append(u.rstrip("\\"))
        except Exception:
            pass

    # Relative endpoints such as /wp-json/, /api/, /ajax/
    for txt in [html] + [x[1] for x in script_texts]:
        for p in re.findall(
            r'["\']((?:/|\./)[^"\']*(?:wp-json|api|ajax|json|players|jugadores|roster|plantilla)[^"\']*)["\']',
            txt, re.I
        ):
            sources.append(urljoin(team_url, p))

    return list(dict.fromkeys(sources)), html, script_texts

def parse_player_records(obj):
    rows = []
    def walk(x):
        if isinstance(x, dict):
            keys = {str(k).lower(): k for k in x}
            name = None
            for k in ("nombre", "name", "jugador", "player", "full_name"):
                if k in keys and isinstance(x[keys[k]], str):
                    name = x[keys[k]].strip()
                    break
            age = None
            for k in ("edad", "age"):
                if k in keys:
                    try:
                        n = int(float(str(x[keys[k]]).strip()))
                        if 15 <= n <= 80:
                            age = n
                    except Exception:
                        pass
            if name and age is not None:
                rows.append((name, age))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(obj)
    return list(dict.fromkeys(rows))

def analyze_team(slug, url):
    sources, html, scripts = discover_dynamic_sources(url)
    records = []

    # Embedded JSON
    for blob in extract_json_like(html):
        try:
            obj = json.loads(blob)
            records.extend(parse_player_records(obj))
        except Exception:
            pass

    # JSON/API candidates
    for src in sources[:80]:
        try:
            r = requests.get(src, headers=HEADERS, timeout=15)
            if "json" in r.headers.get("content-type", "").lower() or r.text.lstrip().startswith(("{", "[")):
                try:
                    records.extend(parse_player_records(r.json()))
                except Exception:
                    pass
        except Exception:
            pass

    # Also inspect JS text for JSON-ish player objects
    for _, txt in scripts:
        for name, age in re.findall(
            r'(?i)(?:name|nombre)\s*["\']?\s*:\s*["\']([^"\']{2,80})["\'][^{}]{0,250}?'
            r'(?:age|edad)\s*["\']?\s*:\s*["\']?(\d{1,2})',
            txt
        ):
            n = int(age)
            if 15 <= n <= 80:
                records.append((name.strip(), n))

    records = list(dict.fromkeys(records))
    return records, sources

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
        "Esta versión intenta localizar automáticamente la fuente dinámica "
        "que FutbolGol usa para cargar jugadores y edades."
    )

    if st.button("🚀 Analizar galerías de todos los equipos", type="primary"):
        try:
            teams = team_links_from_superliga()
            st.info(f"Se identificaron {len(teams)} páginas únicas de equipos.")
            all_rows, diagnostics = [], []

            progress = st.progress(0)
            for i, (slug, url) in enumerate(teams.items(), start=1):
                try:
                    records, sources = analyze_team(slug, url)
                    diagnostics.append({
                        "Equipo": slug.replace("-", " ").title(),
                        "Jugadores con edad": len(records),
                        "Fuentes dinámicas encontradas": len(sources),
                        "URL": url,
                    })
                    for name, age in records:
                        all_rows.append({
                            "Equipo": slug.replace("-", " ").title(),
                            "Jugador": name,
                            "Edad": age,
                            "URL": url,
                        })
                except Exception as e:
                    diagnostics.append({
                        "Equipo": slug.replace("-", " ").title(),
                        "Jugadores con edad": 0,
                        "Fuentes dinámicas encontradas": 0,
                        "URL": url,
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
        st.success(f"Se encontraron {len(players)} registros jugador/edad.")
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
            st.metric("👶 Equipo más joven", f"{youngest['Equipo']} — {youngest['Edad_promedio']:.1f} años")
            st.metric("👴 Equipo más veterano", f"{oldest['Equipo']} — {oldest['Edad_promedio']:.1f} años")

        st.subheader("👤 Jugadores")
        st.dataframe(
            players.sort_values(["Equipo", "Edad", "Jugador"]),
            use_container_width=True,
            hide_index=True,
            column_config={"URL": st.column_config.LinkColumn("URL")},
        )

        csv = players.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Descargar jugadores y edades (CSV)",
            csv,
            "superliga_jugadores_edades.csv",
            "text/csv",
        )
    elif not diagnostics.empty:
        st.warning(
            "Las páginas de equipos responden, pero todavía no se recuperaron "
            "registros jugador/edad. Revisa el diagnóstico: allí veremos cuántas "
            "fuentes dinámicas expone cada equipo."
        )
