"""Estrazione offerte da HTML: JSON-LD prima, CSS/regex come fallback."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

PRICE_KWH = re.compile(r"(\d+[.,]\d+)\s*€\s*(?:/|al?\s)?\s*kWh", re.I)
PRICE_SMC = re.compile(r"(\d+[.,]\d+)\s*€\s*(?:/|al?\s)?\s*Smc", re.I)
PRICE_MONTH = re.compile(r"(\d+[.,]?\d*)\s*€(?:\s*/?\s*mese|\s*al\s*mese)?", re.I)
GIGA = re.compile(r"(\d+)\s*(?:GB|Giga)", re.I)
FIXED_FEE = re.compile(r"(\d+[.,]\d+)\s*€\s*/?\s*mese", re.I)
GENERIC_SELECTORS = "[class*=card], [class*=offer], [class*=offerta], [class*=tariff], [class*=plan], [class*=product], article, li"


def _num(value: str) -> float:
    return float(value.replace(",", "."))


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
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))


def jsonld_offers(soup: BeautifulSoup) -> list[dict]:
    out: list[dict] = []
    for node in _iter_jsonld(soup):
        node_type = str(node.get("@type", ""))
        if node_type not in ("Product", "Service", "Offer", "AggregateOffer"):
            continue
        name = node.get("name") or ""
        desc = node.get("description") or ""
        price = None
        offers = node.get("offers") or node
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            for key in ("price", "lowPrice"):
                if offers.get(key) is not None:
                    try:
                        price = float(str(offers[key]).replace(",", "."))
                    except ValueError:
                        pass
                    break
        if name and price is not None:
            out.append({"name": str(name)[:100], "price": price, "text": f"{name} {desc}"})
    return out


def block_candidates(soup: BeautifulSoup, selector: str | None = None):
    seen: set[str] = set()
    for block in soup.select(selector or GENERIC_SELECTORS)[:140]:
        text = " ".join(block.get_text(" ", strip=True).split())
        if not (15 <= len(text) <= 1400) or text in seen:
            continue
        seen.add(text)
        name_el = block.select_one("h1, h2, h3, h4, [class*=title], [class*=name]")
        yield (name_el.get_text(strip=True)[:100] if name_el else None), text


def extract_energy(html: str, provider: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict] = []

    def push(name: str | None, text: str, commodity: str, price: float) -> None:
        fixed = FIXED_FEE.search(text)
        found.append({
            "fornitore": provider["nome"],
            "offerta": name or "Offerta",
            "commodity": commodity,
            "prezzo_energia": price,
            "quota_fissa_mese": _num(fixed.group(1)) if fixed else 0.0,
            "tipo": "fisso" if re.search(r"\bfiss[oa]\b|bloccato", text, re.I) else "variabile",
            "fonte": "sito fornitore",
        })

    for offer in jsonld_offers(soup):
        text = offer["text"]
        mk = PRICE_KWH.search(text)
        ms = PRICE_SMC.search(text)
        if mk:
            push(offer["name"], text, "luce", _num(mk.group(1)))
        if ms:
            push(offer["name"], text, "gas", _num(ms.group(1)))

    if not found:
        for name, text in block_candidates(soup, provider.get("selector")):
            mk = PRICE_KWH.search(text)
            ms = PRICE_SMC.search(text)
            if mk:
                push(name, text, "luce", _num(mk.group(1)))
            if ms:
                push(name, text, "gas", _num(ms.group(1)))

    out: list[dict] = []
    seen: set[tuple] = set()
    for offer in found:
        price = offer["prezzo_energia"]
        good = (offer["commodity"] == "luce" and 0.01 <= price <= 1.0) or (offer["commodity"] == "gas" and 0.05 <= price <= 3.0)
        key = (offer["offerta"], offer["commodity"], price)
        if good and key not in seen:
            seen.add(key)
            out.append(offer)
    return out


def extract_mobile(html: str, provider: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict] = []

    def push(name: str | None, text: str, price: float, giga: int) -> None:
        found.append({
            "operatore": provider["nome"],
            "offerta": name or f"{giga} GB",
            "prezzo_mese": price,
            "giga": giga,
            "prezzo_per_gb": round(price / giga, 3),
            "rete_5g": bool(re.search(r"\b5G\b", text, re.I)),
            "fonte": "sito operatore",
        })

    for offer in jsonld_offers(soup):
        g = GIGA.search(offer["text"])
        if g:
            push(offer["name"], offer["text"], offer["price"], int(g.group(1)))

    if not found:
        for name, text in block_candidates(soup, provider.get("selector")):
            pm = PRICE_MONTH.search(text)
            gm = GIGA.search(text)
            if pm and gm:
                push(name, text, _num(pm.group(1)), int(gm.group(1)))

    out: list[dict] = []
    seen: set[tuple] = set()
    for offer in found:
        key = (offer["operatore"], offer["prezzo_mese"], offer["giga"])
        if 1 <= offer["prezzo_mese"] <= 60 and 1 <= offer["giga"] <= 1000 and key not in seen:
            seen.add(key)
            out.append(offer)
    return out
