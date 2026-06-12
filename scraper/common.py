"""Utility condivise per TariffaRadar v2.2.

Aggiunge fetch con rendering Playwright, auto-discovery via sitemap, report
fonti, dump HTML di debug, gestione cookie banner/lazy-load e backoff anti-429.
"""

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
DEBUG_DIR = ROOT / "debug"

USER_AGENT = "TariffaRadarBot/2.2 (+https://github.com/fadefa88/luce-gas)"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/124.0 Safari/537.36 TariffaRadarBot/2.2"
)

REPORT: dict[str, dict] = {}
_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "it-IT,it;q=0.9,en;q=0.6"})
_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
_playwright = None
_browser = None


def robots_allows(url: str) -> bool:
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


def fetch(url: str, timeout: int = 25, retries: int = 1, pause: float = 1.0) -> str | None:
    if not url:
        return None
    if not robots_allows(url):
        print(f"  [skip] robots.txt non consente: {url}")
        return None
    last_error = None
    for attempt in range(1, retries + 2):
        try:
            response = _session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            time.sleep(pause)
            return response.text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt <= retries:
                time.sleep(pause * attempt)
    print(f"  [http] {url}: {last_error}")
    return None


def fetch_json(url: str, timeout: int = 25, retries: int = 3, pause: float = 1.5):
    """GET JSON con throttling e backoff sul 429."""
    for attempt in range(retries):
        try:
            time.sleep(pause)
            response = _session.get(url, timeout=timeout)
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", 0)) or 20 * (attempt + 1)
                print(f"  [429] rate limit, attendo {wait}s ({url})")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"  [http] {url}: {exc}")
            if attempt == retries - 1:
                return None
            time.sleep(5 * (attempt + 1))
    return None


def _looks_js_only(html: str) -> bool:
    text = re.sub(r"<script.*?</script>", "", html or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return len(text.split()) < 150


CONSENT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "#didomi-notice-agree-button",
    ".iubenda-cs-accept-btn",
    "button[data-testid*=accept]",
    "button[id*=accept i], button[class*=accept i]",
    "button:has-text('Accetta tutt')",
    "button:has-text('Accetta')",
    "button:has-text('Accetto')",
]


def fetch_rendered(url: str, timeout_ms: int = 35000) -> str | None:
    """Scarica una pagina con Chromium headless.

    Gestisce due ostacoli comuni:
    - banner cookie che bloccano l'idratazione dei contenuti;
    - contenuti lazy-load, facendo scroll progressivo.
    """
    global _playwright, _browser
    if not robots_allows(url):
        return None
    try:
        if _browser is None:
            from playwright.sync_api import sync_playwright
            _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(headless=True)
        page = _browser.new_page(
            user_agent=BROWSER_UA,
            locale="it-IT",
            viewport={"width": 1366, "height": 900},
        )
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        for selector in CONSENT_SELECTORS:
            try:
                button = page.locator(selector).first
                if button.is_visible(timeout=400):
                    button.click(timeout=1500)
                    page.wait_for_timeout(1200)
                    break
            except Exception:
                continue
        for fraction in (0.35, 0.7, 1.0):
            try:
                page.evaluate(f"window.scrollTo(0, document.body.scrollHeight*{fraction})")
                page.wait_for_timeout(900)
            except Exception:
                break
        page.wait_for_timeout(1500)
        html = page.content()
        page.close()
        return html
    except Exception as exc:  # noqa: BLE001
        print(f"  [playwright] {url}: {exc}")
        return None


def fetch_page(urls: list[str], render: str = "auto") -> tuple[str | None, str | None]:
    for url in urls:
        if render == "always":
            html = fetch_rendered(url)
        else:
            html = fetch(url)
            if html and render == "auto" and _looks_js_only(html):
                print("  [info] pagina quasi vuota: provo rendering Playwright")
                html = fetch_rendered(url) or html
        if html:
            return html, url
    return None, None


def discover_offers_url(base: str, keywords: list[str]) -> str | None:
    for sitemap in (f"{base}/sitemap.xml", f"{base}/sitemap_index.xml"):
        xml = fetch(sitemap)
        if not xml:
            continue
        urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        for candidate in urls[:600]:
            low = candidate.lower()
            if any(str(k).lower() in low for k in keywords):
                print(f"  [discover] {candidate}")
                return candidate
    return None


def report(source_id: str, status: str, detail: str = "", n: int = 0) -> None:
    REPORT[source_id] = {"status": status, "detail": detail, "n": n, "checked": now_iso()}


def save_report() -> None:
    save_json(DATA_DIR / "scrape_report.json", {"updated": now_iso(), "sources": REPORT})


def dump_debug(source_id: str, html: str | None) -> None:
    if not html:
        return
    DEBUG_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", source_id)[:80]
    (DEBUG_DIR / f"{safe}.html").write_text(html[:800000], encoding="utf-8")


def close_browser() -> None:
    global _playwright, _browser
    try:
        if _browser:
            _browser.close()
        if _playwright:
            _playwright.stop()
    except Exception:
        pass
    _browser = None
    _playwright = None


def parse_euro(text: str) -> float | None:
    match = re.search(r"(\d{1,4}(?:[.,]\d{1,5})?)", text or "")
    return float(match.group(1).replace(",", ".")) if match else None


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
    merged = {r.get(key): r for r in history}
    current = merged.get(record.get(key), {})
    current.update(record)
    merged[record.get(key)] = current
    out = sorted(merged.values(), key=lambda r: r.get(key, ""))
    save_json(path, out[-keep:])
