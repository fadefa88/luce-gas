"""Noitel — offerte mobile reali dalla pagina ufficiale.

Pagina: https://noitel.it/listingofferte

Niente fallback manuali. La pagina Noitel espone gia' in HTML le offerte, ma il
formato e' line-oriented:
- titolo offerta come heading
- GIGA / valore
- MINUTI / valore
- SMS / valore
- prezzo su riga separata, es. € 9,99 / AL MESE
Il parser generico non aggancia bene questa struttura, quindi qui usiamo un
parser specifico sulle righe visibili della pagina.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://noitel.it/listingofferte"
OPERATORE = "Noitel"

TITLE = re.compile(r"^(?:SUPER\s+JUMP|Voice\s+plus|Next\s+step\s+plus|Step\s+plus|Big\s+Jump\s+plus)", re.I)
PRICE = re.compile(r"€\s*(\d{1,3})\s*[,\.]\s*(\d{2})", re.I)
SIM_COST = re.compile(r"SIM\s*:\s*(\d{1,3})\s*[,\.]\s*(\d{2})\s*€", re.I)
ACTIVATION = re.compile(r"ATTIVAZIONE\s+Promo\s*:\s*(\d{1,3})\s*[,\.]\s*(\d{2})\s*€", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _lines(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [x for x in (_clean(v) for v in soup.get_text("\n", strip=True).splitlines()) if x and x not in {"*", "•"}]


def _euro(match: re.Match[str] | None) -> float | None:
    if not match:
        return None
    return float(f"{match.group(1)}.{match.group(2)}")


def _value_after_label(block_lines: list[str], label: str) -> str:
    for i, line in enumerate(block_lines):
        if line.strip().lower() == label.lower() and i + 1 < len(block_lines):
            return _clean(block_lines[i + 1])
    return ""


def _parse_noitel(html: str) -> list[Offer]:
    lines = _lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        title = _clean(line)
        if not TITLE.search(title):
            continue

        end = len(lines)
        for j in range(i + 1, len(lines)):
            if TITLE.search(lines[j]) or lines[j].startswith("Perché scegliere"):
                end = j
                break

        block_lines = lines[i:end]
        block = _clean(" ".join(block_lines))
        price = _euro(PRICE.search(block))
        if price is None or not (1 <= price <= 80):
            continue

        giga_text = _value_after_label(block_lines, "GIGA")
        giga = None
        if giga_text:
            if giga_text.lower().startswith("illimit"):
                giga = None
                unlimited = True
            elif giga_text.isdigit():
                giga = int(giga_text)
                unlimited = False
            else:
                unlimited = False
        else:
            # Voice plus è solo voce/SMS: non la mettiamo nel comparatore dati mobile.
            continue

        if not unlimited and (giga is None or not (1 <= giga <= 2000)):
            continue

        minuti_raw = _value_after_label(block_lines, "MINUTI")
        sms_raw = _value_after_label(block_lines, "SMS")
        minuti = "illimitati" if minuti_raw.lower().startswith("illimit") else minuti_raw
        sms = sms_raw

        activation = _euro(ACTIVATION.search(block))
        sim = _euro(SIM_COST.search(block))
        note_parts = []
        if sim is not None:
            note_parts.append(f"SIM {sim:.2f}€")
        if "Per i nuovi clienti" in block:
            note_parts.append("per nuovi clienti")

        key = (round(price, 2), giga, unlimited, title.lower())
        if key in seen:
            continue
        seen.add(key)

        offers.append(Offer(
            operatore=OPERATORE,
            offerta=title if unlimited else f"{title} {giga} GB",
            url=URL,
            prezzo_mese=price,
            giga=None if unlimited else giga,
            giga_illimitati=unlimited,
            attivazione=activation,
            minuti=minuti,
            sms=sms,
            rete_5g=bool(re.search(r"5G|FULL\s+SPEED", block, re.I)),
            note="; ".join(note_parts),
            fonte="scraping",
        ))

    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_noitel(html)
    if offers:
        return offers
    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("noitel", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "noitel", OPERATORE, scrape)
