"""1Mobile — offerte mobile.

Pagina: https://unomobile.it/offerte/5g

STATO: scraping DA CALIBRARE per questo fornitore. Finché il parser non è
verificato, scrape() pubblica i VALORI VERIFICATI A MANO (sotto) così il
sito resta corretto, e marca fonte="verificato". Quando vuoi attivare lo
scraping reale, implementa parse_html() e togli il fallback.

Per calibrare: lancia l'Action di questo fornitore, scarica l'artifact
debug/unomobile.html e scrivi qui i selettori giusti in parse_html().
"""

from __future__ import annotations

from lib.base import Offer, cli_main, dump_debug, fetch_rendered

URL = "https://unomobile.it/offerte/5g"
CLICKS = []

# Valori verificati a mano (giugno 2026). (nome, giga|None, prezzo, attivazione, sms, note)
VERIFIED = [('Flash 5G 320 Limited Edition', 320, 8.99, 0.0, '60', '1° mese 4,99€; +1 mese omaggio'), ('Speed 5G 250', 250, 7.99, 0.0, '50', '1° mese 5,00€'), ('Speed 5G 180', 180, 6.99, 0.0, '50', '1° mese 5,00€'), ('World Plus 5G', 130, 9.99, 0.0, '0', '320 minuti internazionali; +20GB dal 3° rinnovo')]


def _verified_offers() -> list[Offer]:
    out = []
    for nome, giga, prezzo, att, sms, note in VERIFIED:
        out.append(Offer(
            operatore="1Mobile", offerta=nome, url=URL,
            prezzo_mese=prezzo, giga=giga, giga_illimitati=(giga is None),
            attivazione=att, minuti="illimitati", sms=str(sms),
            rete_5g=True, note=note, fonte="verificato",
        ))
    return out


def parse_html(html: str) -> list[Offer]:
    """TODO: estrazione reale calibrata su unomobile. Vuoto finché non implementata."""
    return []


def scrape() -> list[Offer]:
    html, _xhr = fetch_rendered(URL, clicks=CLICKS)
    dump_debug("unomobile", html)
    scraped = parse_html(html) if html else []
    # Quando parse_html sarà affidabile, qui si confronterà con VERIFIED e si
    # restituiranno gli scraped. Per ora pubblichiamo i valori verificati.
    return scraped or _verified_offers()


if __name__ == "__main__":
    cli_main("mobile", "unomobile", "1Mobile", scrape)
