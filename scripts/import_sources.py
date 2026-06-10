#!/usr/bin/env python3
"""
Tariff Radar importer.

Obiettivo: raccogliere offerte italiane luce, gas e fibra in modo non aggressivo.
- Luce/Gas: fonte primaria Open Data Portale Offerte ARERA/Acquirente Unico.
- Fibra: pagine pubbliche ufficiali/trasparenza tariffaria degli operatori.

Non bypassa login, CAPTCHA, paywall o blocchi tecnici. Rispetta robots.txt di default.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover
    pdfplumber = None

TODAY = date.today().isoformat()
DEFAULT_UA = "TariffRadarBot/0.3 (+https://example.com/contatti; ricerca offerte pubbliche; no aggressive scraping)"
OPEN_DATA_PAGE = "https://www.ilportaleofferte.it/portaleOfferte/it/open-data.page"
OPEN_DATA_HOST = "www.ilportaleofferte.it"

PRICE_RE = re.compile(r"(?<!\d)(\d{1,4}(?:[\.,]\d{1,4})?)\s*(?:€|euro|eur)(?:\s*/\s*(?:mese|mes|m|anno|kwh|smc))?", re.I)
MONTHLY_RE = re.compile(r"(\d{1,3}(?:[\.,]\d{1,2})?)\s*(?:€|euro|eur)\s*(?:/|al|ogni)?\s*(?:mese|mes|m)\b", re.I)
EUR_KWH_RE = re.compile(r"(\d+(?:[\.,]\d{3,6})?)\s*(?:€|euro|eur)\s*/?\s*kwh", re.I)
EUR_SMC_RE = re.compile(r"(\d+(?:[\.,]\d{3,6})?)\s*(?:€|euro|eur)\s*/?\s*smc", re.I)
DATE_RE = re.compile(r"(?:fino\s+al|entro\s+il|scade\s+il|valida\s+fino\s+al|promozione\s+fino\s+al)?\s*(\d{1,2})[\-/\.](\d{1,2})[\-/\.](20\d{2})", re.I)
SPEED_RE = re.compile(r"(?:fino\s+a\s*)?(\d+(?:[\.,]\d+)?)\s*(Gbps|Gbit/s|Gb/s|Mega|Mbps|Mbit/s)", re.I)
HIDDEN_WORDS = [
    "attivazione", "disattivazione", "modem", "router", "vincolo", "recesso", "rata", "rate",
    "installazione", "spedizione", "sim", "domiciliazione", "bolletta", "sconto", "promo", "dopo", "dal 13"
]

ENERGY_FIELD_ALIASES = {
    "provider": ["ragionesociale", "denominazionevenditore", "venditore", "fornitore", "nomevenditore", "seller"],
    "name": ["nomeofferta", "denominazioneofferta", "offerta", "nomecommerciale", "descrizioneofferta"],
    "code": ["codiceofferta", "codice", "idofferta", "codofferta"],
    "start_date": ["datainizio", "iniziovalidita", "datainiziovalidita", "validitad"],
    "end_date": ["datafine", "finevalidita", "datascadenza", "datafinevalidita", "validitaa"],
    "tariff_type": ["tipoprezzo", "tipoofferta", "tipologiaofferta", "prezzofissoovariabile", "tipologia"],
    "index_name": ["indice", "nomeindice", "indicizzazione", "parametroindicizzazione"],
    "unit_price": ["prezzoenergia", "prezzomateriaenergia", "prezzomateriaprima", "prezzo", "prezzocomponenteenergia", "prezzogas", "prezzomateriagas"],
    "spread": ["spread", "delta", "corrispettivovariabile", "corrispettivoenergia", "corrispettivogas"],
    "fixed_fee_month": ["quotafissamese", "corrispettivofissomese", "costofissomensile", "pcvmese", "pfixmese"],
    "fixed_fee_year": ["quotafissaanno", "corrispettivofissoanno", "costofissoannuo", "pcv", "commercializzazione", "pfix"],
}

@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    text: str | None
    content: bytes

class RespectfulClient:
    def __init__(self, user_agent: str, delay: float = 2.0, timeout: int = 35, respect_robots: bool = True):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml,text/xml,text/csv,application/pdf,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
        })
        self.delay = delay
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.last_hit: dict[str, float] = {}
        self.robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.user_agent = user_agent

    def can_fetch(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urllib.parse.urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(urllib.parse.urljoin(base, "/robots.txt"))
            try:
                rp.read()
            except Exception:
                # Se robots non è leggibile, non blocco: mantengo delay e richieste minime.
                pass
            self.robots[base] = rp
        return self.robots[base].can_fetch(self.user_agent, url)

    def wait_host(self, url: str) -> None:
        host = urllib.parse.urlparse(url).netloc
        elapsed = time.time() - self.last_hit.get(host, 0)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_hit[host] = time.time()

    def fetch(self, url: str) -> FetchResult | None:
        if not self.can_fetch(url):
            print(f"[robots] skip {url}", file=sys.stderr)
            return None
        self.wait_host(url)
        try:
            headers = {}
            if urllib.parse.urlparse(url).netloc == OPEN_DATA_HOST:
                headers["Referer"] = OPEN_DATA_PAGE
            r = self.session.get(url, timeout=self.timeout, allow_redirects=True, headers=headers)
            ctype = r.headers.get("content-type", "")
            text = None
            if any(x in ctype.lower() for x in ["text", "html", "xml", "csv", "json"]):
                r.encoding = r.encoding or "utf-8"
                text = r.text
            return FetchResult(r.url, r.status_code, ctype, text, r.content)
        except Exception as exc:
            print(f"[fetch-error] {url}: {exc}", file=sys.stderr)
            return None


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value[:80] or "item"


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = re.sub(r"[^0-9,\.\-]", "", s)
    if s.count(",") == 1 and s.count(".") >= 1:
        # formato 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif s.count(",") == 1:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def iso_date_from_match(m: re.Match[str]) -> str:
    dd, mm, yyyy = m.groups()
    return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"


def sha_id(*parts: str) -> str:
    raw = "|".join(p or "" for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def flatten_xml_element(el: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for child in el.iter():
        tag = child.tag.split("}")[-1].lower()
        text = clean_text("".join(child.itertext()))
        if text and len(text) < 300:
            if tag in out and out[tag] != text:
                out[tag] = out[tag] + " | " + text
            else:
                out[tag] = text
        for k, v in child.attrib.items():
            out[f"{tag}_{k.lower()}"] = str(v)
    return out


def first_by_alias(flat: dict[str, str], alias_group: str) -> str | None:
    aliases = ENERGY_FIELD_ALIASES[alias_group]
    normalized = {re.sub(r"[^a-z0-9]", "", k.lower()): v for k, v in flat.items()}
    for alias in aliases:
        key = re.sub(r"[^a-z0-9]", "", alias.lower())
        if key in normalized and normalized[key]:
            return normalized[key]
    for key, value in normalized.items():
        if any(alias in key for alias in aliases) and value:
            return value
    return None


def discover_arera_links(client: RespectfulClient, page_url: str = OPEN_DATA_PAGE) -> dict[str, str]:
    """Discover current Open Data download URLs from the official Portale Offerte page.

    The page itself is an Open Data catalogue. Some robots.txt configurations block generic
    crawlers from the catalogue URL even though the page exposes public CSV/XML downloads.
    The caller can pass a dedicated client with respect_robots=False only for this official
    Open Data catalogue/resources, while keeping robots enabled for ordinary provider sites.
    """
    result = client.fetch(page_url)
    if not result or not result.text:
        return {}
    soup = BeautifulSoup(result.text, "html.parser")
    links: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(page_url, a["href"])
        low = href.lower()
        label = clean_text(a.get_text(" ")).lower()
        key = None
        if "prezzi" in label and ".csv" in low:
            key = "commodity_history"
        elif "po_offerte_e_mlibero" in low:
            key = "energy_electricity_xml"
        elif "po_parametri_mercato_libero_e" in low:
            key = "energy_electricity_params"
        elif "po_offerte_g_mlibero" in low:
            key = "energy_gas_xml"
        elif "po_parametri_mercato_libero_g" in low:
            key = "energy_gas_params"
        elif "po_offerte_d_mlibero" in low:
            key = "energy_dual_xml"
        elif "offerte_e_placet" in low:
            key = "placet_electricity_csv"
        elif "offerte_g_placet" in low:
            key = "placet_gas_csv"
        if key:
            links[key] = href
    return links


def arera_fallback_links(days_back: int = 14) -> dict[str, list[str]]:
    """Build conservative fallback URLs for the current Open Data month.

    The Portale Offerte filenames include YYYY_M and YYYYMMDD. If discovery fails because
    the catalogue HTML changes, try only the last few calendar days instead of crawling.
    """
    out: dict[str, list[str]] = defaultdict(list)
    base = "https://www.ilportaleofferte.it/portaleOfferte/resources/opendata/csv"
    for i in range(max(1, days_back)):
        d = date.today() - timedelta(days=i)
        ym = f"{d.year}_{d.month}"
        ymd = d.strftime("%Y%m%d")
        out["energy_electricity_xml"].append(f"{base}/offerteML/{ym}/PO_Offerte_E_MLIBERO_{ymd}.xml")
        out["energy_gas_xml"].append(f"{base}/offerteML/{ym}/PO_Offerte_G_MLIBERO_{ymd}.xml")
        out["energy_dual_xml"].append(f"{base}/offerteML/{ym}/PO_Offerte_D_MLIBERO_{ymd}.xml")
        out["energy_electricity_params"].append(f"{base}/parametriML/{ym}/PO_Parametri_Mercato_Libero_E_{ymd}.csv")
        out["energy_gas_params"].append(f"{base}/parametriML/{ym}/PO_Parametri_Mercato_Libero_G_{ymd}.csv")
    return out


def as_candidates(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [v for v in value if v]
    return [value]


def merge_link_candidates(discovered: dict[str, str], overrides: dict[str, Any], fallback_days: int) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {k: [v] for k, v in discovered.items() if v}
    for key, value in (overrides or {}).items():
        vals = as_candidates(value)
        if vals:
            merged[key] = vals + [v for v in merged.get(key, []) if v not in vals]
    fallback = arera_fallback_links(fallback_days)
    for key, vals in fallback.items():
        existing = merged.get(key, [])
        merged[key] = existing + [v for v in vals if v not in existing]
    return merged


def candidate_offer_elements(root: ET.Element) -> list[ET.Element]:
    candidates = []
    for el in root.iter():
        tag = el.tag.split("}")[-1].lower()
        children = list(el)
        if not children:
            continue
        if "offerta" in tag or "offer" in tag:
            text_len = len(clean_text(" ".join(el.itertext())))
            if text_len > 20:
                candidates.append(el)
    if candidates:
        return candidates
    # fallback: elementi figli del root con molti sotto-nodi
    return [el for el in list(root) if len(list(el)) >= 3]


def normalize_energy_offer(flat: dict[str, str], sector: str, source_url: str) -> dict[str, Any] | None:
    provider = first_by_alias(flat, "provider") or "Venditore non identificato"
    name = first_by_alias(flat, "name") or "Offerta energia"
    code = first_by_alias(flat, "code") or sha_id(provider, name, source_url)
    start_date = normalize_date(first_by_alias(flat, "start_date"))
    end_date = normalize_date(first_by_alias(flat, "end_date"))
    tariff_type = first_by_alias(flat, "tariff_type") or "non classificata"
    index_name = first_by_alias(flat, "index_name")
    unit_price = parse_number(first_by_alias(flat, "unit_price"))
    spread = parse_number(first_by_alias(flat, "spread"))
    fixed_month = parse_number(first_by_alias(flat, "fixed_fee_month"))
    fixed_year = parse_number(first_by_alias(flat, "fixed_fee_year"))

    # Eur/MWh -> Eur/kWh heuristic: numbers > 5 are likely €/MWh.
    if sector == "luce" and unit_price and unit_price > 5:
        unit_price = unit_price / 1000
    if sector == "gas" and unit_price and unit_price > 10:
        # Gas sometimes appears in €/MWh PCS; don't force if unclear, mark low confidence.
        pass

    hidden = detect_hidden_costs(" ".join(flat.values()))
    confidence = 58
    confidence += 10 if provider != "Venditore non identificato" else 0
    confidence += 10 if unit_price is not None or spread is not None else 0
    confidence += 8 if end_date else 0
    confidence += 8 if fixed_month is not None or fixed_year is not None else 0
    confidence = min(confidence, 92)

    return {
        "id": f"{sector}-{slugify(provider)}-{slugify(code)}",
        "provider": provider,
        "name": name,
        "sector": sector,
        "status": "active",
        "baseMonthly": fixed_month if fixed_month is not None else ((fixed_year or 0) / 12 if fixed_year else 0),
        "activation": 0,
        "setupLabel": "verificare scheda condizioni economiche",
        "expiryDate": end_date,
        "validFrom": start_date,
        "tariffType": tariff_type,
        "indexName": index_name,
        "unitPrice": unit_price,
        "unitPriceEurPerKwh": unit_price if sector == "luce" else None,
        "unitPriceEurPerSmc": unit_price if sector == "gas" else None,
        "spread": spread,
        "fixedFeeMonth": fixed_month,
        "fixedFeeYear": fixed_year,
        "hiddenCosts": hidden,
        "hiddenCostFlags": [x["type"] for x in hidden],
        "allowance": unit_label(sector, unit_price, spread, fixed_month, fixed_year, index_name),
        "constraintMonths": 0,
        "score": score_energy(unit_price, spread, fixed_month, fixed_year, hidden),
        "confidence": confidence,
        "sourceType": "ARERA Open Data",
        "sourceUrl": source_url,
        "sourceLabel": "Portale Offerte ARERA/Acquirente Unico - Open Data",
        "lastChecked": TODAY,
        "rawCode": code,
        "rawFieldSample": dict(list(flat.items())[:32]),
        "tags": [sector, "open-data", tariff_type.lower()[:24]] + ([index_name] if index_name else []),
    }


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"]:
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except Exception:
            pass
    m = DATE_RE.search(s)
    if m:
        return iso_date_from_match(m)
    return None


def unit_label(sector: str, unit: float | None, spread: float | None, fixed_month: float | None, fixed_year: float | None, index: str | None) -> str:
    parts = []
    if unit is not None:
        parts.append(f"materia prima {unit:.5f} €/{'kWh' if sector == 'luce' else 'Smc'}")
    if spread is not None:
        parts.append(f"spread {spread:.5f}")
    if index:
        parts.append(f"indice {index}")
    if fixed_month is not None:
        parts.append(f"quota fissa {fixed_month:.2f} €/mese")
    elif fixed_year is not None:
        parts.append(f"quota fissa {fixed_year:.2f} €/anno")
    return " · ".join(parts) or "Condizioni economiche nei dati fonte"


def score_energy(unit: float | None, spread: float | None, fixed_month: float | None, fixed_year: float | None, hidden: list[dict[str, Any]]) -> int:
    score = 70
    if unit is not None:
        score += max(-18, min(16, int((0.18 - unit) * 120)))
    if spread is not None:
        score += max(-14, min(10, int((0.03 - spread) * 180)))
    fixed = fixed_month if fixed_month is not None else ((fixed_year or 0) / 12 if fixed_year else 0)
    score -= int(min(18, fixed * 1.2))
    score -= min(12, len(hidden) * 2)
    return max(15, min(96, score))


def parse_arera_xml(client: RespectfulClient, url: str, sector: str, limit: int | None = None) -> list[dict[str, Any]]:
    res = client.fetch(url)
    if not res or res.status_code >= 400:
        print(f"[arera] failed {url}: {res.status_code if res else 'no response'}", file=sys.stderr)
        return []
    try:
        root = ET.fromstring(res.content)
    except Exception as exc:
        print(f"[arera-xml] parse error {url}: {exc}", file=sys.stderr)
        return []
    offers = []
    for el in candidate_offer_elements(root):
        flat = flatten_xml_element(el)
        item = normalize_energy_offer(flat, sector, url)
        if item:
            offers.append(item)
        if limit and len(offers) >= limit:
            break
    return dedupe_offers(offers)


def parse_arera_xml_candidates(client: RespectfulClient, urls: list[str], sector: str, limit: int | None = None) -> list[dict[str, Any]]:
    last_status = "not-tried"
    for url in urls:
        offers = parse_arera_xml(client, url, sector, limit)
        if offers:
            print(f"[arera] {sector}: imported {len(offers)} from {url}")
            return offers
        last_status = url
    print(f"[arera] {sector}: no offers from {len(urls)} candidate URL(s); last={last_status}", file=sys.stderr)
    return []


def parse_commodity_history_candidates(client: RespectfulClient, urls: list[str]) -> list[dict[str, Any]]:
    for url in urls:
        points = parse_commodity_history_csv(client, url)
        if points:
            print(f"[arera] commodity history: imported {len(points)} points from {url}")
            return points
    return []


def parse_commodity_history_csv(client: RespectfulClient, url: str) -> list[dict[str, Any]]:
    res = client.fetch(url)
    if not res or not res.content:
        return []
    text = decode_bytes(res.content)
    rows = read_csv_rows(text)
    points = []
    for row in rows:
        keys = {normalize_key(k): v for k, v in row.items()}
        d = normalize_date(first_existing(keys, ["data", "mese", "periodo", "dataprezzo", "giorno"]))
        if not d:
            continue
        pun = parse_number(first_existing(keys, ["pun", "puneurMwh", "puneuromwh", "prezzoenergia", "electricity"] ))
        psv = parse_number(first_existing(keys, ["psv", "psveurSmc", "psveuromc", "prezzogas", "gas"] ))
        if pun is None and psv is None:
            # heuristic scan
            for k, v in keys.items():
                if "pun" in k:
                    pun = parse_number(v)
                if "psv" in k:
                    psv = parse_number(v)
        points.append({"date": d, "punEurMwh": pun, "psvEurSmc": psv, "sourceUrl": url})
    return sorted(points, key=lambda x: x["date"])


def decode_bytes(content: bytes) -> str:
    for enc in ["utf-8-sig", "utf-8", "cp1252", "latin1"]:
        try:
            return content.decode(enc)
        except Exception:
            pass
    return content.decode("utf-8", errors="replace")


def read_csv_rows(text: str) -> list[dict[str, str]]:
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
    except Exception:
        dialect = csv.excel
        dialect.delimiter = ";"
    reader = csv.DictReader(StringIO(text), dialect=dialect)
    return [dict(row) for row in reader]


def normalize_key(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (k or "").lower())


def first_existing(keys: dict[str, str], aliases: list[str]) -> str | None:
    norm = {normalize_key(k): v for k, v in keys.items()}
    for alias in aliases:
        a = normalize_key(alias)
        if a in norm and norm[a]:
            return norm[a]
    return None


def detect_hidden_costs(text: str) -> list[dict[str, Any]]:
    t = clean_text(text).lower()
    results = []
    for word in HIDDEN_WORDS:
        idx = t.find(word)
        if idx >= 0:
            window = t[max(0, idx - 80): idx + 160]
            prices = [parse_number(m.group(1)) for m in PRICE_RE.finditer(window)]
            results.append({
                "type": word,
                "amount": next((p for p in prices if p is not None), None),
                "evidence": window[:220]
            })
    # dedupe by type
    out = []
    seen = set()
    for item in results:
        if item["type"] not in seen:
            seen.add(item["type"])
            out.append(item)
    return out[:12]


def extract_pdf_text(content: bytes) -> str:
    if not pdfplumber:
        return ""
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages[:8])
    except Exception:
        return ""


def extract_html_text_and_links(url: str, html: str) -> tuple[str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    links = []
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(url, a["href"])
        if any(x in href.lower() for x in ["pdf", "traspar", "prospetto", "sintesi", "offert", "fibra", "casa"]):
            links.append(href)
    return clean_text(soup.get_text(" ")), list(dict.fromkeys(links))[:40]


def parse_fiber_from_text(provider: str, url: str, text: str, source_type: str = "official") -> list[dict[str, Any]]:
    text = clean_text(text)
    if not text:
        return []
    chunks = split_offer_chunks(text)
    offers = []
    for idx, chunk in enumerate(chunks):
        monthly = first_monthly_price(chunk)
        if monthly is None:
            continue
        speed = first_speed(chunk)
        expiry = first_expiry(chunk)
        activation = price_near_keyword(chunk, ["attivazione", "installazione", "contributo"])
        modem = price_near_keyword(chunk, ["modem", "router"])
        hidden = detect_hidden_costs(chunk)
        name = guess_offer_name(provider, chunk, idx)
        confidence = 45 + (15 if speed else 0) + (10 if activation is not None else 0) + (10 if expiry else 0)
        offers.append({
            "id": f"fibra-{slugify(provider)}-{sha_id(url, name, str(monthly), str(idx))}",
            "provider": provider,
            "name": name,
            "sector": "fibra",
            "status": "active",
            "baseMonthly": monthly,
            "activation": activation or 0,
            "modemCostMonthly": modem if modem and modem < 20 else None,
            "setupLabel": build_setup_label(activation, modem, hidden),
            "expiryDate": expiry,
            "allowance": speed or "Fibra/casa: dettaglio nella fonte ufficiale",
            "speed": speed,
            "constraintMonths": guess_constraint_months(chunk),
            "unitPrice": None,
            "fixedFeeMonth": monthly,
            "hiddenCosts": hidden,
            "hiddenCostFlags": [x["type"] for x in hidden],
            "score": score_fiber(monthly, activation, modem, hidden),
            "confidence": min(confidence, 88),
            "sourceType": source_type,
            "sourceUrl": url,
            "sourceLabel": "pagina ufficiale / trasparenza tariffaria",
            "lastChecked": TODAY,
            "tags": ["fibra", "trasparenza", "scraping-leggero"] + ([speed] if speed else []),
        })
    return dedupe_offers(offers)


def split_offer_chunks(text: str) -> list[str]:
    # Prima prova con finestre attorno ai prezzi mensili, evitando di creare 200 duplicati.
    chunks = []
    for m in MONTHLY_RE.finditer(text):
        start = max(0, m.start() - 360)
        end = min(len(text), m.end() + 520)
        chunks.append(text[start:end])
    if not chunks and PRICE_RE.search(text):
        chunks = [text[:2500]]
    # dedupe simile
    unique = []
    seen = set()
    for c in chunks:
        sig = hashlib.sha1(c[:220].encode("utf-8", errors="ignore")).hexdigest()[:10]
        if sig not in seen:
            seen.add(sig)
            unique.append(c)
    return unique[:24]


def first_monthly_price(text: str) -> float | None:
    prices = [parse_number(m.group(1)) for m in MONTHLY_RE.finditer(text)]
    prices = [p for p in prices if p is not None and 5 <= p <= 120]
    return prices[0] if prices else None


def first_speed(text: str) -> str | None:
    m = SPEED_RE.search(text)
    return clean_text(m.group(0)) if m else None


def first_expiry(text: str) -> str | None:
    for m in DATE_RE.finditer(text):
        return iso_date_from_match(m)
    return None


def price_near_keyword(text: str, keywords: list[str]) -> float | None:
    low = text.lower()
    for kw in keywords:
        idx = low.find(kw)
        if idx >= 0:
            window = low[idx: idx + 220]
            prices = [parse_number(m.group(1)) for m in PRICE_RE.finditer(window)]
            prices = [p for p in prices if p is not None]
            if prices:
                return prices[0]
    return None


def guess_constraint_months(text: str) -> int:
    low = text.lower()
    for m in re.finditer(r"(\d{1,2})\s*mesi", low):
        n = int(m.group(1))
        if any(w in low[max(0, m.start()-80):m.end()+80] for w in ["vincolo", "durata", "rata", "rate", "modem", "promo"]):
            return n
    return 0


def guess_offer_name(provider: str, chunk: str, idx: int) -> str:
    # Cerca una frase vicino a fibra/casa prima del prezzo.
    names = re.findall(r"([A-ZÀ-Ü][A-Za-zÀ-ÿ0-9\s\-\.]{2,45}(?:Fibra|Casa|WiFi|Internet|Ultra|Super|Start|Premium)[A-Za-zÀ-ÿ0-9\s\-\.]*)", chunk)
    if names:
        name = clean_text(names[0])[:70]
        if provider.lower() not in name.lower():
            return name
    return f"Offerta fibra rilevata #{idx+1}"


def build_setup_label(activation: float | None, modem: float | None, hidden: list[dict[str, Any]]) -> str:
    parts = []
    if activation is not None:
        parts.append(f"attivazione {activation:.2f}€")
    if modem is not None:
        parts.append(f"modem/router {modem:.2f}€")
    for flag in ["disattivazione", "recesso", "vincolo"]:
        if any(h["type"] == flag for h in hidden):
            parts.append(flag)
    return " · ".join(parts) or "nessun costo nascosto estratto"


def score_fiber(monthly: float, activation: float | None, modem: float | None, hidden: list[dict[str, Any]]) -> int:
    score = 88 - int(max(0, monthly - 20) * 1.6)
    if activation:
        score -= min(12, int(activation / 10))
    if modem:
        score -= 6
    score -= min(16, len(hidden) * 2)
    return max(20, min(96, score))


def scrape_fiber_sources(client: RespectfulClient, sources: list[dict[str, Any]], follow_pdfs: bool = True) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    offers: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for src in sources:
        if not src.get("enabled", True):
            continue
        provider = src.get("provider") or src.get("name") or "Operatore"
        for url in src.get("urls", []):
            res = client.fetch(url)
            if not res:
                audit.append({"provider": provider, "url": url, "status": "no-response"})
                continue
            if res.status_code >= 400:
                audit.append({"provider": provider, "url": url, "status": f"http-{res.status_code}"})
                continue
            found = []
            if "pdf" in res.content_type.lower() or url.lower().endswith(".pdf"):
                text = extract_pdf_text(res.content)
                found = parse_fiber_from_text(provider, res.url, text, "official-pdf")
            elif res.text:
                text, links = extract_html_text_and_links(res.url, res.text)
                found = parse_fiber_from_text(provider, res.url, text, "official-html")
                if follow_pdfs:
                    for pdf_url in [l for l in links if l.lower().split("?")[0].endswith(".pdf")][: int(src.get("maxPdfFollow", 4))]:
                        pdf = client.fetch(pdf_url)
                        if pdf and pdf.status_code < 400:
                            pdf_text = extract_pdf_text(pdf.content)
                            found.extend(parse_fiber_from_text(provider, pdf.url, pdf_text, "official-pdf"))
            offers.extend(found)
            audit.append({"provider": provider, "url": res.url, "status": "ok", "offers_found": len(found)})
    return dedupe_offers(offers), audit


def dedupe_offers(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {}
    for o in offers:
        key = (o.get("sector"), slugify(o.get("provider", "")), slugify(o.get("name", "")), round(float(o.get("baseMonthly") or 0), 2), o.get("expiryDate"))
        if key not in seen or float(o.get("confidence") or 0) > float(seen[key].get("confidence") or 0):
            seen[key] = o
    return list(seen.values())


def enrich_costs(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for o in offers:
        sector = o.get("sector")
        unit = o.get("unitPrice")
        spread = o.get("spread")
        fixed_month = o.get("fixedFeeMonth", o.get("baseMonthly", 0)) or 0
        fixed_year = o.get("fixedFeeYear")
        if fixed_year and not fixed_month:
            fixed_month = fixed_year / 12
        hidden_amount = 0.0
        for h in o.get("hiddenCosts", []) or []:
            amount = h.get("amount")
            if isinstance(amount, (int, float)) and math.isfinite(amount):
                hidden_amount += amount
        o["costBreakdown"] = {
            "commodityUnit": unit,
            "spreadUnit": spread,
            "fixedMonthly": fixed_month,
            "activationOnce": o.get("activation", 0) or 0,
            "hiddenDetectedOnce": round(hidden_amount, 2),
            "normalized1000kwh": normalized_energy_cost(o, 1000, "luce") if sector == "luce" else None,
            "normalized500smc": normalized_energy_cost(o, 500, "gas") if sector == "gas" else None,
            "firstYearFiber": round((o.get("baseMonthly", 0) or 0) * 12 + (o.get("activation", 0) or 0) + hidden_amount, 2) if sector == "fibra" else None,
        }
    return offers


def normalized_energy_cost(o: dict[str, Any], qty: float, expected_sector: str) -> float | None:
    if o.get("sector") != expected_sector:
        return None
    unit = o.get("unitPrice") or 0
    spread = o.get("spread") or 0
    fixed = o.get("fixedFeeMonth") or o.get("baseMonthly") or 0
    return round(qty * (unit + spread) + 12 * fixed, 2)


def build_market_correlation(offers: list[dict[str, Any]], commodity: list[dict[str, Any]], snapshots_path: Path | None = None) -> list[dict[str, Any]]:
    # Se esiste storico snapshot, aggrega su quello; altrimenti usa ultimo dataset.
    rows = []
    if snapshots_path and snapshots_path.exists():
        try:
            snapshots = json.loads(snapshots_path.read_text(encoding="utf-8"))
            rows = snapshots.get("snapshots", []) if isinstance(snapshots, dict) else snapshots
        except Exception:
            rows = []
    if not rows:
        rows = [{"date": TODAY, "offers": offers}]
    by_month = defaultdict(list)
    for snap in rows:
        m = str(snap.get("date", TODAY))[:7]
        by_month[m].extend(snap.get("offers", []))
    commodity_by_month = {str(p.get("date", ""))[:7]: p for p in commodity}
    out = []
    for month, arr in sorted(by_month.items()):
        luce = [o for o in arr if o.get("sector") == "luce"]
        gas = [o for o in arr if o.get("sector") == "gas"]
        c = commodity_by_month.get(month, {})
        out.append({
            "month": month,
            "punEurMwh": c.get("punEurMwh"),
            "psvEurSmc": c.get("psvEurSmc"),
            "electricityOfferCount": len(luce),
            "gasOfferCount": len(gas),
            "avgElectricityCommodityEurKwh": avg([o.get("unitPrice") for o in luce]),
            "avgGasCommodityEurSmc": avg([o.get("unitPrice") for o in gas]),
            "avgElectricityFixedMonth": avg([o.get("fixedFeeMonth") or o.get("baseMonthly") for o in luce]),
            "avgGasFixedMonth": avg([o.get("fixedFeeMonth") or o.get("baseMonthly") for o in gas]),
        })
    return out


def avg(values: Iterable[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    return round(sum(nums) / len(nums), 6) if nums else None


def append_snapshot(path: Path, offers: list[dict[str, Any]]) -> None:
    slim = [{
        "id": o.get("id"), "provider": o.get("provider"), "name": o.get("name"), "sector": o.get("sector"),
        "baseMonthly": o.get("baseMonthly"), "unitPrice": o.get("unitPrice"), "spread": o.get("spread"),
        "fixedFeeMonth": o.get("fixedFeeMonth"), "hiddenCostFlags": o.get("hiddenCostFlags", [])
    } for o in offers]
    data = {"snapshots": []}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            data["snapshots"] = loaded.get("snapshots", loaded if isinstance(loaded, list) else [])
        except Exception:
            pass
    data["snapshots"] = [s for s in data["snapshots"] if s.get("date") != TODAY]
    data["snapshots"].append({"date": TODAY, "offers": slim})
    data["snapshots"] = sorted(data["snapshots"], key=lambda s: s.get("date", ""))[-730:]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_offers(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], sectors_replace: set[str]) -> list[dict[str, Any]]:
    kept = [o for o in existing if o.get("sector") not in sectors_replace]
    return dedupe_offers(kept + incoming)


def main() -> int:
    ap = argparse.ArgumentParser(description="Importa offerte luce/gas/fibra da fonti ufficiali e pagine trasparenza tariffaria.")
    ap.add_argument("--sources", default="data/sources.example.json")
    ap.add_argument("--output", default="data/offers.json")
    ap.add_argument("--commodity-output", default="data/commodity-index.json")
    ap.add_argument("--correlation-output", default="data/market-correlation.json")
    ap.add_argument("--snapshot-output", default="data/offer-snapshots.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-energy", action="store_true")
    ap.add_argument("--skip-fiber", action="store_true")
    ap.add_argument("--no-robots", action="store_true", help="Disabilita robots.txt. Usare solo per test interni se autorizzati.")
    ap.add_argument("--limit-energy", type=int, default=None, help="Limite offerte energia per test.")
    ap.add_argument("--delay", type=float, default=None)
    args = ap.parse_args()

    source_path = Path(args.sources)
    cfg = load_json(source_path) if source_path.exists() else {}
    settings = cfg.get("settings", {})
    ua = os.environ.get("TARIFF_RADAR_UA") or settings.get("userAgent") or DEFAULT_UA
    delay = args.delay if args.delay is not None else float(settings.get("delaySeconds", 2.0))
    client = RespectfulClient(ua, delay=delay, respect_robots=not args.no_robots and bool(settings.get("respectRobots", True)))

    # Keep robots enabled for ordinary provider websites. For Portale Offerte Open Data,
    # use a dedicated client that may bypass robots only for the official public Open Data
    # catalogue/downloads. This avoids the previous failure: robots skipped the catalogue
    # page and therefore discovered zero XML/CSV files.
    arera_cfg = cfg.get("areraOpenData", {})
    open_data_respect_robots = bool(arera_cfg.get("respectRobots", False)) and not args.no_robots
    arera_client = RespectfulClient(ua, delay=delay, respect_robots=open_data_respect_robots)
    if not open_data_respect_robots:
        print("[arera] official Open Data mode: robots bypass enabled only for Portale Offerte catalogue/resources")

    existing_data = load_json(Path(args.output)) if Path(args.output).exists() else {"offers": []}
    existing_offers = existing_data.get("offers", existing_data if isinstance(existing_data, list) else [])
    imported: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    commodity: list[dict[str, Any]] = []

    if not args.skip_energy:
        discovered = discover_arera_links(arera_client, arera_cfg.get("page", OPEN_DATA_PAGE))
        fallback_days = int(arera_cfg.get("fallbackDays", 14))
        links = merge_link_candidates(discovered, arera_cfg.get("overrides", {}), fallback_days)
        print(f"[arera] discovered: {sorted(discovered)}")
        print(f"[arera] candidate sets: { {k: len(v) for k, v in links.items()} }")
        if links.get("commodity_history"):
            commodity = parse_commodity_history_candidates(arera_client, links["commodity_history"])
        if links.get("energy_electricity_xml"):
            imported.extend(parse_arera_xml_candidates(arera_client, links["energy_electricity_xml"], "luce", args.limit_energy))
        if links.get("energy_gas_xml"):
            imported.extend(parse_arera_xml_candidates(arera_client, links["energy_gas_xml"], "gas", args.limit_energy))
        if links.get("energy_dual_xml"):
            # Dual fuel viene importato come dual, ma senza separare unit economics se non chiaro.
            imported.extend(parse_arera_xml_candidates(arera_client, links["energy_dual_xml"], "dual", args.limit_energy))

    if not args.skip_fiber:
        fiber_sources = cfg.get("fiberSources", [])
        fiber_offers, fiber_audit = scrape_fiber_sources(client, fiber_sources, follow_pdfs=bool(settings.get("followPdfs", True)))
        imported.extend(fiber_offers)
        audit.extend(fiber_audit)

    imported = enrich_costs(dedupe_offers(imported))
    replace = set()
    if not args.skip_energy:
        replace.update(["luce", "gas", "dual"])
    if not args.skip_fiber:
        replace.add("fibra")
    merged = enrich_costs(merge_offers(existing_offers, imported, replace))

    out = {
        "generatedAt": TODAY,
        "currency": "EUR",
        "disclaimer": "Offerte importate da fonti pubbliche ufficiali/open data. Verificare sempre la fonte prima di sottoscrivere.",
        "count": len(merged),
        "offers": merged,
        "audit": audit,
    }
    corr = build_market_correlation(merged, commodity, Path(args.snapshot_output))

    print(f"[result] imported={len(imported)} merged={len(merged)} commodity_points={len(commodity)} audit={len(audit)}")
    if args.dry_run:
        print(json.dumps({"sample": imported[:3], "audit": audit[:8], "commoditySample": commodity[:3]}, ensure_ascii=False, indent=2))
        return 0

    write_json(Path(args.output), out)
    if commodity:
        write_json(Path(args.commodity_output), {"generatedAt": TODAY, "source": "Portale Offerte Open Data - prezzi storici", "series": commodity})
    write_json(Path(args.correlation_output), {"generatedAt": TODAY, "series": corr})
    append_snapshot(Path(args.snapshot_output), merged)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
