"""Vianova — offerte mobile reali dalla pagina ufficiale.

Pagina principale: https://www.vianova.it/privati/mobile

Niente fallback manuali. Vianova e' meno consumer di altri operatori e la pagina
puo' mischiare mobile, fibra, centralino/cloud e contenuti aziendali. Questo
scraper quindi prova piu' URL ufficiali e legge solo blocchi con segnali SIM/mobile:
GB/Giga + prezzo mensile + SIM/mobile/minuti/SMS/5G.

Se il testo HTML non basta, scarica anche i chunk JavaScript referenziati dalla
pagina e prova Playwright/rendering.
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

URL = "https://www.vianova.it/privati/mobile"
URLS = [
    URL,
    "https://www.vianova.it/privati/mobile/",
    "https://www.vianova.it/mobile",
    "https://www.vianova.it/mobile/",
    "https://www.vianova.it/aziende/mobile",
    "https://www.vianova.it/aziende/mobile/",
]
OPERATORE = "Vianova"

PRICE = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{1,2})\s*€", re.I)
PRICE_STRUCT = re.compile(
    r"(?:price|prezzo|monthly|monthlyPrice|canone|fee|amount|tariffa|costo)\W{0,50}(\d{1,3})\s*[,\.]\s*(\d{1,2})",
    re.I,
)
PRICE_EUR_WORD = re.compile(r"(\d{1,3})\s*[,\.]\s*(\d{1,2})\s*(?:euro|eur)\b", re.I)
GB = re.compile(r"(\d{1,4})\s*(?:GB|Giga)\b", re.I)
GB_STRUCT = re.compile(r"(?:data|giga|gb|volume|includedData|bundle)\W{0,50}(\d{1,4})", re.I)
SMS = re.compile(r"(\d{1,4})\s*SMS", re.I)
MINUTES = re.compile(r"(\d{1,5})\s*minuti", re.I)
TITLE_HINT = re.compile(r"\b(?:Vianova|Mobile|SIM|5G|Plus|Start|Pro|Top|Business|Smart|Giga)\b", re.I)
MOBILE_SIGNAL = re.compile(r"\b(?:mobile|sim|giga|gb|minuti|sms|5g|4g|voce|dati)\b", re.I)
EXCLUDE_BLOCK = re.compile(
    r"fibra|centralino|cloud|data\s*center|server|backup|firewall|voip|pec|dominio|hosting|router|modem|sd-wan|vpn|ufficio|telefono\s+fisso",
    re.I,
)
SCRIPT_HINT = re.compile(r"vianova|mobile|sim|giga|gb|price|prezzo|tariff|bundle|offer|offerta", re.I)


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
            return value if 1 <= value <= 120 else None
    return None


def _primary_giga(block: str) -> int | None:
    vals = [int(x) for x in GB.findall(block) if 1 <= int(x) <= 2000]
    if vals:
        return vals[0]
    for m in GB_STRUCT.finditer(block):
        val = int(m.group(1))
        if 1 <= val <= 2000:
            return val
    return None


def _minutes(block: str) -> str:
    if re.search(r"minuti[^.;]{0,120}illimitat|illimitat[^.;]{0,120}minuti|chiamate[^.;]{0,120}illimitat|illimitat[^.;]{0,120}chiamate", block, re.I):
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


def _title(block: str, giga: int | None) -> str:
    # Cerca una riga breve vicino al blocco che somigli a un nome offerta.
    for piece in re.split(r"[|•\n]", block):
        c = _clean(piece)
        if not c or len(c) > 90:
            continue
        if PRICE.search(c) or GB.fullmatch(c) or re.search(r"scopri|attiva|mese|minuti|sms|giga|gb|prezzo|costo|dettagli", c, re.I):
            continue
        if TITLE_HINT.search(c):
            return c[:80]
    return f"Vianova Mobile {giga} GB" if giga else "Vianova Mobile"


def _offer_from_text(block: str, source_url: str) -> Offer | None:
    block = _clean(block)
    if len(block) < 12:
        return None
    if not MOBILE_SIGNAL.search(block):
        return None
    # Se parla chiaramente di prodotti non mobile e non ha SIM/minuti/SMS, scarta.
    if EXCLUDE_BLOCK.search(block) and not re.search(r"\bSIM\b|minuti|SMS|\bGB\b|Giga|5G", block, re.I):
        return None

    price = _price(block)
    giga = _primary_giga(block)
    if price is None or giga is None:
        return None
    if not (1 <= price <= 120 and 1 <= giga <= 2000):
        return None

    note_parts: list[str] = []
    if re.search(r"solo\s+aziende|partita\s+iva|business|professionisti", block, re.I):
        note_parts.append("utenza business/professionisti")
    if re.search(r"5G", block, re.I):
        note_parts.append("5G")
    if re.search(r"eSIM", block, re.I):
        note_parts.append("eSIM disponibile")

    return Offer(
        operatore=OPERATORE,
        offerta=_title(block, giga),
        url=source_url,
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


def _parse_visible(html: str, source_url: str) -> list[Offer]:
    lines = _visible_lines(html)
    offers: list[Offer] = []

    # Finestre intorno ai prezzi.
    for i, line in enumerate(lines):
        joined = _clean(" ".join(lines[i:i + 3]))
        if _price(line) is None and _price(joined) is None:
            continue
        start = max(0, i - 16)
        end = min(len(lines), i + 18)
        if offer := _offer_from_text(" ".join(lines[start:end]), source_url):
            offers.append(offer)

    # Finestre intorno a GB/Giga, utili se il prezzo viene dopo.
    for i, line in enumerate(lines):
        if not GB.search(line):
            continue
        start = max(0, i - 14)
        end = min(len(lines), i + 18)
        if offer := _offer_from_text(" ".join(lines[start:end]), source_url):
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


def _parse_json_like(html: str, source_url: str) -> list[Offer]:
    offers: list[Offer] = []
    for payload in _json_candidates(html):
        for node in _walk(payload):
            blob = _clean(json.dumps(node, ensure_ascii=False))
            if not SCRIPT_HINT.search(blob):
                continue
            if offer := _offer_from_text(blob, source_url):
                offers.append(offer)
    return _dedupe(offers)


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
    return urls[:30]


def _fetch_script_texts(html: str, base_url: str) -> str:
    chunks: list[str] = []
    for src in _script_urls(html, base_url):
        js = fetch_html(src, timeout=20)
        if js and SCRIPT_HINT.search(js):
            chunks.append(f"\n/* {src} */\n{js[:1_200_000]}")
    combined = "\n".join(chunks)
    dump_debug("vianova_assets", combined)
    return combined


def _parse_raw_text(raw: str, source_url: str) -> list[Offer]:
    raw = _clean(raw)
    offers: list[Offer] = []
    starts: set[int] = set()
    for rx in (PRICE, GB, re.compile(r"(?:mobile|sim|tariff|bundle|offerta|price|prezzo)", re.I)):
        for m in rx.finditer(raw):
            starts.add(max(0, m.start() - 500))
            if len(starts) > 600:
                break
    for start in sorted(starts):
        if offer := _offer_from_text(raw[start:start + 1800], source_url):
            offers.append(offer)
    return _dedupe(offers)


def parse_html(html: str, xhr: list | None = None, source_url: str = URL) -> list[Offer]:
    offers = _parse_visible(html, source_url)
    if offers:
        return offers

    offers = _parse_json_like(html, source_url)
    if offers:
        return offers

    assets = _fetch_script_texts(html, source_url)
    if assets:
        offers = _parse_raw_text(assets, source_url)
        if offers:
            return offers

    # Fallback tecnici, sempre sulla fonte reale.
    offers = [o for o in parse_cards(html, OPERATORE, source_url) if o.giga_illimitati or (o.giga is not None and o.giga >= 1)]
    if offers:
        return offers

    if xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, source_url)
    return offers


def scrape() -> list[Offer]:
    for url in URLS:
        html, xhr = fetch_mobile_page(url)
        dump_debug("vianova", html)
        if html:
            offers = parse_html(html, xhr, source_url=url)
            if offers:
                return offers

    rendered, rendered_xhr = fetch_rendered(URL)
    dump_debug("vianova_rendered", rendered)
    if not rendered:
        return []
    return parse_html(rendered, rendered_xhr, source_url=URL)


if __name__ == "__main__":
    cli_main("mobile", "vianova", OPERATORE, scrape)
