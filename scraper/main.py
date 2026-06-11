"""Entry point: python -m scraper.main

1. Offerte luce/gas  -> data/offers_energy.json  + storico medie giornaliere
2. Offerte mobile    -> data/offers_mobile.json  + storico medie giornaliere
3. Indici materia prima (PUN/PSV) -> data/history/commodity_history.json

Lo storico salva, per ogni giorno, gli aggregati (minimo / media) per non far
crescere il repository all'infinito; l'ultimo snapshot completo resta nei
file *_latest.
"""

from __future__ import annotations

import statistics
from pathlib import Path

import yaml

from .common import DATA_DIR, HISTORY_DIR, append_history, save_json, today
from .fetch_commodity import update_commodity
from .fetch_energy_offers import collect_energy_offers
from .fetch_mobile_offers import collect_mobile_offers

CONFIG = Path(__file__).parent / "config" / "providers.yaml"


def _agg(values: list[float]) -> dict:
    if not values:
        return {}
    return {
        "min": round(min(values), 4),
        "media": round(statistics.mean(values), 4),
        "n": len(values),
    }


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    print("== Offerte luce & gas ==")
    energy = collect_energy_offers(cfg.get("energia", []))
    if energy["offers"]:
        save_json(DATA_DIR / "offers_energy.json", energy)
        rec = {"date": today()}
        for c in ("luce", "gas"):
            prices = [o["prezzo_energia"] for o in energy["offers"] if o["commodity"] == c]
            if prices:
                rec[c] = _agg(prices)
        append_history(HISTORY_DIR / "energy_history.json", rec)
        print(f"  salvate {len(energy['offers'])} offerte")
    else:
        print("  nessuna offerta rilevata: mantengo l'ultimo dato valido")

    print("== Offerte mobile ==")
    mobile = collect_mobile_offers(cfg.get("mobile", []))
    if mobile["offers"]:
        save_json(DATA_DIR / "offers_mobile.json", mobile)
        rec = {
            "date": today(),
            "prezzo_mese": _agg([o["prezzo_mese"] for o in mobile["offers"]]),
            "prezzo_per_gb": _agg([o["prezzo_per_gb"] for o in mobile["offers"]]),
        }
        append_history(HISTORY_DIR / "mobile_history.json", rec)
        print(f"  salvate {len(mobile['offers'])} offerte")
    else:
        print("  nessuna offerta rilevata: mantengo l'ultimo dato valido")

    print("== Indici materia prima ==")
    update_commodity(cfg.get("commodity", {}))

    print("Fatto.")


if __name__ == "__main__":
    main()
