"""
Filtre geographique.
Exclut les contacts hors zone francophone (France, Belgique, Suisse, Luxembourg, Monaco, Canada).
Utilise l'indicatif telephone + pays IP + pays declare.
"""
import re
from config.settings import ALLOWED_PHONE_PREFIXES, ALLOWED_COUNTRIES, ALLOWED_COUNTRY_CODES


def _normalize_phone(phone):
    """Normalise un numero de telephone pour extraire l'indicatif."""
    if not phone:
        return None
    phone = phone.strip().replace(" ", "").replace(".", "").replace("-", "")
    return phone


def _is_french_local(phone):
    """Detecte un numero francais local (06, 07, 01, etc.)."""
    if not phone:
        return False
    phone = phone.strip().replace(" ", "").replace(".", "").replace("-", "")
    return bool(re.match(r'^0[1-9]\d{8}$', phone))


def _has_allowed_prefix(phone):
    """Verifie si le numero a un indicatif autorise."""
    phone = _normalize_phone(phone)
    if not phone:
        return None  # Pas de telephone = on ne peut pas juger
    if _is_french_local(phone):
        return True
    for prefix in ALLOWED_PHONE_PREFIXES:
        if phone.startswith(prefix):
            return True
    return False


def _has_allowed_country(contact):
    """Verifie si le pays du contact est dans la zone autorisee."""
    # Verifier le code pays (le plus fiable)
    for prop in ["ip_country_code", "hs_country_region_code"]:
        code = contact.get(prop)
        if code and code.upper() in ALLOWED_COUNTRY_CODES:
            return True

    # Verifier le nom du pays
    for prop in ["country", "ip_country", "pays__liste_deroulante_form_"]:
        country = contact.get(prop)
        if country and country.lower().strip() in ALLOWED_COUNTRIES:
            return True

    return None  # Pas de donnee pays


def is_in_allowed_zone(contact):
    """
    Determine si un contact est dans la zone geo autorisee.

    Logique :
    1. Si on a un telephone avec indicatif hors zone → EXCLURE
    2. Si on a un pays hors zone → EXCLURE
    3. Si on a un telephone FR ou pays FR → INCLURE
    4. Si on n'a aucune donnee geo → INCLURE (benefice du doute)
    """
    phone = contact.get("phone") or contact.get("mobilephone")
    phone_result = _has_allowed_prefix(phone)
    country_result = _has_allowed_country(contact)

    # Si le telephone dit explicitement non → exclure
    if phone_result is False:
        return False

    # Si le pays dit explicitement oui → inclure
    if country_result is True:
        return True

    # Si le telephone dit oui → inclure
    if phone_result is True:
        return True

    # Pas de donnee = benefice du doute
    return True


def get_geo_exclusion_reason(contact):
    """Retourne la raison d'exclusion geo si applicable."""
    if is_in_allowed_zone(contact):
        return None

    phone = contact.get("phone") or contact.get("mobilephone")
    country = contact.get("country") or contact.get("ip_country")
    return f"Hors zone: tel={phone}, pays={country}"
