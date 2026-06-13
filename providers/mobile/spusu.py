"""spusu — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.spusu.it/tariffe

Niente fallback manuali. La pagina spusu e' abbastanza dinamica e spesso il
parser generico non trova nulla. Le card possono contenere:
- nome offerta, es. spusu 150 / spusu 200 / spusu 300
- bundle dati principale in GB
- riserva dati in GB, che non va confusa col bundle principale
- minuti/SMS
- prezzo mensile in formato 5,98 € o simile
Se l'HTML statico non basta, forza rendering Playwright.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page, fetch_rendered
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.spusu.it/tariffe"
OPERATORE = "spusu"

TITLE = re.compile(r"^spusu(?:\s+[A-Za-z0-9+._-]+){0,4}$", re.I)
PRICE = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{2})\s*€", re.I)
PRICE_INT = re.compile(r"€\s*(\d{1,3})(?:\s*/\s*mese|\s*al\s*mese|\s*mese)?", re.I)
GB = re.compile(r"(\d{1,4})\s*(?:GB|Giga)\b", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)
MINUTES = re.compile(r"(\d{1,5})\s*minuti", re.I)
EXCLUDE_BLOCK = re.compile(r"router|fibra|casa|internet\s+casa|business|estero|roaming|dettagli\s+tariffari", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _visible_lines(html: str) -> list[str]:
    soup = _soup(html)
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [x for x in (_clean(v) for v in soup.get_text("\n", strip=True).splitlines()) if x and x not in {"*", "•", "|"}]


def _price(text: str) -> float | None:
    if "€" not in text and not re.search(r"mese|mensil", text, re.I):
        return None
    if m := PRICE.search(text):
        value = float(f"{m.group(1)}.{m.group(2)}")
        return value if 1 <= value <= 80 else None
    if m := PRICE_INT.search(text):
        value = float(m.group(1))
        return value if 1 <= value <= 80 else None
    return None


def _primary_giga(block: str) -> int | None:
    # Scarta i GB legati alla riserva dati: spusu spesso scrive 150 GB + 300 GB di riserva.
    vals: list[int] = []
    for m in GB.finditer(block):
        around = block[max(0, m.start() - 80): min(len(block), m.end() + 90)]
        if re.search(r"riserva|reserve", around, re.I):
            continue
        val = int(m.group(1))
        if 1 <= val <= 2000:
            vals.append(val)
    if vals:
        return vals[0]

    # Se tutto e' marcato in modo ambiguo, usa il primo GB plausibile, ma non il massimo
    # per evitare di prendere la riserva come bundle principale.
    all_vals = [int(x) for x in GB.findall(block) if 1 <= int(x) <= 2000]
    return all_vals[0] if all_vals else None


def _reserve_giga(block: str) -> int | None:
    for m in GB.finditer(block):
        around = block[max(0, m.start() - 80): min(len(block), m.end() + 90)]
        if re.search(r"riserva|reserve", around, re.I):
            val = int(m.group(1))
            return val if 1 <= val <= 5000 else None
    return None


def _minutes(block: str) -> str:
    if re.search(r"minuti[^.;]{0,80}illimitat|illimitat[^.;]{0,80}minuti", block, re.I):
        return "illimitati"
    if m := MINUTES.search(block):
        return m.group(1)
    return ""


def _sms(block: str) -> str:
    if re.search(r"SMS[^.;]{0,80}illimitat|illimitat[^.;]{0,80}SMS", block, re.I):
        return "illimitati"
    if m := SMS.search(block):
        return m.group(1)
    return ""


def _offer_from_block(title: str, block_lines: list[str]) -> Offer | None:
    block = _clean(" ".join(block_lines))
    if EXCLUDE_BLOCK.search(block) and not re.search(r"\bGB\b|Giga|SIM|minuti|SMS", block, re.I):
        return None

    price = _price(block)
    giga = _primary_giga(block)
    if price is None or giga is None:
        return None
    if not (1 <= price <= 80 and 1 <= giga <= 2000):
        return None

    reserve = _reserve_giga(block)
    note_parts: list[str] = []
    if reserve:
        note_parts.append(f"riserva dati {reserve} GB")
    if re.search(r"eSIM", block, re.I):
        note_parts.append("eSIM disponibile")
    if re.search(r"5G", block, re.I):
        note_parts.append("5G")

    return Offer(
        operatore=OPERATORE,
        offerta=title if str(giga) in title else f"{title} {giga} GB",
        url=URL,
        prezzo_mese=price,
        giga=giga,
        giga_illimitati=False,
        attivazione=None,
        minuti=_minutes(block),
        sms=_sms(block),
        rete_5g=bool(re.search(r"\b5G\b", block, re.I)),
        note="; ".join(note_parts),
        fonte="scraping",
    )


def _parse_title_blocks(lines: list[str]) -> list[Offer]:
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        title = _clean(line)
        if not TITLE.match(title):
            continue
        # Evita il logo/testata semplice "spusu" senza numero/nome tariffa.
        if title.lower() == "spusu":
            continue

        end = len(lines)
        for j in range(i + 1, len(lines)):
            nxt = _clean(lines[j])
            if (TITLE.match(nxt) and nxt.lower() != "spusu") or re.search(r"^FAQ$|^Perché\s+spusu|^Dettagli", nxt, re.I):
                end = j
                break

        block_lines = lines[i:end]
        offer = _offer_from_block(title, block_lines)
        if not offer:
            continue
        key = (round(offer.prezzo_mese or 0, 2), offer.giga, offer.offerta.lower())
        if key in seen:
            continue
        seen.add(key)
        offers.append(offer)

    return offers


def _parse_price_windows(lines: list[str]) -> list[Offer]:
    offers: list[Offer] = []
    seen: set[tuple] = set()
    for i, line in enumerate(lines):
        joined = _clean(" ".join(lines[i:i + 3]))
        if _price(line) is None and _price(joined) is None:
            continue
        start = max(0, i - 12)
        end = min(len(lines), i + 14)
        block_lines = lines[start:end]
        block = _clean(" ".join(block_lines))
        # Trova un titolo spusu vicino al prezzo.
        title = ""
        for candidate in reversed(block_lines[: max(1, i - start + 1)]):
            c = _clean(candidate)
            if TITLE.match(c) and c.lower() != "spusu":
                title = c
                break
        if not title:
            giga = _primary_giga(block)
            title = f"spusu {giga}" if giga else "spusu"
        offer = _offer_from_block(title, block_lines)
        if not offer:
            continue
        key = (round(offer.prezzo_mese or 0, 2), offer.giga, offer.offerta.lower())
        if key in seen:
            continue
        seen.add(key)
        offers.append(offer)
    return offers


def _walk(node: Any):
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            stack.extend(x for x in cur if isinstance(x, (dict, list)))


def _json_candidates(html: str) -> list[Any]:
    soup = _soup(html)
    out: list[Any] = []
    for script in soup.find_all("script"):
        txt = script.string or script.get_text(" ", strip=True)
        if not txt or not re.search(r"spusu|tariff|giga|gb|price|prezzo|riserva", txt, re.I):
            continue
        stripped = txt.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                out.append(json.loads(stripped))
            except Exception:
                pass
    return out


def _parse_json(html: str) -> list[Offer]:
    # Primo passaggio con il miner generico; poi normalizza eventuali nomi troppo grezzi.
    out: list[Offer] = []
    for offer in mine_xhr_mobile(_json_candidates(html), OPERATORE, URL):
        if offer.giga is None or offer.giga < 1:
            continue
        offer.fonte = "scraping"
        out.append(offer)
    return out


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    lines = _visible_lines(html)

    offers = _parse_title_blocks(lines)
    if offers:
        return offers

    offers = _parse_price_windows(lines)
    if offers:
        return offers

    offers = _parse_json(html)
    if offers:
        return offers

    offers = parse_cards(html, OPERATORE, URL)
    if offers:
        return offers

    if xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("spusu", html)
    if html:
        offers = parse_html(html, xhr)
        if offers:
            return offers

    # Fallback tecnico: rendering reale della pagina. Non usa fallback manuali.
    rendered, rendered_xhr = fetch_rendered(URL)
    dump_debug("spusu_rendered", rendered)
    if not rendered:
        return []
    return parse_html(rendered, rendered_xhr)


if __name__ == "__main__":
    cli_main("mobile", "spusu", OPERATORE, scrape)
