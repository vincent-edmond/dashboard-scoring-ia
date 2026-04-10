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
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "scored_contacts.json.gz")
DATA_PATH_RAW = os.path.join(os.path.dirname(__file__), "..", "data", "scored_contacts.json")
PORTAL = "27215892"

MOIS_FR = {1:"jan", 2:"fev", 3:"mar", 4:"avr", 5:"mai", 6:"jun",
           7:"jul", 8:"aou", 9:"sep", 10:"oct", 11:"nov", 12:"dec"}

st.set_page_config(
    page_title="Scoring IA - Max Piccinini",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)


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
            return f"{jour} {mois}. {annee}"
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
        height=min(600, len(df_show) * 38 + 40),
        column_config={
            "Score": st.column_config.NumberColumn("Score", width="small"),
            "Ev.": st.column_config.NumberColumn("Ev.", width="small"),
            "Guides": st.column_config.NumberColumn("Guides", width="small"),
            "Fiche contact": st.column_config.LinkColumn("Fiche contact", display_text="Ouvrir ↗", width="small"),
        },
        hide_index=True,
    )


def main():
    st.title("🎯 Scoring IA - Max Piccinini")

    with st.sidebar:
        st.markdown("### Comment ca marche")
        st.markdown("""
**Lead A** (score 60+)
Les prospects les plus chauds : CA 1M+, avances dans le funnel (RDV, candidature), engagement email recent.

**Lead B** (score 40-59)
Bons profils avec plusieurs signaux positifs : events, guides telecharges, emails ouverts.

**Lead C** (score 25-39)
Prospects tides : CA 1M+ avec au moins un signal d'interet (1 guide, 1 email ouvert...). Ideaux pour du nurturing ou une invitation a un event.

**A relancer**
Contacts deja en suivi commercial (statut "En cours" ou "FUP") mais sans activite depuis 30 a 90 jours. Le commercial a oublie de relancer. Reprendre le fil.

**Recyclage**
Meme chose mais oublies depuis plus de 3 mois. La relation commerciale est morte. Les recontacter comme des prospects neufs.

**Candidatures sans RDV**
Ont rempli le Typeform de candidature mais n'ont pas pris de creneau Calendly. Un appel pour proposer un RDV peut suffire.
        """)
        st.divider()
        st.markdown("### Fonctionnement")
        st.caption("Les scores se mettent a jour automatiquement toutes les 4 heures.")
        st.caption("Quand un commercial met a jour le statut d'un contact dans HubSpot (Appel 1, En cours...), le contact sort automatiquement de ces listes au prochain scoring.")
        st.divider()
        st.markdown("### HubSpot")
        st.markdown(f"[Voir les listes HubSpot](https://app.hubspot.com/contacts/{PORTAL}/lists)")
        st.divider()
        if st.button("🔄 Rafraichir l'affichage"):
            st.cache_data.clear()
            st.rerun()

    df, raw_data = load_data()
    if df is None or len(df) == 0:
        st.info("En attente des donnees. Le premier scoring est en cours.")
        return

    updated_at = raw_data.get("updated_at", "")
    stats = raw_data.get("stats", {})
    st.caption(f"Derniere mise a jour : {format_date_fr(updated_at[:10])} a {updated_at[11:16]} UTC")

    # --- KPIs ---
    lead_c_count = len(df[(df["classe"] == "C") & (df["statut"] == "a_appeler")])

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Lead A", stats.get("lead_a", 0))
    col2.metric("Lead B", stats.get("lead_b", 0))
    col3.metric("Lead C", lead_c_count)
    col4.metric("A relancer", stats.get("a_relancer", 0))
    col5.metric("Recyclage", stats.get("recyclage", 0))

    st.divider()

    # --- ONGLETS ---
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        f"🔥 Lead A ({stats.get('lead_a', 0)})",
        f"📞 Lead B ({stats.get('lead_b', 0)})",
        f"💡 Lead C ({lead_c_count})",
        f"⚠️ A relancer ({stats.get('a_relancer', 0)})",
        f"♻️ Recyclage ({stats.get('recyclage', 0)})",
        "🎯 Candidatures sans RDV",
        "🔍 Rechercher",
    ])

    with tab1:
        st.markdown("**Appeler aujourd'hui -- les prospects les plus chauds de la base.**")
        st.caption("Score 60+ : CA 1M+, avances dans le funnel (RDV pris, candidature, engagement fort). Taux de conversion estime le plus eleve.")
        leads_a = df[(df["classe"] == "A") & (df["statut"] == "a_appeler")]
        render_table(leads_a.sort_values("score", ascending=False))

    with tab2:
        st.markdown("**Appeler cette semaine -- bons profils avec plusieurs signaux positifs.**")
        st.caption("Score 40-59 : CA 1M+ avec engagement email, lead magnets telecharges, participations a des events.")
        leads_b = df[(df["classe"] == "B") & (df["statut"] == "a_appeler")]
        render_table(leads_b.sort_values("score", ascending=False))

    with tab3:
        st.markdown("**Prospects tides -- a nourrir ou inviter a un evenement.**")
        st.caption("Score 25-39 : CA 1M+ avec au moins un signal d'interet (a ouvert un email, telecharge un guide, participe a un event). Pas assez chauds pour un appel a froid, mais ideaux pour les inscrire a une Masterclass, un Challenge, ou leur envoyer une sequence email dediee pour les rechauffer.")
        leads_c = df[(df["classe"] == "C") & (df["statut"] == "a_appeler")]
        render_table(leads_c.sort_values("score", ascending=False).head(500))

    with tab4:
        st.markdown("**Contacts en suivi commercial mais sans activite depuis 30 a 90 jours.**")
        st.caption("Un commercial les avait pris en charge (statut 'En cours' ou 'FUP') mais n'a plus donne suite depuis 1 a 3 mois. Il faut reprendre le fil de la conversation la ou elle s'est arretee.")
        a_relancer = df[df["statut"] == "a_relancer"]
        render_table(a_relancer.sort_values("score", ascending=False))

    with tab5:
        st.markdown("**Contacts en suivi commercial mais oublies depuis plus de 3 mois.**")
        st.caption("La relation commerciale precedente est morte. Ces contacts doivent etre recontactes comme des prospects neufs. Certains ont peut-etre entre-temps consomme du contenu ou participe a des evenements -- le score en tient compte.")
        recyclage = df[df["statut"] == "recyclage"]
        render_table(recyclage.sort_values("score", ascending=False))

    with tab6:
        st.markdown("**Ont rempli le formulaire de candidature mais n'ont pas pris de RDV Calendly.**")
        st.caption("Ils ont montre une intention forte en candidatant, mais quelque chose les a bloques avant de booker un creneau. Un simple appel pour leur proposer un RDV peut suffire a les convertir.")
        if "candidature_sans_rdv" in df.columns:
            cand = df[
                (df["candidature_sans_rdv"] == True) &
                (df["statut"].isin(["a_appeler", "a_relancer", "recyclage"]))
            ]
            render_table(cand.sort_values("score", ascending=False))
        else:
            st.caption("Aucune donnee disponible.")

    with tab7:
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

    # --- HISTORIQUE ---
    st.divider()
    history_path = os.path.join(os.path.dirname(__file__), "..", "data", "scoring_history.json")
    if os.path.exists(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)

        if len(history) > 1:
            st.markdown("### Progression du scoring")
            st.caption("Evolution des volumes a chaque mise a jour (toutes les 4h).")

            hist_df = pd.DataFrame(history)
            hist_df["date_fr"] = hist_df["date"].apply(lambda x: format_date_fr(str(x)[:10]) + " " + str(x)[11:16] if x else "-")

            display_hist = hist_df[["date_fr", "lead_a", "lead_b", "lead_c", "a_relancer", "recyclage"]].copy()
            display_hist.columns = ["Date", "Lead A", "Lead B", "Lead C", "A relancer", "Recyclage"]

            # Afficher en ordre inverse (plus recent en haut)
            st.dataframe(
                display_hist.iloc[::-1],
                use_container_width=True,
                height=min(300, len(display_hist) * 38 + 40),
                hide_index=True,
            )

    st.divider()
    st.caption(f"Total contacts scores : {raw_data.get('total', 0)} | Lead A : {stats.get('lead_a', 0)} | Lead B : {stats.get('lead_b', 0)} | Lead C : {lead_c_count} | A relancer : {stats.get('a_relancer', 0)} | Recyclage : {stats.get('recyclage', 0)}")


if __name__ == "__main__":
    main()
