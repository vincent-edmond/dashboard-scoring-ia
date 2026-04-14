"""
Orchestrateur principal - Scoring IA HubSpot
Usage:
    python main.py --score              # Score V1 uniquement
    python main.py --score --train      # Score V1 + entrainement V2
    python main.py --dry-run            # Score sans push HubSpot
    python main.py --dashboard          # Lance le dashboard
    python main.py --cron               # Mode cron (tourne toutes les X heures)
"""
import argparse
import sys
import os
import time
import schedule

# Ajouter le dossier racine au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hubspot.sync import run_scoring_pipeline, run_all_segments


def run_dashboard():
    """Lance le dashboard Streamlit."""
    os.system("streamlit run dashboard/app.py --server.port 8501 --server.headless true")


def run_cron(interval_hours, train_ml=False):
    """Lance le scoring en mode cron."""
    from config.settings import SYNC_INTERVAL_HOURS
    interval = interval_hours or SYNC_INTERVAL_HOURS

    print(f"Mode cron actif - scoring toutes les {interval}h")
    print("Premier scoring maintenant...")

    # Premier run immediat
    run_all_segments(push_to_hubspot=True, train_ml=train_ml)

    # Planifier les suivants
    schedule.every(interval).hours.do(
        run_all_segments,
        push_to_hubspot=True,
        train_ml=False,  # On ne re-entraine pas a chaque cron
    )

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Scoring IA - HubSpot - Max Piccinini")
    parser.add_argument("--score", action="store_true", help="Lancer le scoring")
    parser.add_argument("--train", action="store_true", help="Entrainer le modele IA (V2)")
    parser.add_argument("--dry-run", action="store_true", help="Score sans push HubSpot")
    parser.add_argument("--dashboard", action="store_true", help="Lancer le dashboard")
    parser.add_argument("--cron", action="store_true", help="Mode cron automatique")
    parser.add_argument("--interval", type=int, default=None, help="Intervalle cron en heures")

    args = parser.parse_args()

    if args.dashboard:
        run_dashboard()
    elif args.cron:
        run_cron(args.interval, train_ml=args.train)
    elif args.score or args.dry_run:
        push = not args.dry_run
        run_all_segments(push_to_hubspot=push, train_ml=args.train)
    else:
        parser.print_help()
        print("\nExemples:")
        print("  python main.py --score --train    # Scoring complet V1+V2")
        print("  python main.py --dry-run --train  # Test sans ecrire dans HubSpot")
        print("  python main.py --dashboard        # Ouvrir le dashboard")
        print("  python main.py --cron --interval 4 --train  # Cron toutes les 4h")


if __name__ == "__main__":
    main()
