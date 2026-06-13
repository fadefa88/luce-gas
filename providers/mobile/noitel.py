"""Noitel — offerte mobile.

Pagina: https://www.noitel.it/
STATO: da censire. parse_html() va implementata guardando l'artifact
debug/noitel.html. Nessun dato inventato: finché lo scraping non estrae nulla,
il fornitore risulta "vuoto" nel report. Solo offerte 5G.
"""

from __future__ import annotations

from lib.base import Offer, cli_main, dump_debug, fetch_rendered, euro, giga

URL = "https://www.noitel.it/"
CLICKS = []


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    """TODO: estrazione reale per noitel. Vuoto finché non implementata."""
    return []


def scrape() -> list[Offer]:
    html, xhr = fetch_rendered(URL, clicks=CLICKS)
    dump_debug("noitel", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "noitel", "Noitel", scrape)
