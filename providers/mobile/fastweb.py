"""Fastweb — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.fastweb.it/myfastweb/shop/mobile/

Parser specifico: la pagina contiene anche smartphone/shop e testi di sezione che
possono generare falsi positivi con il parser generico. Qui leggiamo solo le card
Fastweb Mobile Start/Pro/Power/Ultra dal testo pagina corrente.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.fastweb.it/myfastweb/shop/mobile/"
OPERATORE = "Fastweb"
PLANS = (
    "Fastweb Mobile Start",
    "Fastweb Mobile Pro",
    "Fastweb Mobile Power",
    "Fastweb Mobile Ultra",
)

PRICE = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{2})\s*€?\s*al\s*mese", re.I)
GB = re.compile(r"(\d{1,4})\s*GB\b", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [x for x in (_clean(v) for v in soup.get_text("\n", strip=True).splitlines()) if x and x not in {"*", "•"}]


def _price(text: str) -> float | None:
    m = PRICE.search(text)
    if not m:
        return None
    value = float(f"{m.group(1)}.{m.group(2)}")
    return value if 1 <= value <= 80 else None


def _parse_plan(name: str, block_lines: list[str]) -> Offer | None:
    block = _clean(" ".join(block_lines))
    price = _price(block)
    if price is None:
        return None

    unlimited = bool(re.search(r"GB\s+illimitati|illimitati\s+GB", block, re.I))
    giga = None
    if not unlimited:
        # Il primo GB della card è il bundle nazionale; quelli successivi sono
        # roaming UE o prodotti smartphone e non vanno usati.
        vals = [int(x) for x in GB.findall(block) if 1 <= int(x) <= 2000]
        if not vals:
            return None
        giga = vals[0]

    sms = ""
    if m := SMS.search(block):
        sms = m.group(1)

    short = name.replace("Fastweb Mobile ", "")
    return Offer(
        operatore=OPERATORE,
        offerta=f"Fastweb Mobile {short}" if unlimited else f"Fastweb Mobile {short} {giga} GB",
        url=URL,
        prezzo_mese=price,
        giga=None if unlimited else giga,
        giga_illimitati=unlimited,
        attivazione=None,
        minuti="illimitati" if re.search(r"Minuti\s+illimitati|illimitati[^.]{0,40}minuti", block, re.I) else "",
        sms=sms,
        rete_5g=True,
        fonte="scraping",
    )


def _parse_fastweb(html: str) -> list[Offer]:
    lines = _lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()
    for i, line in enumerate(lines):
        if line not in PLANS:
            continue
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if lines[j] in PLANS or lines[j].startswith("*Il 5G") or lines[j] == "Plafond aggiuntivi":
                end = j
                break
        offer = _parse_plan(line, lines[i:end])
        if not offer:
            continue
        key = (round(offer.prezzo_mese or 0, 2), offer.giga, offer.giga_illimitati)
        if key in seen:
            continue
        seen.add(key)
        offers.append(offer)
    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_fastweb(html)
    if offers:
        return offers
    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("fastweb", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "fastweb", OPERATORE, scrape)
