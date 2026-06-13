"""PosteMobile — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.postemobile.it/privati/offerte-telefonia-mobile

Niente fallback manuali. La pagina PosteMobile espone le offerte in HTML, ma con
nomi e prezzi multilinea:
- titolo offerta su piu' righe, es. Creami EXTRA / WOW 150 Online
- 150GB Internet 4G+
- Credit illimitati per chiamate e SMS
- €6,99 / al mese
Il parser generico non aggancia bene questa struttura, quindi qui usiamo un
parser specifico sulle righe visibili.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.postemobile.it/privati/offerte-telefonia-mobile"
OPERATORE = "PosteMobile"

TITLE_START = re.compile(
    r"^(?:PosteMobile|Creami|Postepay\s+Connect|300%\s+Digital|Tariffa\s+Dati\s+Base)",
    re.I,
)
PRICE = re.compile(r"€\s*(\d{1,3})\s*[,\.]\s*(\d{2})", re.I)
PRICE_INT = re.compile(r"(?:Costo\s+piano\s*:\s*)?(\d{1,3})\s*€\s*/\s*mese", re.I)
GB = re.compile(r"(\d{1,4})\s*GB\b", re.I)
MB_DAY = re.compile(r"(\d{1,4})\s*MB\s*/\s*giorno", re.I)
EXCLUDE_TITLE = re.compile(r"Unica|Tariffa\s+Dati\s+Base", re.I)
EXCLUDE_BLOCK = re.compile(r"casa|fibra|ultraveloce|giorno|MB/giorno", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _lines(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [x for x in (_clean(v) for v in soup.get_text("\n", strip=True).splitlines()) if x and x not in {"*", "•"}]


def _price(block: str) -> float | None:
    if m := PRICE.search(block):
        value = float(f"{m.group(1)}.{m.group(2)}")
        return value if 1 <= value <= 80 else None
    if m := PRICE_INT.search(block):
        value = float(m.group(1))
        return value if 1 <= value <= 80 else None
    return None


def _title(lines: list[str]) -> str:
    chunks: list[str] = []
    for line in lines[:5]:
        if re.search(r"GB|Credit|Chiamate|SMS|€|Per nuovi clienti|Esclusiva|Costo|Fino a", line, re.I):
            break
        if line.lower().startswith("offerte") or line.lower().startswith("se sei"):
            continue
        chunks.append(line)
    return _clean(" ".join(chunks))[:80]


def _parse_postemobile(html: str) -> list[Offer]:
    lines = _lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        if not TITLE_START.search(line):
            continue

        end = len(lines)
        for j in range(i + 1, len(lines)):
            if TITLE_START.search(lines[j]) or lines[j].startswith("Info navigazione"):
                end = j
                break

        block_lines = lines[i:end]
        block = _clean(" ".join(block_lines))
        title = _title(block_lines) or line

        # Escludo offerte solo voce, dati giornalieri e prodotti/carta bundle non comparabili.
        if EXCLUDE_TITLE.search(title) or MB_DAY.search(block):
            continue
        if EXCLUDE_BLOCK.search(block) and not re.search(r"Internet\s+4G\+|GB\s+al\s+mese", block, re.I):
            continue

        gm = GB.search(block)
        if not gm:
            continue
        giga = int(gm.group(1))
        if not (1 <= giga <= 2000):
            continue

        price = _price(block)
        if price is None:
            continue

        # Credit illimitati = bundle chiamate/SMS PosteMobile.
        unlimited_credits = bool(re.search(r"Credit\s+illimitati", block, re.I))
        calls_sms_paid = bool(re.search(r"Chiamate\s+e\s+SMS\s+\d+\s*cent", block, re.I))
        minuti = "illimitati" if unlimited_credits else ("a consumo" if calls_sms_paid else "")
        sms = "illimitati" if unlimited_credits else ("a consumo" if calls_sms_paid else "")

        note_parts: list[str] = []
        if "Esclusiva Online" in block or "Esclusiva online" in block:
            note_parts.append("esclusiva online")
        if "Esclusiva Ufficio Postale" in block:
            note_parts.append("esclusiva ufficio postale")
        if "Per nuovi clienti" in block:
            note_parts.append("per nuovi clienti")
        if "Costo SIM gratuito" in block:
            note_parts.append("SIM gratuita in promo")
        if "ricarica bonus" in block:
            note_parts.append("ricarica bonus sui giga non usati")

        key = (round(price, 2), giga, title.lower())
        if key in seen:
            continue
        seen.add(key)

        offers.append(Offer(
            operatore=OPERATORE,
            offerta=title if str(giga) in title else f"{title} {giga} GB",
            url=URL,
            prezzo_mese=price,
            giga=giga,
            giga_illimitati=False,
            attivazione=None,
            minuti=minuti,
            sms=sms,
            rete_5g=False,
            note="; ".join(note_parts),
            fonte="scraping",
        ))

    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_postemobile(html)
    if offers:
        return offers
    offers = parse_cards(html, OPERATORE, URL)
    if not offers and xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("postemobile", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "postemobile", OPERATORE, scrape)
