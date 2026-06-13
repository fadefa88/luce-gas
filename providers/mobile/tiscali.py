"""Tiscali Mobile — offerte mobile.

Pagina: https://promozioni.tiscali.it/offerte-mobile/

STATO: scraping DA CALIBRARE per questo fornitore. Finché il parser non è
verificato, scrape() pubblica i VALORI VERIFICATI A MANO (sotto) così il
sito resta corretto, e marca fonte="verificato". Quando vuoi attivare lo
scraping reale, implementa parse_html() e togli il fallback.

Per calibrare: lancia l'Action di questo fornitore, scarica l'artifact
debug/tiscali.html e scrivi qui i selettori giusti in parse_html().
"""

from __future__ import annotations

from lib.base import Offer, cli_main, dump_debug, fetch_rendered

URL = "https://promozioni.tiscali.it/offerte-mobile/"
CLICKS = []

# Valori verificati a mano (giugno 2026). (nome, giga|None, prezzo, attivazione, sms, note)
VERIFIED = [('Mobile 150 GB 5G', 150, 5.99, 0.0, '100', 'promo; riservata alla portabilità'), ('Mobile 250 GB 5G', 250, 7.99, 0.0, '100', ''), ('Mobile 350 GB 5G', 350, 10.99, 0.0, '100', '')]


def _verified_offers() -> list[Offer]:
    out = []
    for nome, giga, prezzo, att, sms, note in VERIFIED:
        out.append(Offer(
            operatore="Tiscali Mobile", offerta=nome, url=URL,
            prezzo_mese=prezzo, giga=giga, giga_illimitati=(giga is None),
            attivazione=att, minuti="illimitati", sms=str(sms),
            rete_5g=True, note=note, fonte="verificato",
        ))
    return out


def parse_html(html: str) -> list[Offer]:
    """TODO: estrazione reale calibrata su tiscali. Vuoto finché non implementata."""
    return []


def scrape() -> list[Offer]:
    html, _xhr = fetch_rendered(URL, clicks=CLICKS)
    dump_debug("tiscali", html)
    scraped = parse_html(html) if html else []
    # Quando parse_html sarà affidabile, qui si confronterà con VERIFIED e si
    # restituiranno gli scraped. Per ora pubblichiamo i valori verificati.
    return scraped or _verified_offers()


if __name__ == "__main__":
    cli_main("mobile", "tiscali", "Tiscali Mobile", scrape)
