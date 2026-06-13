"""lib/base.py — fondamenta condivise da tutti gli scraper per-fornitore.

Filosofia della nuova architettura:
- Ogni fornitore ha UN proprio modulo in providers/<categoria>/<id>.py che
  espone una funzione scrape() -> list[Offer]. La logica è isolata: se Iliad
  cambia pagina, si tocca SOLO providers/mobile/iliad.py.
- Ogni fornitore ha la SUA GitHub Action, quindi un fornitore rotto non
  blocca gli altri e si rilancia/aggiusta singolarmente.
- Ogni run scrive data/providers/<categoria>__<id>.json (il "frammento" del
  fornitore). Un aggregatore li unisce in data/offers_mobile.json ecc.

Questo file fornisce: fetch HTML (requests con fallback Playwright),
helper di parsing, il dataclass Offer e il salvataggio standardizzato del
frammento con stato (ok / vuoto / errore) per la diagnostica nel sito.
"""

from __future__ import annotations

import json
import re
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
FRAGMENTS_DIR = ROOT / "data" / "providers"
DEBUG_DIR = ROOT / "debug"

DESKTOP_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 TariffaRadarBot/5.0 (+contatti nel repo)"
)

_session = requests.Session()
_session.headers.update({"User-Agent": DESKTOP_UA, "Accept-Language": "it-IT,it;q=0.9"})


# --------------------------------------------------------------------------
# Modello dati
# --------------------------------------------------------------------------
@dataclass
class Offer:
    """Un'offerta normalizzata. I campi non pertinenti restano None/''."""
    operatore: str
    offerta: str
    url: str
    # --- mobile ---
    prezzo_mese: float | None = None
    giga: int | None = None
    giga_illimitati: bool = False
    prezzo_per_gb: float | None = None
    attivazione: float | None = None
    minuti: str = ""
    sms: str = ""
    rete_5g: bool = True
    # --- luce / gas ---
    commodity: str = ""              # "luce" | "gas"
    prezzo_energia: float | None = None
    quota_fissa_mese: float | None = None
    tipo: str = ""                   # "fisso" | "variabile"
    indice: str = ""                 # "PUN" | "PSV" (se a spread)
    spread: float | None = None
    # --- comune ---
    note: str = ""
    fonte: str = "scraping"

    def finalize(self) -> "Offer":
        if self.prezzo_mese and self.giga and not self.giga_illimitati:
            self.prezzo_per_gb = round(self.prezzo_mese / self.giga, 3)
        return self


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------
def fetch_html(url: str, timeout: int = 25) -> str | None:
    """GET semplice via requests."""
    try:
        r = _session.get(url, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as exc:  # noqa: BLE001
        print(f"  [http] {url}: {exc}")
        return None


def fetch_mobile_page(url: str, wait_selector: str | None = None,
                      clicks: list[str] | None = None,
                      timeout: int = 25) -> tuple[str | None, list]:
    """Fetch robusto per pagine offerte mobile.

    Prova prima l'HTML statico via requests, perché molti siti espongono già
    offerte nel markup e Playwright può essere fragile/lento. Se l'HTML non
    contiene segnali utili (GB/Giga + mese), usa Playwright come fallback
    tecnico e cattura eventuali JSON interni. Non usa dati manuali.
    """
    html = fetch_html(url, timeout=timeout)
    if html:
        low = html.lower()
        if ("giga" in low or "gb" in low or "illimitat" in low) and "mese" in low:
            return html, []

    rendered, xhr = fetch_rendered(url, wait_selector=wait_selector, clicks=clicks)
    if rendered:
        return rendered, xhr
    return html, []


def fetch_rendered(url: str, wait_selector: str | None = None,
                   clicks: list[str] | None = None,
                   timeout_ms: int = 40000) -> tuple[str | None, list]:
    """Rendering con Playwright. Ritorna (html, payload_json_catturati).

    - clicks: lista di selettori da cliccare in sequenza (es. tab "altro
      operatore", accettazione cookie) prima di leggere il contenuto.
    - wait_selector: attende che compaia, se indicato.
    Cattura anche le risposte JSON delle API interne (utile per le SPA).
    """
    xhr: list = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("  [playwright] non installato in questo ambiente")
        return None, xhr
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=DESKTOP_UA, locale="it-IT",
                                    viewport={"width": 1366, "height": 900})

            def _cap(resp):
                try:
                    if len(xhr) < 50 and resp.status == 200 \
                            and "json" in resp.headers.get("content-type", ""):
                        xhr.append(resp.json())
                except Exception:
                    pass

            page.on("response", _cap)
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            _accept_cookies(page)
            for sel in (clicks or []):
                try:
                    page.locator(sel).first.click(timeout=4000)
                    page.wait_for_timeout(1800)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [click] '{sel}' non riuscito: {exc}")
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=8000)
                except Exception:
                    pass
            for frac in (0.4, 0.8, 1.0):
                try:
                    page.evaluate(f"window.scrollTo(0,document.body.scrollHeight*{frac})")
                    page.wait_for_timeout(800)
                except Exception:
                    break
            html = page.content()
            browser.close()
            return html, xhr
    except Exception as exc:  # noqa: BLE001
        print(f"  [playwright] {url}: {exc}")
        return None, xhr


_CONSENT = [
    "#onetrust-accept-btn-handler", "#didomi-notice-agree-button",
    ".iubenda-cs-accept-btn", "button[data-testid*=accept]",
    "button:has-text('Accetta tutt')", "button:has-text('Accetta')",
    "button:has-text('Accetto')", "button:has-text('OK')",
]


def _accept_cookies(page) -> None:
    for sel in _CONSENT:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=400):
                btn.click(timeout=1500)
                page.wait_for_timeout(1000)
                return
        except Exception:
            continue


# --------------------------------------------------------------------------
# Helper di parsing (riusabili, ma ogni provider può ignorarli)
# --------------------------------------------------------------------------
def euro(s: str) -> float | None:
    m = re.search(r"(\d{1,4})[.,](\d{1,2})", s or "")
    return float(f"{m.group(1)}.{m.group(2)}") if m else None


def giga(s: str) -> int | None:
    m = re.search(r"(\d{1,4})\s*(?:GB|Giga)", s or "", re.I)
    if m:
        g = int(m.group(1))
        return g if 1 <= g <= 2000 else None
    return None


# --------------------------------------------------------------------------
# Salvataggio del frammento + runner standard
# --------------------------------------------------------------------------
def _fragment_path(category: str, provider_id: str) -> Path:
    return FRAGMENTS_DIR / f"{category}__{provider_id}.json"


def save_fragment(category: str, provider_id: str, operator: str,
                  offers: list[Offer], status: str, detail: str = "") -> None:
    FRAGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "operatore": operator,
        "categoria": category,
        "provider_id": provider_id,
        "status": status,                 # ok | vuoto | errore
        "detail": detail,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "offers": [asdict(o.finalize()) for o in offers],
    }
    _fragment_path(category, provider_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  -> salvato {category}__{provider_id}.json "
          f"({status}, {len(offers)} offerte)")


def dump_debug(provider_id: str, html: str | None) -> None:
    if not html:
        return
    DEBUG_DIR.mkdir(exist_ok=True)
    (DEBUG_DIR / f"{provider_id}.html").write_text(html[:900_000], encoding="utf-8")


def run_provider(category: str, provider_id: str, operator: str, scrape_fn) -> int:
    """Esegue lo scrape di un fornitore, salva il frammento, non solleva mai
    (così l'Action del singolo fornitore fallisce solo per problemi veri).
    Ritorna il numero di offerte trovate."""
    print(f"== {operator} [{category}/{provider_id}] ==")
    try:
        offers = [o for o in (scrape_fn() or []) if o]
        if offers:
            save_fragment(category, provider_id, operator, offers, "ok")
        else:
            save_fragment(category, provider_id, operator, [], "vuoto",
                          "nessuna offerta estratta (vedi artifact debug)")
        return len(offers)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        save_fragment(category, provider_id, operator, [], "errore",
                      f"{type(exc).__name__}: {exc}"[:200])
        return 0


def cli_main(category: str, provider_id: str, operator: str, scrape_fn) -> None:
    """Punto d'ingresso standard: `python -m providers.mobile.iliad`."""
    n = run_provider(category, provider_id, operator, scrape_fn)
    # exit 0 sempre: il frammento registra lo stato; l'Action resta verde
    # anche quando un sito è temporaneamente vuoto, ma il sito lo segnala.
    sys.exit(0)
