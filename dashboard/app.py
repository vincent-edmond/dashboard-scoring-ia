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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "scored_contacts.json.gz")
DATA_PATH_RAW = os.path.join(os.path.dirname(__file__), "..", "data", "scored_contacts.json")
PORTAL = "27215892"

st.set_page_config(
    page_title="Scoring IA - Max Piccinini",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)


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

    display = df_subset.copy()
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
    display["Fiche contact"] = display["id"].apply(
        lambda x: hubspot_url(x) if x else ""
    )

    cols_map = {
        "score": "Score",
        "Proba": "Proba",
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
        height=min(600, len(df_show) * 38 + 40),
        column_config={
            "Score": st.column_config.NumberColumn("Score", width="small"),
            "Proba": st.column_config.TextColumn("Proba", width="small"),
            "Ev.": st.column_config.NumberColumn("Ev.", width="small"),
            "Guides": st.column_config.NumberColumn("Guides", width="small"),
            "Fiche contact": st.column_config.LinkColumn("Fiche contact", display_text="Ouvrir ↗", width="small"),
        },
        hide_index=True,
    )


def main():
    st.title("🎯 Scoring IA - Max Piccinini")

    with st.sidebar:
        st.markdown("### HubSpot")
        st.markdown(f"[Voir tous les contacts](https://app.hubspot.com/contacts/{PORTAL}/objects/0-1/views/all/list)")
        st.markdown(f"[Voir les listes](https://app.hubspot.com/contacts/{PORTAL}/lists)")
        st.divider()
        st.caption("Les scores se mettent a jour automatiquement toutes les 4 heures.")
        st.caption("Quand un commercial met a jour le statut d'un contact dans HubSpot, le contact sort automatiquement de la liste au prochain scoring.")
        if st.button("🔄 Rafraichir l'affichage"):
            st.cache_data.clear()
            st.rerun()

    df, raw_data = load_data()
    if df is None or len(df) == 0:
        st.info("En attente des donnees. Le premier scoring est en cours.")
        return

    updated_at = raw_data.get("updated_at", "")
    stats = raw_data.get("stats", {})
    st.caption(f"Derniere mise a jour : {updated_at[:16].replace('T', ' ')} UTC")

    # --- KPIs ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Lead A", stats.get("lead_a", 0))
    col2.metric("Lead B", stats.get("lead_b", 0))
    col3.metric("A relancer", stats.get("a_relancer", 0))
    col4.metric("Recyclage", stats.get("recyclage", 0))

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
        st.markdown("**Contacts priorite absolue a appeler aujourd'hui.**")
        st.caption("Score 60+ : CA 1M+, avances dans le funnel, engages recemment. Ce sont les prospects les plus chauds de votre base.")
        leads_a = df[(df["classe"] == "A") & (df["statut"] == "a_appeler")]
        render_table(leads_a.sort_values("score", ascending=False))

    with tab2:
        st.markdown("**Bons profils a appeler cette semaine.**")
        st.caption("Score 40-59 : CA 1M+ avec plusieurs signaux positifs (engagement email, lead magnets, events).")
        leads_b = df[(df["classe"] == "B") & (df["statut"] == "a_appeler")]
        render_table(leads_b.sort_values("score", ascending=False))

    with tab3:
        st.markdown("**Contacts en suivi commercial mais sans activite depuis 30 a 90 jours.**")
        st.caption("Un commercial a commence a les traiter (statut 'En cours' ou 'FUP') mais n'a plus donne suite depuis 1 a 3 mois. Il faut reprendre le fil de la conversation.")
        a_relancer = df[df["statut"] == "a_relancer"]
        render_table(a_relancer.sort_values("score", ascending=False))

    with tab4:
        st.markdown("**Contacts en suivi commercial mais oublies depuis plus de 3 mois.**")
        st.caption("La relation commerciale precedente est morte. Ces contacts doivent etre recontactes comme des prospects neufs. Certains ont peut-etre entre-temps consomme du contenu ou participe a des evenements.")
        recyclage = df[df["statut"] == "recyclage"]
        render_table(recyclage.sort_values("score", ascending=False))

    with tab5:
        st.markdown("**Contacts qui ont rempli le formulaire de candidature MAIS qui n'ont pas pris de RDV Calendly.**")
        st.caption("Ils ont montre une intention forte en candidatant, mais quelque chose les a bloques avant de booker. Un appel pour leur proposer un creneau peut suffire.")
        if "candidature_sans_rdv" in df.columns:
            cand = df[
                (df["candidature_sans_rdv"] == True) &
                (df["statut"].isin(["a_appeler", "a_relancer", "recyclage"]))
            ]
            render_table(cand.sort_values("score", ascending=False))
        else:
            st.caption("Aucune donnee disponible.")

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
            render_table(results.head(50))

    st.divider()
    st.caption(f"Total contacts scores : {raw_data.get('total', 0)} | Lead A : {stats.get('lead_a', 0)} | Lead B : {stats.get('lead_b', 0)} | A relancer : {stats.get('a_relancer', 0)} | Recyclage : {stats.get('recyclage', 0)}")


if __name__ == "__main__":
    main()
