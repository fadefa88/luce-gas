"""Offerte LUCE e GAS.

Fonte primaria: dataset open data del Portale Offerte, se configurato tramite
PORTALE_OPEN_DATA_URL. Fallback: pagine pubbliche dei fornitori definite in
scraper/config/providers.yaml.
"""

from __future__ import annotations

import csv
import io
import os
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .common import fetch, norm_text, now_iso, parse_euro

PORTALE_OPEN_DATA_URL = os.environ.get("PORTALE_OPEN_DATA_URL", "").strip()


def _field(row: dict[str, str], *needles: str) -> str:
    low = {str(k).lower(): (v or "").strip() for k, v in row.items() if k is not None}
    for needle in needles:
        n = needle.lower()
        for key, value in low.items():
            if n in key and value:
                return value
    return ""


def _detect_commodity(text: str) -> str | None:
    t = text.lower()
    if any(x in t for x in ("energia elettrica", "elettric", "luce", "kwh", "power")):
        return "luce"
    if any(x in t for x in ("gas", "smc", "standard metro cubo")):
        return "gas"
    return None


def _detect_price_type(text: str) -> str:
    return "fisso" if re.search(r"\bfiss[oa]\b|bloccato|prezzo bloccato", text, re.I) else "variabile"


def _is_valid_offer(offer: dict) -> bool:
    price = offer.get("prezzo_energia")
    commodity = offer.get("commodity")
    if not isinstance(price, (int, float)):
        return False
    if commodity == "luce":
        return 0.01 <= price <= 1.0
    if commodity == "gas":
        return 0.05 <= price <= 3.0
    return False


def _dedupe(offers: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for offer in offers:
        if not _is_valid_offer(offer):
            continue
        key = "|".join(
            [
                norm_text(offer.get("fornitore", "")).lower(),
                norm_text(offer.get("offerta", "")).lower(),
                offer.get("commodity", ""),
                str(round(float(offer.get("prezzo_energia", 0)), 5)),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(offer)
    return out


def _read_csv(raw: str) -> list[dict[str, str]]:
    sample = raw[:4096]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        delimiter = dialect.delimiter
    except Exception:
        pass
    return list(csv.DictReader(io.StringIO(raw), delimiter=delimiter))


def _from_portale_offerte() -> list[dict]:
    if not PORTALE_OPEN_DATA_URL:
        return []

    raw = fetch(PORTALE_OPEN_DATA_URL, timeout=45)
    if not raw:
        return []

    offers: list[dict] = []
    try:
        for row in _read_csv(raw):
            all_text = " ".join(str(v or "") for v in row.values())
            commodity = _detect_commodity(all_text)
            if not commodity:
                continue

            price_text = _field(row, "prezzo", "corrispettivo", "componente energia", "materia", "price")
            price = parse_euro(price_text)
            if price is None:
                continue

            fixed_fee = parse_euro(_field(row, "quota fissa", "pcv", "commercializzazione", "fisso")) or 0
            provider = _field(row, "venditore", "ragione sociale", "fornitore", "operatore") or "n.d."
            name = _field(row, "nome offerta", "offerta", "denominazione") or "Offerta"

            offers.append(
                {
                    "fornitore": norm_text(provider),
                    "offerta": norm_text(name),
                    "commodity": commodity,
                    "prezzo_energia": round(float(price), 5),
                    "quota_fissa_mese": round(float(fixed_fee), 2),
                    "tipo": _detect_price_type(all_text),
                    "fonte": "Portale Offerte open data",
                    "url": "https://www.ilportaleofferte.it/",
                }
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  [errore] parsing Portale Offerte: {exc}")
    return _dedupe(offers)


def _find_fixed_fee(text: str) -> float:
    patterns = [
        r"(\d+[.,]\d+)\s*€\s*/?\s*mese",
        r"quota\s+fissa\D{0,30}(\d+[.,]\d+)",
        r"pcv\D{0,30}(\d+[.,]\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1).replace(",", "."))
    return 0.0


def _offer_link(block, base_url: str) -> str:
    link = block.select_one("a[href]")
    return urljoin(base_url, link.get("href")) if link else base_url


def _from_provider_pages(providers: list[dict]) -> list[dict]:
    offers: list[dict] = []
    for provider in providers:
        name = provider.get("nome", provider.get("id", "fornitore"))
        url = provider.get("url", "")
        print(f"- {name} ({url})")
        html = fetch(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        selector = provider.get("selector", "article, section, [class*=card], [class*=offer]")
        price_re = re.compile(provider.get("price_regex", r"(\d+[.,]\d+)\s*€"), re.I)
        blocks = soup.select(selector)[:40]

        for block in blocks:
            text = norm_text(block.get_text(" ", strip=True), 1200)
            match = price_re.search(text)
            if not match:
                continue

            price = float(match.group(1).replace(",", "."))
            name_el = block.select_one(provider.get("name_selector", "h1, h2, h3, h4, strong"))
            offer_name = norm_text(name_el.get_text(" ", strip=True) if name_el else "Offerta")
            configured = provider.get("commodity", "luce")
            commodities = ["luce", "gas"] if configured == "luce+gas" else [configured]

            for commodity in commodities:
                if configured == "luce+gas":
                    unit = "kwh" if commodity == "luce" else "smc"
                    if unit not in text.lower():
                        continue
                offers.append(
                    {
                        "fornitore": norm_text(name),
                        "offerta": offer_name,
                        "commodity": commodity,
                        "prezzo_energia": round(price, 5),
                        "quota_fissa_mese": round(_find_fixed_fee(text), 2),
                        "tipo": _detect_price_type(text),
                        "fonte": "pagina offerte fornitore",
                        "url": _offer_link(block, url),
                    }
                )
    return _dedupe(offers)


def collect_energy_offers(providers: list[dict]) -> dict:
    source = "portale_offerte"
    offers = _from_portale_offerte()
    if not offers:
        source = "siti_fornitori"
        offers = _from_provider_pages(providers)

    cleaned = _dedupe(offers)
    return {"updated": now_iso(), "source": source, "offers": cleaned}
