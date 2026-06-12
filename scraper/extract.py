"""Estrazione offerte da HTML: JSON-LD prima, CSS/regex come fallback."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

PRICE_KWH = re.compile(r"(\d+[.,]\d+)\s*(?:€|euro)\s*(?:/|al?\s|per\s)?\s*kWh", re.I)
PRICE_SMC = re.compile(r"(\d+[.,]\d+)\s*(?:€|euro)\s*(?:/|al?\s|per\s)?\s*Smc", re.I)
CENTS_KWH = re.compile(r"(\d+[.,]\d+)\s*(?:c€|cent(?:esimi)?(?:\s*di\s*euro)?)\s*/?\s*kWh", re.I)
CENTS_SMC = re.compile(r"(\d+[.,]\d+)\s*(?:c€|cent(?:esimi)?(?:\s*di\s*euro)?)\s*/?\s*Smc", re.I)
SPREAD_PUN = re.compile(r"PUN\s*\+\s*(\d+[.,]\d+)\s*(?:€|euro)?\s*/?\s*kWh", re.I)
SPREAD_PSV = re.compile(r"PSV\s*\+\s*(\d+[.,]\d+)\s*(?:€|euro)?\s*/?\s*Smc", re.I)
PRICE_MONTH = re.compile(r"(\d+[.,]?\d*)\s*€(?:\s*/?\s*mese|\s*al\s*mese)?", re.I)
GIGA = re.compile(r"(\d+)\s*(?:GB|Giga)", re.I)
FIXED_FEE = re.compile(r"(\d+[.,]\d+)\s*€\s*/?\s*mese", re.I)


def energy_price(text: str, commodity: str) -> tuple[float | None, str | None]:
    """Cerca prezzi diretti, in centesimi o formule indice + spread."""
    direct = PRICE_KWH if commodity == "luce" else PRICE_SMC
    cents = CENTS_KWH if commodity == "luce" else CENTS_SMC
    spread = SPREAD_PUN if commodity == "luce" else SPREAD_PSV
    if m := spread.search(text):
        return float(m.group(1).replace(",", ".")), ("PUN" if commodity == "luce" else "PSV")
    if m := cents.search(text):
        return round(float(m.group(1).replace(",", ".")) / 100, 5), None
    if m := direct.search(text):
        return float(m.group(1).replace(",", ".")), None
    return None, None

GENERIC_SELECTORS = (
    "[class*=card], [class*=offer], [class*=offerta], [class*=tariff], "
    "[class*=plan], [class*=product], article, li"
)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                yield node
                stack.extend(v for v in node.values()
                             if isinstance(v, (dict, list)))


def jsonld_offers(soup: BeautifulSoup) -> list[dict]:
    """Estrae coppie nome/prezzo/testo da nodi schema.org."""
    out = []
    for node in _iter_jsonld(soup):
        t = str(node.get("@type", ""))
        if t not in ("Product", "Service", "Offer", "AggregateOffer"):
            continue
        name = node.get("name") or ""
        desc = node.get("description") or ""
        price = None
        offers = node.get("offers") or node
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            for k in ("price", "lowPrice"):
                if offers.get(k) is not None:
                    try:
                        price = float(str(offers[k]).replace(",", "."))
                    except ValueError:
                        pass
                    break
        if name and price is not None:
            out.append({"name": str(name)[:80], "price": price,
                        "text": f"{name} {desc}"})
    return out


def block_candidates(soup: BeautifulSoup, selector: str | None = None):
    sel = selector or GENERIC_SELECTORS
    seen = set()
    for block in soup.select(sel)[:120]:
        text = " ".join(block.get_text(" ", strip=True).split())
        if not (15 <= len(text) <= 1200):
            continue
        if text in seen:
            continue
        seen.add(text)
        name_el = block.select_one("h1, h2, h3, h4, [class*=title], [class*=name]")
        yield (name_el.get_text(strip=True)[:80] if name_el else None), text


def extract_energy(html: str, provider: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict] = []

    def push(name, text, c, price, indice=None):
        o = {
            "fornitore": provider["nome"],
            "offerta": name or "Offerta",
            "commodity": c,
            "prezzo_energia": price,
            "quota_fissa_mese": _num(FIXED_FEE.search(text).group(1)) if FIXED_FEE.search(text) else 0.0,
            "tipo": "fisso" if re.search(r"\bfiss[oa]\b", text, re.I) else "variabile",
            "fonte": "sito fornitore",
        }
        if indice:
            o["spread"] = price
            o["indice"] = indice
            o["prezzo_energia"] = None
            o["tipo"] = "variabile"
        found.append(o)

    sources = [(o["name"], o["text"]) for o in jsonld_offers(soup)]
    if not sources:
        sources = list(block_candidates(soup, provider.get("selector")))
    for name, text in sources:
        for c in ("luce", "gas"):
            price, indice = energy_price(text, c)
            if price is not None:
                push(name, text, c, price, indice)

    ok, seen = [], set()
    for o in found:
        if o.get("indice"):
            good = 0.0 <= o["spread"] <= 0.5
        else:
            good = (o["commodity"] == "luce" and 0.01 <= o["prezzo_energia"] <= 1.0) or \
                   (o["commodity"] == "gas" and 0.05 <= o["prezzo_energia"] <= 3.0)
        key = (o["offerta"], o["commodity"], o.get("prezzo_energia"), o.get("spread"))
        if good and key not in seen:
            seen.add(key)
            ok.append(o)
    return ok


def extract_mobile(html: str, provider: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict] = []

    def push(name, text, price, giga):
        found.append({
            "operatore": provider["nome"],
            "offerta": name or f"{giga} GB",
            "prezzo_mese": price,
            "giga": giga,
            "prezzo_per_gb": round(price / giga, 3),
            "rete_5g": bool(re.search(r"\b5G\b", text)),
            "fonte": "sito operatore",
        })

    for o in jsonld_offers(soup):
        g = GIGA.search(o["text"])
        if g:
            push(o["name"], o["text"], o["price"], int(g.group(1)))

    if not found:
        for name, text in block_candidates(soup, provider.get("selector")):
            pm, gm = PRICE_MONTH.search(text), GIGA.search(text)
            if pm and gm:
                push(name, text, _num(pm.group(1)), int(gm.group(1)))

    ok, seen = [], set()
    for o in found:
        key = (o["operatore"], o["prezzo_mese"], o["giga"])
        if 1 <= o["prezzo_mese"] <= 60 and 1 <= o["giga"] <= 1000 and key not in seen:
            seen.add(key)
            ok.append(o)
    return ok
