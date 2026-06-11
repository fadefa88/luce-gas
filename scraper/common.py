"""Utilità condivise per gli scraper di TariffaRadar."""

from __future__ import annotations

import json
import re
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"

USER_AGENT = "TariffaRadarBot/1.0 (+https://github.com/fadefa88/luce-gas)"

_session = requests.Session()
_session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.6",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
    }
)

_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


def robots_allows(url: str) -> bool:
    """True se robots.txt consente di leggere `url`."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    base = f"{parsed.scheme}://{parsed.netloc}"
    rp = _robots_cache.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.set_url(base + "/robots.txt")
            rp.read()
        except Exception:
            rp.allow_all = True
        _robots_cache[base] = rp
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def fetch(url: str, timeout: int = 25, retries: int = 2, pause: float = 1.2) -> str | None:
    """Scarica una pagina con retry, robots.txt e log non bloccanti."""
    if not url:
        return None
    if not robots_allows(url):
        print(f"  [skip] robots.txt non consente: {url}")
        return None

    last_error = None
    for attempt in range(1, retries + 2):
        try:
            response = _session.get(url, timeout=timeout)
            response.raise_for_status()
            time.sleep(pause)
            return response.text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt <= retries:
                time.sleep(pause * attempt)
    print(f"  [errore] {url}: {last_error}")
    return None


def parse_euro(text: str) -> float | None:
    """Estrae un numero italiano/anglosassone da una stringa prezzo."""
    if not text:
        return None
    match = re.search(r"(\d{1,4}(?:[.,]\d{1,5})?)", str(text))
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def norm_text(value: str, limit: int = 140) -> str:
    return " ".join((value or "").split())[:limit]


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def append_history(path: Path, record: dict, key: str = "date", keep: int = 3650) -> None:
    history: list[dict] = load_json(path, [])
    history = [r for r in history if r.get(key) != record.get(key)]
    history.append(record)
    history.sort(key=lambda r: r.get(key, ""))
    save_json(path, history[-keep:])
