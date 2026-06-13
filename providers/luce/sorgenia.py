"""Sorgenia — offerte luce.

Pagina: https://www.sorgenia.it/offerte-luce-gas-casa
STATO: scraping DA CALIBRARE. parse_html() è il punto in cui scrivere
l'estrazione specifica per questo fornitore una volta esaminato
l'artifact debug/sorgenia_luce.html.

L'energia usa spesso prezzi in centesimi ("11,8 c€/kWh") o a spread
("PUN + 0,012 €/kWh"): gli helper energy_price() in lib.energy aiutano.
"""

from __future__ import annotations

from lib.base import Offer, cli_main, dump_debug, fetch_rendered
from lib.energy import energy_price

URL = "https://www.sorgenia.it/offerte-luce-gas-casa"


def parse_html(html: str, commodity: str) -> list[Offer]:
    """TODO: estrazione reale per sorgenia (luce). Vuoto finché non implementata."""
    offers = []
    # Esempio di scheletro:
    # from bs4 import BeautifulSoup
    # soup = BeautifulSoup(html, "html.parser")
    # for card in soup.select("SELETTORE_DA_TROVARE"):
    #     testo = card.get_text(" ", strip=True)
    #     prezzo, indice = energy_price(testo, commodity)
    #     if prezzo is None: continue
    #     offers.append(Offer(operatore="Sorgenia", offerta="...", url=URL,
    #         commodity=commodity, prezzo_energia=(None if indice else prezzo),
    #         spread=(prezzo if indice else None), indice=indice or "",
    #         tipo=("variabile" if indice else "fisso"), fonte="scraping"))
    return offers


def scrape() -> list[Offer]:
    html, _ = fetch_rendered(URL)
    dump_debug("sorgenia_luce", html)
    if not html:
        return []
    return parse_html(html, "luce")


if __name__ == "__main__":
    cli_main("luce", "sorgenia", "Sorgenia", scrape)
