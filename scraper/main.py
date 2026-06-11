"""Entry point: python -m scraper.main."""

from __future__ import annotations

import statistics
from pathlib import Path

import yaml

from .common import DATA_DIR, HISTORY_DIR, append_history, load_json, now_iso, save_json, today
from .fetch_commodity import update_commodity
from .fetch_energy_offers import collect_energy_offers
from .fetch_mobile_offers import collect_mobile_offers

CONFIG = Path(__file__).parent / "config" / "providers.yaml"


def _agg(values: list[float]) -> dict:
    values = [v for v in values if isinstance(v, (int, float))]
    if not values:
        return {}
    return {
        "min": round(min(values), 4),
        "media": round(statistics.mean(values), 4),
        "n": len(values),
    }


def _write_status(payload: dict) -> None:
    save_json(DATA_DIR / "scrape_status.json", payload)


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    status = {
        "updated": now_iso(),
        "energy_saved": False,
        "mobile_saved": False,
        "notes": [],
    }

    print("== Offerte luce & gas ==")
    energy = collect_energy_offers(cfg.get("energia", []))
    status["energy_count"] = len(energy.get("offers", []))
    status["energy_source"] = energy.get("source")
    if energy.get("offers"):
        save_json(DATA_DIR / "offers_energy.json", energy)
        rec = {"date": today()}
        for commodity in ("luce", "gas"):
            prices = [o["prezzo_energia"] for o in energy["offers"] if o.get("commodity") == commodity]
            if prices:
                rec[commodity] = _agg(prices)
        append_history(HISTORY_DIR / "energy_history.json", rec)
        status["energy_saved"] = True
        print(f"  salvate {len(energy['offers'])} offerte")
    else:
        previous = load_json(DATA_DIR / "offers_energy.json", {})
        if previous.get("updated") == "DEMO":
            save_json(DATA_DIR / "offers_energy.json", {"updated": None, "source": "pending", "offers": []})
        status["notes"].append("Nessuna offerta energia rilevata; mantenuto ultimo snapshot valido se presente.")
        print("  nessuna offerta rilevata: mantengo l'ultimo dato valido")

    print("== Offerte mobile ==")
    mobile = collect_mobile_offers(cfg.get("mobile", []))
    status["mobile_count"] = len(mobile.get("offers", []))
    status["mobile_source"] = mobile.get("source")
    if mobile.get("offers"):
        save_json(DATA_DIR / "offers_mobile.json", mobile)
        rec = {
            "date": today(),
            "prezzo_mese": _agg([o["prezzo_mese"] for o in mobile["offers"]]),
            "prezzo_per_gb": _agg([o["prezzo_per_gb"] for o in mobile["offers"]]),
        }
        append_history(HISTORY_DIR / "mobile_history.json", rec)
        status["mobile_saved"] = True
        print(f"  salvate {len(mobile['offers'])} offerte")
    else:
        previous = load_json(DATA_DIR / "offers_mobile.json", {})
        if previous.get("updated") == "DEMO":
            save_json(DATA_DIR / "offers_mobile.json", {"updated": None, "source": "pending", "offers": []})
        status["notes"].append("Nessuna offerta mobile rilevata; mantenuto ultimo snapshot valido se presente.")
        print("  nessuna offerta rilevata: mantengo l'ultimo dato valido")

    print("== Indici materia prima ==")
    update_commodity(cfg.get("commodity", {}))
    _write_status(status)

    print("Fatto.")


if __name__ == "__main__":
    main()
