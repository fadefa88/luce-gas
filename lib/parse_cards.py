"""lib/parse_cards.py — parser generico di "card offerta mobile".

Molti operatori, una volta renderizzati da Playwright, espongono le offerte
come blocchi di testo che contengono: GB, un prezzo "X,99 € al mese",
talvolta l'attivazione e un indicatore 5G. Questo parser estrae le offerte
da quel testo in modo tollerante, ed è il DEFAULT per i provider non ancora
calibrati a mano. Prende TUTTE le offerte (5G e non): il flag rete_5g
distingue, ma non filtra.

Strategie, in ordine:
  1) blocchi DOM "card-like" (BeautifulSoup): un blocco = un'offerta
  2) fallback: spezza il testo intero attorno ai prezzi "€ al mese"
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer

# prezzo mensile: "7,99€ al mese", "7,99 € al mese", "€7.99/mese", "7,99€/mese"
PRICE = re.compile(
    r"(?:€\s*)?(\d{1,3})[.,](\d{2})\s*€?\s*(?:/\s*mese|al\s*mese|/\s*30\s*giorni|al/?\s*mese|/mese)",
    re.I)
# fallback prezzo senza "mese" esplicito ma con €
PRICE_LOOSE = re.compile(r"(\d{1,3})[.,](\d{2})\s*€")
GB = re.compile(r"(\d{1,4})\s*(?:GB|Giga)\b", re.I)
GB_BAD = re.compile(r"riserva|roaming|rinnovo|omaggio|estero|reserve", re.I)
ACTIV = re.compile(r"attivazione\s*(?:€\s*)?(\d{1,2})[.,](\d{2})", re.I)
ACTIV_FREE = re.compile(r"attivazione[^.]{0,30}(gratis|gratuit|free|0€)", re.I)
SMS = re.compile(r"(\d{2,4})\s*SMS", re.I)
UNLIM = re.compile(r"illimitat[io]\s*giga|giga\s*illimitat|GB\s*illimitat", re.I)
FIVEG = re.compile(r"\b5G\b|five_g", re.I)


def _num(a: str, b: str) -> float:
    return float(f"{a}.{b}")


def _card_text_offer(operator: str, url: str, text: str) -> Offer | None:
    text = " ".join(text.split())
    pm = PRICE.search(text) or PRICE_LOOSE.search(text)
    if not pm:
        return None
    price = _num(pm.group(1), pm.group(2))
    if not (1 <= price <= 80):
        return None

    unlimited = bool(UNLIM.search(text))
    g = None
    if not unlimited:
        for m in GB.finditer(text):
            if GB_BAD.search(text[m.end(): m.end() + 18]):
                continue
            val = int(m.group(1))
            if 1 <= val <= 2000:
                g = val          # primo GB "buono" = taglio principale
                break
        if g is None:
            return None

    attiv = None
    if ACTIV_FREE.search(text):
        attiv = 0.0
    elif (am := ACTIV.search(text)):
        attiv = _num(am.group(1), am.group(2))

    sms = ""
    if (sm := SMS.search(text)):
        sms = sm.group(1)

    return Offer(
        operatore=operator, offerta="", url=url,
        prezzo_mese=price, giga=None if unlimited else g,
        giga_illimitati=unlimited,
        attivazione=attiv,
        minuti="illimitati" if re.search(r"illimitat", text, re.I) else "",
        sms=sms,
        rete_5g=bool(FIVEG.search(text)),
        fonte="scraping",
    )


def parse_cards(html: str, operator: str, url: str,
                selectors: str = "[class*=card],[class*=offer],[class*=offerta],[class*=plan],[class*=tariff],article,li") -> list[Offer]:
    soup = BeautifulSoup(html, "html.parser")
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for block in soup.select(selectors):
        text = block.get_text(" ", strip=True)
        if not (12 <= len(text) <= 900):
            continue
        o = _card_text_offer(operator, url, text)
        if not o:
            continue
        key = (o.prezzo_mese, o.giga, o.giga_illimitati)
        if key in seen:
            continue
        seen.add(key)
        # nome: prima intestazione del blocco, se c'è
        h = block.find(["h1", "h2", "h3", "h4"])
        o.offerta = (h.get_text(strip=True)[:80] if h else
                     (f"{o.giga} GB" if o.giga else "Giga illimitati"))
        offers.append(o)

    return offers
