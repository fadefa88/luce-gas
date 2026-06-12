"""Offerte LUCE e GAS — v2.

Fonte primaria: open data del Portale Offerte ARERA (se PORTALE_OPEN_DATA_URL
è configurata). Fallback: pagine pubbliche dei fornitori, con rendering
Playwright, estrazione JSON-LD e auto-scoperta via sitemap.
"""

from __future__ import annotations

import csv
import io
import os
import re

from .common import (discover_offers_url, dump_debug, fetch, fetch_page,
                     now_iso, parse_euro, report)
from .extract import extract_energy

PORTALE_OPEN_DATA_URL = os.environ.get("PORTALE_OPEN_DATA_URL", "")


def _from_portale_offerte() -> list[dict]:
    if not PORTALE_OPEN_DATA_URL:
        return []
    raw = fetch(PORTALE_OPEN_DATA_URL)
    if not raw:
        report("portale_offerte", "errore", "download fallito")
        return []
    offers: list[dict] = []
    try:
        sample = raw[:4000]
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(io.StringIO(raw), delimiter=delim)
        for row in reader:
            low = {k.lower(): (v or "").strip() for k, v in row.items() if k}

            def col(*names):
                for n in names:
                    for k, v in low.items():
                        if n in k:
                            return v
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
                "fonte": "Portale Offerte ARERA (open data)",
                "url": "https://www.ilportaleofferte.it/",
            })
        report("portale_offerte", "ok" if offers else "vuota", n=len(offers))
    except Exception as exc:  # noqa: BLE001
        report("portale_offerte", "errore", str(exc)[:120])
    return offers


def _base(url: str) -> str:
    match = re.match(r"(https?://[^/]+)", url)
    return match.group(1) if match else url


def _from_provider_pages(providers: list[dict]) -> list[dict]:
    offers: list[dict] = []
    for p in providers:
        if p.get("enabled") is False:
            report(p["id"], "disattivata", "vedi providers.yaml")
            continue
        print(f"- {p['nome']}")
        urls = list(p.get("urls", []))
        html, used = fetch_page(urls, render=p.get("render", "auto"))
        if html is None and urls and p.get("sitemap_keywords"):
            found = discover_offers_url(_base(urls[0]), p["sitemap_keywords"])
            if found:
                html, used = fetch_page([found], render=p.get("render", "auto"))
        if html is None:
            report(p["id"], "errore", "nessun URL raggiungibile")
            continue
        got = extract_energy(html, p)
        for o in got:
            o["url"] = used
        offers.extend(got)
        if got:
            report(p["id"], "ok", used, n=len(got))
            print(f"  {len(got)} offerte da {used}")
        else:
            report(p["id"], "vuota", f"pagina letta ma 0 offerte ({used})")
            dump_debug(p["id"], html)
    return offers


def _resolve_spreads(offers: list[dict]) -> list[dict]:
    """Trasforma offerte 'PUN/PSV + spread' in prezzi assoluti."""
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
        offers = _resolve_spreads(_from_provider_pages(providers))
        source = "siti_fornitori"
    return {"updated": now_iso(), "source": source, "offers": offers}
