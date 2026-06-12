"""Offerte TELEFONIA MOBILE v2: Playwright + JSON-LD + discovery."""

from __future__ import annotations

from urllib.parse import urlparse

from .common import discover_offers_url, dump_debug, fetch_page, now_iso, report
from .extract import extract_mobile


def _base(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _dedupe(offers: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for offer in offers:
        price = offer.get("prezzo_mese")
        giga = offer.get("giga")
        if not isinstance(price, (int, float)) or not isinstance(giga, int):
            continue
        key = (offer.get("operatore"), offer.get("offerta"), round(float(price), 2), giga)
        if 1 <= price <= 60 and 1 <= giga <= 1000 and key not in seen:
            seen.add(key)
            out.append(offer)
    return out


def collect_mobile_offers(providers: list[dict]) -> dict:
    offers: list[dict] = []
    for provider in providers:
        if provider.get("enabled") is False:
            report(provider["id"], "disattivata", "vedi providers.yaml")
            print(f"- {provider['nome']} [disattivato]")
            continue

        print(f"- {provider['nome']}")
        urls = list(provider.get("urls") or ([provider["url"]] if provider.get("url") else []))
        html, used = fetch_page(urls, render=provider.get("render", "always"))
        if html is None and urls and provider.get("sitemap_keywords"):
            found = discover_offers_url(_base(urls[0]), provider["sitemap_keywords"])
            if found:
                html, used = fetch_page([found], render=provider.get("render", "always"))

        if html is None:
            report(provider["id"], "errore", "nessun URL raggiungibile")
            continue

        found_offers = extract_mobile(html, provider)
        for offer in found_offers:
            offer["url"] = used
        offers.extend(found_offers)

        if found_offers:
            report(provider["id"], "ok", used or "", n=len(found_offers))
            print(f"  {len(found_offers)} offerte da {used}")
        else:
            report(provider["id"], "vuota", f"pagina letta ma 0 offerte ({used})")
            dump_debug(provider["id"], html)

    return {"updated": now_iso(), "source": "siti_operatori", "offers": _dedupe(offers)}
