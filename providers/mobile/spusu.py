"""spusu — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.spusu.it/tariffe

Niente fallback manuali. Spusu non espone sempre le tariffe come testo HTML
pulito: spesso i dati sono in chunk JavaScript/Nuxt caricati dalla pagina.
Questo scraper quindi prova, in ordine:
1. testo visibile HTML/renderizzato;
2. JSON inline;
3. chunk JS referenziati dalla pagina;
4. XHR catturati da Playwright.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_html, fetch_mobile_page, fetch_rendered
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.spusu.it/tariffe"
URLS = [URL, "https://www.spusu.it/tariffe/"]
OPERATORE = "spusu"

TITLE = re.compile(r"\bspusu(?:\s+[A-Za-z0-9+._-]+){0,4}\b", re.I)
PRICE = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{1,2})\s*€", re.I)
PRICE_STRUCT = re.compile(
    r"(?:price|prezzo|monthly|monthlyPrice|canone|fee|amount|tariffa)\W{0,40}(\d{1,3})\s*[,\.]\s*(\d{1,2})",
    re.I,
)
PRICE_EUR_WORD = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{1,2})\s*(?:euro|eur)\b", re.I)
GB = re.compile(r"(\d{1,4})\s*(?:GB|Giga)\b", re.I)
GB_STRUCT = re.compile(r"(?:data|giga|gb|volume|includedData)\W{0,40}(\d{1,4})", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)
MINUTES = re.compile(r"(\d{1,5})\s*minuti", re.I)
EXCLUDE_BLOCK = re.compile(
    r"router|fibra|internet\s+casa|business|estero|roaming|dettagli\s+tariffari|impressum|privacy|cookie",
    re.I,
)
SCRIPT_HINT = re.compile(r"spusu|tariff|tarif|giga|gb|price|prezzo|riserva|bundle|offer", re.I)


def _clean(text: str) -> str:
    text = html_lib.unescape(text or "")
    text = text.replace("\\u002F", "/").replace("\\u003C", "<").replace("\\u003E", ">")
    text = text.replace("\\u0026", "&").replace("\\n", " ").replace("\\t", " ")
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _visible_lines(html: str) -> list[str]:
    soup = _soup(html)
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [x for x in (_clean(v) for v in soup.get_text("\n", strip=True).splitlines()) if x and x not in {"*", "•", "|"}]


def _price(text: str) -> float | None:
    for rx in (PRICE, PRICE_STRUCT, PRICE_EUR_WORD):
        if m := rx.search(text):
            dec = m.group(2)
            if len(dec) == 1:
                dec = f"{dec}0"
            value = float(f"{m.group(1)}.{dec[:2]}")
            return value if 1 <= value <= 80 else None
    return None


def _primary_giga(block: str, title: str = "") -> int | None:
    vals: list[int] = []
    for m in GB.finditer(block):
        around = block[max(0, m.start() - 90): min(len(block), m.end() + 90)]
        if re.search(r"riserva|reserve", around, re.I):
            continue
        val = int(m.group(1))
        if 1 <= val <= 2000:
            vals.append(val)
    if vals:
        return vals[0]

    # Nei chunk JS può esserci solo dataVolume:150 o il titolo spusu 150.
    for m in GB_STRUCT.finditer(block):
        val = int(m.group(1))
        around = block[max(0, m.start() - 80): min(len(block), m.end() + 80)]
        if re.search(r"riserva|reserve", around, re.I):
            continue
        if 1 <= val <= 2000:
            return val

    if m := re.search(r"spusu\s+(\d{1,4})\b", title, re.I):
        val = int(m.group(1))
        return val if 1 <= val <= 2000 else None
    if m := re.search(r"spusu\s+(\d{1,4})\b", block, re.I):
        val = int(m.group(1))
        return val if 1 <= val <= 2000 else None
    return None


def _reserve_giga(block: str) -> int | None:
    for m in GB.finditer(block):
        around = block[max(0, m.start() - 90): min(len(block), m.end() + 90)]
        if re.search(r"riserva|reserve", around, re.I):
            val = int(m.group(1))
            return val if 1 <= val <= 5000 else None
    return None


def _minutes(block: str) -> str:
    if re.search(r"minuti[^.;]{0,120}illimitat|illimitat[^.;]{0,120}minuti", block, re.I):
        return "illimitati"
    if m := MINUTES.search(block):
        return m.group(1)
    return ""


def _sms(block: str) -> str:
    if re.search(r"SMS[^.;]{0,120}illimitat|illimitat[^.;]{0,120}SMS", block, re.I):
        return "illimitati"
    if m := SMS.search(block):
        return m.group(1)
    return ""


def _title(block: str) -> str:
    if m := TITLE.search(block):
        title = _clean(m.group(0))
        # Evita di salvare solo il brand quando c'è un numero vicino.
        if title.lower() == "spusu":
            if n := re.search(r"spusu\W{0,20}(\d{1,4})", block, re.I):
                return f"spusu {n.group(1)}"
        return title[:80]
    if g := _primary_giga(block):
        return f"spusu {g}"
    return "spusu"


def _offer_from_text(block: str) -> Offer | None:
    block = _clean(block)
    if len(block) < 12:
        return None
    if EXCLUDE_BLOCK.search(block) and not re.search(r"\bGB\b|Giga|SIM|minuti|SMS|tariff", block, re.I):
        return None
    if not re.search(r"spusu|\bGB\b|Giga|tariff|offer|bundle", block, re.I):
        return None

    title = _title(block)
    price = _price(block)
    giga = _primary_giga(block, title)
    if price is None or giga is None:
        return None
    if not (1 <= price <= 80 and 1 <= giga <= 2000):
        return None

    reserve = _reserve_giga(block)
    note_parts: list[str] = []
    if reserve and reserve != giga:
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


def _dedupe(offers: list[Offer]) -> list[Offer]:
    out: list[Offer] = []
    seen: set[tuple] = set()
    for offer in offers:
        key = (round(offer.prezzo_mese or 0, 2), offer.giga, offer.offerta.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(offer)
    return out


def _parse_visible(html: str) -> list[Offer]:
    lines = _visible_lines(html)
    offers: list[Offer] = []

    # Blocchi per titolo.
    for i, line in enumerate(lines):
        if not TITLE.search(line) or _clean(line).lower() == "spusu":
            continue
        end = min(len(lines), i + 28)
        for j in range(i + 1, min(len(lines), i + 40)):
            nxt = _clean(lines[j])
            if TITLE.search(nxt) and nxt.lower() != "spusu":
                end = j
                break
        if offer := _offer_from_text(" ".join(lines[i:end])):
            offers.append(offer)

    # Blocchi per prezzo.
    for i, line in enumerate(lines):
        if _price(line) is None and _price(" ".join(lines[i:i + 3])) is None:
            continue
        start = max(0, i - 16)
        end = min(len(lines), i + 18)
        if offer := _offer_from_text(" ".join(lines[start:end])):
            offers.append(offer)

    return _dedupe(offers)


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
        if not txt or not SCRIPT_HINT.search(txt):
            continue
        stripped = txt.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                out.append(json.loads(stripped))
            except Exception:
                pass
    return out


def _parse_json_like(html: str) -> list[Offer]:
    out: list[Offer] = []
    for payload in _json_candidates(html):
        for node in _walk(payload):
            blob = _clean(json.dumps(node, ensure_ascii=False))
            if "spusu" not in blob.lower() and not re.search(r"gb|giga|tariff|price|prezzo", blob, re.I):
                continue
            if offer := _offer_from_text(blob):
                out.append(offer)
    return _dedupe(out)


def _script_urls(html: str, base_url: str) -> list[str]:
    soup = _soup(html)
    urls: list[str] = []
    seen: set[str] = set()
    for tag in soup.find_all("script", src=True):
        src = str(tag.get("src") or "")
        if not src:
            continue
        full = urljoin(base_url, src)
        if not re.search(r"\.js(?:\?|$)", full, re.I):
            continue
        if full in seen:
            continue
        seen.add(full)
        urls.append(full)
    return urls[:25]


def _fetch_script_texts(html: str, base_url: str) -> str:
    chunks: list[str] = []
    for src in _script_urls(html, base_url):
        js = fetch_html(src, timeout=20)
        if js and SCRIPT_HINT.search(js):
            chunks.append(f"\n/* {src} */\n{js[:1_200_000]}")
    combined = "\n".join(chunks)
    dump_debug("spusu_assets", combined)
    return combined


def _parse_raw_text(raw: str) -> list[Offer]:
    raw = _clean(raw)
    offers: list[Offer] = []

    starts: set[int] = set()
    for rx in (TITLE, re.compile(r"(?:price|prezzo|tariff|bundle)", re.I), GB):
        for m in rx.finditer(raw):
            starts.add(max(0, m.start() - 450))
            if len(starts) > 500:
                break
    for start in sorted(starts):
        block = raw[start:start + 1600]
        if offer := _offer_from_text(block):
            offers.append(offer)
    return _dedupe(offers)


def parse_html(html: str, xhr: list | None = None, base_url: str = URL) -> list[Offer]:
    offers = _parse_visible(html)
    if offers:
        return offers

    offers = _parse_json_like(html)
    if offers:
        return offers

    assets = _fetch_script_texts(html, base_url)
    if assets:
        offers = _parse_raw_text(assets)
        if offers:
            return offers

    # Ultimi fallback tecnici, sempre su dati della pagina/API, mai manuali.
    offers = parse_cards(html, OPERATORE, base_url)
    if offers:
        return offers

    if xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, base_url)
    return offers


def scrape() -> list[Offer]:
    for url in URLS:
        html, xhr = fetch_mobile_page(url)
        dump_debug("spusu", html)
        if html:
            offers = parse_html(html, xhr, base_url=url)
            if offers:
                return offers

    rendered, rendered_xhr = fetch_rendered(URL)
    dump_debug("spusu_rendered", rendered)
    if not rendered:
        return []
    return parse_html(rendered, rendered_xhr, base_url=URL)


if __name__ == "__main__":
    cli_main("mobile", "spusu", OPERATORE, scrape)
