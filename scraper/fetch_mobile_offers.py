"""Offerte TELEFONIA MOBILE.

Non esiste un portale ufficiale equivalente al Portale Offerte ARERA per il
mobile, quindi si legge la sola pagina principale pubblica di ogni operatore
(config/providers.yaml), estraendo nome offerta, prezzo mensile e GB inclusi.
Niente navigazione in profondità, niente parametri personali.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .common import fetch, now_iso


def collect_mobile_offers(providers: list[dict]) -> dict:
    offers: list[dict] = []
    for p in providers:
        print(f"- {p['nome']} ({p['url']})")
        html = fetch(p["url"])
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        price_re = re.compile(p.get("price_regex", r"(\d+[.,]?\d*)\s*€"))
        gb_re = re.compile(p.get("gb_regex", r"(\d+)\s*(?:GB|Giga)"), re.I)
        seen: set[str] = set()
        for block in soup.select(p.get("selector", "[class*=card]"))[:30]:
            text = " ".join(block.get_text(" ", strip=True).split())
            pm, gm = price_re.search(text), gb_re.search(text)
            if not (pm and gm):
                continue
            price = float(pm.group(1).replace(",", "."))
            giga = int(gm.group(1))
            if not (1 <= price <= 60) or not (1 <= giga <= 1000):
                continue  # plausibilità
            name_el = block.select_one(p.get("name_selector", "h2, h3"))
            name = (name_el.get_text(strip=True) if name_el else f"{giga} GB")[:80]
            key = f"{p['id']}|{price}|{giga}"
            if key in seen:
                continue
            seen.add(key)
            offers.append(
                {
                    "operatore": p["nome"],
                    "offerta": name,
                    "prezzo_mese": price,
                    "giga": giga,
                    "prezzo_per_gb": round(price / giga, 3),
                    "rete_5g": bool(re.search(r"\b5G\b", text)),
                    "fonte": "pagina offerte operatore",
                    "url": p["url"],
                }
            )
    return {"updated": now_iso(), "offers": offers}
