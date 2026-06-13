"""PosteMobile — offerte mobile.

Pagina: https://www.postemobile.it/offerte-tariffe/

Usa il parser GENERICO (lib.parse_cards) come default: estrae le card
"GB + prezzo/mese" dal testo renderizzato da Playwright, prendendo TUTTE le
offerte (5G e non; il flag rete_5g distingue ma non filtra).

In più tenta l'XHR mining: molti operatori (SPA) caricano le offerte da una
API JSON interna, e quei payload vengono catturati durante il rendering.

Se i risultati non combaciano con la pagina, calibra qui parse_html() con
selettori specifici guardando l'artifact debug/postemobile.html.
"""

from __future__ import annotations

from lib.base import Offer, cli_main, dump_debug, fetch_rendered
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.postemobile.it/offerte-tariffe/"
CLICKS = []
OPERATORE = "PosteMobile"


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_rendered(URL, clicks=CLICKS)
    dump_debug("postemobile", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "postemobile", OPERATORE, scrape)
