"""Kena Mobile — offerte mobile.

Pagina: https://www.kenamobile.it/offerte/  (HTML statico, WooCommerce)

Usa il parser generico sul testo delle card (i GB mostrati includono il bonus
ricarica automatica, es. "300 giga", ed è quello che vede l'utente). Prende
TUTTE le offerte mobile (5G e non) ed esclude IoT/domotica/voce-only.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_html, fetch_rendered
from lib.parse_cards import parse_cards

URL = "https://www.kenamobile.it/offerte/"
EXCLUDE = re.compile(r"domo|alarm|iot|dispositivi smart", re.I)


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = parse_cards(html, "Kena Mobile", URL)
    # scarta IoT/domotica
    return [o for o in offers if not EXCLUDE.search(o.offerta or "")]


def scrape() -> list[Offer]:
    html = fetch_html(URL)
    if not html or "al mese" not in html:
        html, _ = fetch_rendered(URL)
    dump_debug("kena", html)
    if not html:
        return []
    return parse_html(html)


if __name__ == "__main__":
    cli_main("mobile", "kena", "Kena Mobile", scrape)
