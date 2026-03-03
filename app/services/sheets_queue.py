"""Pequeña cola basada en archivo para diferir exportes a Google Sheets.

- enqueue_sheet_export(): agrega una línea JSONL a logs/sheets_queue.jsonl
- flush_pending_exports(): lee el archivo, intenta exportar y reescribe con los fallidos

Esto evita llamadas a Sheets durante horario laboral; se ejecuta un flush después de las 17:00.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.sheets_service import GoogleSheetsService

BASE_DIR = Path(__file__).resolve().parent.parent.parent
QUEUE_DIR = BASE_DIR / "logs"
QUEUE_FILE = QUEUE_DIR / "sheets_queue.jsonl"
FLUSH_HOUR = int(os.environ.get("SHEETS_FLUSH_HOUR", "17"))

# Mapea el tipo lógico a la función en GoogleSheetsService
KIND_TO_METHOD = {
    "diagnostico": "exportar_diagnostico",
    "movimiento_wh": "exportar_movimiento_wh",
    "movimiento_hydro": "exportar_movimiento_hydro",
    "movimiento_legacy": "exportar_movimiento",
    "rma_aire": "exportar_rma_aire",
    "rma_hydro": "exportar_rma_hydro",
    "cambio_piezas": "exportar_cambio_piezas",
}


def enqueue_sheet_export(kind: str, payload: Dict[str, Any]) -> None:
    """Agrega un export pendiente a la cola en disco."""
    if kind not in KIND_TO_METHOD:
        raise ValueError(f"Tipo de export no soportado: {kind}")

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "kind": kind,
        "payload": payload,
        "created_at": datetime.now().isoformat(),
    }
    with QUEUE_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def _load_queue() -> List[Dict[str, Any]]:
    if not QUEUE_FILE.exists():
        return []
    entries: List[Dict[str, Any]] = []
    with QUEUE_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _write_queue(entries: List[Dict[str, Any]]) -> None:
    if not entries:
        if QUEUE_FILE.exists():
            QUEUE_FILE.unlink()
        return
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    with QUEUE_FILE.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, default=str) + "\n")


def flush_pending_exports(limit: Optional[int] = None, force: bool = False) -> Dict[str, int]:
    """Procesa la cola y exporta a Sheets; mantiene en cola los fallidos.

    Por defecto solo ejecuta desde la hora configurada (SHEETS_FLUSH_HOUR, default 17).
    """
    now = datetime.now()
    if not force and now.hour < FLUSH_HOUR:
        return {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "remaining": len(_load_queue()),
            "skipped": 1,
            "message": f"Flush permitido a partir de las {FLUSH_HOUR:02d}:00"
        }

    entries = _load_queue()
    if not entries:
        return {"processed": 0, "success": 0, "failed": 0, "remaining": 0, "skipped": 0}

    to_process = entries if limit is None else entries[:limit]
    remaining_tail = [] if limit is None else entries[limit:]

    service = GoogleSheetsService()
    processed = success = 0
    failed: List[Dict[str, Any]] = []

    for entry in to_process:
        processed += 1
        kind = entry.get("kind")
        payload = entry.get("payload", {})
        method_name = KIND_TO_METHOD.get(kind, "")
        method = getattr(service, method_name, None)

        ok = False
        try:
            if callable(method):
                ok = bool(method(payload))
        except Exception:
            ok = False

        if ok:
            success += 1
        else:
            failed.append(entry)

    new_queue = failed + remaining_tail
    _write_queue(new_queue)

    return {
        "processed": processed,
        "success": success,
        "failed": len(failed),
        "remaining": len(new_queue),
        "skipped": 0,
    }
