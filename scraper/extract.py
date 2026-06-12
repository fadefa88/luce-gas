"""Estrazione offerte da HTML, JSON-LD, URL e payload JSON catturati."""

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
GENERIC_SELECTORS = "[class*=card], [class*=offer], [class*=offerta], [class*=tariff], [class*=plan], [class*=product], article, li"
PRICE_KEYS = ("price", "prezzo", "amount", "canone", "monthlyprice", "monthly_price", "costo", "importo", "renewalprice")
GB_KEYS = ("gb", "giga", "gigabyte", "data", "dataamount", "data_amount", "internet", "traffico")
NAME_KEYS = ("name", "nome", "title", "titolo", "label", "displayname")
MOBILE_BLOCKLIST = re.compile(r"\b(fibra|casa|fwa|adsl|internet\s+casa|fisso|modem|iliadbox|tv)\b", re.I)


def _num(s: str) -> float:
    return float(str(s).replace(",", "."))


def energy_price(text: str, commodity: str) -> tuple[float | None, str | None]:
    direct = PRICE_KWH if commodity == "luce" else PRICE_SMC
    cents = CENTS_KWH if commodity == "luce" else CENTS_SMC
    spread = SPREAD_PUN if commodity == "luce" else SPREAD_PSV
    if m := spread.search(text):
        return _num(m.group(1)), ("PUN" if commodity == "luce" else "PSV")
    if m := cents.search(text):
        return round(_num(m.group(1)) / 100, 5), None
    if m := direct.search(text):
        return _num(m.group(1)), None
    return None, None


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
    out = []
    for node in _iter_jsonld(soup):
        if str(node.get("@type", "")) not in ("Product", "Service", "Offer", "AggregateOffer"):
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
                        price = _num(offers[key])
                    except Exception:
                        pass
                    break
        if name and price is not None:
            out.append({"name": str(name)[:80], "price": price, "text": f"{name} {desc}"})
    return out


def block_candidates(soup: BeautifulSoup, selector: str | None = None):
    seen = set()
    for block in soup.select(selector or GENERIC_SELECTORS)[:120]:
        text = " ".join(block.get_text(" ", strip=True).split())
        if not (15 <= len(text) <= 1200) or text in seen:
            continue
        seen.add(text)
        name_el = block.select_one("h1, h2, h3, h4, [class*=title], [class*=name]")
        yield (name_el.get_text(strip=True)[:80] if name_el else None), text


def extract_energy(html: str, provider: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found = []

    def push(name, text, commodity, price, indice=None):
        fixed = FIXED_FEE.search(text)
        offer = {
            "fornitore": provider["nome"],
            "offerta": name or "Offerta",
            "commodity": commodity,
            "prezzo_energia": None if indice else price,
            "quota_fissa_mese": _num(fixed.group(1)) if fixed else 0.0,
            "tipo": "variabile" if indice else ("fisso" if re.search(r"\bfiss[oa]\b", text, re.I) else "variabile"),
            "fonte": "sito fornitore",
        }
        if indice:
            offer["spread"] = price
            offer["indice"] = indice
        found.append(offer)

    sources = [(o["name"], o["text"]) for o in jsonld_offers(soup)] or list(block_candidates(soup, provider.get("selector")))
    for name, text in sources:
        for commodity in ("luce", "gas"):
            price, indice = energy_price(text, commodity)
            if price is not None:
                push(name, text, commodity, price, indice)

    ok, seen = [], set()
    for offer in found:
        if offer.get("indice"):
            good = 0 <= offer["spread"] <= 0.5
        else:
            price = offer["prezzo_energia"]
            good = (offer["commodity"] == "luce" and 0.01 <= price <= 1.0) or (offer["commodity"] == "gas" and 0.05 <= price <= 3.0)
        key = (offer["offerta"], offer["commodity"], offer.get("prezzo_energia"), offer.get("spread"))
        if good and key not in seen:
            seen.add(key)
            ok.append(offer)
    return ok


def extract_mobile(html: str, provider: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found = []

    def push(name, text, price, giga):
        found.append({
            "operatore": provider["nome"], "offerta": name or f"{giga} GB",
            "prezzo_mese": price, "giga": giga, "prezzo_per_gb": round(price / giga, 3),
            "rete_5g": bool(re.search(r"\b5G\b", text, re.I)), "fonte": "sito operatore",
        })

    for item in jsonld_offers(soup):
        g = GIGA.search(item["text"])
        if g:
            push(item["name"], item["text"], item["price"], int(g.group(1)))
    if not found:
        for name, text in block_candidates(soup, provider.get("selector")):
            pm, gm = PRICE_MONTH.search(text), GIGA.search(text)
            if pm and gm:
                push(name, text, _num(pm.group(1)), int(gm.group(1)))
    return filter_mobile(found)


def _walk(node):
    stack = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            yield item
            stack.extend(v for v in item.values() if isinstance(v, (dict, list)))
        elif isinstance(item, list):
            stack.extend(x for x in item if isinstance(x, (dict, list)))


def _pick(d: dict, keys) -> object | None:
    low = {str(k).lower().replace("-", "").replace("_", ""): v for k, v in d.items()}
    for key in keys:
        kk = key.replace("_", "")
        if kk in low and low[kk] not in (None, ""):
            return low[kk]
    return None


def _to_float(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.search(r"(\d+[.,]?\d*)", value)
        if m:
            x = _num(m.group(1))
            return x / 100 if x > 100 and x % 1 == 0 and x < 10000 else x
    return None


def _to_giga(value) -> int | None:
    if isinstance(value, (int, float)) and 1 <= value <= 1000:
        return int(value)
    if isinstance(value, str):
        m = GIGA.search(value) or re.search(r"^(\d+)$", value.strip())
        if m:
            g = int(m.group(1))
            return g if 1 <= g <= 1000 else None
    return None


def mine_xhr_mobile(payloads: list, provider: dict) -> list[dict]:
    out = []
    for payload in payloads:
        for node in _walk(payload):
            price = _to_float(_pick(node, PRICE_KEYS))
            giga = _to_giga(_pick(node, GB_KEYS))
            if price is None or giga is None:
                continue
            name = _pick(node, NAME_KEYS)
            text = json.dumps(node, ensure_ascii=False)[:600]
            out.append({
                "operatore": provider["nome"], "offerta": str(name)[:80] if name else f"{giga} GB",
                "prezzo_mese": round(price, 2), "giga": giga,
                "prezzo_per_gb": round(price / giga, 3),
                "rete_5g": bool(re.search(r"\b5G\b", text, re.I)), "fonte": "payload JSON",
            })
    return filter_mobile(out)


def mine_xhr_energy(payloads: list, provider: dict) -> list[dict]:
    out = []
    for payload in payloads:
        for node in _walk(payload):
            text = " ".join(str(v) for v in node.values() if isinstance(v, str))[:800]
            if not text:
                continue
            for commodity in ("luce", "gas"):
                price, indice = energy_price(text, commodity)
                if price is None:
                    continue
                name = _pick(node, NAME_KEYS)
                offer = {
                    "fornitore": provider["nome"], "offerta": str(name)[:80] if name else "Offerta",
                    "commodity": commodity, "prezzo_energia": None if indice else price,
                    "quota_fissa_mese": 0.0,
                    "tipo": "variabile" if indice else ("fisso" if re.search(r"\bfiss", text, re.I) else "variabile"),
                    "fonte": "payload JSON",
                }
                if indice:
                    offer["spread"], offer["indice"] = price, indice
                out.append(offer)
    return out


def mine_links_mobile(html: str, provider: dict) -> list[dict]:
    out, seen = [], set()
    for pattern in provider.get("link_patterns") or []:
        for match in re.finditer(pattern, html, re.I):
            data = match.groupdict()
            try:
                giga = int(data["giga"])
                price = int(data["cents"]) / 100
            except Exception:
                continue
            key = (giga, price)
            if key in seen or not (1 <= giga <= 1000) or not (1 <= price <= 60):
                continue
            seen.add(key)
            out.append({
                "operatore": provider["nome"], "offerta": data.get("name", f"{giga} GB").replace("-", " ").strip().title(),
                "prezzo_mese": price, "giga": giga, "prezzo_per_gb": round(price / giga, 3),
                "rete_5g": True, "fonte": "URL offerta",
            })
    return filter_mobile(out)


def filter_mobile(offers: list[dict]) -> list[dict]:
    ok, seen = [], set()
    for offer in offers:
        text = f"{offer.get('offerta','')}".lower()
        price, giga = offer.get("prezzo_mese") or 0, offer.get("giga") or 0
        if MOBILE_BLOCKLIST.search(text) or not (3.99 <= price <= 60) or not (10 <= giga <= 1000):
            continue
        eur_gb = price / giga
        if not (0.015 <= eur_gb <= 1.0):
            continue
        key = (offer["operatore"], round(price, 2), giga)
        if key in seen:
            continue
        seen.add(key)
        offer["prezzo_per_gb"] = round(eur_gb, 3)
        ok.append(offer)
    return ok


def dedup_energy(offers: list[dict]) -> list[dict]:
    best: dict[tuple, dict] = {}
    for offer in offers:
        key = (offer["fornitore"], offer["commodity"], offer.get("prezzo_energia"), offer.get("spread"))
        cur = best.get(key)
        score = 0 if offer["offerta"].strip().lower() in ("offerta", "") else len(offer["offerta"])
        cur_score = -1 if cur is None else (0 if cur["offerta"].strip().lower() in ("offerta", "") else len(cur["offerta"]))
        if score > cur_score:
            best[key] = offer
    return list(best.values())
