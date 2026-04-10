import os
from dotenv import load_dotenv

load_dotenv()

# HubSpot - supporte .env local ET Streamlit Cloud secrets
def _get_secret(key, default=None):
    """Recupere un secret depuis .env ou Streamlit secrets."""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default

HUBSPOT_API_KEY = _get_secret("HUBSPOT_API_KEY")
HUBSPOT_PORTAL_ID = _get_secret("HUBSPOT_PORTAL_ID", "27215892")
HUBSPOT_BASE_URL = f"https://app.hubspot.com/contacts/{HUBSPOT_PORTAL_ID}/record/0-1"

# Sync
SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "4"))

# --- SCORING CONFIG ---

# Proprietes CA
CA_PROPERTY = "chiffre_d_affaires_annuel_new"
CA_1M_10M = "1 million € à 10 millions € de C.A annuel"
CA_10M_PLUS = "+ 10 millions € de C.A annuel"

# Proprietes a exclure (clients actifs)
EXCLUSION_RULES = {
    "client_mm": ["MM Actif", "MM En Pause"],
    "n3m___clients": ["3M Actif", "3M En Pause"],
    "lifecyclestage": ["235301569", "235178993"],  # Client 3M, Client MM
}

# Produits a exclure dans achat_produit
EXCLUDED_PRODUCTS = [
    "MM", "3M", "3MP", "3MD",
    "BM 2024", "BM2025", "BM 2026",
    "FM Evergreen", "FM 2026", "FM2025", "FM2027",
    "LM 2025", "LM2026",
    "BusinessPackage", "LifePackage", "MegaPackage",
]

# Statuts "en suivi actif" (exclus de la liste 1 si contact recent)
ACTIVE_FOLLOW_STATUSES = ["IN_PROGRESS", "FUP", "FUP ECA", "FUP MM", "FUP 3M", "FUP PA"]

# Statuts disqualifiants
DISQUALIFIED_STATUSES = ["UNQUALIFIED"]
BAD_NUMBER_STATUS = "CONNECTED"  # = "Mauvais numéro" dans HubSpot

# Zone geo autorisee (indicatifs tel)
ALLOWED_PHONE_PREFIXES = ["+33", "+32", "+352", "+41", "0033", "0032", "0352", "0041"]
ALLOWED_COUNTRIES = [
    "france", "belgique", "belgium", "suisse", "switzerland",
    "luxembourg", "monaco", "canada", "québec", "quebec",
]
ALLOWED_COUNTRY_CODES = ["FR", "BE", "LU", "CH", "MC", "CA"]

# Proprietes de participation webinaire/challenge (Absent/Present)
PARTICIPATION_PROPERTIES = [
    "participation_au_webinaire___rb",
    "participation_au_webinaire___bl",
    "participation_au_webinaire__af",
    "participation_au_webinaire___fm",
    "participation_au_webinaire___mcm",
    "participation_au_webinaire___3dc",
    "participation_au_webinaire___gr",
    "participation_au_webinaire___rns",
    "participation_au_webinaire___webi_treso",
    "participation_au_webinaire___defi_dr",
    "bm_business_max_webi_2024",
]

# Proprietes lead magnet (pour compter le nombre de LM telecharges)
LEADMAGNET_PROPERTIES = [
    "date_telechargement_guideca",
    "source_telechargement_guide_treso",
    "date_telechargement_3focus",
    "source_telechargement_calculateur",
    "source_telechargement_checklist",
    "date_telechargement_videosfullvaleur",
    "date_telechargement_vsl_courte",
    "date_telechargement_vsl_longue",
    "reponses_au_quizz",
]

# Toutes les proprietes a recuperer pour le scoring
SCORING_PROPERTIES = [
    # Identite
    "firstname", "lastname", "email", "phone", "mobilephone",
    # CA
    "chiffre_d_affaires_annuel_new", "chiffre_d_affaires_annuel",
    # Statut client
    "client_mm", "n3m___clients", "clients_3m", "achat_produit", "lifecyclestage",
    # Tunnel MM/3M
    "date_d_entree_leadmagnet_mm_3m", "mm_3m___date_optin_leadmagnet",
    "mm_3m___date_call_leadmagnet", "leadmagnet_telecharges",
    # Candidature
    "mm___candidature_effectuee", "mm_3m___candidature___motivation",
    "mm_3m___candidature___budget", "mm_3m___candidature___engagement",
    "mm_3m___candidature___stade_entreprise",
    # Calendly
    "calendly", "calendly_event", "calendly_date", "source_outbound",
    # Typeform
    "source_typeform", "date_typeform", "campagne_typeform",
    # Formulaires
    "num_unique_conversion_events", "n420__formulaire_d_interet_remplis",
    "formulaire_audit_strategique_rempli",
    # Engagement email
    "hs_email_open", "hs_email_click",
    "hs_email_last_open_date", "hs_email_last_click_date",
    "hs_email_sends_since_last_engagement",
    # Activite commerciale
    "hs_lead_status", "notes_last_contacted", "notes_last_updated",
    "hs_last_sales_activity_timestamp", "hs_sa_first_engagement_date",
    "hs_v2_date_entered_current_stage",
    # DR
    "all_time_dr", "source_optin_defi_dr",
    # Masterclass
    "source_optin_masterclass_mensuelle", "source_optin_masterclass_af",
    # Geo
    "country", "ip_country", "ip_country_code",
    "hs_country_region_code", "pays__liste_deroulante_form_",
    # Participations events
    *PARTICIPATION_PROPERTIES,
    # Lead magnets
    *LEADMAGNET_PROPERTIES,
]
