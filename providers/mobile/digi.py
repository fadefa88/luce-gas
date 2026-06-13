"""Digi Mobil — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.digi.it/it/mobile

Niente fallback manuali: la pagina Digi espone gia' in HTML le card con:
- titolo offerta, es. Illimitato 5
- taglio dati, es. 30GB cumulabili
- prezzo, es. € 5 / mese
Il parser generico non aggancia bene questo formato, quindi qui usiamo un parser
specifico line-oriented.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.digi.it/it/mobile"
OPERATORE = "Digi Mobil"
TITLE = re.compile(r"^Illimitato\s+(\d+)", re.I)
GB = re.compile(r"(\d{1,4})\s*GB\s+cumulabili", re.I)
PRICE = re.compile(r"€\s*(\d{1,3})\s*/\s*mese", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _lines(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [x for x in (_clean(v) for v in soup.get_text("\n", strip=True).splitlines()) if x and x not in {"*", "•"}]


def _parse_digi(html: str) -> list[Offer]:
    lines = _lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        if not TITLE.search(line):
            continue

        # Ogni card termina prima del titolo Illimitato successivo o prima delle
        # sezioni roaming/internazionale.
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if TITLE.search(lines[j]) or lines[j].lower().startswith("internazionale e roaming"):
                end = j
                break
        block_lines = lines[i:end]
        block = _clean(" ".join(block_lines))

        gm = GB.search(block)
        pm = PRICE.search(block)
        if not gm or not pm:
            continue

        giga = int(gm.group(1))
        price = float(pm.group(1))
        if not (1 <= giga <= 2000 and 1 <= price <= 80):
            continue

        sms = ""
        # Digi scrive "1000 SMS verso DIGI + 10 SMS nazionali". Per il sito
        # salvo una nota sintetica, non sommo SMS eterogenei verso destinazioni diverse.
        sms_matches = SMS.findall(block)
        if sms_matches:
            sms = "+".join(sms_matches)

        key = (round(price, 2), giga)
        if key in seen:
            continue
        seen.add(key)

        international_minutes = ""
        if m := re.search(r"(\d{1,4})\s+minuti\s+internazionali", block, re.I):
            international_minutes = f"; {m.group(1)} minuti internazionali"

        offers.append(Offer(
            operatore=OPERATORE,
            offerta=line,
            url=URL,
            prezzo_mese=price,
            giga=giga,
            giga_illimitati=False,
            attivazione=None,
            minuti="illimitati",
            sms=sms,
            rete_5g=False,
            note=f"GB cumulabili{international_minutes}",
            fonte="scraping",
        ))
    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_digi(html)
    if offers:
        return offers
    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("digi", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "digi", OPERATORE, scrape)
