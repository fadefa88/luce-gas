"""Indici materia prima v2.

Elettricità: API pubblica Energy-Charts, senza chiave. Il valore salvato è la
media semplice delle zone italiane disponibili, usata come proxy del PUN.
Gas/PSV: import opzionale tramite data/manual_commodity.csv.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone

from .common import DATA_DIR, HISTORY_DIR, append_history, fetch_json, load_json, now_iso, report, save_json


def _zone_daily_avg(base: str, zone: str, start: str, end: str) -> dict[str, list[float]]:
    data = fetch_json(f"{base}?bzn={zone}&start={start}&end={end}")
    if not data:
        data = fetch_json(f"{base}?bzn={zone}")
    out: dict[str, list[float]] = {}
    if not data or "unix_seconds" not in data:
        return out
    for ts, price in zip(data.get("unix_seconds", []), data.get("price", [])):
        if price is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        out.setdefault(day, []).append(float(price))
    return out


def fetch_electricity_days(cfg: dict, start: str, end: str) -> dict[str, float]:
    base = cfg.get("energy_charts_base", "https://api.energy-charts.info/price")
    zones = cfg.get("it_zones", ["IT-North"])
    per_day: dict[str, list[float]] = {}
    zones_ok = 0
    for zone in zones:
        zone_days = _zone_daily_avg(base, zone, start, end)
        if zone_days:
            zones_ok += 1
            for day, prices in zone_days.items():
                per_day.setdefault(day, []).append(sum(prices) / len(prices))
    if zones_ok < int(cfg.get("min_zones", 1)):
        return {}
    return {
        day: round((sum(values) / len(values)) / 1000, 5)
        for day, values in per_day.items()
        if 0.01 <= (sum(values) / len(values)) / 1000 <= 1.0
    }


def _manual_overrides() -> dict[str, dict]:
    path = DATA_DIR / "manual_commodity.csv"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            rec = {}
            if row.get("pun"):
                rec["pun_eur_kwh"] = float(row["pun"])
            if row.get("psv"):
                rec["psv_eur_smc"] = float(row["psv"])
            if rec:
                out[row["date"].strip()] = rec
    return out


def update_commodity(cfg: dict) -> None:
    history_path = HISTORY_DIR / "commodity_history.json"
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")

    days = fetch_electricity_days(cfg, start, end)
    if days:
        for day, value in sorted(days.items()):
            append_history(history_path, {"date": day, "pun_eur_kwh": value})
        last = sorted(days)[-1]
        report("energy_charts", "ok", f"ultimo {last}: {days[last]} €/kWh", n=len(days))
        print(f"  elettricità Energy-Charts: {len(days)} giorni, ultimo {last}={days[last]} €/kWh")
    else:
        report("energy_charts", "errore", "API non raggiungibile o vuota")
        print("  elettricità non disponibile in questo giro")

    overrides = _manual_overrides()
    if overrides:
        for date, rec in overrides.items():
            append_history(history_path, {"date": date, **rec})
        print(f"  importati {len(overrides)} record manuali")

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
