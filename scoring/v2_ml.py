"""
Scoring V2 - Modele IA predictif.
Entraine un modele sur les vrais clients 3MP/MM pour predire la probabilite de conversion.
"""
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder
import pickle

from config.settings import (
    PARTICIPATION_PROPERTIES, LEADMAGNET_PROPERTIES,
    CA_1M_10M, CA_10M_PLUS,
)


MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "model_v2.pkl")
INSIGHTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "insights.json")


def _days_since(date_str):
    """Calcule le nombre de jours depuis une date."""
    if not date_str:
        return None
    try:
        date_str = str(date_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(date_str)
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).days
    except (ValueError, TypeError):
        return None


def _safe_float(val, default=0):
    """Convertit en float de maniere securisee."""
    if val is None or val == "" or val == "null":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def extract_features(contact):
    """
    Extrait les features d'un contact pour le modele ML.
    Retourne un dict de features numeriques.
    """
    features = {}

    # Feature 1: CA
    ca = contact.get("chiffre_d_affaires_annuel_new", "")
    features["ca_10m_plus"] = 1 if ca == CA_10M_PLUS else 0
    features["ca_1m_10m"] = 1 if ca == CA_1M_10M else 0

    # Feature 2: Nombre de lead magnets
    features["nb_leadmagnets"] = sum(
        1 for prop in LEADMAGNET_PROPERTIES
        if contact.get(prop) and contact.get(prop) != ""
    )

    # Feature 3: Nombre de participations events
    features["nb_events"] = sum(
        1 for prop in PARTICIPATION_PROPERTIES
        if contact.get(prop) == "Présent"
    )

    # Feature 4: DR All Time
    features["dr_all_time"] = 1 if contact.get("all_time_dr") == "true" else 0

    # Feature 5: Candidature effectuee
    candidature = contact.get("mm___candidature_effectuee", "")
    features["candidature_etape2"] = 1 if candidature == "Etape 2" else 0
    features["candidature_etape1"] = 1 if candidature in ("true", "Etape 1") else 0

    # Feature 6: RDV Calendly
    calendly = contact.get("calendly", "")
    features["rdv_pris"] = 1 if calendly == "RDV pris" else 0

    calendly_event = contact.get("calendly_event", "") or ""
    features["rdv_strategique"] = 1 if ("3M" in calendly_event or "Stratégique" in calendly_event) else 0
    features["rdv_diagnostic"] = 1 if "Diagnostic" in calendly_event else 0

    # Feature 7: Fraicheur RDV
    days_rdv = _days_since(contact.get("calendly_date"))
    features["jours_depuis_rdv"] = min(days_rdv, 365) if days_rdv is not None else 365

    # Feature 8: Engagement email
    features["nb_email_open"] = _safe_float(contact.get("hs_email_open"))
    features["nb_email_click"] = _safe_float(contact.get("hs_email_click"))

    days_last_open = _days_since(contact.get("hs_email_last_open_date"))
    features["jours_depuis_ouverture"] = min(days_last_open, 365) if days_last_open is not None else 365

    days_last_click = _days_since(contact.get("hs_email_last_click_date"))
    features["jours_depuis_clic"] = min(days_last_click, 365) if days_last_click is not None else 365

    features["emails_sans_engagement"] = _safe_float(contact.get("hs_email_sends_since_last_engagement"))

    # Feature 9: Formulaires
    features["nb_formulaires"] = _safe_float(contact.get("num_unique_conversion_events"))

    # Feature 10: Fraicheur entree tunnel
    days_tunnel = _days_since(contact.get("date_d_entree_leadmagnet_mm_3m"))
    features["jours_depuis_entree_tunnel"] = min(days_tunnel, 730) if days_tunnel is not None else 730

    # Feature 11: Activite commerciale
    days_last_contact = _days_since(contact.get("notes_last_contacted"))
    features["jours_depuis_dernier_contact"] = min(days_last_contact, 730) if days_last_contact is not None else 730

    # Feature 12: Engagement candidature
    features["engagement_oui"] = 1 if contact.get("mm_3m___candidature___engagement") == "Oui" else 0

    # Feature 13: Budget
    budget = contact.get("mm_3m___candidature___budget", "") or ""
    budget_score = 0
    if "Plus de 100 000" in budget:
        budget_score = 5
    elif "50 000" in budget:
        budget_score = 4
    elif "40 000" in budget or "30 000" in budget or "25 000" in budget:
        budget_score = 3
    elif "20 000" in budget:
        budget_score = 3
    elif "10 000" in budget:
        budget_score = 2
    elif "5000" in budget or "1000" in budget:
        budget_score = 1
    elif "aucune intention" in budget.lower():
        budget_score = -2
    features["budget_score"] = budget_score

    # Feature 14: Candidature sans RDV (lead bloque dans le funnel)
    has_candidature = contact.get("mm___candidature_effectuee", "") in ("Etape 2", "true", "Etape 1")
    has_rdv = contact.get("calendly", "") == "RDV pris"
    features["candidature_sans_rdv"] = 1 if (has_candidature and not has_rdv) else 0

    # Feature 15: Source handraiser
    features["handraiser"] = 1 if contact.get("source_outbound") == "handraiser" else 0

    # Feature 15: Masterclass
    features["mc_mensuelle"] = 1 if contact.get("source_optin_masterclass_mensuelle") else 0

    # Feature 16: Optin DR
    features["optin_dr"] = 1 if contact.get("source_optin_defi_dr") else 0

    return features


def prepare_training_data(all_contacts):
    """
    Prepare les donnees d'entrainement.
    Labels : 1 = client (a achete MM/3M), 0 = prospect (n'a pas achete).
    On utilise TOUS les contacts (clients + prospects) pour entrainer.
    """
    X = []
    y = []

    for contact in all_contacts:
        features = extract_features(contact)
        X.append(features)

        # Label : est-ce un client ?
        is_client = False
        client_mm = contact.get("client_mm", "")
        client_3m = contact.get("n3m___clients", "")
        achat = contact.get("achat_produit", "") or ""

        if client_mm in ("MM Actif", "MM Non Actif", "MM En Pause"):
            is_client = True
        if client_3m in ("3M Actif", "3M Non Actif", "3M En Pause"):
            is_client = True
        if any(p in achat for p in ["3MP", "3MD", "MM"]):
            is_client = True

        y.append(1 if is_client else 0)

    df = pd.DataFrame(X)
    return df, np.array(y)


def train_model(all_contacts):
    """
    Entraine le modele predictif sur les donnees reelles.
    Retourne le modele entraine et les metriques.
    """
    print("Preparation des donnees d'entrainement...")
    X, y = prepare_training_data(all_contacts)

    n_clients = y.sum()
    n_prospects = len(y) - n_clients
    print(f"  {n_clients} clients / {n_prospects} prospects")

    if n_clients < 10:
        print("  Pas assez de clients pour entrainer un modele fiable.")
        return None, None

    # Modele : Gradient Boosting (bon pour les donnees tabulaires desequilibrees)
    model = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        min_samples_split=20,
        min_samples_leaf=10,
        subsample=0.8,
        random_state=42,
    )

    # Cross-validation
    print("  Entrainement avec cross-validation...")
    scores = cross_val_score(model, X, y, cv=5, scoring="roc_auc")
    print(f"  AUC moyenne: {scores.mean():.3f} (+/- {scores.std():.3f})")

    # Entrainement final sur toutes les donnees
    model.fit(X, y)

    # Feature importance
    feature_names = list(X.columns)
    importances = model.feature_importances_
    feature_ranking = sorted(
        zip(feature_names, importances),
        key=lambda x: x[1],
        reverse=True,
    )

    insights = {
        "auc_score": float(scores.mean()),
        "auc_std": float(scores.std()),
        "n_clients": int(n_clients),
        "n_prospects": int(n_prospects),
        "feature_importance": [
            {"feature": name, "importance": float(imp)}
            for name, imp in feature_ranking[:15]
        ],
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    # Sauvegarder le modele et les insights
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "features": feature_names}, f)
    print(f"  Modele sauvegarde: {MODEL_PATH}")

    with open(INSIGHTS_PATH, "w") as f:
        json.dump(insights, f, indent=2, ensure_ascii=False)
    print(f"  Insights sauvegardes: {INSIGHTS_PATH}")

    # Afficher le top features
    print("\n  Top 10 features les plus importantes:")
    for name, imp in feature_ranking[:10]:
        bar = "█" * int(imp * 100)
        print(f"    {name:35s} {imp:.3f} {bar}")

    return model, insights


def load_model():
    """Charge le modele sauvegarde."""
    if not os.path.exists(MODEL_PATH):
        return None, None
    with open(MODEL_PATH, "rb") as f:
        data = pickle.load(f)
    insights = None
    if os.path.exists(INSIGHTS_PATH):
        with open(INSIGHTS_PATH, "r") as f:
            insights = json.load(f)
    return data["model"], insights


def predict_conversion(model, contact):
    """
    Predit la probabilite de conversion d'un contact.
    Retourne un float entre 0 et 1 (probabilite).
    """
    if model is None:
        return None

    features = extract_features(contact)
    df = pd.DataFrame([features])

    proba = model.predict_proba(df)[0][1]  # Probabilite de la classe 1 (client)
    return round(float(proba) * 100, 1)  # En pourcentage
