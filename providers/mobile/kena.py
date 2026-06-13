"""Kena Mobile — offerte mobile. Pagina: https://www.kenamobile.it/offerte/

HTML statico (WooCommerce). Ogni card-offerta contiene un link
/prodotto/... (per individuare le card) e un testo con:
  - prezzo mensile "X,99€ al mese"  (NON l'attivazione "X,00€")
  - giga, a volte "200 300 giga" (barrato + reale): si prende il numero
    PIÙ ALTO prima di "giga"/"GB"
  - "five_g"/"5G" se l'offerta è 5G
Prende sia 5G sia non-5G (flag rete_5g). Esclude IoT/domotica e i pack
non mensili ("ogni 6 mesi").
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards

URL = "https://www.kenamobile.it/offerte/"
PRODUCT = re.compile(r"/prodotto/", re.I)

# prezzo MENSILE: numero,99 seguito (anche con testo in mezzo) da "mese"
PRICE_MONTH = re.compile(r"(\d{1,3})[.,](\d{2})\s*€?\s*al\s*mese", re.I)
PRICE_ANY = re.compile(r"(\d{1,3})[.,](\d{2})\s*€")
GIGA = re.compile(r"(\d{1,4})\s*(?:giga|GB)", re.I)
EXCLUDE_TXT = re.compile(r"dispositivi smart|domokena|domotica|alarm", re.I)


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    soup = BeautifulSoup(html, "html.parser")
    offers: list[Offer] = []
    seen: set[tuple] = set()

    # 2026: la pagina Kena non usa più URL /prodotto/ sulle CTA, ma link
    # tipo /mso/?said=...; quindi il vecchio selettore per href non trova
    # nessuna card. Usiamo prima i blocchi DOM se presenti, poi un fallback
    # line-oriented sul testo visibile.
    cards: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not (PRODUCT.search(href) or "/mso/" in href.lower() or "said=" in href.lower()):
            continue
        card = a
        for _ in range(8):
            if card.parent is None:
                break
            card = card.parent
            if "mese" in card.get_text(" ", strip=True).lower():
                break
        txt = " ".join(card.get_text(" ", strip=True).split())
        if "mese" in txt.lower():
            cards.append((txt, href))

    if not cards:
        lines = [x.strip() for x in soup.get_text("\n", strip=True).splitlines() if x.strip()]
        price_idxs = [i for i, line in enumerate(lines) if PRICE_MONTH.search(line)]
        for pos, i in enumerate(price_idxs):
            prev_price = price_idxs[pos - 1] if pos else -1
            next_price = price_idxs[pos + 1] if pos + 1 < len(price_idxs) else len(lines)

            start = prev_price + 1
            for j in range(prev_price + 1, i):
                if "acquista online" in lines[j].lower():
                    start = j + 1
            end = min(next_price, i + 8)
            for j in range(i + 1, min(next_price, i + 10)):
                if "acquista online" in lines[j].lower():
                    end = j
                    break
            block = " ".join(lines[start:end])
            cards.append((" ".join(block.split()), URL))

    for text, href in cards:
        if EXCLUDE_TXT.search(text):
            continue
        if re.search(r"ogni\s*\d+\s*mes", text, re.I):       # pack non mensile
            continue

        price = None
        if (pm := PRICE_MONTH.search(text)):
            price = float(f"{pm.group(1)}.{pm.group(2)}")
        else:
            for m in PRICE_ANY.finditer(text):
                before = text[max(0, m.start() - 24): m.start()].lower()
                if "attivazione" in before:
                    continue
                price = float(f"{m.group(1)}.{m.group(2)}")
                break
        if price is None or not (1.0 <= price <= 60.0):
            continue

        gigas = [int(n) for n in GIGA.findall(text) if 1 <= int(n) <= 2000]
        if not gigas:
            continue
        giga = max(gigas)

        # Kena Voce / DomoKena sono prodotti non dati-mobile comparabili.
        if giga < 50 or re.search(r"kena\s+voce|voce\s+e\s+dati", text, re.I):
            continue

        is_5g = ("5g" in href.lower()) or ("five_g" in text.lower()) or bool(re.search(r"\b5G\b", text))

        attiv = None
        if (am := re.search(r"attivazione\s*€?\s*(\d{1,2})[.,](\d{2})", text, re.I)):
            attiv = float(f"{am.group(1)}.{am.group(2)}")
        elif (am2 := re.search(r"attivazione\s*(\d{1,2})\s*€", text, re.I)):
            attiv = float(am2.group(1))
        elif re.search(r"attivazione[^.;]{0,40}(gratis|sim)", text, re.I):
            attiv = 0.0

        sms = (sm.group(1) if (sm := re.search(r"(\d{2,4})\s*SMS", text, re.I)) else "")

        key = (price, giga)
        if key in seen:
            continue
        seen.add(key)
        offers.append(Offer(
            operatore="Kena Mobile",
            offerta=f"{giga} GB" + (" 5G" if is_5g else ""),
            url=URL, prezzo_mese=price, giga=giga, attivazione=attiv,
            minuti="illimitati" if re.search(r"illimitat", text, re.I) else "",
            sms=sms, rete_5g=is_5g, fonte="scraping",
        ))
    return offers

def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("kena", html)
    if not html:
        return []

    offers = parse_html(html, xhr)
    if not offers:
        # Fallback tecnico sul testo visibile della stessa pagina. Non usa dati
        # manuali: serve solo quando Kena spezza prezzo/GB su righe diverse.
        offers = [o for o in parse_cards(html, "Kena Mobile", URL)
                  if (o.giga_illimitati or (o.giga is not None and o.giga >= 50))]
    return offers


if __name__ == "__main__":
    cli_main("mobile", "kena", "Kena Mobile", scrape)
