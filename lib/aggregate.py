"""lib/aggregate.py — unisce i frammenti per-fornitore nei file del sito.

Legge tutti i data/providers/<categoria>__<id>.json prodotti dalle singole
Action e compone:
  - data/offers_mobile.json   (tutte le offerte mobile)
  - data/offers_energy.json   (luce + gas)
  - data/scrape_report.json   (stato per fornitore: ok/vuoto/errore + quando)
  - aggiorna gli storici giornalieri in data/history/

Eseguito dall'Action di aggregazione, che parte dopo gli scraper (o a mano).
Idempotente: si può lanciare quante volte si vuole.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FRAGMENTS = ROOT / "data" / "providers"
DATA = ROOT / "data"
HIST = DATA / "history"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_fragments() -> list[dict]:
    out = []
    if FRAGMENTS.exists():
        for f in sorted(FRAGMENTS.glob("*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception as exc:  # noqa: BLE001
                print(f"  frammento illeggibile {f.name}: {exc}")
    return out


def _save(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def _append_history(path: Path, record: dict) -> None:
    hist = []
    if path.exists():
        try:
            hist = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            hist = []
    merged = {r.get("date"): r for r in hist}
    cur = merged.get(record["date"], {})
    cur.update(record)
    merged[record["date"]] = cur
    _save(path, sorted(merged.values(), key=lambda r: r.get("date", ""))[-3650:])



def _load_curated_mobile() -> tuple[list[dict], dict]:
    """Carica le offerte mobile verificate a mano.

    Serve come fallback editoriale: i frammenti per-provider sono diagnostici,
    ma non devono svuotare il sito quando gli scraper reali non estraggono.
    """
    path = ROOT / "scraper" / "config" / "curated_mobile.yaml"
    if not path.exists():
        return [], {}
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    verified = str(cfg.get("verificato", ""))
    offers: list[dict] = []
    summary: dict[str, int] = {}
    for op in cfg.get("operatori", []) or []:
        op_offers = op.get("offerte") or []
        summary[f"mobile_curated/{op.get('id')}"] = len(op_offers)
        for item in op_offers:
            unlimited = bool(item.get("illimitati"))
            giga = None if unlimited else int(item["giga"])
            price = float(item["prezzo_mese"])
            offers.append({
                "operatore": op.get("nome", ""),
                "offerta": item.get("nome", ""),
                "url": op.get("url", ""),
                "prezzo_mese": price,
                "giga": giga,
                "giga_illimitati": unlimited,
                "prezzo_per_gb": None if unlimited else round(price / giga, 3),
                "attivazione": float(item.get("attivazione", 0) or 0),
                "minuti": str(item.get("minuti", "")),
                "sms": str(item.get("sms", "")),
                "rete_5g": True,
                "commodity": "",
                "prezzo_energia": None,
                "quota_fissa_mese": None,
                "tipo": "",
                "indice": "",
                "spread": None,
                "note": item.get("note", ""),
                "fonte": f"verificata manualmente il {verified}",
            })
    return offers, summary

def _agg(vals: list[float]) -> dict:
    vals = [v for v in vals if v is not None]
    if not vals:
        return {}
    return {"min": round(min(vals), 4),
            "media": round(statistics.mean(vals), 4), "n": len(vals)}


def main() -> None:
    frags = _load_fragments()
    report = {"updated": _now(), "sources": {}}
    mobile, energy = [], []

    for fr in frags:
        cat, pid = fr.get("categoria"), fr.get("provider_id")
        report["sources"][f"{cat}/{pid}"] = {
            "operatore": fr.get("operatore"), "status": fr.get("status"),
            "detail": fr.get("detail", ""), "n": len(fr.get("offers", [])),
            "updated": fr.get("updated"),
        }
        for o in fr.get("offers", []):
            if cat == "mobile":
                mobile.append(o)
            elif cat in ("luce", "gas"):
                energy.append(o)

    curated_mobile, curated_summary = _load_curated_mobile()
    if curated_mobile and not mobile:
        mobile = curated_mobile
        report["mobile_publication_source"] = "curated_mobile.yaml"
        report["mobile_curated_offers"] = len(curated_mobile)
        for sid, n in curated_summary.items():
            report["sources"][sid] = {
                "operatore": sid.split("/", 1)[1],
                "status": "curated",
                "detail": "pubblicata da scraper/config/curated_mobile.yaml",
                "n": n,
                "updated": _now(),
            }

    _save(DATA / "offers_mobile.json", {"updated": _now(), "offers": mobile})
    _save(DATA / "offers_energy.json", {"updated": _now(), "offers": energy})
    _save(DATA / "scrape_report.json", report)

    # storici giornalieri (per i grafici)
    if mobile:
        prezzi = [o["prezzo_mese"] for o in mobile if o.get("prezzo_mese")]
        per_gb = [o["prezzo_per_gb"] for o in mobile if o.get("prezzo_per_gb")]
        _append_history(HIST / "mobile_history.json", {
            "date": _today(), "prezzo_mese": _agg(prezzi),
            "prezzo_per_gb": _agg(per_gb)})
    if energy:
        rec = {"date": _today()}
        for c in ("luce", "gas"):
            pr = [o["prezzo_energia"] for o in energy
                  if o.get("commodity") == c and o.get("prezzo_energia")]
            if pr:
                rec[c] = _agg(pr)
        if len(rec) > 1:
            _append_history(HIST / "energy_history.json", rec)

    ok = sum(1 for s in report["sources"].values() if s["status"] == "ok")
    print(f"Aggregati {len(frags)} frammenti | mobile {len(mobile)} offerte, "
          f"energy {len(energy)} | fonti ok: {ok}/{len(frags)}")


if __name__ == "__main__":
    main()
