"""Offerte TELEFONIA MOBILE.

Legge la pagina pubblica principale di ogni operatore configurato, estraendo
nome offerta, prezzo mensile, GB inclusi e link all'offerta quando disponibile.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .common import fetch, norm_text, now_iso


def _price_to_float(value: str) -> float:
    return float(value.replace(",", "."))


def _offer_link(block, base_url: str) -> str:
    link = block.select_one("a[href]")
    return urljoin(base_url, link.get("href")) if link else base_url


def _dedupe(offers: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for offer in offers:
        price = offer.get("prezzo_mese")
        giga = offer.get("giga")
        if not isinstance(price, (int, float)) or not isinstance(giga, int):
            continue
        if not (1 <= price <= 60 and 1 <= giga <= 1000):
            continue
        key = "|".join(
            [
                norm_text(offer.get("operatore", "")).lower(),
                norm_text(offer.get("offerta", "")).lower(),
                str(round(float(price), 2)),
                str(giga),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(offer)
    return out


def collect_mobile_offers(providers: list[dict]) -> dict:
    offers: list[dict] = []
    for provider in providers:
        name = provider.get("nome", provider.get("id", "operatore"))
        url = provider.get("url", "")
        print(f"- {name} ({url})")
        html = fetch(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        selector = provider.get("selector", "article, section, [class*=card], [class*=offer]")
        price_re = re.compile(provider.get("price_regex", r"(\d+[.,]?\d*)\s*€"), re.I)
        gb_re = re.compile(provider.get("gb_regex", r"(\d+)\s*(?:GB|Giga)"), re.I)

        for block in soup.select(selector)[:40]:
            text = norm_text(block.get_text(" ", strip=True), 1200)
            price_match = price_re.search(text)
            gb_match = gb_re.search(text)
            if not (price_match and gb_match):
                continue

            price = _price_to_float(price_match.group(1))
            giga = int(gb_match.group(1))
            if not (1 <= price <= 60 and 1 <= giga <= 1000):
                continue

            name_el = block.select_one(provider.get("name_selector", "h1, h2, h3, h4, strong"))
            offer_name = norm_text(name_el.get_text(" ", strip=True) if name_el else f"{giga} GB")

            offers.append(
                {
                    "operatore": norm_text(name),
                    "offerta": offer_name,
                    "prezzo_mese": round(price, 2),
                    "giga": giga,
                    "prezzo_per_gb": round(price / giga, 3),
                    "rete_5g": bool(re.search(r"\b5G\b", text, re.I)),
                    "fonte": "pagina offerte operatore",
                    "url": _offer_link(block, url),
                }
            )

    return {"updated": now_iso(), "source": "siti_operatori", "offers": _dedupe(offers)}
