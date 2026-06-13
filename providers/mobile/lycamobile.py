"""Lycamobile — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.lycamobile.it/it/offerte-mobile-5g/

Niente fallback manuali. Lycamobile usa markup/JS poco stabile e prezzi spesso in
formati diversi dal parser generico, ad esempio €5.99, 5,99€, /30 giorni o mese.
Questo scraper:
- prova HTML statico;
- se non trova offerte, forza Playwright/rendering;
- legge testo visibile, script JSON e XHR catturati.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page, fetch_rendered
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.lycamobile.it/it/offerte-mobile-5g/"
OPERATORE = "Lycamobile"

GB = re.compile(r"(\d{1,4})\s*(?:GB|Giga)\b", re.I)
UNLIMITED = re.compile(r"(?:GB|Giga)\s+illimitat[io]|illimitat[io]\s+(?:GB|Giga)", re.I)
PRICE_DEC = re.compile(
    r"(?:€\s*)?(\d{1,3})\s*[,\.]\s*(\d{2})\s*€?\s*(?:/\s*(?:mese|month|30\s*giorni)|al\s*mese|mese|month|30\s*giorni)?",
    re.I,
)
PRICE_INT = re.compile(r"€\s*(\d{1,3})\s*(?:/\s*(?:mese|month|30\s*giorni)|al\s*mese|mese|month)?", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)
EXCLUDE = re.compile(r"ricarica|top\s*up|credito|roaming|sim\s+only\s+plans\s+uk|business|terms|condizioni", re.I)
NAME_HINT = re.compile(r"(?:Italy|Italia|Lyca|Globe|National|International|Data|5G|Bundle|Pass|Plan)", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _visible_lines(html: str) -> list[str]:
    soup = _soup(html)
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [x for x in (_clean(v) for v in soup.get_text("\n", strip=True).splitlines()) if x and x not in {"*", "•", "|"}]


def _price(text: str) -> float | None:
    # Richiedi almeno un segnale temporale o euro vicino per ridurre falsi positivi.
    low = text.lower()
    if "€" not in text and not re.search(r"mese|month|30\s*giorni", low):
        return None
    if m := PRICE_DEC.search(text):
        value = float(f"{m.group(1)}.{m.group(2)}")
        return value if 1 <= value <= 80 else None
    if m := PRICE_INT.search(text):
        value = float(m.group(1))
        return value if 1 <= value <= 80 else None
    return None


def _pick_giga(text: str) -> tuple[int | None, bool]:
    if UNLIMITED.search(text):
        return None, True
    vals = [int(v) for v in GB.findall(text) if 1 <= int(v) <= 2000]
    if not vals:
        return None, False
    # Nelle card Lyca il primo GB rilevante è quasi sempre il bundle nazionale.
    return vals[0], False


def _sms(text: str) -> str:
    if re.search(r"SMS[^.;]{0,50}illimitat|illimitat[^.;]{0,50}SMS", text, re.I):
        return "illimitati"
    if m := SMS.search(text):
        return m.group(1)
    return ""


def _minutes(text: str) -> str:
    if re.search(r"minuti[^.;]{0,80}illimitat|illimitat[^.;]{0,80}minuti|calls?[^.;]{0,80}unlimited|unlimited[^.;]{0,80}calls?", text, re.I):
        return "illimitati"
    if m := re.search(r"(\d{1,5})\s*(?:minuti|minutes)", text, re.I):
        return m.group(1)
    return ""


def _name_from_block(lines: list[str]) -> str:
    for candidate in lines[:8]:
        c = _clean(candidate)
        if not c or len(c) > 90:
            continue
        if PRICE_DEC.search(c) or PRICE_INT.search(c) or GB.fullmatch(c):
            continue
        if re.search(r"acquista|buy|scopri|details|mese|month|sms|minuti|minutes", c, re.I):
            continue
        if NAME_HINT.search(c) or re.search(r"^[A-Z][A-Za-z0-9 +\-]{2,}$", c):
            return c[:80]
    giga, unlimited = _pick_giga(" ".join(lines))
    return "Giga illimitati" if unlimited else (f"{giga} GB" if giga else "Offerta Lycamobile")


def _offer_from_block(block_lines: list[str]) -> Offer | None:
    block = _clean(" ".join(block_lines))
    if len(block) < 12 or EXCLUDE.search(block):
        return None
    price = _price(block)
    if price is None:
        return None
    giga, unlimited = _pick_giga(block)
    if giga is None and not unlimited:
        return None

    # Scarta condizioni legali/roaming: se manca qualsiasi riferimento a dati o chiamate reali, non è card.
    if not re.search(r"GB|Giga|illimit|minuti|minutes|calls?|SMS", block, re.I):
        return None

    return Offer(
        operatore=OPERATORE,
        offerta=_name_from_block(block_lines),
        url=URL,
        prezzo_mese=price,
        giga=None if unlimited else giga,
        giga_illimitati=unlimited,
        attivazione=None,
        minuti=_minutes(block),
        sms=_sms(block),
        rete_5g=bool(re.search(r"\b5G\b|full\s*speed", block, re.I)),
        note="30 giorni" if re.search(r"30\s*giorni", block, re.I) else "",
        fonte="scraping",
    )


def _parse_lines(html: str) -> list[Offer]:
    lines = _visible_lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    # Cerca blocchi intorno a ogni prezzo. È più robusto dei selettori perché Lyca cambia classi spesso.
    for i, line in enumerate(lines):
        nearby = _clean(" ".join(lines[i:i + 3]))
        if _price(nearby) is None and _price(line) is None:
            continue

        start = max(0, i - 10)
        end = min(len(lines), i + 12)
        block_lines = lines[start:end]
        offer = _offer_from_block(block_lines)
        if not offer:
            continue
        key = (round(offer.prezzo_mese or 0, 2), offer.giga, offer.giga_illimitati)
        if key in seen:
            continue
        seen.add(key)
        offers.append(offer)

    return offers


def _walk_json(node: Any):
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            stack.extend(x for x in cur if isinstance(x, (dict, list)))


def _json_candidates(html: str) -> list[Any]:
    soup = _soup(html)
    out: list[Any] = []
    for script in soup.find_all("script"):
        txt = script.string or script.get_text(" ", strip=True)
        if not txt or not re.search(r"gb|giga|price|prezzo|bundle|lyca", txt, re.I):
            continue
        stripped = txt.strip()
        # JSON puro, ad esempio application/json o __NEXT_DATA__.
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                out.append(json.loads(stripped))
                continue
            except Exception:
                pass
        # Oggetti assegnati a variabili: estrai pezzi JSON ragionevoli.
        for m in re.finditer(r"(\{[^{}]{0,4000}(?:price|prezzo|gb|giga|bundle)[^{}]{0,4000}\})", stripped, re.I):
            try:
                out.append(json.loads(m.group(1)))
            except Exception:
                continue
    return out


def _parse_json(html: str) -> list[Offer]:
    offers = mine_xhr_mobile(_json_candidates(html), OPERATORE, URL)
    # Lyca può avere offerte 4G/5G; non filtro 5G, salvo il flag se presente.
    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_lines(html)
    if offers:
        return offers

    offers = _parse_json(html)
    if offers:
        return offers

    offers = parse_cards(html, OPERATORE, URL)
    if offers:
        return offers

    if xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("lycamobile", html)
    if html:
        offers = parse_html(html, xhr)
        if offers:
            return offers

    # Fallback tecnico: se l'HTML statico è incompleto, forza rendering.
    rendered, rendered_xhr = fetch_rendered(URL)
    dump_debug("lycamobile_rendered", rendered)
    if not rendered:
        return []
    return parse_html(rendered, rendered_xhr)


if __name__ == "__main__":
    cli_main("mobile", "lycamobile", OPERATORE, scrape)
