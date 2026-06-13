"""Sky Mobile — offerte mobile.

Pagina: https://www.sky.it/offerte/telefonia-mobile

STATO: scraping DA CALIBRARE per questo fornitore. Finché il parser non è
verificato, scrape() pubblica i VALORI VERIFICATI A MANO (sotto) così il
sito resta corretto, e marca fonte="verificato". Quando vuoi attivare lo
scraping reale, implementa parse_html() e togli il fallback.

Per calibrare: lancia l'Action di questo fornitore, scarica l'artifact
debug/sky.html e scrivi qui i selettori giusti in parse_html().
"""

from __future__ import annotations

from lib.base import Offer, cli_main, dump_debug, fetch_rendered

URL = "https://www.sky.it/offerte/telefonia-mobile"
CLICKS = []

# Valori verificati a mano (giugno 2026). (nome, giga|None, prezzo, attivazione, sms, note)
VERIFIED = [('Sky Mobile Start', 150, 9.95, 10.0, 'illimitati', 'powered by Fastweb; 10€ SIM una tantum'), ('Sky Mobile Pro', 250, 11.95, 10.0, 'illimitati', 'powered by Fastweb'), ('Sky Mobile Power', 400, 14.95, 10.0, 'illimitati', 'powered by Fastweb'), ('Sky Mobile Ultra', None, 19.95, 10.0, 'illimitati', 'powered by Fastweb; GB e minuti illimitati')]


def _verified_offers() -> list[Offer]:
    out = []
    for nome, giga, prezzo, att, sms, note in VERIFIED:
        out.append(Offer(
            operatore="Sky Mobile", offerta=nome, url=URL,
            prezzo_mese=prezzo, giga=giga, giga_illimitati=(giga is None),
            attivazione=att, minuti="illimitati", sms=str(sms),
            rete_5g=True, note=note, fonte="verificato",
        ))
    return out


def parse_html(html: str) -> list[Offer]:
    """TODO: estrazione reale calibrata su sky. Vuoto finché non implementata."""
    return []


def scrape() -> list[Offer]:
    html, _xhr = fetch_rendered(URL, clicks=CLICKS)
    dump_debug("sky", html)
    scraped = parse_html(html) if html else []
    # Quando parse_html sarà affidabile, qui si confronterà con VERIFIED e si
    # restituiranno gli scraped. Per ora pubblichiamo i valori verificati.
    return scraped or _verified_offers()


if __name__ == "__main__":
    cli_main("mobile", "sky", "Sky Mobile", scrape)
