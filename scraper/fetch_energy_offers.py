"""Offerte LUCE e GAS.

Strategia a due livelli:

1) FONTE PRIMARIA — Portale Offerte ARERA (ilportaleofferte.it), sezione
   Open Data. È il comparatore ufficiale: i venditori sono OBBLIGATI a
   pubblicarvi tutte le offerte, e i dati sono rilasciati in modalità aperta.
   È la via più completa, stabile e rispettosa (nessuno scraping dei siti
   commerciali). L'URL del dataset va indicato in PORTALE_OPEN_DATA_URL
   (vedi README: si ricava dalla pagina "Open Data" del portale).

2) FALLBACK — pagina principale pubblica delle offerte di ciascun fornitore
   in config/providers.yaml. Lettura superficiale: solo nome offerta e
   prezzo in evidenza, senza entrare nelle pagine di dettaglio.
"""

from __future__ import annotations

import csv
import io
import os
import re

from bs4 import BeautifulSoup

from .common import fetch, now_iso, parse_euro

# Da impostare (variabile d'ambiente o qui) con il link CSV/JSON pubblicato
# nella pagina Open Data del Portale Offerte. Lasciare vuoto per usare solo
# il fallback sui siti dei fornitori.
PORTALE_OPEN_DATA_URL = os.environ.get("PORTALE_OPEN_DATA_URL", "")


def _from_portale_offerte() -> list[dict]:
    """Legge il dataset open data del Portale Offerte ARERA (CSV)."""
    if not PORTALE_OPEN_DATA_URL:
        return []
    raw = fetch(PORTALE_OPEN_DATA_URL)
    if not raw:
        return []
    offers: list[dict] = []
    try:
        reader = csv.DictReader(io.StringIO(raw), delimiter=";")
        for row in reader:
            # I nomi colonna del dataset possono variare: si cerca in modo tollerante
            low = {k.lower(): (v or "").strip() for k, v in row.items()}

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
            offers.append(
                {
                    "fornitore": col("venditore", "ragione", "fornitore") or "n.d.",
                    "offerta": col("nome", "offerta") or "Offerta",
                    "commodity": commodity,
                    "prezzo_energia": price,  # €/kWh o €/Smc
                    "quota_fissa_mese": parse_euro(col("quota", "pcv", "fisso")) or 0,
                    "tipo": "fisso" if "fiss" in col("tipologia", "tipo").lower() else "variabile",
                    "fonte": "Portale Offerte ARERA (open data)",
                    "url": "https://www.ilportaleofferte.it/",
                }
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  [errore] parsing open data Portale Offerte: {exc}")
    return offers


def _from_provider_pages(providers: list[dict]) -> list[dict]:
    """Fallback: legge solo la pagina principale delle offerte di ogni fornitore."""
    offers: list[dict] = []
    for p in providers:
        print(f"- {p['nome']} ({p['url']})")
        html = fetch(p["url"])
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        price_re = re.compile(p.get("price_regex", r"(\d+[.,]\d+)\s*€"))
        seen: set[str] = set()
        for block in soup.select(p.get("selector", "[class*=card]"))[:30]:
            text = " ".join(block.get_text(" ", strip=True).split())
            m = price_re.search(text)
            if not m:
                continue
            name_el = block.select_one(p.get("name_selector", "h2, h3"))
            name = (name_el.get_text(strip=True) if name_el else "Offerta")[:80]
            key = f"{name}|{m.group(1)}"
            if key in seen:
                continue
            seen.add(key)
            commodities = (
                ["luce", "gas"] if p.get("commodity") == "luce+gas"
                else [p.get("commodity", "luce")]
            )
            # Se la pagina copre luce+gas, si assegna in base al contesto testuale
            for c in commodities:
                if len(commodities) == 2:
                    unit = "kwh" if c == "luce" else "smc"
                    if unit not in text.lower():
                        continue
                offers.append(
                    {
                        "fornitore": p["nome"],
                        "offerta": name,
                        "commodity": c,
                        "prezzo_energia": float(m.group(1).replace(",", ".")),
                        "quota_fissa_mese": _find_fixed_fee(text),
                        "tipo": "fisso" if re.search(r"\bfiss[oa]\b", text, re.I) else "variabile",
                        "fonte": "pagina offerte fornitore",
                        "url": p["url"],
                    }
                )
    return offers


def _find_fixed_fee(text: str) -> float:
    m = re.search(r"(\d+[.,]\d+)\s*€\s*/?\s*mese", text, re.I)
    return float(m.group(1).replace(",", ".")) if m else 0.0


def collect_energy_offers(providers: list[dict]) -> dict:
    offers = _from_portale_offerte()
    source = "portale_offerte"
    if not offers:
        offers = _from_provider_pages(providers)
        source = "siti_fornitori"
    # sanity check: prezzi plausibili (€/kWh < 1, €/Smc < 3)
    cleaned = [
        o for o in offers
        if (o["commodity"] == "luce" and 0.01 <= o["prezzo_energia"] <= 1.0)
        or (o["commodity"] == "gas" and 0.05 <= o["prezzo_energia"] <= 3.0)
    ]
    return {"updated": now_iso(), "source": source, "offers": cleaned}
