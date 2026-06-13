"""Vianova — offerte mobile.

Pagina: https://www.vianova.it/
STATO: da censire. parse_html() va implementata guardando l'artifact
debug/vianova.html. Nessun dato inventato: finché lo scraping non estrae nulla,
il fornitore risulta "vuoto" nel report. Solo offerte 5G.
"""

from __future__ import annotations

from lib.base import Offer, cli_main, dump_debug, fetch_rendered, euro, giga

URL = "https://www.vianova.it/"
CLICKS = []


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    """TODO: estrazione reale per vianova. Vuoto finché non implementata."""
    return []


def scrape() -> list[Offer]:
    html, xhr = fetch_rendered(URL, clicks=CLICKS)
    dump_debug("vianova", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "vianova", "Vianova", scrape)
