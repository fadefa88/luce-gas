"""Iliad — offerte mobile.

Pagina: https://www.iliad.it/offerte-iliad-mobile.html
Tecnica: Iliad codifica GB e prezzo nello SLUG dell'URL di ogni offerta,
es. offerta-iliad-top250plus-999.html -> 250 GB a 9,99€. È il dato più
stabile (niente prezzi resi come immagini). Verificato sull'HTML reale.

Per modificare: se Iliad cambia gli slug, aggiorna SLUG_RE / EXCLUDE qui.
"""

from __future__ import annotations

import re

from lib.base import Offer, cli_main, dump_debug, fetch_html, fetch_rendered

URL = "https://www.iliad.it/offerte-iliad-mobile.html"
SLUG_RE = re.compile(r"offerta-iliad-(?P<slug>[a-z0-9]+?)-(?P<cents>\d{3,4})\.html", re.I)
EXCLUDE = ("voce", "domotica", "dati")          # no solo-voce / IoT / solo-dati
GIGA_BY_SLUG = {"gigaprime": 300}               # slug senza numero -> GB noti
ATTIVAZIONE = 9.99


def _pretty(slug: str, giga: int) -> str:
    name = slug.replace("plus", " Plus").replace("top", "TOP ").replace("giga", "Giga ")
    name = re.sub(r"\s+", " ", name).strip()
    return name if str(giga) in name else f"{name} {giga}".strip()


def scrape() -> list[Offer]:
    html = fetch_html(URL)
    if not html or "offerta-iliad-" not in html:
        html, _ = fetch_rendered(URL)
    if not html:
        return []
    dump_debug("iliad", html)

    offers, seen = [], set()
    for m in SLUG_RE.finditer(html):
        slug = m.group("slug").lower()
        if any(slug.startswith(x) for x in EXCLUDE):
            continue
        gm = re.search(r"(\d{2,4})", slug)
        g = int(gm.group(1)) if gm else GIGA_BY_SLUG.get(slug)
        if not g or not (10 <= g <= 2000):
            continue
        price = int(m.group("cents")) / 100
        if not (1 <= price <= 60) or (g, price) in seen:
            continue
        seen.add((g, price))
        offers.append(Offer(
            operatore="Iliad", offerta=_pretty(slug, g), url=URL,
            prezzo_mese=price, giga=g, attivazione=ATTIVAZIONE,
            minuti="illimitati", sms="illimitati", rete_5g=True,
        ))
    return offers


if __name__ == "__main__":
    cli_main("mobile", "iliad", "Iliad", scrape)
