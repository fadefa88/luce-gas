"""lib/parse_cards.py — parser generico di offerte mobile.

Estrae offerte da HTML statico o renderizzato senza usare fallback manuali.
Strategie:
  1) blocchi DOM card-like;
  2) testo visibile line-oriented, utile quando prezzo e "al mese" sono su
     righe separate (es. "4" / ",99€" / "al mese").
"""

from __future__ import annotations

import re
from bs4 import BeautifulSoup

from lib.base import Offer

PRICE = re.compile(
    r"(?:€\s*)?(\d{1,3})\s*[.,]\s*(\d{2})\s*€?\s*(?:/\s*mese|al\s*mese|/\s*30\s*giorni|al/?\s*mese|mese)",
    re.I,
)
PRICE_LOOSE = re.compile(r"(?:€\s*)?(\d{1,3})\s*[.,]\s*(\d{2})\s*€", re.I)
# Casi in cui la parte intera e i centesimi sono spezzati in righe/tag diversi.
PRICE_SPLIT = re.compile(
    r"(?:^|\D)(\d{1,3})\s*[,\.]\s*(\d{2})\s*€?\s*(?:al\s*mese|/\s*mese|mese)",
    re.I,
)
PRICE_INT_MONTH = re.compile(
    r"(?:€\s*)?(\d{1,3})\s*€?\s*(?:/\s*mese|al\s*mese|mese)",
    re.I,
)
GB = re.compile(r"(\d{1,4})\s*(?:GB|Giga)\b", re.I)
GB_UNLIMITED = re.compile(r"(?:GB|Giga)\s*illimitat[io]|illimitat[io]\s*(?:GB|Giga)", re.I)
GB_BAD_NEAR = re.compile(r"roaming|riserva|rinnovo|omaggio|estero|reserve|ue|europa", re.I)
ACTIV = re.compile(r"attivazione[^\d€]{0,30}(?:€\s*)?(\d{1,2})\s*[.,]\s*(\d{1,2})", re.I)
ACTIV_INT = re.compile(r"attivazione[^\d€]{0,30}(\d{1,2})\s*€", re.I)
ACTIV_FREE = re.compile(r"attivazione[^.]{0,50}(gratis|gratuit|free|0\s*€)", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)
FIVEG = re.compile(r"\b5G\b|five_g|full\s*speed", re.I)
MIN_UNLIM = re.compile(r"minuti[^.;]{0,50}illimitat|illimitat[^.;]{0,50}minuti", re.I)
EXCLUDE_OFFER = re.compile(
    r"smartphone|iphone|galaxy|router|fibra|adsl|fisso|casa|roaming|estero|internazional|tablet|watch",
    re.I,
)


def _num(a: str, b: str) -> float:
    return float(f"{a}.{b}")


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _price(text: str) -> float | None:
    m = PRICE.search(text) or PRICE_SPLIT.search(text)
    if m:
        price = _num(m.group(1), m.group(2))
        return price if 1 <= price <= 80 else None
    m = PRICE_INT_MONTH.search(text)
    if m:
        price = float(m.group(1))
        return price if 1 <= price <= 80 else None
    m = PRICE_LOOSE.search(text)
    if not m:
        return None
    price = _num(m.group(1), m.group(2))
    return price if 1 <= price <= 80 else None


def _activation(text: str) -> float | None:
    if ACTIV_FREE.search(text):
        return 0.0
    if m := ACTIV.search(text):
        return _num(m.group(1), m.group(2).zfill(2))
    if m := ACTIV_INT.search(text):
        return float(m.group(1))
    return None


def _sms(text: str) -> str:
    if re.search(r"SMS[^.;]{0,50}illimitat|illimitat[^.;]{0,50}SMS", text, re.I):
        return "illimitati"
    if m := SMS.search(text):
        return m.group(1)
    return ""


def _pick_giga(text: str, prefer_last: bool = False) -> tuple[int | None, bool]:
    unlimited = bool(GB_UNLIMITED.search(text))
    if unlimited:
        return None, True

    vals: list[int] = []
    for m in GB.finditer(text):
        val = int(m.group(1))
        if not (1 <= val <= 2000):
            continue
        near = text[max(0, m.start() - 28): m.end() + 42]
        # Scarta GB di roaming/riserva/omaggio quando sono chiaramente marcati.
        if GB_BAD_NEAR.search(near) and len(vals) > 0:
            continue
        vals.append(val)
    if not vals:
        return None, False
    return (vals[-1] if prefer_last else vals[0]), False


def _card_text_offer(operator: str, url: str, text: str) -> Offer | None:
    text = _clean_text(text)
    if len(text) < 12:
        return None
    price = _price(text)
    if price is None:
        return None
    giga, unlimited = _pick_giga(text)
    if not unlimited and giga is None:
        return None

    return Offer(
        operatore=operator,
        offerta="",
        url=url,
        prezzo_mese=price,
        giga=None if unlimited else giga,
        giga_illimitati=unlimited,
        attivazione=_activation(text),
        minuti="illimitati" if MIN_UNLIM.search(text) else "",
        sms=_sms(text),
        rete_5g=bool(FIVEG.search(text)),
        fonte="scraping",
    )


def _visible_lines(soup: BeautifulSoup) -> list[str]:
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    raw = soup.get_text("\n", strip=True).replace("\xa0", " ")
    lines = [_clean_text(x) for x in raw.splitlines()]
    return [x for x in lines if x and x not in {"*", "•"}]


def _line_price_indices(lines: list[str]) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    covered_until = -1
    for i in range(len(lines)):
        if i < covered_until:
            continue
        for span in range(1, 7):
            chunk_lines = lines[i:i + span]
            if not chunk_lines:
                continue
            chunk = _clean_text(" ".join(chunk_lines))
            compact = re.sub(r"\s+", "", chunk)
            # Serve un contesto mensile: evita prezzi di SIM, smartphone e attivazioni.
            if not re.search(r"mese|/mese|30\s*giorni", chunk, re.I) and not re.search(r"mese", compact, re.I):
                continue
            if PRICE.search(chunk) or PRICE_SPLIT.search(chunk) or PRICE_INT_MONTH.search(chunk) or PRICE.search(compact) or PRICE_SPLIT.search(compact) or PRICE_INT_MONTH.search(compact):
                found.append((i, i + span, chunk))
                covered_until = i + span
                break
    return found


def _line_window_offers(html: str, operator: str, url: str) -> list[Offer]:
    soup = BeautifulSoup(html, "html.parser")
    lines = _visible_lines(soup)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    price_positions = _line_price_indices(lines)
    for pos, (start_price, end_price, price_chunk) in enumerate(price_positions):
        prev_end = price_positions[pos - 1][1] if pos else 0
        next_start = price_positions[pos + 1][0] if pos + 1 < len(price_positions) else len(lines)
        block_start = max(prev_end, start_price - 12)
        block_end = min(next_start, end_price + 8)
        block_lines = lines[block_start:block_end]
        block = _clean_text(" ".join(block_lines))

        if EXCLUDE_OFFER.search(block) and not re.search(r"minuti|sms|sim", block, re.I):
            continue

        # Per offerte visive scegli il GB più vicino al prezzo, cioè l'ultimo GB
        # prima del prezzo. Serve per pagine tipo Very: titolo 150 Giga, card 100 Giga.
        before = _clean_text(" ".join(lines[block_start:start_price]))
        after = _clean_text(" ".join(lines[end_price:block_end]))
        giga, unlimited = _pick_giga(before, prefer_last=True)
        if not unlimited and giga is None:
            giga, unlimited = _pick_giga(after, prefer_last=False)
        if not unlimited and giga is None:
            giga, unlimited = _pick_giga(block, prefer_last=True)
        if not unlimited and giga is None:
            continue

        price = _price(price_chunk) or _price(block)
        if price is None:
            continue

        # Se nella finestra c'è solo un prodotto IoT/domotica con pochi GB, non è
        # un'offerta mobile comparabile voce+dati. Gli altri operatori mantengono
        # anche tagli piccoli se hanno minuti/SMS.
        if not unlimited and giga is not None and giga < 1:
            continue

        key = (round(price, 2), giga, unlimited)
        if key in seen:
            continue
        seen.add(key)

        # Nome: prendi una riga leggibile sopra il blocco GB/prezzo, altrimenti fallback.
        name = ""
        for candidate in reversed(lines[block_start:start_price]):
            if GB.search(candidate) or PRICE_LOOSE.search(candidate):
                continue
            if re.search(r"minuti|sms|attivazione|sim|spedizione|costo|per clienti|offerta 5g|scopri", candidate, re.I):
                continue
            if 2 <= len(candidate) <= 80:
                name = candidate
                break
        if not name:
            name = "Giga illimitati" if unlimited else f"{giga} GB"

        offers.append(Offer(
            operatore=operator,
            offerta=name[:80],
            url=url,
            prezzo_mese=price,
            giga=None if unlimited else giga,
            giga_illimitati=unlimited,
            attivazione=_activation(block),
            minuti="illimitati" if MIN_UNLIM.search(block) else "",
            sms=_sms(block),
            rete_5g=bool(FIVEG.search(block)),
            fonte="scraping",
        ))

    return offers


def parse_cards(
    html: str,
    operator: str,
    url: str,
    selectors: str = "[class*=card],[class*=offer],[class*=offerta],[class*=plan],[class*=tariff],article,li",
) -> list[Offer]:
    soup = BeautifulSoup(html, "html.parser")
    offers: list[Offer] = []
    seen: set[tuple] = set()

    # 1) Card DOM. Funziona quando il markup conserva card coerenti.
    for block in soup.select(selectors):
        text = block.get_text(" ", strip=True)
        if not (12 <= len(text) <= 1400):
            continue
        o = _card_text_offer(operator, url, text)
        if not o:
            continue
        key = (round(o.prezzo_mese or 0, 2), o.giga, o.giga_illimitati)
        if key in seen:
            continue
        seen.add(key)
        h = block.find(["h1", "h2", "h3", "h4"])
        o.offerta = (h.get_text(strip=True)[:80] if h else
                     ("Giga illimitati" if o.giga_illimitati else f"{o.giga} GB"))
        offers.append(o)

    # 2) Fallback tecnico sul testo visibile. Non inventa dati: legge sempre
    # la pagina corrente, ma tollera prezzo/GB spezzati in tag o righe diverse.
    for o in _line_window_offers(html, operator, url):
        key = (round(o.prezzo_mese or 0, 2), o.giga, o.giga_illimitati)
        if key in seen:
            continue
        seen.add(key)
        offers.append(o)

    return offers
