"""
Dashboard IA - Scoring Lead HubSpot
Interface de pilotage commercial.
"""
import os
import sys
import json
import gzip
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "scored_contacts.json.gz")
DATA_PATH_RAW = os.path.join(os.path.dirname(__file__), "..", "data", "scored_contacts.json")
PORTAL = "27215892"

MOIS_FR = {1:"jan.", 2:"fev.", 3:"mars", 4:"avr.", 5:"mai", 6:"juin",
           7:"juil.", 8:"aout", 9:"sept.", 10:"oct.", 11:"nov.", 12:"dec."}

# --- STYLE ---
st.set_page_config(
    page_title="Scoring IA - Max Piccinini",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    /* Header */
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .main-header h1 {
        color: white;
        font-size: 2rem;
        margin: 0;
        font-weight: 700;
    }
    .main-header p {
        color: #94a3b8;
        margin: 0.3rem 0 0 0;
        font-size: 0.9rem;
    }

    /* KPI cards */
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    div[data-testid="stMetric"] label {
        color: #64748b;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 800;
        color: #1e293b;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background: #f8fafc;
        border-radius: 12px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 0.6rem 1rem;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .stTabs [aria-selected="true"] {
        background: white;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }

    /* Dataframe */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
    }

    /* Tab description */
    .tab-desc {
        background: #f0f9ff;
        border-left: 4px solid #3b82f6;
        padding: 0.8rem 1rem;
        border-radius: 0 8px 8px 0;
        margin-bottom: 1rem;
        font-size: 0.9rem;
        color: #1e40af;
    }
    .tab-desc-warm {
        background: #fff7ed;
        border-left-color: #f97316;
        color: #9a3412;
    }
    .tab-desc-recycle {
        background: #f0fdf4;
        border-left-color: #22c55e;
        color: #166534;
    }
    .tab-desc-alert {
        background: #fef2f2;
        border-left-color: #ef4444;
        color: #991b1b;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #1e293b;
    }
    section[data-testid="stSidebar"] .stMarkdown {
        color: #e2e8f0;
    }
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: white;
        font-size: 1rem;
        margin-top: 1rem;
    }
    section[data-testid="stSidebar"] .stMarkdown strong {
        color: #60a5fa;
    }

    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Divider */
    hr {
        border-color: #e2e8f0;
        margin: 1.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


def format_date_fr(date_str):
    """Convertit 2026-04-03 en 03 avr. 2026"""
    if not date_str or date_str == "-" or len(str(date_str)) < 10:
        return "-"
    try:
        s = str(date_str)[:10]
        parts = s.split("-")
        if len(parts) == 3:
            jour = parts[2]
            mois = MOIS_FR.get(int(parts[1]), parts[1])
            annee = parts[0]
            return f"{jour} {mois} {annee}"
    except (ValueError, IndexError):
        pass
    return str(date_str)[:10]


@st.cache_data(ttl=14400)
def load_data():
    for path, opener in [(DATA_PATH, lambda p: gzip.open(p, "rt", encoding="utf-8")),
                         (DATA_PATH_RAW, lambda p: open(p, "r", encoding="utf-8"))]:
        if os.path.exists(path):
            with opener(path) as f:
                data = json.load(f)
            return pd.DataFrame(data["contacts"]), data
    return None, None


def hubspot_url(contact_id):
    return f"https://app.hubspot.com/contacts/{PORTAL}/record/0-1/{contact_id}"


def render_table(df_subset):
    """Tableau avec lien fiche contact integre dans chaque ligne."""
    if len(df_subset) == 0:
        st.caption("Aucun contact dans cette liste.")
        return

    # Compteur
    st.caption(f"{len(df_subset)} contact(s)")

    display = df_subset.copy()
    display["CA"] = display["ca"].apply(
        lambda x: "10M+" if "10M" in str(x) else "1M-10M" if "1M" in str(x) else str(x)[:10]
    )
    display["Dernier contact"] = display["dernier_contact"].apply(format_date_fr)
    display["Date RDV"] = display["calendly_date"].apply(format_date_fr)
    display["Fiche contact"] = display["id"].apply(
        lambda x: hubspot_url(x) if x else ""
    )

    cols_map = {
        "score": "Score",
        "prenom": "Prenom",
        "nom": "Nom",
        "CA": "CA",
        "lead_status": "Statut",
        "calendly_event": "Type de RDV",
        "Date RDV": "Date RDV",
        "nb_events": "Ev.",
        "nb_leadmagnets": "Guides",
        "Dernier contact": "Dernier contact",
        "details": "Criteres",
    }

    df_show = display[[c for c in cols_map if c in display.columns]].copy()
    df_show.columns = [cols_map[c] for c in df_show.columns]
    df_show["Fiche contact"] = display["Fiche contact"]

    st.dataframe(
        df_show,
        use_container_width=True,
        height=min(600, len(df_show) * 38 + 50),
        column_config={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d", width="small"),
            "Ev.": st.column_config.NumberColumn("Ev.", width="small"),
            "Guides": st.column_config.NumberColumn("Guides", width="small"),
            "Fiche contact": st.column_config.LinkColumn("Fiche contact", display_text="Ouvrir ↗", width="small"),
        },
        hide_index=True,
    )


def main():
    # --- HEADER ---
    st.markdown("""
    <div class="main-header">
        <h1>🎯 Scoring IA - Max Piccinini</h1>
        <p>Dashboard de pilotage commercial | Donnees synchronisees avec HubSpot toutes les 4h</p>
    </div>
    """, unsafe_allow_html=True)

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown("### Comment lire ce dashboard")
        st.markdown("""
**Lead A** (score 60+)
Les prospects les plus chauds : CA 1M+, avances dans le funnel (RDV, candidature), engagement email recent.

**Lead B** (score 40-59)
Bons profils avec plusieurs signaux positifs : events, guides telecharges, emails ouverts.

**Lead C** (score 25-39)
Prospects tides : CA 1M+ avec au moins un signal d'interet. Ideaux pour du nurturing ou une invitation a un event.

**A relancer**
Contacts en suivi commercial mais sans activite depuis 30 a 90 jours. Le commercial a oublie de relancer.

**Recyclage**
Oublies depuis plus de 3 mois. Les recontacter comme des prospects neufs.

**Candidatures sans RDV**
Ont candidat mais n'ont pas pris de creneau Calendly.
        """)
        st.divider()
        st.markdown("### Fonctionnement")
        st.caption("Les scores se mettent a jour automatiquement toutes les 4 heures.")
        st.caption("Quand un commercial met a jour le statut d'un contact dans HubSpot, le contact sort automatiquement de ces listes.")
        st.divider()
        st.markdown(f"[Listes HubSpot](https://app.hubspot.com/contacts/{PORTAL}/lists)")
        st.divider()
        if st.button("🔄 Rafraichir", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # --- DATA ---
    df, raw_data = load_data()
    if df is None or len(df) == 0:
        st.info("En attente des donnees. Le premier scoring est en cours.")
        return

    updated_at_raw = raw_data.get("updated_at", "")
    stats = raw_data.get("stats", {})

    # Convertir UTC -> heure de Paris (UTC+1 hiver, UTC+2 ete)
    try:
        dt_utc = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
        # Paris = UTC+2 en ete (avril-octobre), UTC+1 en hiver
        month = dt_utc.month
        offset = 2 if 4 <= month <= 10 else 1
        dt_paris = dt_utc + timedelta(hours=offset)
        updated_at_display = f"{format_date_fr(dt_paris.strftime('%Y-%m-%d'))} a {dt_paris.strftime('%Hh%M')}"
    except Exception:
        updated_at_display = updated_at_raw[:16]

    # --- KPIs ---
    lead_c_count = len(df[(df["classe"] == "C") & (df["statut"] == "a_appeler")])

    cols = st.columns(5)
    kpi_data = [
        ("Lead A", stats.get("lead_a", 0)),
        ("Lead B", stats.get("lead_b", 0)),
        ("Lead C", lead_c_count),
        ("A relancer", stats.get("a_relancer", 0)),
        ("Recyclage", stats.get("recyclage", 0)),
    ]
    for col, (label, value) in zip(cols, kpi_data):
        col.metric(label, f"{value:,}".replace(",", " "))

    st.caption(f"Mise a jour : {updated_at_display} (heure de Paris)")

    # --- ONGLETS ---
    # Calculer le nombre de "sans suite apres RDV"
    sans_suite = df[
        (df["calendly_event"].notna()) & (df["calendly_event"] != "") &
        (df["lead_status"].isin(["NEW", "ATTEMPTED_TO_CONTACT", "BAD_TIMING", ""])) &
        (df["statut"].isin(["a_appeler", "a_relancer", "recyclage"]))
    ]
    sans_suite_count = len(sans_suite)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        f"🔥 Lead A",
        f"📞 Lead B",
        f"💡 Lead C",
        f"⚠️ A relancer",
        f"♻️ Recyclage",
        f"🎯 Sans suite apres RDV ({sans_suite_count})",
    ])

    with tab1:
        st.markdown('<div class="tab-desc">Appeler aujourd\'hui -- les prospects les plus chauds. Score 60+ : avances dans le funnel, engagement fort, taux de conversion le plus eleve.</div>', unsafe_allow_html=True)
        leads_a = df[(df["classe"] == "A") & (df["statut"] == "a_appeler")]
        render_table(leads_a.sort_values("score", ascending=False))

    with tab2:
        st.markdown('<div class="tab-desc">Appeler cette semaine -- bons profils avec plusieurs signaux positifs. Score 40-59 : engagement email, guides telecharges, events suivis.</div>', unsafe_allow_html=True)
        leads_b = df[(df["classe"] == "B") & (df["statut"] == "a_appeler")]
        render_table(leads_b.sort_values("score", ascending=False))

    with tab3:
        st.markdown('<div class="tab-desc-warm tab-desc">Prospects a rechauffer. Score 25-39 : au moins un signal d\'interet. Ideaux pour une invitation Masterclass, Challenge, ou sequence email dediee.</div>', unsafe_allow_html=True)
        leads_c = df[(df["classe"] == "C") & (df["statut"] == "a_appeler")]
        render_table(leads_c.sort_values("score", ascending=False).head(500))

    with tab4:
        st.markdown('<div class="tab-desc-alert tab-desc">En suivi commercial mais sans activite depuis 30 a 90 jours. Le commercial a oublie de relancer -- reprendre le fil de la conversation.</div>', unsafe_allow_html=True)
        a_relancer = df[df["statut"] == "a_relancer"]
        render_table(a_relancer.sort_values("score", ascending=False))

    with tab5:
        st.markdown('<div class="tab-desc-recycle tab-desc">Oublies depuis plus de 3 mois. La relation commerciale est morte. Les recontacter comme des prospects neufs -- le score tient compte de leur engagement recent.</div>', unsafe_allow_html=True)
        recyclage = df[df["statut"] == "recyclage"]
        render_table(recyclage.sort_values("score", ascending=False))

    with tab6:
        st.markdown('<div class="tab-desc-alert tab-desc">Contacts qui ont pris un RDV Calendly (Diagnostic, Session Strategique, Plan d\'action 3M) mais dont le statut n\'a jamais progresse. Ils sont restes en "Tentative de contact", "Mauvais timing" ou "NEW". Angle d\'attaque : "on s\'etait parle le [date], je reviens vers vous..."</div>', unsafe_allow_html=True)
        render_table(sans_suite.sort_values("score", ascending=False))

    # --- HISTORIQUE ---
    history_path = os.path.join(os.path.dirname(__file__), "..", "data", "scoring_history.json")
    if os.path.exists(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)

        if len(history) > 1:
            st.divider()
            st.markdown("### Progression")
            st.caption("Evolution des volumes a chaque mise a jour.")

            hist_df = pd.DataFrame(history)
            hist_df["date_fr"] = hist_df["date"].apply(
                lambda x: format_date_fr(str(x)[:10]) + " " + str(x)[11:16] if x else "-"
            )

            display_hist = hist_df[["date_fr", "lead_a", "lead_b", "lead_c", "a_relancer", "recyclage"]].copy()
            display_hist.columns = ["Date", "Lead A", "Lead B", "Lead C", "A relancer", "Recyclage"]

            st.dataframe(
                display_hist.iloc[::-1],
                use_container_width=True,
                height=min(250, len(display_hist) * 38 + 40),
                hide_index=True,
            )

    # --- FOOTER ---
    st.divider()
    total = raw_data.get('total', 0)
    st.caption(f"Base : {total:,} contacts scores | Scoring IA v2 | AUC 0.94".replace(",", " "))


if __name__ == "__main__":
    main()
