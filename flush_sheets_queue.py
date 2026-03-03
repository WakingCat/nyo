"""Ejecuta el flush de la cola de exportes a Google Sheets.

Uso:
    python flush_sheets_queue.py           # Procesa todo
    python flush_sheets_queue.py --limit 100

Ideal para correrlo a las 17:00 via cron/systemd timer.
"""
import argparse

from app import create_app
from app.services.sheets_queue import flush_pending_exports

app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Flush de exportes pendientes a Google Sheets")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de eventos a procesar en esta ejecución")
    parser.add_argument("--force", action="store_true", help="Forzar flush aunque sea antes de la hora configurada")
    args = parser.parse_args()

    with app.app_context():
        result = flush_pending_exports(limit=args.limit, force=args.force)
        print(
            f"Procesados: {result['processed']} | OK: {result['success']} | "
            f"Fallidos: {result['failed']} | Quedan: {result['remaining']}"
        )
        if result.get('skipped'):
            print(result.get('message', 'Ejecución omitida por ventana horaria'))


if __name__ == "__main__":
    main()
