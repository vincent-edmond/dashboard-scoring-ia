"""
Dashboard IA - Scoring Lead HubSpot
Interface de pilotage pour Vincent, Alex et Max.
"""
import os
import sys
import json
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone

# Ajouter le dossier racine au path pour les imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "scored_contacts.json")
INSIGHTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "insights.json")


st.set_page_config(
    page_title="Scoring IA - Max Piccinini",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def run_scoring_from_cloud():
    """Lance le scoring directement depuis Streamlit Cloud."""
    from hubspot.sync import run_scoring_pipeline
    with st.spinner("Scoring en cours... Recuperation des 15 000+ contacts depuis HubSpot et calcul des scores. Ca peut prendre 5-10 minutes."):
        scored = run_scoring_pipeline(push_to_hubspot=True, train_ml=True)
    return scored


@st.cache_data(ttl=14400)  # Cache 4h
def load_data_with_auto_scoring():
    """Charge les donnees. Si aucune donnee locale, lance le scoring."""
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        df = pd.DataFrame(data["contacts"])
        return df, data
    return None, None


@st.cache_data(ttl=14400)
def load_insights():
    """Charge les insights du modele IA."""
    if not os.path.exists(INSIGHTS_PATH):
        return None
    with open(INSIGHTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def render_kpi_cards(df, stats):
    """Affiche les KPI principaux en haut du dashboard."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Lead A",
            value=stats["lead_a"],
            help="Score >= 75 - Appeler en priorite absolue",
        )
    with col2:
        st.metric(
            label="Lead B",
            value=stats["lead_b"],
            help="Score 50-74 - Appeler cette semaine",
        )
    with col3:
        st.metric(
            label="A relancer",
            value=stats["a_relancer"],
            help="En cours mais sans contact depuis 30-90j",
        )
    with col4:
        st.metric(
            label="Recyclage",
            value=stats["recyclage"],
            help="En cours sans contact depuis > 90j",
        )


def render_alerts(df):
    """Affiche les alertes intelligentes."""
    st.markdown("### Alertes")

    # Alerte 1: Leads A a appeler
    leads_a_appeler = df[(df["classe"] == "A") & (df["statut"] == "a_appeler")]
    if len(leads_a_appeler) > 0:
        with st.expander(f"🔥 **{len(leads_a_appeler)} Lead A a appeler en priorite**", expanded=True):
            render_contact_table(leads_a_appeler.sort_values("score", ascending=False))

    # Alerte 2: Haute proba conversion
    if "proba_conversion" in df.columns:
        high_proba = df[
            (df["proba_conversion"].notna()) &
            (df["proba_conversion"] > 60) &
            (df["statut"] == "a_appeler")
        ]
        if len(high_proba) > 0:
            with st.expander(f"🎯 **{len(high_proba)} contacts avec proba conversion > 60%**"):
                render_contact_table(high_proba.sort_values("proba_conversion", ascending=False))

    # Alerte 3: A relancer
    a_relancer = df[df["statut"] == "a_relancer"]
    if len(a_relancer) > 0:
        with st.expander(f"⚠️ **{len(a_relancer)} contacts a relancer** (oublies 30-90j)"):
            render_contact_table(a_relancer.sort_values("score", ascending=False))

    # Alerte 4: Recyclage
    recyclage = df[df["statut"] == "recyclage"]
    if len(recyclage) > 0:
        with st.expander(f"♻️ **{len(recyclage)} contacts en recyclage** (oublies > 90j)"):
            render_contact_table(recyclage.sort_values("score", ascending=False).head(50))

    # Alerte 5: Candidature sans RDV (leads bloques dans le funnel)
    if "candidature_sans_rdv" in df.columns:
        cand_sans_rdv = df[
            (df["candidature_sans_rdv"] == True) &
            (df["statut"].isin(["a_appeler", "a_relancer", "recyclage"]))
        ]
        if len(cand_sans_rdv) > 0:
            with st.expander(f"🎯 **{len(cand_sans_rdv)} contacts ont candidaté SANS prendre de RDV** - a appeler en priorite"):
                st.caption("Ils ont rempli le Typeform de candidature mais n'ont pas booké de Calendly. Un simple appel pour proposer un creneau peut suffire.")
                render_contact_table(cand_sans_rdv.sort_values("score", ascending=False))

    # Alerte 6: Leads B a appeler
    leads_b_appeler = df[(df["classe"] == "B") & (df["statut"] == "a_appeler")]
    if len(leads_b_appeler) > 0:
        with st.expander(f"📞 **{len(leads_b_appeler)} Lead B a appeler cette semaine**"):
            render_contact_table(leads_b_appeler.sort_values("score", ascending=False).head(100))


def render_contact_table(df_subset):
    """Affiche un tableau de contacts avec liens HubSpot."""
    display_cols = {
        "score": "Score",
        "proba_conversion": "Proba %",
        "prenom": "Prenom",
        "nom": "Nom",
        "ca": "CA",
        "lead_status": "Statut",
        "calendly_event": "RDV Calendly",
        "calendly_date": "Date RDV",
        "nb_events": "Events",
        "nb_leadmagnets": "LM",
        "dernier_contact": "Dernier contact",
        "details": "Details scoring",
    }

    df_display = df_subset[[c for c in display_cols.keys() if c in df_subset.columns]].copy()
    df_display.columns = [display_cols.get(c, c) for c in df_display.columns]

    # Formater les dates
    for col in ["Date RDV", "Dernier contact"]:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(
                lambda x: x[:10] if isinstance(x, str) and len(x) > 10 else x
            )

    # Formater CA
    if "CA" in df_display.columns:
        df_display["CA"] = df_display["CA"].apply(
            lambda x: "10M+" if "10 millions" in str(x) else "1M-10M" if "1 million" in str(x) else str(x)[:15]
        )

    st.dataframe(
        df_display,
        use_container_width=True,
        height=min(400, len(df_display) * 40 + 50),
    )

    # Liens HubSpot
    if "hubspot_url" in df_subset.columns:
        urls = df_subset[["prenom", "nom", "score", "hubspot_url"]].head(20)
        st.markdown("**Ouvrir dans HubSpot :**")
        cols = st.columns(min(5, len(urls)))
        for i, (_, row) in enumerate(urls.iterrows()):
            col_idx = i % 5
            with cols[col_idx]:
                name = f"{row.get('prenom', '')} {row.get('nom', '')}".strip()
                score = row.get("score", 0)
                url = row.get("hubspot_url", "")
                if url:
                    st.markdown(f"[{name} ({score}pts)]({url})")


def render_distribution(df):
    """Graphiques de distribution des scores."""
    st.markdown("### Distribution des scores")

    col1, col2 = st.columns(2)

    with col1:
        # Histogramme des scores
        fig = px.histogram(
            df[df["statut"] != "exclu"],
            x="score",
            color="classe",
            color_discrete_map={"A": "#22c55e", "B": "#3b82f6", "C": "#f59e0b", "D": "#ef4444"},
            nbins=30,
            title="Distribution des scores",
            labels={"score": "Score IA", "count": "Nombre de contacts"},
        )
        fig.update_layout(height=350, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Repartition par classe
        classe_counts = df[df["statut"] != "exclu"]["classe"].value_counts()
        fig = go.Figure(data=[go.Pie(
            labels=[f"Lead {c}" for c in classe_counts.index],
            values=classe_counts.values,
            marker_colors=["#22c55e", "#3b82f6", "#f59e0b", "#ef4444"],
            hole=0.4,
        )])
        fig.update_layout(title="Repartition par classe", height=350)
        st.plotly_chart(fig, use_container_width=True)


def render_breakdown(df):
    """Analyse du breakdown des scores."""
    st.markdown("### Analyse par critere")

    # Moyenne des composantes par classe
    breakdown_cols = [c for c in df.columns if c.startswith("breakdown_")]
    if breakdown_cols:
        avg_by_class = df[df["statut"] != "exclu"].groupby("classe")[breakdown_cols].mean()
        avg_by_class.columns = [c.replace("breakdown_", "").title() for c in avg_by_class.columns]

        fig = px.bar(
            avg_by_class.reset_index(),
            x="classe",
            y=avg_by_class.columns.tolist(),
            title="Score moyen par composante et par classe",
            barmode="stack",
            color_discrete_sequence=["#3b82f6", "#8b5cf6", "#06b6d4", "#22c55e", "#f59e0b", "#ef4444"],
        )
        fig.update_layout(height=400, xaxis_title="Classe", yaxis_title="Points")
        st.plotly_chart(fig, use_container_width=True)


def render_insights(insights):
    """Affiche les insights du modele IA."""
    if not insights:
        return

    st.markdown("### Insights IA")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Performance du modele (AUC)", f"{insights.get('auc_score', 0):.1%}")
        st.caption(f"Entraine sur {insights.get('n_clients', 0)} clients et {insights.get('n_prospects', 0)} prospects")

    with col2:
        st.metric("Derniere mise a jour", insights.get("trained_at", "N/A")[:16])

    # Feature importance
    fi = insights.get("feature_importance", [])
    if fi:
        st.markdown("#### Ce qui predit le mieux la conversion")
        df_fi = pd.DataFrame(fi)
        df_fi["importance"] = df_fi["importance"] * 100

        # Labels lisibles
        labels = {
            "rdv_strategique": "RDV Strategique 3M",
            "rdv_pris": "RDV Calendly pris",
            "candidature_etape2": "Candidature Etape 2",
            "candidature_etape1": "Candidature Etape 1",
            "engagement_oui": "Engagement = Oui",
            "budget_score": "Budget candidature",
            "nb_leadmagnets": "Nb lead magnets",
            "nb_events": "Nb evenements",
            "dr_all_time": "Destination Reussite",
            "nb_email_click": "Nb clics email",
            "nb_email_open": "Nb ouvertures email",
            "jours_depuis_rdv": "Fraicheur RDV",
            "jours_depuis_clic": "Fraicheur clic email",
            "jours_depuis_ouverture": "Fraicheur ouverture email",
            "jours_depuis_entree_tunnel": "Fraicheur entree tunnel",
            "jours_depuis_dernier_contact": "Fraicheur dernier contact",
            "nb_formulaires": "Nb formulaires",
            "handraiser": "Handraiser",
            "mc_mensuelle": "Masterclass mensuelle",
            "optin_dr": "Optin Defi DR",
            "emails_sans_engagement": "Emails sans engagement",
            "ca_10m_plus": "CA +10M",
            "ca_1m_10m": "CA 1M-10M",
        }
        df_fi["label"] = df_fi["feature"].map(labels).fillna(df_fi["feature"])

        fig = px.bar(
            df_fi.head(10),
            x="importance",
            y="label",
            orientation="h",
            title="Top 10 des facteurs de conversion",
            labels={"importance": "Importance (%)", "label": ""},
            color="importance",
            color_continuous_scale="Viridis",
        )
        fig.update_layout(height=400, yaxis=dict(autorange="reversed"), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)


def render_search(df):
    """Barre de recherche de contact."""
    st.markdown("### Rechercher un contact")

    search = st.text_input("Nom, prenom ou email", placeholder="Ex: Jean-Francois")

    if search and len(search) >= 2:
        mask = (
            df["prenom"].str.contains(search, case=False, na=False) |
            df["nom"].str.contains(search, case=False, na=False) |
            df["email"].str.contains(search, case=False, na=False)
        )
        results = df[mask].sort_values("score", ascending=False)
        if len(results) > 0:
            st.write(f"{len(results)} resultat(s)")
            render_contact_table(results.head(20))
        else:
            st.write("Aucun resultat")


def main():
    """Point d'entree du dashboard."""
    st.title("🎯 Scoring IA - Max Piccinini")
    st.caption("Dashboard de pilotage commercial | Donnees synchronisees avec HubSpot")

    # Sidebar avec actions
    with st.sidebar:
        st.markdown("### Actions")
        if st.button("🔄 Rafraichir le scoring", use_container_width=True):
            st.cache_data.clear()
            run_scoring_from_cloud()
            st.rerun()

        st.divider()
        st.markdown("### Liens HubSpot")
        portal = "27215892"
        st.markdown(f"[📋 Tous les contacts]({f'https://app.hubspot.com/contacts/{portal}/objects/0-1/views/all/list'})")
        st.markdown(f"[⚙️ Proprietes contacts]({f'https://app.hubspot.com/contacts/{portal}/settings/properties?type=0-1'})")

    # Charger les donnees
    df, raw_data = load_data_with_auto_scoring()

    if df is None or len(df) == 0:
        st.warning("Aucune donnee disponible. Cliquez sur le bouton ci-dessous pour lancer le premier scoring.")
        if st.button("🚀 Lancer le scoring initial", type="primary"):
            run_scoring_from_cloud()
            st.rerun()
        return

    # Metadata
    updated_at = raw_data.get("updated_at", "N/A")
    if updated_at != "N/A":
        st.caption(f"Derniere MAJ: {updated_at[:16].replace('T', ' ')}")

    stats = raw_data.get("stats", {})

    # KPI Cards
    render_kpi_cards(df, stats)
    st.divider()

    # Alertes
    render_alerts(df)
    st.divider()

    # Distribution
    render_distribution(df)
    st.divider()

    # Breakdown
    render_breakdown(df)
    st.divider()

    # Insights IA
    insights = load_insights()
    if insights:
        render_insights(insights)
        st.divider()

    # Recherche
    render_search(df)

    # Footer
    st.divider()
    st.caption(f"Total contacts scores: {raw_data.get('total', 0)} | "
               f"Lead A: {stats.get('lead_a', 0)} | Lead B: {stats.get('lead_b', 0)} | "
               f"A relancer: {stats.get('a_relancer', 0)} | Recyclage: {stats.get('recyclage', 0)}")


if __name__ == "__main__":
    main()
