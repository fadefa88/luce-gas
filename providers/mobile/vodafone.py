"""Vodafone — offerte mobile reali dalla pagina ufficiale.

Pagina: https://privati.vodafone.it/mobile/telefonia-mobile

La pagina Vodafone spezza spesso prezzo e centesimi in nodi diversi, ad esempio:
150 GIGA / 9 / ,95€/mese. Per questo qui usiamo un parser specifico
line-oriented, senza fallback manuali: legge solo il testo presente nella pagina.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://privati.vodafone.it/mobile/telefonia-mobile"
CLICKS = []
OPERATORE = "Vodafone"

PRICE = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{2})\s*€?\s*/?\s*mese", re.I)
PRICE_COMPACT = re.compile(r"(\d{1,3})[,\.](\d{2})€?/?mese", re.I)
GB = re.compile(r"(\d{1,4})\s*GIGA\b", re.I)
ACTIVATION = re.compile(r"Costo\s+di\s+attivazione\s*(\d{1,3})\s*€", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)
PLAN_NAMES = {"START", "PRO", "POWER", "ULTRA"}
STOP_MARKERS = (
    "Casa e mobile, insieme.",
    "Cerchi di più dalla tua offerta?",
    "Essere Vodafone ha i suoi vantaggi.",
    "FAQ",
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _visible_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    raw = soup.get_text("\n", strip=True)
    return [line for line in (_clean(x) for x in raw.splitlines()) if line and line not in {"*", "•"}]


def _price(block: str) -> float | None:
    compact = re.sub(r"\s+", "", block)
    match = PRICE.search(block) or PRICE_COMPACT.search(compact)
    if not match:
        return None
    value = float(f"{match.group(1)}.{match.group(2)}")
    return value if 1 <= value <= 80 else None


def _parse_plan(name: str, block_lines: list[str]) -> Offer | None:
    block = _clean(" ".join(block_lines))
    price = _price(block)
    if price is None:
        return None

    unlimited = bool(re.search(r"GIGA\s+ILLIMITATI|ILLIMITATI\s+GIGA", block, re.I))
    giga = None
    if not unlimited:
        # Il primo valore GIGA della card e' il bundle principale; quelli dopo
        # il prezzo sono spesso roaming UE e non vanno usati come taglio offerta.
        before_price = block.split("€/mese", 1)[0]
        gigas = [int(x) for x in GB.findall(before_price) if 1 <= int(x) <= 2000]
        if not gigas:
            gigas = [int(x) for x in GB.findall(block) if 1 <= int(x) <= 2000]
        if not gigas:
            return None
        giga = gigas[0]

    activation = None
    if match := ACTIVATION.search(block):
        activation = float(match.group(1))

    sms = ""
    if match := SMS.search(block):
        sms = match.group(1)

    return Offer(
        operatore=OPERATORE,
        offerta=name if unlimited else f"{name} {giga} GB",
        url=URL,
        prezzo_mese=price,
        giga=None if unlimited else giga,
        giga_illimitati=unlimited,
        attivazione=activation,
        minuti="illimitati" if re.search(r"Minuti\s+illimitati|illimitati[^.]{0,40}minuti", block, re.I) else "",
        sms=sms,
        rete_5g=True,
        fonte="scraping",
    )


def _parse_vodafone_lines(html: str) -> list[Offer]:
    lines = _visible_lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        name = line.upper()
        if name not in PLAN_NAMES:
            continue

        # Taglia il blocco alla prossima card Vodafone o a una sezione successiva.
        end = len(lines)
        for j in range(i + 1, len(lines)):
            upper = lines[j].upper()
            if upper in PLAN_NAMES or any(marker.lower() == lines[j].lower() for marker in STOP_MARKERS):
                end = j
                break

        block_lines = lines[i:end]
        offer = _parse_plan(name, block_lines)
        if not offer:
            continue

        key = (round(offer.prezzo_mese or 0, 2), offer.giga, offer.giga_illimitati)
        if key in seen:
            continue
        seen.add(key)
        offers.append(offer)

    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_vodafone_lines(html)
    if offers:
        return offers

    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL, clicks=CLICKS)
    dump_debug("vodafone", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "vodafone", OPERATORE, scrape)
