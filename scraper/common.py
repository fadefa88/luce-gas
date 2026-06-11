"""Utilità condivise per gli scraper di TariffaRadar.

Principi:
- Si visita SOLO la pagina pubblica principale delle offerte di ogni operatore
  (nessuna navigazione in profondità, nessun dato personale, nessun login).
- Si rispetta robots.txt: se la pagina è disallow, l'operatore viene saltato.
- Richieste rade (il workflow gira 1 volta/ora) con User-Agent trasparente.
"""

from __future__ import annotations

import json
import re
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"

USER_AGENT = (
    "TariffaRadarBot/1.0 (+https://github.com/TUO-UTENTE/tariffaradar; "
    "confronto offerte non commerciale; contatti nel repository)"
)

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "it-IT,it;q=0.9"})

_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


def robots_allows(url: str) -> bool:
    """True se robots.txt del dominio consente di leggere `url`."""
    m = re.match(r"(https?://[^/]+)", url)
    if not m:
        return False
    base = m.group(1)
    rp = _robots_cache.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.set_url(base + "/robots.txt")
            rp.read()
        except Exception:
            # robots.txt irraggiungibile: prudenza, ma non blocchiamo
            rp.allow_all = True
        _robots_cache[base] = rp
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def fetch(url: str, timeout: int = 25) -> str | None:
    """Scarica una pagina rispettando robots.txt. Ritorna None in caso di problemi."""
    if not robots_allows(url):
        print(f"  [skip] robots.txt non consente: {url}")
        return None
    try:
        r = _session.get(url, timeout=timeout)
        r.raise_for_status()
        time.sleep(1.5)  # cortesia tra una richiesta e l'altra
        return r.text
    except Exception as exc:  # noqa: BLE001
        print(f"  [errore] {url}: {exc}")
        return None


def parse_euro(text: str) -> float | None:
    """Estrae un numero in formato italiano (12,34) o anglosassone (12.34)."""
    m = re.search(r"(\d{1,4}(?:[.,]\d{1,4})?)", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def append_history(path: Path, record: dict, key: str = "date", keep: int = 3650) -> None:
    """Aggiunge/aggiorna il record del giorno in uno storico JSON (lista)."""
    history: list[dict] = load_json(path, [])
    history = [r for r in history if r.get(key) != record.get(key)]
    history.append(record)
    history.sort(key=lambda r: r.get(key, ""))
    save_json(path, history[-keep:])
