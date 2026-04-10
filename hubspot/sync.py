"""
Synchronisation bidirectionnelle HubSpot.
Pull contacts → Score → Push scores dans HubSpot.
"""
import os
import json
import pandas as pd
from datetime import datetime, timezone

from hubspot.client import (
    fetch_target_contacts,
    batch_update_contacts,
    setup_scoring_properties,
    get_contact_url,
)
from scoring.v1_rules import score_contact
from scoring.v2_ml import train_model, predict_conversion, load_model
from scoring.geo_filter import is_in_allowed_zone, get_geo_exclusion_reason


DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def ensure_data_dir():
    """Cree le dossier data si necessaire."""
    os.makedirs(DATA_DIR, exist_ok=True)


def run_scoring_pipeline(push_to_hubspot=True, train_ml=True):
    """
    Pipeline complet de scoring.
    1. Setup des proprietes HubSpot
    2. Pull des contacts 1M+
    3. Filtre geo
    4. Scoring V1 (regles)
    5. Training V2 (ML) si demande
    6. Scoring V2 (prediction)
    7. Push des scores dans HubSpot
    8. Sauvegarde locale (dashboard)
    """
    ensure_data_dir()
    print("=" * 60)
    print("PIPELINE DE SCORING IA")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. Setup proprietes
    if push_to_hubspot:
        print("\n[1/7] Configuration des proprietes HubSpot...")
        setup_scoring_properties()

    # 2. Pull contacts
    print("\n[2/7] Recuperation des contacts 1M+...")
    contacts = fetch_target_contacts()

    # 3. Filtre geo
    print("\n[3/7] Filtre geographique...")
    geo_excluded = 0
    geo_included = []
    for c in contacts:
        if is_in_allowed_zone(c):
            geo_included.append(c)
        else:
            geo_excluded += 1
    print(f"  {len(geo_included)} contacts en zone / {geo_excluded} hors zone exclus")
    contacts = geo_included

    # 4. Scoring V1
    print("\n[4/7] Scoring V1 (regles)...")
    scored_contacts = []
    for c in contacts:
        result = score_contact(c)
        c["_score"] = result["score"]
        c["_classe"] = result["classe"]
        c["_statut"] = result["statut"]
        c["_details"] = result["details"]
        c["_breakdown"] = result["breakdown"]
        c["_hubspot_url"] = get_contact_url(c.get("id", ""))
        scored_contacts.append(c)

    # Stats V1
    classes = {"A": 0, "B": 0, "C": 0, "D": 0}
    statuts = {"a_appeler": 0, "a_relancer": 0, "recyclage": 0, "exclu": 0}
    for c in scored_contacts:
        classes[c["_classe"]] = classes.get(c["_classe"], 0) + 1
        statuts[c["_statut"]] = statuts.get(c["_statut"], 0) + 1

    print(f"\n  Distribution des classes:")
    for cls, count in sorted(classes.items()):
        bar = "█" * (count // 50)
        print(f"    Lead {cls}: {count:>5} {bar}")

    print(f"\n  Distribution des statuts:")
    for st, count in statuts.items():
        print(f"    {st:>15}: {count:>5}")

    # 5. Training V2
    model = None
    if train_ml:
        print("\n[5/7] Entrainement du modele IA (V2)...")
        model, insights = train_model(contacts)
    else:
        print("\n[5/7] Chargement du modele existant...")
        model, insights = load_model()
        if model:
            print(f"  Modele charge (AUC: {insights.get('auc_score', 'N/A')})")
        else:
            print("  Aucun modele trouve, scoring V2 desactive")

    # 6. Scoring V2
    print("\n[6/7] Scoring V2 (predictions IA)...")
    if model:
        for c in scored_contacts:
            proba = predict_conversion(model, c)
            c["_proba_conversion"] = proba
        print("  Predictions calculees pour tous les contacts")
    else:
        for c in scored_contacts:
            c["_proba_conversion"] = None
        print("  Modele non disponible, probas = None")

    # 7. Push vers HubSpot
    if push_to_hubspot:
        print("\n[7/7] Push des scores dans HubSpot...")
        updates = []
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        for c in scored_contacts:
            props = {
                "score_ia": str(c["_score"]),
                "classe_lead": c["_classe"],
                "statut_scoring": c["_statut"],
                "score_ia_details": c["_details"][:500],  # Limite HubSpot
                "score_ia_last_update": now_iso,
            }
            if c["_proba_conversion"] is not None:
                props["score_ia_proba"] = str(c["_proba_conversion"])

            updates.append({"id": c["id"], "properties": props})

        batch_update_contacts(updates)
        print(f"  {len(updates)} contacts mis a jour dans HubSpot")
    else:
        print("\n[7/7] Push desactive (mode dry-run)")

    # Sauvegarder pour le dashboard
    print("\nSauvegarde locale pour le dashboard...")
    save_for_dashboard(scored_contacts)

    print("\n" + "=" * 60)
    print("SCORING TERMINE")
    print(f"  Contacts scores: {len(scored_contacts)}")
    print(f"  Lead A: {classes.get('A', 0)} | Lead B: {classes.get('B', 0)}")
    print(f"  A appeler: {statuts.get('a_appeler', 0)}")
    print(f"  A relancer: {statuts.get('a_relancer', 0)}")
    print(f"  Recyclage: {statuts.get('recyclage', 0)}")
    print("=" * 60)

    return scored_contacts


def save_for_dashboard(scored_contacts):
    """Sauvegarde les donnees pour le dashboard."""
    ensure_data_dir()

    # Convertir en format dashboard
    dashboard_data = []
    for c in scored_contacts:
        dashboard_data.append({
            "id": c.get("id"),
            "prenom": c.get("firstname", ""),
            "nom": c.get("lastname", ""),
            "email": c.get("email", ""),
            "telephone": c.get("phone", ""),
            "ca": c.get("chiffre_d_affaires_annuel_new", ""),
            "score": c.get("_score", 0),
            "classe": c.get("_classe", "D"),
            "statut": c.get("_statut", ""),
            "proba_conversion": c.get("_proba_conversion"),
            "details": c.get("_details", ""),
            "breakdown_profil": c.get("_breakdown", {}).get("profil", 0),
            "breakdown_funnel": c.get("_breakdown", {}).get("funnel", 0),
            "breakdown_contenu": c.get("_breakdown", {}).get("contenu", 0),
            "breakdown_email": c.get("_breakdown", {}).get("email", 0),
            "breakdown_commercial": c.get("_breakdown", {}).get("commercial", 0),
            "breakdown_malus": c.get("_breakdown", {}).get("malus", 0),
            "lead_status": c.get("hs_lead_status", ""),
            "dernier_contact": c.get("notes_last_contacted", ""),
            "calendly_event": c.get("calendly_event", ""),
            "calendly_date": c.get("calendly_date", ""),
            "nb_events": sum(
                1 for prop in [
                    "participation_au_webinaire___rb", "participation_au_webinaire___bl",
                    "participation_au_webinaire__af", "participation_au_webinaire___fm",
                    "participation_au_webinaire___mcm", "participation_au_webinaire___3dc",
                    "participation_au_webinaire___gr", "participation_au_webinaire___rns",
                    "participation_au_webinaire___webi_treso", "participation_au_webinaire___defi_dr",
                    "bm_business_max_webi_2024",
                ] if c.get(prop) == "Présent"
            ),
            "nb_leadmagnets": sum(
                1 for prop in [
                    "date_telechargement_guideca", "source_telechargement_guide_treso",
                    "date_telechargement_3focus", "source_telechargement_calculateur",
                    "source_telechargement_checklist", "date_telechargement_videosfullvaleur",
                    "date_telechargement_vsl_courte", "date_telechargement_vsl_longue",
                    "reponses_au_quizz",
                ] if c.get(prop)
            ),
            "hubspot_url": c.get("_hubspot_url", ""),
            "last_email_open": c.get("hs_email_last_open_date", ""),
            "last_email_click": c.get("hs_email_last_click_date", ""),
            "candidature": c.get("mm___candidature_effectuee", ""),
            "dr_all_time": c.get("all_time_dr", ""),
            "candidature": c.get("mm___candidature_effectuee", ""),
            "candidature_sans_rdv": (
                c.get("mm___candidature_effectuee", "") in ("Etape 2", "true", "Etape 1")
                and c.get("calendly", "") != "RDV pris"
            ),
            "owner_id": c.get("hubspot_owner_id", ""),
        })

    # Sauvegarder en JSON
    filepath = os.path.join(DATA_DIR, "scored_contacts.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "contacts": dashboard_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total": len(dashboard_data),
            "stats": {
                "lead_a": sum(1 for c in dashboard_data if c["classe"] == "A" and c["statut"] == "a_appeler"),
                "lead_b": sum(1 for c in dashboard_data if c["classe"] == "B" and c["statut"] == "a_appeler"),
                "lead_c": sum(1 for c in dashboard_data if c["classe"] == "C" and c["statut"] == "a_appeler"),
                "lead_d": sum(1 for c in dashboard_data if c["classe"] == "D"),
                "a_appeler": sum(1 for c in dashboard_data if c["statut"] == "a_appeler"),
                "a_relancer": sum(1 for c in dashboard_data if c["statut"] == "a_relancer"),
                "recyclage": sum(1 for c in dashboard_data if c["statut"] == "recyclage"),
            },
        }, f, ensure_ascii=False, indent=2)

    print(f"  Sauvegarde: {filepath} ({len(dashboard_data)} contacts)")

    # Sauvegarder l'historique
    save_history(data["stats"], data["updated_at"])


def save_history(stats, updated_at):
    """Ajoute une entree a l'historique des scorings."""
    ensure_data_dir()
    history_path = os.path.join(DATA_DIR, "scoring_history.json")

    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            history = []

    entry = {
        "date": updated_at,
        "lead_a": stats.get("lead_a", 0),
        "lead_b": stats.get("lead_b", 0),
        "lead_c": stats.get("lead_c", 0),
        "a_relancer": stats.get("a_relancer", 0),
        "recyclage": stats.get("recyclage", 0),
        "a_appeler": stats.get("a_appeler", 0),
    }

    history.append(entry)

    # Garder les 90 derniers jours max (6 runs/jour * 90 = 540 entrees)
    history = history[-540:]

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"  Historique: {len(history)} entrees")
