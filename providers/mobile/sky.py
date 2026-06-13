"""Sky Mobile — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.sky.it/sky-mobile-telefonia

Parser specifico: la pagina contiene anche bundle Sky Wifi, costi extra e testo
legale che generano falsi positivi. Qui leggiamo solo i quattro piani Sky Mobile
Start/Pro/Power/Ultra indicati nella sezione informativa della pagina.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.sky.it/sky-mobile-telefonia"
OPERATORE = "Sky Mobile"
PLAN_LINE = re.compile(
    r"Sky Mobile\s+(Start|Pro|Power|Ultra)[^\n-]*-\s*(?:(\d{1,4})\s*Giga|Giga\s+illimitati|GB\s+ILLIMITATI)[^,]*,?\s*al\s+costo\s+di\s+(\d{1,3})\s*[,\.]\s*(\d{2})\s*€\s+al\s+mese",
    re.I,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return _clean(soup.get_text("\n", strip=True))


def _parse_sky(html: str) -> list[Offer]:
    text = _text(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()
    for m in PLAN_LINE.finditer(text):
        tier = m.group(1).title()
        giga = int(m.group(2)) if m.group(2) else None
        unlimited = giga is None
        price = float(f"{m.group(3)}.{m.group(4)}")
        key = (round(price, 2), giga, unlimited)
        if key in seen:
            continue
        seen.add(key)
        offers.append(Offer(
            operatore=OPERATORE,
            offerta=f"Sky Mobile {tier}" if unlimited else f"Sky Mobile {tier} {giga} GB",
            url=URL,
            prezzo_mese=price,
            giga=giga,
            giga_illimitati=unlimited,
            attivazione=10.0,
            minuti="illimitati",
            sms="200",
            rete_5g=True,
            fonte="scraping",
        ))
    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_sky(html)
    if offers:
        return offers
    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("sky", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "sky", OPERATORE, scrape)
