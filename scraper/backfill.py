from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .common import HISTORY_DIR, append_history
from .fetch_commodity import fetch_electricity_days

CONFIG = Path(__file__).parent / "config" / "providers.yaml"


def main() -> None:
    start_str = sys.argv[1] if len(sys.argv) > 1 else "2024-01-01"
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")).get("commodity", {})
    start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc)
    history_path = HISTORY_DIR / "commodity_history.json"

    current = start
    total = 0
    while current < today:
        chunk_end = min(current + timedelta(days=60), today)
        days = fetch_electricity_days(cfg, current.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"))
        for day, value in sorted(days.items()):
            append_history(history_path, {"date": day, "pun_eur_kwh": value})
        total += len(days)
        print(f"{current:%Y-%m-%d} / {chunk_end:%Y-%m-%d}: {len(days)} giorni")
        current = chunk_end
    print(f"Completato: {total} giorni totali.")


if __name__ == "__main__":
    main()
