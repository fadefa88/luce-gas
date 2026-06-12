"""Offerte LUCE/GAS: open data se configurato, altrimenti pagine fornitori."""

from __future__ import annotations

import csv
import io
import os
import re

from .common import LAST_XHR, discover_offers_url, dump_debug, fetch, fetch_page, now_iso, parse_euro, report
from .extract import dedup_energy, extract_energy, mine_xhr_energy

PORTALE_OPEN_DATA_URL = os.environ.get("PORTALE_OPEN_DATA_URL", "")


def _from_portale_offerte() -> list[dict]:
    if not PORTALE_OPEN_DATA_URL:
        return []
    raw = fetch(PORTALE_OPEN_DATA_URL)
    if not raw:
        report("portale_offerte", "errore", "download fallito")
        return []
    offers = []
    try:
        sample = raw[:4000]
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        for row in csv.DictReader(io.StringIO(raw), delimiter=delimiter):
            low = {str(k).lower(): (v or "").strip() for k, v in row.items() if k}

            def col(*names):
                for name in names:
                    for key, value in low.items():
                        if name in key:
                            return value
                return ""

            commodity = "luce" if "ele" in col("commodity", "mercato", "tipo").lower() else "gas"
            price = parse_euro(col("prezzo", "price", "corrispettivo"))
            if price is None:
                continue
            offers.append({
                "fornitore": col("venditore", "ragione", "fornitore") or "n.d.",
                "offerta": col("nome", "offerta") or "Offerta",
                "commodity": commodity,
                "prezzo_energia": price,
                "quota_fissa_mese": parse_euro(col("quota", "pcv", "fisso")) or 0,
                "tipo": "fisso" if "fiss" in col("tipologia", "tipo").lower() else "variabile",
                "fonte": "open data",
                "url": "https://www.ilportaleofferte.it/",
            })
        report("portale_offerte", "ok" if offers else "vuota", n=len(offers))
    except Exception as exc:
        report("portale_offerte", "errore", str(exc)[:120])
    return offers


def _base(url: str) -> str:
    match = re.match(r"(https?://[^/]+)", url)
    return match.group(1) if match else url


def _from_provider_pages(providers: list[dict]) -> list[dict]:
    offers = []
    for provider in providers:
        if provider.get("enabled") is False:
            report(provider["id"], "disattivata", "vedi providers.yaml")
            continue
        print(f"- {provider['nome']}")
        urls = list(provider.get("urls", []))
        html, used = fetch_page(urls, render=provider.get("render", "auto"))
        if html is None and urls and provider.get("sitemap_keywords"):
            found = discover_offers_url(_base(urls[0]), provider["sitemap_keywords"])
            if found:
                html, used = fetch_page([found], render=provider.get("render", "auto"))
        if html is None:
            report(provider["id"], "errore", "nessun URL raggiungibile")
            continue
        got = extract_energy(html, provider)
        if not got:
            got = mine_xhr_energy(list(LAST_XHR), provider)
        for offer in got:
            offer["url"] = used
        offers.extend(got)
        if got:
            report(provider["id"], "ok", used, n=len(got))
        else:
            report(provider["id"], "vuota", f"pagina letta ma 0 offerte ({used})")
            dump_debug(provider["id"], html)
    return offers


def _resolve_spreads(offers: list[dict]) -> list[dict]:
    from .common import DATA_DIR, load_json
    latest = load_json(DATA_DIR / "commodity_latest.json", {})
    pun = (latest.get("pun") or {}).get("eur_kwh")
    psv = (latest.get("psv") or {}).get("eur_smc")
    out = []
    for offer in offers:
        if offer.get("indice"):
            base = pun if offer["indice"] == "PUN" else psv
            if base is None:
                continue
            offer["prezzo_energia"] = round(base + offer["spread"], 4)
            offer["offerta"] += f" ({offer['indice']} + {offer['spread']})"
        out.append(offer)
    return out


def collect_energy_offers(providers: list[dict]) -> dict:
    offers = _from_portale_offerte()
    source = "portale_offerte"
    if not offers:
        offers = dedup_energy(_resolve_spreads(_from_provider_pages(providers)))
        source = "siti_fornitori"
    return {"updated": now_iso(), "source": source, "offers": offers}
