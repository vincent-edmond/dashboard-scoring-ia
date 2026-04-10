"""
Scoring V1 - Modele a regles.
Grille de scoring deterministe basee sur les criteres valides avec Vincent.
Score sur ~100 points + bonus/malus.
"""
from datetime import datetime, timezone
from config.settings import (
    CA_1M_10M, CA_10M_PLUS,
    EXCLUSION_RULES, EXCLUDED_PRODUCTS,
    ACTIVE_FOLLOW_STATUSES, DISQUALIFIED_STATUSES, BAD_NUMBER_STATUS,
    PARTICIPATION_PROPERTIES, LEADMAGNET_PROPERTIES,
)


def _parse_date(date_str):
    """Parse une date HubSpot (ISO 8601) en datetime."""
    if not date_str:
        return None
    try:
        date_str = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def _days_since(date_str):
    """Retourne le nombre de jours depuis une date."""
    dt = _parse_date(date_str)
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def _prop(contact, name):
    """Recupere une propriete du contact (None si vide)."""
    val = contact.get(name)
    if val is None or val == "" or val == "null":
        return None
    return val


def is_excluded_client(contact):
    """Verifie si le contact est un client actif a exclure."""
    # Exclusion par statut client
    for prop, excluded_values in EXCLUSION_RULES.items():
        val = _prop(contact, prop)
        if val and val in excluded_values:
            return True

    # Exclusion par achat produit
    achat = _prop(contact, "achat_produit")
    if achat:
        for product in EXCLUDED_PRODUCTS:
            if product in achat:
                return True

    return False


def get_contact_status(contact):
    """
    Determine le statut scoring du contact :
    - 'exclu' : client actif, desabonne, non qualifie
    - 'a_appeler' : prospect scorable
    - 'a_relancer' : en cours mais oublie (30-90j)
    - 'recyclage' : en cours depuis > 90j
    """
    if is_excluded_client(contact):
        return "exclu"

    lead_status = _prop(contact, "hs_lead_status")

    # Disqualifie
    if lead_status in DISQUALIFIED_STATUSES:
        return "exclu"

    # En suivi actif ? Verifier la fraicheur
    if lead_status in ACTIVE_FOLLOW_STATUSES:
        days = _days_since(_prop(contact, "notes_last_contacted"))
        if days is not None:
            if days < 30:
                return "exclu"  # Suivi actif, ne pas toucher
            elif days <= 90:
                return "a_relancer"
            else:
                return "recyclage"
        else:
            # Pas de date de dernier contact = probablement oublie
            days_stage = _days_since(_prop(contact, "hs_v2_date_entered_current_stage"))
            if days_stage is not None and days_stage > 90:
                return "recyclage"
            elif days_stage is not None and days_stage > 30:
                return "a_relancer"
            return "a_appeler"

    return "a_appeler"


def score_profil(contact):
    """Tier 1 - Score profil / avatar (max 30 pts)."""
    score = 0
    details = []

    ca = _prop(contact, "chiffre_d_affaires_annuel_new")
    if ca == CA_10M_PLUS:
        score += 30
        details.append("CA +10M (+30)")
    elif ca == CA_1M_10M:
        score += 20
        details.append("CA 1M-10M (+20)")

    if _prop(contact, "all_time_dr") == "true":
        score += 10
        details.append("DR All Time (+10)")

    return score, details


def score_funnel(contact):
    """Tier 2 - Avancement dans le funnel MM/3M (max 35 pts)."""
    score = 0
    details = []

    # 2a. Calendly / RDV (max 20 pts)
    calendly_status = _prop(contact, "calendly")
    calendly_event = _prop(contact, "calendly_event") or ""
    calendly_date = _prop(contact, "calendly_date")

    if calendly_status == "RDV pris":
        if "3M" in calendly_event or "Stratégique" in calendly_event or "stratégique" in calendly_event:
            score += 20
            details.append("RDV Strat/3M (+20)")
        elif "Diagnostic" in calendly_event or "diagnostic" in calendly_event:
            score += 15
            details.append("RDV Diagnostic (+15)")
        else:
            score += 12
            details.append("RDV Calendly (+12)")

        # Bonus fraicheur RDV
        days_rdv = _days_since(calendly_date)
        if days_rdv is not None:
            if days_rdv <= 30:
                score += 5
                details.append("RDV <30j (+5)")
            elif days_rdv <= 90:
                score += 3
                details.append("RDV 30-90j (+3)")

    # 2b. Candidature (max 15 pts)
    candidature = _prop(contact, "mm___candidature_effectuee")
    if candidature == "Etape 2":
        score += 15
        details.append("Candidature Etape 2 (+15)")
    elif candidature in ("true", "Etape 1"):
        score += 10
        details.append("Candidature Etape 1 (+10)")

    # Formulaire d'interet
    if _prop(contact, "n420__formulaire_d_interet_remplis") == "true":
        score += 5
        details.append("Formulaire interet (+5)")

    # Audit strategique
    if _prop(contact, "formulaire_audit_strategique_rempli"):
        score += 5
        details.append("Audit Strat (+5)")

    # Bonus budget candidature
    budget = _prop(contact, "mm_3m___candidature___budget")
    if budget:
        high_budgets = ["20 000€ et plus", "Plus de 100 000€",
                        "Entre 50 000 et 100 000€", "Entre 40 000 et 50 000€",
                        "Entre 30 000 et 40 000€", "Entre 25 000 et 50 000€",
                        "Entre 20 000 et 30 000€"]
        if any(b in budget for b in high_budgets):
            score += 5
            details.append(f"Budget élevé (+5)")

    # Bonus engagement
    if _prop(contact, "mm_3m___candidature___engagement") == "Oui":
        score += 5
        details.append("Engagement Oui (+5)")

    # Signal fort : candidature SANS RDV Calendly = lead chaud bloque
    has_candidature = candidature in ("Etape 2", "true", "Etape 1")
    has_rdv = calendly_status == "RDV pris"
    if has_candidature and not has_rdv:
        score += 8
        details.append("Candidature SANS RDV (+8)")

    return score, details


def score_contenu(contact):
    """Tier 3 - Consommation de contenu (max 15 pts)."""
    score = 0
    details = []

    # 3a. Comptage lead magnets
    lm_count = sum(1 for prop in LEADMAGNET_PROPERTIES if _prop(contact, prop))

    if lm_count >= 4:
        score += 10
        details.append(f"{lm_count} lead magnets (+10)")
    elif lm_count >= 2:
        score += 7
        details.append(f"{lm_count} lead magnets (+7)")
    elif lm_count >= 1:
        score += 4
        details.append(f"{lm_count} lead magnet (+4)")

    # Bonus fraicheur entree tunnel
    days_tunnel = _days_since(_prop(contact, "date_d_entree_leadmagnet_mm_3m"))
    if days_tunnel is not None:
        if days_tunnel <= 30:
            score += 3
            details.append("Tunnel <30j (+3)")
        elif days_tunnel <= 90:
            score += 2
            details.append("Tunnel 30-90j (+2)")

    # 3b. Participation events
    event_count = sum(
        1 for prop in PARTICIPATION_PROPERTIES
        if _prop(contact, prop) == "Présent"
    )

    if event_count >= 3:
        score += 5
        details.append(f"{event_count} events (+5)")
    elif event_count >= 1:
        score += 3
        details.append(f"{event_count} event(s) (+3)")

    # Masterclass mensuelle
    if _prop(contact, "source_optin_masterclass_mensuelle"):
        score += 2
        details.append("MC mensuelle (+2)")

    return score, details


def score_engagement_email(contact):
    """Tier 4 - Engagement email recent (max 15 pts)."""
    score = 0
    details = []

    days_click = _days_since(_prop(contact, "hs_email_last_click_date"))
    days_open = _days_since(_prop(contact, "hs_email_last_open_date"))

    if days_click is not None and days_click <= 30:
        score += 15
        details.append("Clic email <30j (+15)")
    elif days_open is not None and days_open <= 30:
        score += 10
        details.append("Ouverture email <30j (+10)")
    elif days_click is not None and days_click <= 60:
        score += 8
        details.append("Clic email 30-60j (+8)")
    elif days_open is not None and days_open <= 60:
        score += 5
        details.append("Ouverture email 30-60j (+5)")

    return score, details


def score_signaux_commerciaux(contact):
    """Tier 5 - Signaux commerciaux bonus (max 10 pts)."""
    score = 0
    details = []

    lead_status = _prop(contact, "hs_lead_status")

    # Nouveau + dans le tunnel
    if lead_status == "NEW" and _prop(contact, "date_d_entree_leadmagnet_mm_3m"):
        score += 5
        details.append("NEW + tunnel (+5)")

    # Mauvais timing = etait interesse
    if lead_status == "BAD_TIMING":
        score += 5
        details.append("Mauvais timing (+5)")

    # Source handraiser
    if _prop(contact, "source_outbound") == "handraiser":
        score += 5
        details.append("Handraiser (+5)")

    # Nombre de formulaires soumis
    forms = _prop(contact, "num_unique_conversion_events")
    if forms and int(float(forms)) > 3:
        score += 3
        details.append(f"{forms} formulaires (+3)")

    # Activite commerciale recente
    days_activity = _days_since(_prop(contact, "hs_last_sales_activity_timestamp"))
    if days_activity is not None and days_activity <= 90:
        score += 5
        details.append("Activite comm. <90j (+5)")

    return score, details


def score_malus(contact):
    """Tier 6 - Malus (points negatifs)."""
    score = 0
    details = []

    lead_status = _prop(contact, "hs_lead_status")

    if lead_status == BAD_NUMBER_STATUS:
        score -= 20
        details.append("Mauvais numéro (-20)")

    # Budget "aucune intention"
    budget = _prop(contact, "mm_3m___candidature___budget")
    if budget and "aucune intention" in budget.lower():
        score -= 25
        details.append("Aucune intention investir (-25)")

    # Emails sans engagement
    sends_since = _prop(contact, "hs_email_sends_since_last_engagement")
    if sends_since and int(float(sends_since)) > 20:
        score -= 10
        details.append(f"Emails sans engagement: {sends_since} (-10)")

    # Appel 5-6 sans conversion
    if lead_status in ("Appel 5", "Appel 6"):
        score -= 5
        details.append("Appel 5-6 sans conversion (-5)")

    return score, details


def classify_lead(score):
    """Classifie un lead en A/B/C/D selon son score."""
    if score >= 75:
        return "A"
    elif score >= 50:
        return "B"
    elif score >= 30:
        return "C"
    else:
        return "D"


def score_contact(contact):
    """
    Calcule le score complet d'un contact.
    Retourne un dict avec score, classe, statut, details.
    """
    # Determiner le statut d'abord
    statut = get_contact_status(contact)

    # Si exclu (client actif, suivi < 30j, disqualifie), on score quand meme
    # mais on marque comme exclu
    s1, d1 = score_profil(contact)
    s2, d2 = score_funnel(contact)
    s3, d3 = score_contenu(contact)
    s4, d4 = score_engagement_email(contact)
    s5, d5 = score_signaux_commerciaux(contact)
    s6, d6 = score_malus(contact)

    total = max(0, s1 + s2 + s3 + s4 + s5 + s6)
    classe = classify_lead(total)
    all_details = d1 + d2 + d3 + d4 + d5 + d6

    return {
        "score": total,
        "classe": classe,
        "statut": statut,
        "details": " | ".join(all_details),
        "breakdown": {
            "profil": s1,
            "funnel": s2,
            "contenu": s3,
            "email": s4,
            "commercial": s5,
            "malus": s6,
        },
    }
