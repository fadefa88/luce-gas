"""Offerte LUCE e GAS v2.

Fonte primaria: open data del Portale Offerte se PORTALE_OPEN_DATA_URL è
configurata. Fallback: pagine pubbliche dei fornitori con rendering Playwright,
JSON-LD e discovery via sitemap.
"""

from __future__ import annotations

import csv
import io
import os
import re
from urllib.parse import urlparse

from .common import discover_offers_url, dump_debug, fetch, fetch_page, now_iso, parse_euro, report
from .extract import extract_energy

PORTALE_OPEN_DATA_URL = os.environ.get("PORTALE_OPEN_DATA_URL", "").strip()


def _base(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _from_portale_offerte() -> list[dict]:
    if not PORTALE_OPEN_DATA_URL:
        return []
    raw = fetch(PORTALE_OPEN_DATA_URL, timeout=45)
    if not raw:
        report("portale_offerte", "errore", "download fallito")
        return []

    offers: list[dict] = []
    try:
        sample = raw[:4000]
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(io.StringIO(raw), delimiter=delimiter)
        for row in reader:
            low = {str(k).lower(): (v or "").strip() for k, v in row.items() if k}

            def col(*names: str) -> str:
                for name in names:
                    for key, value in low.items():
                        if name in key and value:
                            return value
                return ""

            text = " ".join(low.values()).lower()
            commodity = "luce" if any(x in text for x in ("elettric", "luce", "kwh")) else "gas"
            price = parse_euro(col("prezzo", "price", "corrispettivo", "materia"))
            if price is None:
                continue
            offers.append({
                "fornitore": col("venditore", "ragione", "fornitore") or "n.d.",
                "offerta": col("nome", "offerta", "denominazione") or "Offerta",
                "commodity": commodity,
                "prezzo_energia": price,
                "quota_fissa_mese": parse_euro(col("quota", "pcv", "fisso", "commercializzazione")) or 0,
                "tipo": "fisso" if "fiss" in col("tipologia", "tipo").lower() else "variabile",
                "fonte": "Portale Offerte open data",
                "url": "https://www.ilportaleofferte.it/",
            })
        report("portale_offerte", "ok" if offers else "vuota", n=len(offers))
    except Exception as exc:  # noqa: BLE001
        report("portale_offerte", "errore", str(exc)[:180])
    return _dedupe(offers)


def _dedupe(offers: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for offer in offers:
        price = offer.get("prezzo_energia")
        commodity = offer.get("commodity")
        if not isinstance(price, (int, float)):
            continue
        valid = (commodity == "luce" and 0.01 <= price <= 1.0) or (commodity == "gas" and 0.05 <= price <= 3.0)
        key = (offer.get("fornitore"), offer.get("offerta"), commodity, round(float(price), 5))
        if valid and key not in seen:
            seen.add(key)
            out.append(offer)
    return out


def _from_provider_pages(providers: list[dict]) -> list[dict]:
    offers: list[dict] = []
    for provider in providers:
        if provider.get("enabled") is False:
            report(provider["id"], "disattivata", "vedi providers.yaml")
            continue

        print(f"- {provider['nome']}")
        urls = list(provider.get("urls") or ([provider["url"]] if provider.get("url") else []))
        html, used = fetch_page(urls, render=provider.get("render", "auto"))
        if html is None and urls and provider.get("sitemap_keywords"):
            found = discover_offers_url(_base(urls[0]), provider["sitemap_keywords"])
            if found:
                html, used = fetch_page([found], render=provider.get("render", "auto"))

        if html is None:
            report(provider["id"], "errore", "nessun URL raggiungibile")
            continue

        found_offers = extract_energy(html, provider)
        for offer in found_offers:
            offer["url"] = used
        offers.extend(found_offers)

        if found_offers:
            report(provider["id"], "ok", used or "", n=len(found_offers))
            print(f"  {len(found_offers)} offerte da {used}")
        else:
            report(provider["id"], "vuota", f"pagina letta ma 0 offerte ({used})")
            dump_debug(provider["id"], html)
    return _dedupe(offers)


def collect_energy_offers(providers: list[dict]) -> dict:
    offers = _from_portale_offerte()
    source = "portale_offerte"
    if not offers:
        offers = _from_provider_pages(providers)
        source = "siti_fornitori"
    return {"updated": now_iso(), "source": source, "offers": _dedupe(offers)}
