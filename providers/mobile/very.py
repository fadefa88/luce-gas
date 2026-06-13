"""Very Mobile — offerte mobile reali dalla pagina ufficiale.

Pagina: https://verymobile.it/offerte

Parser specifico: Very separa Giga, prezzo intero, centesimi e "al mese" su
righe diverse. Il parser legge solo la pagina corrente e scarta domotica/dati-only.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://verymobile.it/offerte"
OPERATORE = "Very Mobile"
GB = re.compile(r"(\d{1,4})\s*Giga\b", re.I)
PRICE_COMPACT = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{2})\s*€?\s*al\s*mese", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [x for x in (_clean(v) for v in soup.get_text("\n", strip=True).splitlines()) if x and x not in {"*", "•"}]


def _price(block: str) -> float | None:
    compact = re.sub(r"\s+", "", block)
    m = PRICE_COMPACT.search(block) or re.search(r"(\d{1,3})[,\.](\d{2})€?almese", compact, re.I)
    if not m:
        return None
    value = float(f"{m.group(1)}.{m.group(2)}")
    return value if 1 <= value <= 80 else None


def _parse_very(html: str) -> list[Offer]:
    lines = _lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        m = GB.fullmatch(line)
        unlimited = bool(re.fullmatch(r"Giga\s+illimitati", line, re.I))
        if not m and not unlimited:
            continue

        block_lines = lines[i:min(i + 16, len(lines))]
        block = _clean(" ".join(block_lines))
        if re.search(r"dispositivi\s+smart|100%\s*internet", block, re.I):
            continue
        if not re.search(r"minuti[^.]{0,30}SMS|SMS[^.]{0,30}minuti", block, re.I):
            continue

        price = _price(block)
        if price is None:
            continue
        giga = None if unlimited else int(m.group(1))
        key = (round(price, 2), giga, unlimited)
        if key in seen:
            continue
        seen.add(key)

        offers.append(Offer(
            operatore=OPERATORE,
            offerta="Giga illimitati" if unlimited else f"{giga} GB",
            url=URL,
            prezzo_mese=price,
            giga=giga,
            giga_illimitati=unlimited,
            attivazione=0.0 if re.search(r"SIM\s+e\s+spedizione\s+gratis", block, re.I) else None,
            minuti="illimitati",
            sms="illimitati",
            rete_5g=True,
            fonte="scraping",
        ))
    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_very(html)
    if offers:
        return offers
    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("very", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "very", OPERATORE, scrape)
