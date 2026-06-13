"""ho. Mobile — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.ho-mobile.it/tutte-le-offerte

Parser specifico: la pagina spezza prezzo/intero/centesimi su righe diverse e
contiene anche una sezione casa/router. Qui estraiamo solo offerte SIM mobile con
Minuti illimitati e 200 SMS, senza fallback manuali.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.ho-mobile.it/tutte-le-offerte"
OPERATORE = "ho. Mobile"
GB = re.compile(r"(\d{1,4})\s*Giga\b", re.I)
PRICE_COMPACT = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{2})\s*€?\s*al\s*mese", re.I)
ACTIVATION = re.compile(r"(?:Costo\s+di\s+attivazione|Attivazione\s+a\s+partire\s+da)\s*(\d{1,2})\s*[,\.]\s*(\d{2})\s*€", re.I)


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


def _activation(block: str) -> float | None:
    if m := ACTIVATION.search(block):
        return float(f"{m.group(1)}.{m.group(2)}")
    return None


def _parse_ho(html: str) -> list[Offer]:
    lines = _lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        m = GB.fullmatch(line)
        if not m:
            continue
        giga = int(m.group(1))
        block_lines = lines[i:min(i + 14, len(lines))]
        block = _clean(" ".join(block_lines))

        if "Minuti illimitati" not in block or "200 SMS" not in block:
            continue
        if re.search(r"casa|router|sconto\s+su\s+un\s+router", block, re.I):
            continue

        price = _price(block)
        if price is None:
            continue
        key = (round(price, 2), giga)
        if key in seen:
            continue
        seen.add(key)

        offers.append(Offer(
            operatore=OPERATORE,
            offerta=f"{giga} GB",
            url=URL,
            prezzo_mese=price,
            giga=giga,
            giga_illimitati=False,
            attivazione=_activation(block),
            minuti="illimitati",
            sms="200",
            rete_5g=True,
            fonte="scraping",
        ))
    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_ho(html)
    if offers:
        return offers
    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("ho", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "ho", OPERATORE, scrape)
