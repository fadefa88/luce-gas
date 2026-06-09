#!/usr/bin/env python3
"""
RadarTariffe importer.

Obiettivo operativo:
- dati reali, minimi, tracciabili;
- niente bypass captcha/login/anti-bot;
- robots.txt rispettato di default;
- ARERA/Portale Offerte usato come fonte strutturata per energia;
- scraping leggero solo per prezzo lancio e condizioni essenziali su pagine pubbliche.

Esempi:
  python scripts/import_sources.py --sources data/sources.example.json --dry-run
  python scripts/import_sources.py --sources data/sources.json --output data/offers.json
  python scripts/import_sources.py --sources data/sources.json --output data/offers.json --no-robots-check
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "offers.json"

EURO_RE = re.compile(r"(\d{1,4})(?:\s*[,.]\s*(\d{2}))?\s*€", re.I)
DATE_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")


@dataclass
class FetchSettings:
    user_agent: str
    timeout: int
    delay: float
    respect_robots: bool
    max_offers_per_run: int
    allow_pdf: bool


class ImporterError(Exception):
    pass


def norm_price(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return float(value)
    text = str(value).strip().replace("\xa0", " ")
    text = text.replace("€", "").replace("/mese", "").replace("al mese", "")
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text:
        return None
    text = text.replace(".", "").replace(",", ".")
    try:
        return round(float(text), 4)
    except ValueError:
        return None


def clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def make_id(*parts: str) -> str:
    raw = "-".join(p for p in parts if p).lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:8]
    return f"{raw[:60]}-{digest}" if raw else digest


def parse_expiry(match: re.Match[str] | None) -> str | None:
    if not match:
        return None
    day = int(match.group(1))
    month = int(match.group(2))
    year_raw = match.group(3)
    year = int(year_raw) if year_raw else date.today().year
    if year < 100:
        year += 2000
    try:
        d = date(year, month, day)
        # Se la data breve è già passata, probabilmente si riferisce all'anno successivo.
        if not year_raw and d < date.today():
            d = date(year + 1, month, day)
        return d.isoformat()
    except ValueError:
        return None


def can_fetch(url: str, ua: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(ua, url)
    except Exception:
        # Fail-open moderato: molti siti bloccano robots.txt ma permettono pagine pubbliche.
        return True


def fetch(session: requests.Session, url: str, settings: FetchSettings) -> str:
    if settings.respect_robots and not can_fetch(url, settings.user_agent):
        raise ImporterError(f"robots.txt non consente fetch: {url}")
    if not settings.allow_pdf and url.lower().split("?")[0].endswith(".pdf"):
        raise ImporterError(f"PDF disabilitati in config: {url}")
    response = session.get(url, timeout=settings.timeout)
    response.raise_for_status()
    ctype = response.headers.get("content-type", "")
    if not settings.allow_pdf and "application/pdf" in ctype.lower():
        raise ImporterError(f"PDF disabilitati in config: {url}")
    return response.text


def regex_first(pattern: str | None, text: str, flags: int = re.I | re.S) -> re.Match[str] | None:
    if not pattern:
        return None
    try:
        return re.search(pattern, text, flags)
    except re.error as exc:
        raise ImporterError(f"Regex non valida: {pattern}: {exc}") from exc


def extract_price(patterns: dict[str, str], text: str) -> float | None:
    m = regex_first(patterns.get("price"), text)
    if not m:
        m = EURO_RE.search(text)
    if not m:
        return None
    if len(m.groups()) >= 2 and m.group(2):
        return norm_price(f"{m.group(1)},{m.group(2)}")
    return norm_price(m.group(0))


def extract_activation(patterns: dict[str, str], text: str) -> float:
    m = regex_first(patterns.get("activation"), text)
    if not m:
        return 0.0
    for group in reversed(m.groups()):
        price = norm_price(group)
        if price is not None:
            return price
    return 0.0


def extract_gb(patterns: dict[str, str], text: str) -> str | None:
    m = regex_first(patterns.get("gb"), text)
    if not m:
        return None
    return f"{m.group(1)} GB" if m.groups() else m.group(0).strip()


def base_offer(provider: str, sector: str, name: str, url: str) -> dict[str, Any]:
    today = date.today().isoformat()
    return {
        "id": make_id(provider, name, sector),
        "provider": provider,
        "name": name,
        "sector": sector,
        "status": "active",
        "baseMonthly": 0,
        "activation": 0,
        "setupLabel": "Da verificare nella pagina ufficiale",
        "expiryDate": None,
        "promoMonths": None,
        "fullPriceAfterPromo": None,
        "allowance": "Dato importato automaticamente da fonte pubblica",
        "speed": "Da verificare",
        "constraintMonths": 0,
        "score": 60,
        "confidence": 58,
        "sourceType": "official",
        "sourceUrl": url,
        "sourceLabel": f"Fonte ufficiale {provider}",
        "lastChecked": today,
        "scrapeHint": "price_launch",
        "tags": [sector, "import automatico"]
    }


def parse_single_offer(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    text = clean_text(html)
    patterns = source.get("patterns", {})
    name = source.get("staticName") or source.get("provider") or "Offerta"
    price = extract_price(patterns, text)
    if price is None:
        return []
    offer = base_offer(source["provider"], source["sector"], name, source["url"])
    offer["baseMonthly"] = price
    offer["activation"] = extract_activation(patterns, text)
    gb = extract_gb(patterns, text)
    if gb:
        offer["allowance"] = f"{gb}; dettagli completi nella fonte ufficiale"
        offer["tags"].append(gb.replace(" ", ""))
    expiry = parse_expiry(regex_first(patterns.get("expiry"), text))
    if expiry:
        offer["expiryDate"] = expiry
        offer["tags"].append("scadenza rilevata")
    offer["confidence"] = 72
    offer["score"] = score_offer(offer)
    return [offer]


def parse_regex_cards(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    text = clean_text(html)
    patterns = source.get("patterns", {})
    blocks_pattern = patterns.get("offerBlocks")
    blocks: list[str]
    if blocks_pattern:
        blocks = [m.group(0) for m in re.finditer(blocks_pattern, text, re.I | re.S)]
    else:
        blocks = [text]

    offers: list[dict[str, Any]] = []
    for idx, block in enumerate(blocks[:20]):
        price = extract_price(patterns, block)
        if price is None:
            continue
        # Nome compatto: prima frase fino a prezzo o prima riga significativa.
        first = re.split(r"\d{1,2}\s*[,\.]\s*\d{2}\s*€", block)[0]
        first = re.sub(r"\s+", " ", first).strip(" -:|•")[:80]
        name = first if len(first) >= 3 else f"Offerta {source['provider']} {idx+1}"
        offer = base_offer(source["provider"], source["sector"], name, source["url"])
        offer["baseMonthly"] = price
        offer["activation"] = extract_activation(patterns, block)
        gb = extract_gb(patterns, block)
        if gb:
            offer["allowance"] = f"{gb}; dettagli completi nella fonte ufficiale"
            offer["tags"].append(gb.replace(" ", ""))
        expiry = parse_expiry(DATE_SLASH_RE.search(block))
        if expiry:
            offer["expiryDate"] = expiry
        offer["confidence"] = 66
        offer["score"] = score_offer(offer)
        offers.append(offer)
    return dedupe_offers(offers)


def parse_energy_unit(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    text = clean_text(html)
    patterns = source.get("patterns", {})
    name = patterns.get("name") or source.get("staticName") or f"{source['provider']} energia"
    m_unit = regex_first(patterns.get("unitPrice"), text)
    if not m_unit:
        return []
    unit = norm_price(m_unit.group(1))
    if unit is None:
        return []
    annual_fixed = 0.0
    m_fixed = regex_first(patterns.get("annualFixed"), text)
    if m_fixed and m_fixed.groups():
        annual_fixed = norm_price(m_fixed.group(1)) or 0.0
    offer = base_offer(source["provider"], source["sector"], name, source["url"])
    offer["baseMonthly"] = round(annual_fixed / 12, 2)
    offer["unitPrice"] = unit
    offer["spread"] = 0
    offer["allowance"] = f"Prezzo materia energia {unit} €/kWh; quota fissa {annual_fixed} €/anno se rilevata"
    offer["speed"] = "Energia: prezzo unitario"
    offer["confidence"] = 72
    offer["score"] = score_offer(offer)
    offer["tags"] = [source["sector"], "unit price", "import automatico"]
    return [offer]


def parse_energy_dual_unit(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    text = clean_text(html)
    patterns = source.get("patterns", {})
    out: list[dict[str, Any]] = []
    annual_fixed = 144.0 if regex_first(patterns.get("annualFixed"), text) else 0.0
    e = regex_first(patterns.get("electricityPrice"), text)
    g = regex_first(patterns.get("gasPrice"), text)
    if e:
        unit = norm_price(e.group(1))
        if unit is not None:
            offer = base_offer(source["provider"], "luce", f"{source['provider']} Fix Web Luce", source["url"])
            offer["baseMonthly"] = round(annual_fixed / 12, 2)
            offer["unitPrice"] = unit
            offer["allowance"] = f"Prezzo luce {unit} €/kWh; quota fissa {annual_fixed} €/anno se rilevata"
            offer["constraintMonths"] = 36
            offer["confidence"] = 70
            offer["score"] = score_offer(offer)
            offer["tags"] = ["luce", "fisso", "web"]
            out.append(offer)
    if g:
        unit = norm_price(g.group(1))
        if unit is not None:
            offer = base_offer(source["provider"], "gas", f"{source['provider']} Fix Web Gas", source["url"])
            offer["baseMonthly"] = round(annual_fixed / 12, 2)
            offer["unitPrice"] = unit
            offer["allowance"] = f"Prezzo gas {unit} €/Smc; quota fissa {annual_fixed} €/anno se rilevata"
            offer["constraintMonths"] = 36
            offer["confidence"] = 70
            offer["score"] = score_offer(offer)
            offer["tags"] = ["gas", "fisso", "web"]
            out.append(offer)
    return out


def score_offer(offer: dict[str, Any]) -> int:
    price = float(offer.get("baseMonthly") or 0)
    sector = offer.get("sector")
    score = 70
    if sector == "mobile":
        if price <= 6: score += 18
        elif price <= 8: score += 12
        elif price <= 10: score += 6
        allowance = str(offer.get("allowance", "")).lower()
        gb_match = re.search(r"(\d{2,4})\s*gb", allowance)
        if gb_match:
            gb = int(gb_match.group(1))
            if gb >= 300: score += 6
            elif gb >= 150: score += 3
    elif sector == "fibra":
        if price <= 23: score += 14
        elif price <= 28: score += 8
        elif price <= 32: score += 3
    elif sector in {"luce", "gas"}:
        unit = float(offer.get("unitPrice") or 0)
        if sector == "luce" and unit and unit <= 0.15: score += 13
        if sector == "gas" and unit and unit <= 0.50: score += 13
    if offer.get("activation", 0) == 0: score += 3
    if not offer.get("expiryDate"): score -= 2
    return max(35, min(98, score))


def dedupe_offers(offers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for offer in offers:
        key = (offer.get("provider", "") + "|" + offer.get("name", "") + "|" + str(offer.get("baseMonthly"))).lower()
        current = best.get(key)
        if current is None or offer.get("confidence", 0) > current.get("confidence", 0):
            best[key] = offer
    return list(best.values())


def flatten_xml_element(elem: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for child in elem.iter():
        tag = child.tag.split("}")[-1].lower()
        text = (child.text or "").strip()
        if text and tag not in out:
            out[tag] = text[:300]
    return out


def pick_field(row: dict[str, str], candidates: list[str]) -> str | None:
    lower = {k.lower(): v for k, v in row.items()}
    for cand in candidates:
        for key, value in lower.items():
            if cand in key and value:
                return value
    return None


def discover_open_data_links(session: requests.Session, settings: FetchSettings, page_url: str) -> list[tuple[str, str]]:
    html = fetch(session, page_url, settings)
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(page_url, a["href"])
        text = a.get_text(" ", strip=True).lower()
        if "offerte" in text and (href.endswith(".xml") or href.endswith(".csv")):
            links.append((text, href))
    return links


def import_arera_open_data(session: requests.Session, settings: FetchSettings, config: dict[str, Any]) -> list[dict[str, Any]]:
    od = config.get("settings", {}).get("energyOpenData", {})
    if not od.get("enabled"):
        return []
    page_url = od.get("openDataPage")
    if not page_url:
        return []
    limit = int(od.get("limitPerSector", 50))
    try:
        links = discover_open_data_links(session, settings, page_url)
    except Exception as exc:
        print(f"[WARN] Open data discovery fallita: {exc}", file=sys.stderr)
        return []

    imported: list[dict[str, Any]] = []
    for label, url in links:
        if "mercato libero" not in label and "offerte" not in label:
            continue
        if not (url.endswith(".xml") or url.endswith(".csv")):
            continue
        sector = "luce" if "_E_" in url or "elettrico" in label else "gas" if "_G_" in url or "gas" in label else "dual"
        try:
            payload = fetch(session, url, settings)
            if url.endswith(".xml"):
                root = ET.fromstring(payload)
                # euristica: un'offerta è un elemento con almeno nome/codice venditore/offerta.
                candidates = []
                for elem in root.iter():
                    data = flatten_xml_element(elem)
                    joined_keys = " ".join(data.keys())
                    if any(k in joined_keys for k in ["nomeofferta", "codiceofferta", "denominazione", "venditore"]):
                        candidates.append(data)
                for row in candidates[:limit]:
                    provider = pick_field(row, ["ragionesociale", "denominazione", "venditore", "nomevenditore"]) or "Venditore energia"
                    name = pick_field(row, ["nomeofferta", "descrizioneofferta", "codiceofferta"]) or "Offerta mercato libero"
                    price_raw = pick_field(row, ["prezzo", "corrispettivo", "pfix", "pvol"])
                    unit_price = norm_price(price_raw)
                    offer = base_offer(provider, sector, name, url)
                    offer["sourceLabel"] = "Portale Offerte ARERA/Acquirente Unico - Open Data"
                    offer["sourceType"] = "official_open_data"
                    offer["confidence"] = 64
                    offer["allowance"] = "Offerta importata da open data; condizioni complete da dettagliare con parser specifico schema ARERA"
                    if unit_price is not None:
                        offer["unitPrice"] = unit_price
                    offer["score"] = score_offer(offer)
                    offer["tags"] = [sector, "ARERA", "open data"]
                    imported.append(offer)
            elif url.endswith(".csv"):
                reader = csv.DictReader(payload.splitlines(), delimiter=";")
                for row in list(reader)[:limit]:
                    provider = pick_field(row, ["ragionesociale", "denominazione", "venditore"]) or "Venditore energia"
                    name = pick_field(row, ["nomeofferta", "codiceofferta", "offerta"]) or "Offerta PLACET"
                    offer = base_offer(provider, sector, name, url)
                    offer["sourceLabel"] = "Portale Offerte ARERA/Acquirente Unico - Open Data"
                    offer["sourceType"] = "official_open_data"
                    offer["confidence"] = 62
                    offer["tags"] = [sector, "PLACET", "ARERA"]
                    imported.append(offer)
        except Exception as exc:
            print(f"[WARN] Import open data fallito per {url}: {exc}", file=sys.stderr)
        time.sleep(settings.delay)
    return imported


def load_existing(output: Path) -> dict[str, Any]:
    if output.exists():
        try:
            return json.loads(output.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"generatedAt": date.today().isoformat(), "currency": "EUR", "offers": []}


def merge(existing: dict[str, Any], imported: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {offer["id"]: offer for offer in existing.get("offers", [])}
    for offer in imported:
        by_id[offer["id"]] = {**by_id.get(offer["id"], {}), **offer}
    merged = list(by_id.values())
    merged.sort(key=lambda o: (str(o.get("sector", "")), str(o.get("provider", "")), float(o.get("baseMonthly") or 0)))
    return {
        "generatedAt": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "currency": existing.get("currency", "EUR"),
        "disclaimer": "Dataset aggiornato automaticamente da fonti pubbliche. Verificare sempre la pagina ufficiale prima della sottoscrizione.",
        "offers": merged,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default=str(ROOT / "data" / "sources.json"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-robots-check", action="store_true")
    args = parser.parse_args()

    sources_path = Path(args.sources)
    if not sources_path.exists():
        raise SystemExit(f"Config fonti non trovata: {sources_path}. Copia data/sources.example.json in data/sources.json")
    config = json.loads(sources_path.read_text(encoding="utf-8"))
    settings_raw = config.get("settings", {})
    settings = FetchSettings(
        user_agent=settings_raw.get("userAgent", "RadarTariffeBot/0.2"),
        timeout=int(settings_raw.get("timeoutSeconds", 25)),
        delay=float(settings_raw.get("delaySeconds", 2)),
        respect_robots=bool(settings_raw.get("respectRobotsTxt", True)) and not args.no_robots_check,
        max_offers_per_run=int(settings_raw.get("maxOffersPerRun", 250)),
        allow_pdf=bool(settings_raw.get("allowPdf", False)),
    )

    session = requests.Session()
    session.headers.update({"User-Agent": settings.user_agent, "Accept-Language": "it-IT,it;q=0.9,en;q=0.7"})

    imported: list[dict[str, Any]] = []
    imported.extend(import_arera_open_data(session, settings, config))

    strategies = {
        "single_offer": parse_single_offer,
        "regex_cards": parse_regex_cards,
        "energy_unit": parse_energy_unit,
        "energy_dual_unit": parse_energy_dual_unit,
    }

    for source in config.get("sources", []):
        if not source.get("enabled"):
            continue
        try:
            html = fetch(session, source["url"], settings)
            strategy_name = source.get("strategy", "single_offer")
            parser_fn = strategies.get(strategy_name)
            if not parser_fn:
                print(f"[WARN] Strategia non supportata: {strategy_name}", file=sys.stderr)
                continue
            new = parser_fn(source, html)
            print(f"[OK] {source['id']}: {len(new)} offerte")
            imported.extend(new)
        except Exception as exc:
            print(f"[WARN] {source.get('id', source.get('url'))}: {exc}", file=sys.stderr)
        time.sleep(settings.delay)
        if len(imported) >= settings.max_offers_per_run:
            imported = imported[: settings.max_offers_per_run]
            break

    imported = dedupe_offers(imported)
    existing = load_existing(Path(args.output))
    result = merge(existing, imported)

    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2)[:12000])
        print(f"\n[DRY RUN] offerte importate/merge: {len(result['offers'])}")
        return 0

    out = Path(args.output)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[DONE] scritto {out} con {len(result['offers'])} offerte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
