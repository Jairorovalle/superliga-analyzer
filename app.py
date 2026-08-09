import re
import time
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE = "https://www.futbolgol.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"}
session = requests.Session()
session.headers.update(HEADERS)

TEAM_SLUGS = [
    "anglo-americano","anglo-colombiano","colombo-britanico","frances-azul",
    "gimnasio-el-hontanar","la-montana","liceo-de-colombia-verde","montessori",
    "nes-fc","nueva-granada","pureza-de-maria","rochester","san-viator",
    "san-bartolo-1941","vermont-a"
]

def soup(url):
    r = session.get(url, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def clean(x):
    return re.sub(r"\s+", " ", x or "").strip()

def team_name(url):
    try:
        s = soup(url)
        h = s.find("h1")
        if h: return clean(h.get_text(" ", strip=True))
        t = s.find("title")
        if t: return clean(t.get_text(" ", strip=True)).replace(" - FutbolGol", "")
    except Exception:
        pass
    return url.rstrip("/").split("/")[-1].replace("-", " ").title()

def candidate_player_url(url, base):
    u = urljoin(base, url).rstrip("/") + "/"
    p = urlparse(u).path.lower()
    if "futbolgol.com" not in u or "/equipo/" in p:
        return None
    if any(x in p for x in ["/superliga/", "/torneo/", "/contact"]):
        return None
    return u

def player_links(team_url):
    s = soup(team_url)
    links = []

    # Primero busca enlaces claramente asociados a jugadores.
    for a in s.find_all("a", href=True):
        u = candidate_player_url(a["href"], team_url)
        if not u: continue
        txt = clean(a.get_text(" ", strip=True)).lower()
        if ("/jugador/" in u.lower() or "/player/" in u.lower()
            or "/futbolista/" in u.lower()
            or any(k in txt for k in ["jugador", "perfil", "plantilla"])):
            if u not in links: links.append(u)

    # Segundo intento: tarjetas de jugadores con foto/nombre.
    if not links:
        for a in s.find_all("a", href=True):
            u = candidate_player_url(a["href"], team_url)
            if not u: continue
            img = a.find("img")
            txt = clean(a.get_text(" ", strip=True))
            alt = clean(img.get("alt", "")) if img else ""
            if len((txt + " " + alt).split()) >= 2 and u not in links:
                links.append(u)

    return links

def age_from_text(text):
    text = clean(text)

    # Caso comprobado en FutbolGol: "Edad 43"
    for pattern in [
        r"\bEdad\b\s*:?\s*(\d{1,2})\b",
        r'"(?:edad|age)"\s*:\s*(\d{1,2})'
    ]:
        m = re.search(pattern, text, re.I)
        if m:
            age = int(m.group(1))
            if 15 <= age <= 80:
                return age

    # Fallback: "Cumpleaños 4 agosto, 1983"
    months = {
        "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
        "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,
        "diciembre":12
    }
    m = re.search(
        r"(?:Cumpleaños|Fecha de nacimiento|Nacimiento)\s*:?\s*"
        r"(\d{1,2})\s+([A-Za-zÁÉÍÓÚÑáéíóúñ]+)[,\s]+(\d{4})", text, re.I
    )
    if m and m.group(2).lower() in months:
        day, month, year = int(m.group(1)), months[m.group(2).lower()], int(m.group(3))
        now = time.localtime()
        age = now.tm_year - year - ((now.tm_mon, now.tm_mday) < (month, day))
        if 15 <= age <= 80:
            return age
    return None

def parse_player(url, team):
    try:
        s = soup(url)
    except Exception:
        return None

    text = clean(s.get_text(" ", strip=True))
    age = age_from_text(text)

    # Evita tratar páginas de navegación como jugadores.
    if age is None and not re.search(r"\b(?:Nombre|Posición|Cumpleaños|Edad)\b", text, re.I):
        return None

    h1 = s.find("h1")
    name = clean(h1.get_text(" ", strip=True)) if h1 else url.rstrip("/").split("/")[-1].replace("-", " ").title()
    return {"Equipo": team, "Jugador": name, "Edad": age, "URL jugador": url}

@st.cache_data(ttl=1800, show_spinner=False)
def scan():
    rows, diag = [], []

    for slug in TEAM_SLUGS:
        team_url = f"{BASE}/equipo/{slug}/"
        try:
            team = team_name(team_url)
            links = player_links(team_url)
            valid = ages = 0

            for url in links:
                rec = parse_player(url, team)
                if rec:
                    valid += 1
                    ages += int(rec["Edad"] is not None)
                    rows.append(rec)

            diag.append({
                "Equipo": team,
                "Enlaces jugadores": len(links),
                "Fichas válidas": valid,
                "Con edad": ages,
                "URL equipo": team_url
            })
        except Exception as e:
            diag.append({
                "Equipo": slug, "Enlaces jugadores": 0,
                "Fichas válidas": 0, "Con edad": 0,
                "URL equipo": team_url, "Error": str(e)
            })

    players = pd.DataFrame(rows)
    if not players.empty:
        players = players.drop_duplicates(["Equipo", "Jugador", "URL jugador"])
    return players, pd.DataFrame(diag)

def team_stats(players):
    if players.empty:
        return pd.DataFrame()

    x = players.dropna(subset=["Edad"]).copy()
    if x.empty:
        return pd.DataFrame()

    out = x.groupby("Equipo").agg(
        Jugadores=("Edad", "count"),
        Edad_promedio=("Edad", "mean"),
        Edad_mediana=("Edad", "median"),
        Mas_joven=("Edad", "min"),
        Mas_veterano=("Edad", "max")
    ).reset_index()

    out[["Edad_promedio", "Edad_mediana"]] = out[["Edad_promedio", "Edad_mediana"]].round(1)
    return out.sort_values(["Edad_promedio", "Equipo"]).reset_index(drop=True)

st.set_page_config(page_title="Superliga Analyzer", page_icon="⚽", layout="wide")
st.title("⚽ Superliga Analyzer")
st.caption("Análisis de galerías y edades de FutbolGol")

if st.button("🔄 Actualizar datos de FutbolGol", type="primary"):
    st.cache_data.clear()
    st.rerun()

players, diagnostic = scan()

tab1, tab2, tab3 = st.tabs(["📊 Edad por equipo", "👥 Jugadores", "🔎 Diagnóstico"])

with tab1:
    s = team_stats(players)
    if s.empty:
        st.error("Todavía no se recuperaron edades de las fichas individuales.")
        st.info("Revisa Diagnóstico.")
    else:
        st.success(f"Se recuperaron {len(players)} fichas de jugadores.")
        st.dataframe(s, use_container_width=True, hide_index=True)

        nes = s[s["Equipo"].str.contains("NES", case=False, na=False)]
        if not nes.empty:
            st.subheader("🟢 NES FC")
            st.dataframe(nes, use_container_width=True, hide_index=True)

with tab2:
    if players.empty:
        st.warning("No se encontraron fichas individuales.")
    else:
        selected = st.selectbox("Equipo", ["Todos"] + sorted(players["Equipo"].unique()))
        view = players if selected == "Todos" else players[players["Equipo"] == selected]
        st.dataframe(
            view, use_container_width=True, hide_index=True,
            column_config={"URL jugador": st.column_config.LinkColumn("Ficha FutbolGol")}
        )
        st.download_button(
            "⬇️ Descargar jugadores CSV",
            view.to_csv(index=False).encode("utf-8-sig"),
            "superliga_jugadores.csv", "text/csv"
        )

with tab3:
    st.dataframe(diagnostic, use_container_width=True, hide_index=True)
    st.metric("Jugadores con edad", int(diagnostic["Con edad"].sum()))
    st.info("La extracción entra a la ficha individual y busca primero el campo Edad; si no aparece, calcula la edad desde Cumpleaños.")
