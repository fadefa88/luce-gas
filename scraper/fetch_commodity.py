"""Indici della materia prima: PUN (energia elettrica) e PSV (gas).

- PUN: il GME pubblica i prezzi orari del Mercato del Giorno Prima in XML
  pubblico. Si calcola la media giornaliera (PUN medio) e la si salva nello
  storico (data/history/commodity_history.json).
- PSV/gas: il GME pubblica anche gli esiti del mercato gas; in alternativa
  (o per importare lo storico passato) si può fornire un CSV manuale in
  data/manual_commodity.csv con intestazione: date,pun,psv
  (pun in €/kWh, psv in €/Smc). I valori manuali hanno la precedenza.

Conversioni usate per confrontare con le offerte retail:
  PUN €/MWh  -> €/kWh  : /1000
  PSV €/MWh  -> €/Smc  : *0.01055  (1 Smc ≈ 10,55 kWh termici)
"""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from .common import DATA_DIR, HISTORY_DIR, append_history, fetch, load_json, save_json, now_iso

MWH_PER_SMC = 0.01055


def _gme_day_url(template: str, day: datetime) -> str:
    return template.format(date=day.strftime("%Y%m%d"))


def _parse_pun_xml(xml_text: str) -> float | None:
    """Media giornaliera del PUN (€/MWh) dall'XML MGP Prezzi del GME."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    values: list[float] = []
    for el in root.iter():
        if el.tag.upper().endswith("PUN") and el.text:
            txt = el.text.strip().replace(".", "").replace(",", ".")
            # i decimali GME usano la virgola; il punto è separatore migliaia
            m = re.match(r"^\d+(\.\d+)?$", txt)
            if m:
                values.append(float(txt))
    if not values:
        return None
    return sum(values) / len(values)


def _manual_overrides() -> dict[str, dict]:
    """CSV opzionale data/manual_commodity.csv -> {date: {pun, psv}}."""
    path = DATA_DIR / "manual_commodity.csv"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rec = {}
            if row.get("pun"):
                rec["pun_eur_kwh"] = float(row["pun"])
            if row.get("psv"):
                rec["psv_eur_smc"] = float(row["psv"])
            if rec:
                out[row["date"].strip()] = rec
    return out


def update_commodity(config: dict) -> None:
    history_path = HISTORY_DIR / "commodity_history.json"
    today = datetime.now(timezone.utc)

    # 1) PUN dal GME: si tenta oggi e ieri (l'XML del giorno esce in giornata)
    template = config.get("pun_xml_template", "")
    pun_eur_kwh = None
    pun_date = None
    for delta in (0, 1):
        day = today - timedelta(days=delta)
        xml = fetch(_gme_day_url(template, day)) if template else None
        if xml:
            pun_mwh = _parse_pun_xml(xml)
            if pun_mwh and 10 <= pun_mwh <= 1000:
                pun_eur_kwh = round(pun_mwh / 1000, 5)
                pun_date = day.strftime("%Y-%m-%d")
                break

    if pun_eur_kwh and pun_date:
        existing = {r["date"]: r for r in load_json(history_path, [])}
        rec = existing.get(pun_date, {"date": pun_date})
        rec["pun_eur_kwh"] = pun_eur_kwh
        append_history(history_path, rec)
        print(f"  PUN {pun_date}: {pun_eur_kwh} €/kWh")
    else:
        print("  PUN non disponibile in questo giro (ok: si ritenta tra un'ora)")

    # 2) Override / integrazioni manuali (incluso PSV e storico passato)
    overrides = _manual_overrides()
    if overrides:
        existing = {r["date"]: r for r in load_json(history_path, [])}
        for date, rec in overrides.items():
            merged = existing.get(date, {"date": date})
            merged.update(rec)
            append_history(history_path, merged)
        print(f"  importati {len(overrides)} record manuali (manual_commodity.csv)")

    # 3) Indice "ultimo valore" comodo per il frontend
    history = load_json(history_path, [])
    latest = {"updated": now_iso()}
    for rec in reversed(history):
        if "pun_eur_kwh" in rec and "pun" not in latest:
            latest["pun"] = {"date": rec["date"], "eur_kwh": rec["pun_eur_kwh"]}
        if "psv_eur_smc" in rec and "psv" not in latest:
            latest["psv"] = {"date": rec["date"], "eur_smc": rec["psv_eur_smc"]}
        if "pun" in latest and "psv" in latest:
            break
    save_json(DATA_DIR / "commodity_latest.json", latest)
