"""TIM — offerte mobile.

Pagina: https://www.tim.it/fisso-e-mobile/mobile/passa-a-tim
Nota operatore: scegliere 'altro operatore' nel menu prima di leggere le offerte

STATO: scraping DA CALIBRARE. parse_html() va implementata guardando
l'artifact debug/tim.html prodotto dall'Action di questo fornitore.
Finché parse_html() ritorna vuoto, il fornitore risulta "vuoto" nel report
(NESSUN dato inventato: il sito mostra solo offerte realmente estratte).

Si pubblicano solo offerte 5G.
"""

from __future__ import annotations

from lib.base import Offer, cli_main, dump_debug, fetch_rendered, euro, giga

URL = "https://www.tim.it/fisso-e-mobile/mobile/passa-a-tim"
CLICKS = ['text=altro operatore']


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    """Estrazione reale per tim.

    TODO: implementare sui selettori veri della pagina. Esempio di scheletro:

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        offers = []
        for card in soup.select("SELETTORE_CARD"):
            testo = card.get_text(" ", strip=True)
            if "5G" not in testo:            # solo 5G
                continue
            prezzo = euro(testo); g = giga(testo)
            if prezzo is None or g is None:
                continue
            offers.append(Offer(
                operatore="TIM", offerta="NOME_OFFERTA", url=URL,
                prezzo_mese=prezzo, giga=g, minuti="illimitati", sms="",
                rete_5g=True, fonte="scraping"))
        return offers
    """
    return []


def scrape() -> list[Offer]:
    html, xhr = fetch_rendered(URL, clicks=CLICKS)
    dump_debug("tim", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "tim", "TIM", scrape)
