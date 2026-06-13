"""Enel Energia — offerte gas.

Pagina: https://www.enel.it/it/luce-e-gas
STATO: scraping DA CALIBRARE. parse_html() è il punto in cui scrivere
l'estrazione specifica per questo fornitore una volta esaminato
l'artifact debug/enel_gas.html.

L'energia usa spesso prezzi in centesimi ("11,8 c€/kWh") o a spread
("PUN + 0,012 €/kWh"): gli helper energy_price() in lib.energy aiutano.
"""

from __future__ import annotations

from lib.base import Offer, cli_main, dump_debug, fetch_rendered
from lib.energy import energy_price

URL = "https://www.enel.it/it/luce-e-gas"


def parse_html(html: str, commodity: str) -> list[Offer]:
    """TODO: estrazione reale per enel (gas). Vuoto finché non implementata."""
    offers = []
    # Esempio di scheletro:
    # from bs4 import BeautifulSoup
    # soup = BeautifulSoup(html, "html.parser")
    # for card in soup.select("SELETTORE_DA_TROVARE"):
    #     testo = card.get_text(" ", strip=True)
    #     prezzo, indice = energy_price(testo, commodity)
    #     if prezzo is None: continue
    #     offers.append(Offer(operatore="Enel Energia", offerta="...", url=URL,
    #         commodity=commodity, prezzo_energia=(None if indice else prezzo),
    #         spread=(prezzo if indice else None), indice=indice or "",
    #         tipo=("variabile" if indice else "fisso"), fonte="scraping"))
    return offers


def scrape() -> list[Offer]:
    html, _ = fetch_rendered(URL)
    dump_debug("enel_gas", html)
    if not html:
        return []
    return parse_html(html, "gas")


if __name__ == "__main__":
    cli_main("gas", "enel", "Enel Energia", scrape)
