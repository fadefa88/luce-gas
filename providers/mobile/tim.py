"""TIM — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.tim.it/fisso-e-mobile/mobile/passa-a-tim

Parser specifico: TIM pubblica molte sezioni descrittive e condizioni legali; il
parser generico finisce spesso nei dettagli e non nelle card. Qui leggiamo le
sezioni "Attiva TIM ... a X,XX€" e i tagli Giga associati.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.tim.it/fisso-e-mobile/mobile/passa-a-tim"
OPERATORE = "TIM"
HEADER = re.compile(r"Attiva\s+(TIM[^\n]+?)\s+a\s+(\d{1,3})\s*[,\.]\s*(\d{2})\s*€", re.I)
GB_LINE = re.compile(r"^(\d{1,4})\s*Giga,?\s*Minuti\s+illimitati\s+e\s+200\s*SMS", re.I)
ACTIVATION_FREE = re.compile(r"Attivazione\s+offerta:\s*0\s*€", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [x for x in (_clean(v).lstrip("# ") for v in soup.get_text("\n", strip=True).splitlines()) if x and x not in {"*", "•"}]


def _parse_tim(html: str) -> list[Offer]:
    lines = _lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        hm = HEADER.search(line)
        if not hm:
            continue
        plan_name = _clean(hm.group(1))
        price = float(f"{hm.group(2)}.{hm.group(3)}")
        if not (1 <= price <= 80):
            continue

        end = len(lines)
        for j in range(i + 1, len(lines)):
            if HEADER.search(lines[j]):
                end = j
                break
        block_lines = lines[i:end]
        block = _clean(" ".join(block_lines))
        activation = 0.0 if ACTIVATION_FREE.search(block) else None

        for candidate in block_lines:
            gm = GB_LINE.search(candidate)
            if not gm:
                continue
            giga = int(gm.group(1))
            key = (round(price, 2), giga)
            if key in seen:
                continue
            seen.add(key)
            offers.append(Offer(
                operatore=OPERATORE,
                offerta=f"{plan_name} {giga} GB",
                url=URL,
                prezzo_mese=price,
                giga=giga,
                giga_illimitati=False,
                attivazione=activation,
                minuti="illimitati",
                sms="200",
                rete_5g=True,
                fonte="scraping",
            ))
    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_tim(html)
    if offers:
        return offers
    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("tim", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "tim", OPERATORE, scrape)
