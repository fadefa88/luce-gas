"""Optima Mobile — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.optimaitalia.com/mobile

Niente fallback manuali. La pagina Optima puo' mischiare mobile, casa, energia e
bundle; il parser quindi cerca solo blocchi con segnali mobile reali:
Giga/GB + prezzo mensile + SIM/mobile/minuti/SMS. Se l'HTML statico non basta,
forza un rendering Playwright.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page, fetch_rendered
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.optimaitalia.com/mobile"
OPERATORE = "Optima Mobile"

GB = re.compile(r"(\d{1,4})\s*(?:GB|Giga)\b", re.I)
UNLIMITED = re.compile(r"(?:GB|Giga)\s+illimitat[io]|illimitat[io]\s+(?:GB|Giga)", re.I)
PRICE = re.compile(
    r"(?:€\s*)?(\d{1,3})\s*[,\.]\s*(\d{2})\s*€?\s*(?:/\s*mese|al\s*mese|mese|mensil|/\s*30\s*giorni)?",
    re.I,
)
PRICE_INT = re.compile(r"€\s*(\d{1,3})\s*(?:/\s*mese|al\s*mese|mese|mensil)?", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)
ACTIVATION = re.compile(r"attivazione[^\d€]{0,40}(?:€\s*)?(\d{1,3})\s*[,\.]\s*(\d{2})", re.I)
ACTIVATION_INT = re.compile(r"attivazione[^\d€]{0,40}(?:€\s*)?(\d{1,3})\s*€", re.I)
EXCLUDE = re.compile(
    r"luce|gas|energia|fibra|internet\s+casa|modem|router|assicurazione|smartphone|iphone|galaxy|tablet|business|partita\s+iva",
    re.I,
)
MOBILE_SIGNAL = re.compile(r"mobile|sim|giga|gb|minuti|sms|5g|4g", re.I)
NAME_BAD = re.compile(r"scopri|attiva|acquista|mese|gratis|minuti|sms|giga|gb|prezzo|costo|promo|dettagli", re.I)


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
    low = text.lower()
    if "€" not in text and not re.search(r"mese|mensil|30\s*giorni", low):
        return None
    if m := PRICE.search(text):
        value = float(f"{m.group(1)}.{m.group(2)}")
        return value if 1 <= value <= 80 else None
    if m := PRICE_INT.search(text):
        value = float(m.group(1))
        return value if 1 <= value <= 80 else None
    return None


def _activation(text: str) -> float | None:
    if re.search(r"attivazione[^.]{0,50}(gratis|gratuita|0\s*€)", text, re.I):
        return 0.0
    if m := ACTIVATION.search(text):
        return float(f"{m.group(1)}.{m.group(2)}")
    if m := ACTIVATION_INT.search(text):
        return float(m.group(1))
    return None


def _sms(text: str) -> str:
    if re.search(r"SMS[^.;]{0,60}illimitat|illimitat[^.;]{0,60}SMS", text, re.I):
        return "illimitati"
    if m := SMS.search(text):
        return m.group(1)
    return ""


def _minutes(text: str) -> str:
    if re.search(r"minuti[^.;]{0,80}illimitat|illimitat[^.;]{0,80}minuti", text, re.I):
        return "illimitati"
    if m := re.search(r"(\d{1,5})\s*minuti", text, re.I):
        return m.group(1)
    return ""


def _pick_giga(text: str) -> tuple[int | None, bool]:
    if UNLIMITED.search(text):
        return None, True
    vals = [int(v) for v in GB.findall(text) if 1 <= int(v) <= 2000]
    if not vals:
        return None, False
    # In Optima potrebbero comparire soglie roaming: scegli il GB più alto nel blocco mobile.
    return max(vals), False


def _name_from_lines(lines: list[str], fallback_giga: int | None, unlimited: bool) -> str:
    for candidate in lines[:10]:
        c = _clean(candidate)
        if not c or len(c) > 90:
            continue
        if NAME_BAD.search(c) or PRICE.search(c) or GB.fullmatch(c):
            continue
        if re.search(r"Optima|Mobile|Smart|Super|Plus|Start|Pro|Top|Special|100|150|200|250|300", c, re.I):
            return c[:80]
    return "Giga illimitati" if unlimited else (f"{fallback_giga} GB" if fallback_giga else "Offerta Optima Mobile")


def _offer_from_block(block_lines: list[str]) -> Offer | None:
    block = _clean(" ".join(block_lines))
    if len(block) < 14:
        return None
    if not MOBILE_SIGNAL.search(block):
        return None
    # Se il blocco parla chiaramente di casa/energia e non ha abbastanza segnali SIM, scarta.
    if EXCLUDE.search(block) and not re.search(r"\bSIM\b|mobile|minuti|SMS", block, re.I):
        return None

    price = _price(block)
    if price is None:
        return None
    giga, unlimited = _pick_giga(block)
    if giga is None and not unlimited:
        return None

    return Offer(
        operatore=OPERATORE,
        offerta=_name_from_lines(block_lines, giga, unlimited),
        url=URL,
        prezzo_mese=price,
        giga=None if unlimited else giga,
        giga_illimitati=unlimited,
        attivazione=_activation(block),
        minuti=_minutes(block),
        sms=_sms(block),
        rete_5g=bool(re.search(r"\b5G\b", block, re.I)),
        fonte="scraping",
    )


def _parse_lines(html: str) -> list[Offer]:
    lines = _visible_lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    # Cerca finestre intorno ai prezzi mensili. Funziona anche se Optima spezza
    # le card in righe separate.
    for i, line in enumerate(lines):
        context_price = _clean(" ".join(lines[i:i + 3]))
        if _price(line) is None and _price(context_price) is None:
            continue
        start = max(0, i - 12)
        end = min(len(lines), i + 14)
        offer = _offer_from_block(lines[start:end])
        if not offer:
            continue
        key = (round(offer.prezzo_mese or 0, 2), offer.giga, offer.giga_illimitati)
        if key in seen:
            continue
        seen.add(key)
        offers.append(offer)
    return offers


def _walk(node: Any):
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
        if not txt or not re.search(r"optima|mobile|giga|gb|price|prezzo|offerta", txt, re.I):
            continue
        stripped = txt.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                out.append(json.loads(stripped))
            except Exception:
                pass
    return out


def _parse_json(html: str) -> list[Offer]:
    offers = mine_xhr_mobile(_json_candidates(html), OPERATORE, URL)
    return [o for o in offers if o.giga_illimitati or (o.giga is not None and o.giga >= 1)]


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_lines(html)
    if offers:
        return offers

    offers = _parse_json(html)
    if offers:
        return offers

    offers = parse_cards(html, OPERATORE, URL)
    if offers:
        # Evita falsi positivi energia/casa.
        return [o for o in offers if o.giga_illimitati or (o.giga is not None and o.giga >= 1)]

    if xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("optima", html)
    if html:
        offers = parse_html(html, xhr)
        if offers:
            return offers

    # Fallback tecnico: rendering reale della pagina. Non usa fallback manuali.
    rendered, rendered_xhr = fetch_rendered(URL)
    dump_debug("optima_rendered", rendered)
    if not rendered:
        return []
    return parse_html(rendered, rendered_xhr)


if __name__ == "__main__":
    cli_main("mobile", "optima", OPERATORE, scrape)
