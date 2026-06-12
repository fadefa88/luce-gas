"""Offerte TELEFONIA MOBILE — v4 "curated-first".

Filosofia: la fonte primaria è il dataset VERIFICATO A MANO
(config/curated_mobile.yaml): è quello che il sito pubblica, sempre.
Lo scraping (HTML + JSON-LD + API interne + URL) resta attivo ma fa da
SENTINELLA: se rileva per un operatore un prezzo diverso da quello curato
per lo stesso taglio di giga, lo segnala nel report come "possibile
variazione", così aggiorni il YAML con un commit. Niente più falsi
positivi pubblicati, niente più card vuote.

Si pubblicano SOLO offerte 5G (scelta editoriale del progetto).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .common import (LAST_XHR, dump_debug, fetch_page, now_iso, report)
from .extract import (extract_mobile, filter_mobile, mine_links_mobile,
                      mine_xhr_mobile)

CURATED = Path(__file__).parent / "config" / "curated_mobile.yaml"


def _load_curated() -> tuple[str, list[dict]]:
    cfg = yaml.safe_load(CURATED.read_text(encoding="utf-8"))
    return str(cfg.get("verificato", "")), cfg.get("operatori", [])


def _published_offer(op: dict, o: dict, verified: str) -> dict:
    giga = o.get("giga")
    illim = bool(o.get("illimitati"))
    price = float(o["prezzo_mese"])
    return {
        "operatore": op["nome"],
        "offerta": o["nome"],
        "prezzo_mese": price,
        "giga": None if illim else int(giga),
        "giga_illimitati": illim,
        "prezzo_per_gb": None if illim else round(price / int(giga), 3),
        "attivazione": float(o.get("attivazione", 0) or 0),
        "minuti": str(o.get("minuti", "")),
        "sms": str(o.get("sms", "")),
        "rete_5g": True,
        "note": o.get("note", ""),
        "fonte": f"verificata manualmente il {verified}",
        "url": op["url"],
    }


def _scrape_sentinel(op: dict) -> list[dict]:
    """Scraping multi-canale, solo a scopo di confronto (sentinella)."""
    p = {"id": op["id"], "nome": op["nome"],
         "link_patterns": op.get("link_patterns")}
    html, used = fetch_page([op["url"]], render="always")
    if not html:
        return []
    got = extract_mobile(html, p)
    got += mine_xhr_mobile(list(LAST_XHR), p)
    if op.get("link_patterns"):
        got += mine_links_mobile(html, p)
    got = [o for o in filter_mobile(got) if o.get("rete_5g")]
    if not got:
        dump_debug(op["id"], html)
    return got


def collect_mobile_offers(_legacy_providers: list[dict] | None = None) -> dict:
    verified, operators = _load_curated()
    published: list[dict] = []

    for op in operators:
        curated = op.get("offerte") or []
        for o in curated:
            published.append(_published_offer(op, o, verified))

        # ---- sentinella -------------------------------------------------
        try:
            scraped = _scrape_sentinel(op)
        except Exception as exc:  # noqa: BLE001
            scraped = []
            print(f"  [sentinella] {op['nome']}: {exc}")

        by_giga = {o.get("giga"): o for o in curated if o.get("giga")}
        drifts, novel = [], []
        for s in scraped:
            c = by_giga.get(s.get("giga"))
            if c and abs(float(c["prezzo_mese"]) - s["prezzo_mese"]) > 0.011:
                drifts.append(f"{s['giga']}GB: sito {s['prezzo_mese']}€ vs curato {c['prezzo_mese']}€")
            elif not c and s.get("giga"):
                novel.append(f"{s['giga']}GB a {s['prezzo_mese']}€?")

        if curated and drifts:
            report(op["id"], "da_verificare", "; ".join(drifts)[:200], n=len(curated))
            print(f"- {op['nome']}: PREZZI FORSE CAMBIATI -> {drifts}")
        elif curated:
            extra = f" | nuove? {novel[:3]}" if novel else ""
            report(op["id"], "ok", f"{len(curated)} offerte curate{extra}"[:200], n=len(curated))
            print(f"- {op['nome']}: {len(curated)} offerte (curate)")
        elif scraped:
            report(op["id"], "solo_rilevate",
                   f"non curate; rilevate: {novel[:4]}"[:200], n=0)
            print(f"- {op['nome']}: nessun dato curato; rilevate {len(scraped)} (non pubblicate)")
        else:
            report(op["id"], "vuota", "né curate né rilevate", n=0)
            print(f"- {op['nome']}: nessun dato")

    return {"updated": now_iso(), "verificato": verified, "offers": published}
