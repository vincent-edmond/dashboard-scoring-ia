"""
Dashboard IA - Scoring Lead HubSpot
Interface de pilotage pour Vincent, Alex et Max.
"""
import os
import sys
import json
import gzip
import streamlit as st
import pandas as pd
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "scored_contacts.json.gz")
DATA_PATH_RAW = os.path.join(os.path.dirname(__file__), "..", "data", "scored_contacts.json")
INSIGHTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "insights.json")

PORTAL = "27215892"

st.set_page_config(
    page_title="Scoring IA - Max Piccinini",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_data(ttl=14400)
def load_data():
    """Charge les donnees depuis le fichier gzip ou json."""
    for path, opener in [(DATA_PATH, lambda p: gzip.open(p, "rt", encoding="utf-8")),
                         (DATA_PATH_RAW, lambda p: open(p, "r", encoding="utf-8"))]:
        if os.path.exists(path):
            with opener(path) as f:
                data = json.load(f)
            df = pd.DataFrame(data["contacts"])
            return df, data
    return None, None


@st.cache_data(ttl=14400)
def load_insights():
    if not os.path.exists(INSIGHTS_PATH):
        return None
    with open(INSIGHTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def hubspot_url(contact_id):
    return f"https://app.hubspot.com/contacts/{PORTAL}/record/0-1/{contact_id}"


def render_contact_table(df_subset, key_prefix=""):
    """Tableau de contacts avec lien HubSpot integre dans chaque ligne."""
    if len(df_subset) == 0:
        st.caption("Aucun contact")
        return

    # Preparer les donnees
    display = df_subset.copy()

    # Formater les colonnes
    display["CA"] = display["ca"].apply(
        lambda x: "10M+" if "10M" in str(x) else "1M-10M" if "1M" in str(x) else str(x)[:10]
    )
    display["Proba"] = display["proba_conversion"].apply(
        lambda x: f"{x:.0f}%" if pd.notna(x) and x > 0 else "-"
    )
    display["Dernier contact"] = display["dernier_contact"].apply(
        lambda x: str(x)[:10] if x else "-"
    )
    display["Date RDV"] = display["calendly_date"].apply(
        lambda x: str(x)[:10] if x else "-"
    )
    display["HubSpot"] = display["id"].apply(
        lambda x: hubspot_url(x) if x else ""
    )

    # Colonnes a afficher
    cols = {
        "score": "Score",
        "Proba": "Proba",
        "prenom": "Prenom",
        "nom": "Nom",
        "CA": "CA",
        "lead_status": "Statut commercial",
        "calendly_event": "Type de RDV",
        "Date RDV": "Date RDV",
        "nb_events": "Ev.",
        "nb_leadmagnets": "Guides",
        "Dernier contact": "Dernier contact",
        "details": "Criteres principaux",
    }

    df_show = display[[c for c in cols.keys() if c in display.columns]].copy()
    df_show.columns = [cols[c] for c in df_show.columns]

    # Config des colonnes
    column_config = {
        "Score": st.column_config.NumberColumn("Score", width="small"),
        "Proba": st.column_config.TextColumn("Proba", width="small"),
        "Ev.": st.column_config.NumberColumn("Ev.", width="small", help="Nombre d'evenements suivis"),
        "Guides": st.column_config.NumberColumn("Guides", width="small", help="Nombre de guides telecharges"),
    }

    # Colonne lien direct vers la fiche HubSpot
    df_show["Fiche contact"] = display["HubSpot"]
    column_config["Fiche contact"] = st.column_config.LinkColumn(
        "Fiche contact",
        display_text="Ouvrir ↗",
        width="small",
    )

    st.dataframe(
        df_show,
        use_container_width=True,
        height=min(500, len(df_show) * 38 + 40),
        column_config=column_config,
        hide_index=True,
    )


def main():
    st.title("🎯 Scoring IA - Max Piccinini")

    # Sidebar
    with st.sidebar:
        st.markdown("### HubSpot")
        st.markdown(f"[Voir tous les contacts](https://app.hubspot.com/contacts/{PORTAL}/objects/0-1/views/all/list)")
        st.divider()
        st.caption("Le scoring se met a jour automatiquement toutes les 4h.")
        if st.button("🔄 Rafraichir l'affichage"):
            st.cache_data.clear()
            st.rerun()

    # Charger
    df, raw_data = load_data()
    if df is None or len(df) == 0:
        st.info("En attente des donnees. Le scoring tourne automatiquement toutes les 4h.")
        return

    updated_at = raw_data.get("updated_at", "")
    stats = raw_data.get("stats", {})

    st.caption(f"Derniere mise a jour : {updated_at[:16].replace('T', ' ')} UTC")

    # --- KPIs ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Lead A - Priorite absolue", stats.get("lead_a", 0))
    col2.metric("Lead B - A appeler", stats.get("lead_b", 0))
    col3.metric("A relancer (oublies)", stats.get("a_relancer", 0))
    col4.metric("Recyclage (> 90j)", stats.get("recyclage", 0))

    st.divider()

    # --- ONGLETS ---
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        f"🔥 Lead A ({stats.get('lead_a', 0)})",
        f"📞 Lead B ({stats.get('lead_b', 0)})",
        f"⚠️ A relancer ({stats.get('a_relancer', 0)})",
        f"♻️ Recyclage ({stats.get('recyclage', 0)})",
        "🎯 Candidatures sans RDV",
        "🔍 Rechercher",
    ])

    with tab1:
        st.markdown("**Appeler aujourd'hui** -- les contacts 1M+ avec le plus fort potentiel de conversion")
        leads_a = df[(df["classe"] == "A") & (df["statut"] == "a_appeler")]
        render_contact_table(leads_a.sort_values("score", ascending=False), "a")

    with tab2:
        st.markdown("**Appeler cette semaine** -- bon potentiel, deuxieme vague de prospection")
        leads_b = df[(df["classe"] == "B") & (df["statut"] == "a_appeler")]
        render_contact_table(leads_b.sort_values("score", ascending=False).head(200), "b")

    with tab3:
        st.markdown("**Contacts en suivi mais sans activite depuis 30 a 90 jours** -- a reprendre en main")
        a_relancer = df[df["statut"] == "a_relancer"]
        render_contact_table(a_relancer.sort_values("score", ascending=False), "r")

    with tab4:
        st.markdown("**Contacts en suivi mais sans activite depuis plus de 90 jours** -- tombes aux oubliettes")
        recyclage = df[df["statut"] == "recyclage"]
        render_contact_table(recyclage.sort_values("score", ascending=False).head(200), "rec")

    with tab5:
        st.markdown("**Ont rempli le formulaire de candidature MAIS n'ont pas pris de RDV**")
        st.caption("Un simple appel pour leur proposer un creneau peut suffire a les convertir.")
        if "candidature_sans_rdv" in df.columns:
            cand = df[
                (df["candidature_sans_rdv"] == True) &
                (df["statut"].isin(["a_appeler", "a_relancer", "recyclage"]))
            ]
            render_contact_table(cand.sort_values("score", ascending=False), "cand")
        else:
            st.caption("Aucune donnee disponible")

    with tab6:
        search = st.text_input("Nom, prenom ou email", placeholder="Ex: Jean-Francois")
        if search and len(search) >= 2:
            mask = (
                df["prenom"].str.contains(search, case=False, na=False) |
                df["nom"].str.contains(search, case=False, na=False) |
                df["email"].str.contains(search, case=False, na=False)
            )
            results = df[mask].sort_values("score", ascending=False)
            st.write(f"{len(results)} resultat(s)")
            render_contact_table(results.head(50), "search")

    # --- INSIGHTS IA (compact) ---
    insights = load_insights()
    if insights:
        st.divider()
        st.markdown("### Ce que l'IA a appris sur vos conversions")
        fi = insights.get("feature_importance", [])
        if fi:
            col1, col2 = st.columns([1, 2])
            with col1:
                st.metric("Fiabilite du modele", f"{insights.get('auc_score', 0):.1%}")
                st.caption(f"Entraine sur {insights.get('n_clients', 0)} clients et {insights.get('n_prospects', 0)} prospects")
            with col2:
                labels_map = {
                    "nb_formulaires": "Nombre de formulaires remplis",
                    "jours_depuis_entree_tunnel": "Fraicheur d'entree dans le tunnel",
                    "jours_depuis_dernier_contact": "Fraicheur du dernier contact",
                    "nb_email_open": "Nombre d'emails ouverts",
                    "nb_events": "Nombre d'evenements suivis",
                    "jours_depuis_ouverture": "Fraicheur derniere ouverture email",
                    "nb_email_click": "Nombre de clics email",
                    "jours_depuis_clic": "Fraicheur dernier clic email",
                    "emails_sans_engagement": "Emails envoyes sans reaction",
                    "dr_all_time": "Participation Destination Reussite",
                    "rdv_pris": "RDV Calendly pris",
                    "rdv_strategique": "RDV Strategique 3M",
                    "candidature_etape2": "Candidature completee",
                    "handraiser": "Leve la main spontanement",
                    "budget_score": "Budget de candidature",
                    "nb_leadmagnets": "Nombre de guides telecharges",
                }
                st.markdown("**Les criteres qui predisent le mieux la conversion :**")
                for item in fi[:7]:
                    name = labels_map.get(item["feature"], item["feature"])
                    pct = item["importance"] * 100
                    bar = "█" * int(pct / 2)
                    st.text(f"{name:35s} {pct:4.1f}% {bar}")

    # Footer
    st.divider()
    st.caption(f"Total contacts scores : {raw_data.get('total', 0)} | Lead A : {stats.get('lead_a', 0)} | Lead B : {stats.get('lead_b', 0)} | A relancer : {stats.get('a_relancer', 0)} | Recyclage : {stats.get('recyclage', 0)}")


if __name__ == "__main__":
    main()
