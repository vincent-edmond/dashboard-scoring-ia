"""
Client API HubSpot pour le scoring IA.
Gere la connexion, la lecture et l'ecriture des contacts.
"""
import time
import requests
from config.settings import HUBSPOT_API_KEY, HUBSPOT_PORTAL_ID, SCORING_PROPERTIES


BASE_URL = "https://api.hubapi.com"
HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_API_KEY}",
    "Content-Type": "application/json",
}
RATE_LIMIT_DELAY = 0.12  # ~8 req/s pour rester sous la limite HubSpot


def _request(method, endpoint, json_data=None, params=None, retries=3):
    """Requete HTTP avec retry et rate limiting."""
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(retries):
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.request(method, url, headers=HEADERS, json=json_data, params=params)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 10))
            print(f"  Rate limited, attente {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise Exception(f"Echec apres {retries} tentatives: {endpoint}")


def search_contacts(filter_groups, properties=None, limit=100):
    """
    Recherche des contacts HubSpot avec filtres.
    Gere la pagination automatiquement.
    Retourne tous les contacts correspondants.
    """
    if properties is None:
        properties = SCORING_PROPERTIES

    all_results = []
    after = 0

    while True:
        payload = {
            "filterGroups": filter_groups,
            "properties": properties,
            "limit": min(limit, 100),
            "after": after,
        }

        data = _request("POST", "/crm/v3/objects/contacts/search", json_data=payload)
        results = data.get("results", [])
        total = data.get("total", 0)

        for r in results:
            contact = r.get("properties", {})
            contact["id"] = r.get("id")
            all_results.append(contact)

        print(f"  Recupere {len(all_results)}/{total} contacts...")

        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        if next_page and next_page.get("after"):
            after = int(next_page["after"])
        else:
            break

    return all_results


def _search_with_date_split(filter_base, label=""):
    """
    Contourne la limite de 10K resultats de l'API search HubSpot
    en splitant par date de creation.
    """
    # D'abord essayer sans split
    try:
        results = search_contacts([{"filters": filter_base}])
        return results
    except Exception:
        pass

    # Si > 10K, splitter par periodes
    print(f"  Plus de 10K resultats pour {label}, split par date...")
    from datetime import datetime, timedelta

    all_results = []
    seen_ids = set()

    # Periodes : avant 2024, 2024-H1, 2024-H2, 2025-H1, 2025-H2, 2026+
    date_ranges = [
        (None, "2024-01-01T00:00:00Z"),
        ("2024-01-01T00:00:00Z", "2024-07-01T00:00:00Z"),
        ("2024-07-01T00:00:00Z", "2025-01-01T00:00:00Z"),
        ("2025-01-01T00:00:00Z", "2025-07-01T00:00:00Z"),
        ("2025-07-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        ("2026-01-01T00:00:00Z", None),
    ]

    for start, end in date_ranges:
        filters = list(filter_base)
        if start:
            filters.append({"propertyName": "createdate", "operator": "GTE", "value": start})
        if end:
            filters.append({"propertyName": "createdate", "operator": "LT", "value": end})

        period_label = f"{start or 'debut'} -> {end or 'now'}"
        print(f"    Periode {period_label}...")

        try:
            results = search_contacts([{"filters": filters}])
            for r in results:
                rid = r.get("id") or r.get("hs_object_id")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    all_results.append(r)
        except Exception as e:
            print(f"    Erreur sur cette periode: {e}")

    print(f"  Total {label}: {len(all_results)} contacts (dedupliques)")
    return all_results


def fetch_target_contacts():
    """
    Recupere tous les contacts 1M+ (la base scorable).
    Deux requetes : 1M-10M et +10M.
    """
    from config.settings import CA_PROPERTY, CA_1M_10M, CA_10M_PLUS

    print("Recuperation des contacts 1M-10M...")
    contacts_1m = _search_with_date_split(
        [{"propertyName": CA_PROPERTY, "operator": "EQ", "value": CA_1M_10M}],
        label="1M-10M",
    )

    print("Recuperation des contacts +10M...")
    contacts_10m = _search_with_date_split(
        [{"propertyName": CA_PROPERTY, "operator": "EQ", "value": CA_10M_PLUS}],
        label="+10M",
    )

    all_contacts = contacts_1m + contacts_10m
    print(f"Total: {len(all_contacts)} contacts 1M+ recuperes")
    return all_contacts


def update_contact_properties(contact_id, properties):
    """Met a jour les proprietes d'un contact."""
    endpoint = f"/crm/v3/objects/contacts/{contact_id}"
    return _request("PATCH", endpoint, json_data={"properties": properties})


def batch_update_contacts(updates):
    """
    Met a jour les contacts par batch de 100.
    updates = [{"id": "123", "properties": {"score_ia": "75"}}, ...]
    """
    batch_size = 100
    total = len(updates)

    for i in range(0, total, batch_size):
        batch = updates[i:i + batch_size]
        payload = {
            "inputs": [
                {"id": str(u["id"]), "properties": u["properties"]}
                for u in batch
            ]
        }
        _request("POST", "/crm/v3/objects/contacts/batch/update", json_data=payload)
        print(f"  Batch update {i + len(batch)}/{total}")


def create_property_if_not_exists(name, label, property_type="number", group_name="contactinformation", field_type="number", options=None):
    """Cree une propriete custom si elle n'existe pas."""
    try:
        _request("GET", f"/crm/v3/properties/contacts/{name}")
        print(f"  Propriete '{name}' existe deja")
        return
    except Exception:
        pass

    payload = {
        "name": name,
        "label": label,
        "type": property_type,
        "fieldType": field_type,
        "groupName": group_name,
    }
    if options:
        payload["options"] = options

    _request("POST", "/crm/v3/properties/contacts", json_data=payload)
    print(f"  Propriete '{name}' creee")


def setup_scoring_properties():
    """Cree les proprietes custom necessaires au scoring dans HubSpot."""
    create_property_if_not_exists(
        name="score_ia",
        label="Score IA",
        property_type="number",
        field_type="number",
    )
    create_property_if_not_exists(
        name="score_ia_proba",
        label="Score IA - Probabilité conversion",
        property_type="number",
        field_type="number",
    )
    create_property_if_not_exists(
        name="classe_lead",
        label="Classe Lead IA",
        property_type="enumeration",
        field_type="select",
        options=[
            {"label": "Lead A", "value": "A"},
            {"label": "Lead B", "value": "B"},
            {"label": "Lead C", "value": "C"},
            {"label": "Lead D", "value": "D"},
        ],
    )
    create_property_if_not_exists(
        name="statut_scoring",
        label="Statut Scoring IA",
        property_type="enumeration",
        field_type="select",
        options=[
            {"label": "A appeler", "value": "a_appeler"},
            {"label": "A relancer", "value": "a_relancer"},
            {"label": "Recyclage", "value": "recyclage"},
            {"label": "Exclu", "value": "exclu"},
        ],
    )
    create_property_if_not_exists(
        name="score_ia_details",
        label="Score IA - Détails",
        property_type="string",
        field_type="text",
    )
    create_property_if_not_exists(
        name="score_ia_last_update",
        label="Score IA - Dernière MAJ",
        property_type="datetime",
        field_type="date",
    )
    print("Proprietes de scoring configurees.")


def get_contact_url(contact_id):
    """Retourne l'URL directe vers la fiche contact HubSpot."""
    return f"https://app.hubspot.com/contacts/{HUBSPOT_PORTAL_ID}/record/0-1/{contact_id}"
