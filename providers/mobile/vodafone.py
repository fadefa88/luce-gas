"""Vodafone — offerte mobile reali dalla pagina ufficiale.

Pagina: https://privati.vodafone.it/mobile/telefonia-mobile

Niente fallback manuali: il parser legge solo la pagina Vodafone corrente.
Vodafone puo' restituire un HTML statico con parole "giga/mese" ma senza
struttura utile; per questo, se il primo parsing non trova offerte, forziamo un
secondo tentativo con Playwright/rendering.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page, fetch_rendered
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://privati.vodafone.it/mobile/telefonia-mobile"
OPERATORE = "Vodafone"
PLAN_NAMES = {"START", "PRO", "POWER", "ULTRA"}
STOP_MARKERS = (
    "Casa e mobile, insieme.",
    "Cerchi di più dalla tua offerta?",
    "Essere Vodafone ha i suoi vantaggi.",
    "FAQ",
)

PRICE = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{2})\s*€?\s*/?\s*mese", re.I)
PRICE_COMPACT = re.compile(r"(\d{1,3})[,\.](\d{2})€?/?mese", re.I)
GB = re.compile(r"(\d{1,4})\s*GIGA\b", re.I)
UNLIMITED = re.compile(r"GIGA\s+ILLIMITATI|ILLIMITATI\s+GIGA", re.I)
ACTIVATION = re.compile(r"Costo\s+di\s+attivazione\s*(\d{1,3})\s*€", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)
MINUTES = re.compile(r"Minuti\s+illimitati|illimitati[^.]{0,60}minuti", re.I)

# Pattern globale: funziona anche quando il DOM non separa bene le card.
PLAN_RE = re.compile(
    r"\b(START|PRO|POWER|ULTRA)\b"
    r"(?:(?!\b(?:START|PRO|POWER|ULTRA)\b|Casa\s+e\s+mobile|FAQ).){0,1600}?"
    r"((?:\d{1,4}\s*GIGA)|(?:GIGA\s+ILLIMITATI\*?))"
    r"(?:(?!\b(?:START|PRO|POWER|ULTRA)\b|Casa\s+e\s+mobile|FAQ).){0,500}?"
    r"(\d{1,3})\s*[,\.]\s*(\d{2})\s*€?\s*/?\s*mese",
    re.I | re.S,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _soup(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return soup


def _visible_lines(html: str) -> list[str]:
    raw = _soup(html).get_text("\n", strip=True)
    return [line for line in (_clean(x) for x in raw.splitlines()) if line and line not in {"*", "•"}]


def _visible_text(html: str) -> str:
    return _clean(_soup(html).get_text(" ", strip=True))


def _price(block: str) -> float | None:
    compact = re.sub(r"\s+", "", block)
    match = PRICE.search(block) or PRICE_COMPACT.search(compact)
    if not match:
        return None
    value = float(f"{match.group(1)}.{match.group(2)}")
    return value if 1 <= value <= 80 else None


def _activation(block: str) -> float | None:
    if match := ACTIVATION.search(block):
        return float(match.group(1))
    return None


def _sms(block: str) -> str:
    if match := SMS.search(block):
        return match.group(1)
    return ""


def _make_offer(name: str, bundle: str, price: float, block: str) -> Offer | None:
    name = name.upper().strip()
    bundle = _clean(bundle).upper().replace("*", "")
    unlimited = bool(UNLIMITED.search(bundle))
    giga = None
    if not unlimited:
        gm = GB.search(bundle)
        if not gm:
            return None
        giga = int(gm.group(1))
        if not (1 <= giga <= 2000):
            return None

    return Offer(
        operatore=OPERATORE,
        offerta=name if unlimited else f"{name} {giga} GB",
        url=URL,
        prezzo_mese=price,
        giga=None if unlimited else giga,
        giga_illimitati=unlimited,
        attivazione=_activation(block),
        minuti="illimitati" if MINUTES.search(block) else "",
        sms=_sms(block),
        rete_5g=True,
        fonte="scraping",
    )


def _parse_global_text(html: str) -> list[Offer]:
    text = _visible_text(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()
    for match in PLAN_RE.finditer(text):
        name = match.group(1).upper()
        bundle = match.group(2)
        price = float(f"{match.group(3)}.{match.group(4)}")
        # Recupera un contesto limitato intorno alla card per attivazione/minuti/SMS.
        block = text[match.start(): min(len(text), match.end() + 360)]
        offer = _make_offer(name, bundle, price, block)
        if not offer:
            continue
        key = (round(offer.prezzo_mese or 0, 2), offer.giga, offer.giga_illimitati)
        if key in seen:
            continue
        seen.add(key)
        offers.append(offer)
    return offers


def _parse_line_blocks(html: str) -> list[Offer]:
    lines = _visible_lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        name = line.upper().strip()
        if name not in PLAN_NAMES:
            continue

        end = len(lines)
        for j in range(i + 1, len(lines)):
            upper = lines[j].upper().strip()
            if upper in PLAN_NAMES or any(marker.lower() == lines[j].lower() for marker in STOP_MARKERS):
                end = j
                break

        block = _clean(" ".join(lines[i:end]))
        price = _price(block)
        if price is None:
            continue

        unlimited = bool(UNLIMITED.search(block))
        if unlimited:
            bundle = "GIGA ILLIMITATI"
        else:
            # Prendi il primo bundle nazionale dopo il nome, non i giga roaming UE.
            gm = GB.search(block)
            if not gm:
                continue
            bundle = f"{gm.group(1)} GIGA"

        offer = _make_offer(name, bundle, price, block)
        if not offer:
            continue
        key = (round(offer.prezzo_mese or 0, 2), offer.giga, offer.giga_illimitati)
        if key in seen:
            continue
        seen.add(key)
        offers.append(offer)

    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    # Prima il regex globale, poi il parser per righe. Entrambi leggono solo HTML reale.
    offers = _parse_global_text(html)
    if offers:
        return offers

    offers = _parse_line_blocks(html)
    if offers:
        return offers

    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("vodafone", html)
    if html:
        offers = parse_html(html, xhr)
        if offers:
            return offers

    # Fallback tecnico: se l'HTML statico contiene segnali ma non dati estraibili,
    # forziamo il rendering. Non usa dati manuali.
    rendered, rendered_xhr = fetch_rendered(URL)
    dump_debug("vodafone_rendered", rendered)
    if not rendered:
        return []
    return parse_html(rendered, rendered_xhr)


if __name__ == "__main__":
    cli_main("mobile", "vodafone", OPERATORE, scrape)
