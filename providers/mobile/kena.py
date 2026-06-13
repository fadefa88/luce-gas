"""Kena Mobile — offerte mobile.

Pagina: https://www.kenamobile.it/offerte/

STATO: scraping DA CALIBRARE per questo fornitore. Finché il parser non è
verificato, scrape() pubblica i VALORI VERIFICATI A MANO (sotto) così il
sito resta corretto, e marca fonte="verificato". Quando vuoi attivare lo
scraping reale, implementa parse_html() e togli il fallback.

Per calibrare: lancia l'Action di questo fornitore, scarica l'artifact
debug/kena.html e scrivi qui i selettori giusti in parse_html().
"""

from __future__ import annotations

from lib.base import Offer, cli_main, dump_debug, fetch_rendered

URL = "https://www.kenamobile.it/offerte/"
CLICKS = []

# Valori verificati a mano (giugno 2026). (nome, giga|None, prezzo, attivazione, sms, note)
VERIFIED = [('100 Giga', 100, 4.99, 0.0, '200', 'per Iliad, Coop, PosteMobile e altri'), ('300 Giga', 300, 5.99, 0.0, '200', 'ricarica automatica; per Iliad, Coop, PosteMobile e altri'), ('350 Giga', 350, 7.99, 2.0, '200', 'ricarica automatica'), ('450 Giga', 450, 9.99, 0.0, '200', 'ricarica automatica'), ('300 Giga (da Vodafone/WindTre/Very/TIM)', 300, 11.99, 3.0, '200', 'ricarica automatica'), ('600 Giga nuovi numeri', 600, 11.99, 3.0, '200', 'Kena Dati; ricarica automatica')]


def _verified_offers() -> list[Offer]:
    out = []
    for nome, giga, prezzo, att, sms, note in VERIFIED:
        out.append(Offer(
            operatore="Kena Mobile", offerta=nome, url=URL,
            prezzo_mese=prezzo, giga=giga, giga_illimitati=(giga is None),
            attivazione=att, minuti="illimitati", sms=str(sms),
            rete_5g=True, note=note, fonte="verificato",
        ))
    return out


def parse_html(html: str) -> list[Offer]:
    """TODO: estrazione reale calibrata su kena. Vuoto finché non implementata."""
    return []


def scrape() -> list[Offer]:
    html, _xhr = fetch_rendered(URL, clicks=CLICKS)
    dump_debug("kena", html)
    scraped = parse_html(html) if html else []
    # Quando parse_html sarà affidabile, qui si confronterà con VERIFIED e si
    # restituiranno gli scraped. Per ora pubblichiamo i valori verificati.
    return scraped or _verified_offers()


if __name__ == "__main__":
    cli_main("mobile", "kena", "Kena Mobile", scrape)
