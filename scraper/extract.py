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


# ======================================================================
# CANALE 3 — XHR mining: cerca offerte dentro i payload JSON che la SPA
# scarica dalle proprie API interne (catturati da common.fetch_rendered).
# ======================================================================
PRICE_KEYS = ("price", "prezzo", "amount", "canone", "monthlyprice",
              "monthly_price", "costo", "importo", "renewalprice")
GB_KEYS = ("gb", "giga", "gigabyte", "data", "dataamount", "data_amount",
           "internet", "traffico")
NAME_KEYS = ("name", "nome", "title", "titolo", "label", "displayname")


def _walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            yield n
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(x for x in n if isinstance(x, (dict, list)))


def _pick(d: dict, keys) -> object | None:
    low = {str(k).lower().replace("-", "").replace("_", ""): v for k, v in d.items()}
    for k in keys:
        kk = k.replace("_", "")
        if kk in low and low[kk] not in (None, ""):
            return low[kk]
    return None


def _to_float(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"(\d+[.,]?\d*)", v)
        if m:
            x = float(m.group(1).replace(",", "."))
            return x / 100 if x > 100 and x % 1 == 0 and x < 10000 else x  # centesimi interi
    return None


def _to_giga(v) -> int | None:
    if isinstance(v, (int, float)) and 1 <= v <= 1000:
        return int(v)
    if isinstance(v, str):
        m = GIGA.search(v) or re.search(r"^(\d+)$", v.strip())
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
                "operatore": provider["nome"],
                "offerta": (str(name)[:80] if name else f"{giga} GB"),
                "prezzo_mese": round(price, 2),
                "giga": giga,
                "prezzo_per_gb": round(price / giga, 3) if giga else None,
                "rete_5g": bool(re.search(r"\b5G\b", text, re.I)),
                "fonte": "API interna del sito",
            })
    return out


def mine_xhr_energy(payloads: list, provider: dict) -> list[dict]:
    out = []
    for payload in payloads:
        for node in _walk(payload):
            strings = " ".join(str(v) for v in node.values()
                               if isinstance(v, str))[:800]
            if not strings:
                continue
            for c in ("luce", "gas"):
                price, indice = energy_price(strings, c)
                if price is None:
                    continue
                name = _pick(node, NAME_KEYS)
                o = {
                    "fornitore": provider["nome"],
                    "offerta": (str(name)[:80] if name else "Offerta"),
                    "commodity": c,
                    "prezzo_energia": None if indice else price,
                    "quota_fissa_mese": 0.0,
                    "tipo": "variabile" if indice else
                            ("fisso" if re.search(r"\bfiss", strings, re.I) else "variabile"),
                    "fonte": "API interna del sito",
                }
                if indice:
                    o["spread"], o["indice"] = price, indice
                out.append(o)
    return out


# ======================================================================
# CANALE 4 — link mining: alcuni siti (es. Iliad) mettono nome, GB e
# prezzo direttamente nell'URL dell'offerta: offerta-iliad-top250plus-999
# ======================================================================
def mine_links_mobile(html: str, provider: dict) -> list[dict]:
    patterns = provider.get("link_patterns") or []
    out, seen = [], set()
    for pat in patterns:
        for m in re.finditer(pat, html, re.I):
            d = m.groupdict()
            try:
                giga = int(d["giga"])
                price = int(d["cents"]) / 100
            except (KeyError, ValueError):
                continue
            key = (giga, price)
            if key in seen or not (1 <= giga <= 1000) or not (1 <= price <= 60):
                continue
            seen.add(key)
            out.append({
                "operatore": provider["nome"],
                "offerta": d.get("name", f"{giga} GB").replace("-", " ").strip().title(),
                "prezzo_mese": price,
                "giga": giga,
                "prezzo_per_gb": round(price / giga, 3),
                "rete_5g": True,
                "fonte": "URL offerta",
            })
    return out


# ======================================================================
# Filtro qualità mobile: elimina i falsi positivi (banner fibra/casa,
# bundle dati assurdi) qualunque sia il canale di provenienza.
# ======================================================================
MOBILE_BLOCKLIST = re.compile(
    r"\b(fibra|casa|fwa|adsl|internet\s+casa|fisso|modem|iliadbox|tv)\b", re.I)


def filter_mobile(offers: list[dict]) -> list[dict]:
    ok, seen = [], set()
    for o in offers:
        text = f"{o.get('offerta','')}".lower()
        if MOBILE_BLOCKLIST.search(text):
            continue
        p, g = o.get("prezzo_mese") or 0, o.get("giga") or 0
        if not (3.99 <= p <= 60) or not (10 <= g <= 1000):
            continue
        eur_gb = p / g
        if not (0.015 <= eur_gb <= 1.0):  # 2€/500GB o 6€/1GB = spazzatura
            continue
        key = (o["operatore"], round(p, 2), g)
        if key in seen:
            continue
        seen.add(key)
        o["prezzo_per_gb"] = round(eur_gb, 3)
        ok.append(o)
    return ok


def dedup_energy(offers: list[dict]) -> list[dict]:
    """Stesso fornitore+commodity+prezzo = stessa offerta vista più volte
    nella pagina: si tiene il nome più informativo."""
    best: dict[tuple, dict] = {}
    for o in offers:
        key = (o["fornitore"], o["commodity"],
               o.get("prezzo_energia"), o.get("spread"))
        cur = best.get(key)
        score = 0 if o["offerta"].strip().lower() in ("offerta", "") else len(o["offerta"])
        cur_score = -1 if cur is None else (
            0 if cur["offerta"].strip().lower() in ("offerta", "") else len(cur["offerta"]))
        if score > cur_score:
            best[key] = o
    return list(best.values())
