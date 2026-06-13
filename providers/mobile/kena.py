"""Kena Mobile — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.kenamobile.it/offerte/

Parser specifico: Kena spezza alcuni prezzi in "5,99€al" + "mese" e contiene
anche Kena Voce, DomoKena e pack semestrali. Qui leggiamo solo offerte mobile
mensili comparabili dalla pagina corrente, senza fallback manuali.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards

URL = "https://www.kenamobile.it/offerte/"
OPERATORE = "Kena Mobile"
GIGA = re.compile(r"(\d{1,4})\s*giga\b", re.I)
PRICE = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{2})\s*€?\s*al\s*mese", re.I)
ACTIV = re.compile(r"Attivazione\s*€?\s*(\d{1,2})\s*[,\.]\s*(\d{2})", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)
EXCLUDE = re.compile(r"KENA\s+VOCE|DOMOKENA|dispositivi\s+smart|domotica|ogni\s+\d+\s+mesi|pack\s+6\s+mesi", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [x for x in (_clean(v) for v in soup.get_text("\n", strip=True).splitlines()) if x and x not in {"*", "•"}]


def _price(block: str) -> float | None:
    compact = re.sub(r"\s+", "", block)
    m = PRICE.search(block) or re.search(r"(\d{1,3})[,\.](\d{2})€?almese", compact, re.I)
    if not m:
        return None
    value = float(f"{m.group(1)}.{m.group(2)}")
    return value if 1 <= value <= 80 else None


def _activation(block: str) -> float | None:
    if m := ACTIV.search(block):
        return float(f"{m.group(1)}.{m.group(2)}")
    if re.search(r"Attivazione[^.]{0,60}(gratis|SIM\s+e\s+consegna\s+gratis)", block, re.I):
        return 0.0
    return None


def _parse_kena(html: str) -> list[Offer]:
    lines = _lines(html)
    price_idx = [i for i, line in enumerate(lines) if _price(" ".join(lines[i:i + 2])) is not None]
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for pos, i in enumerate(price_idx):
        start = price_idx[pos - 1] + 1 if pos else 0
        end = price_idx[pos + 1] if pos + 1 < len(price_idx) else min(len(lines), i + 12)
        block = _clean(" ".join(lines[start:end]))
        if EXCLUDE.search(block):
            continue
        price = _price(block)
        if price is None:
            continue
        # Esclude pack semestrali e anomalie non mensili.
        if price > 20:
            continue
        gigas = [int(x) for x in GIGA.findall(block) if 1 <= int(x) <= 2000]
        if not gigas:
            continue
        giga = max(gigas)
        if giga < 50:
            continue
        key = (round(price, 2), giga)
        if key in seen:
            continue
        seen.add(key)
        sms = ""
        if m := SMS.search(block):
            sms = m.group(1)
        offers.append(Offer(
            operatore=OPERATORE,
            offerta=f"{giga} GB" + (" Dati" if "KENA DATI" in block.upper() else ""),
            url=URL,
            prezzo_mese=price,
            giga=giga,
            giga_illimitati=False,
            attivazione=_activation(block),
            minuti="illimitati" if re.search(r"Minuti\s+illimitati|illimitati[^.]{0,40}Minuti", block, re.I) else "",
            sms=sms,
            rete_5g=bool(re.search(r"five_g|\b5G\b", block, re.I)),
            fonte="scraping",
        ))
    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_kena(html)
    if offers:
        return offers
    # Fallback tecnico sulla stessa pagina: mai dati manuali.
    return [o for o in parse_cards(html, OPERATORE, URL)
            if (o.prezzo_mese or 0) <= 20 and (o.giga_illimitati or (o.giga is not None and o.giga >= 50))]


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("kena", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "kena", OPERATORE, scrape)
