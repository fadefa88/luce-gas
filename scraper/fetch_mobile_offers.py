"""Mobile legacy collector disabilitato.

La vecchia versione pubblicava sempre scraper/config/curated_mobile.yaml.
Questo non e' piu' coerente con la regola scelta per il progetto:
meglio dati vuoti che dati di fallback/manuali.

Il mobile deve essere prodotto solo da:
- workflow .github/workflows/mobile-*.yml
- frammenti data/providers/mobile__*.json
- aggregatore lib.aggregate
"""

from __future__ import annotations

from .common import now_iso, report


def collect_mobile_offers(_legacy_providers: list[dict] | None = None) -> dict:
    """Non pubblica piu' offerte mobile curate/manuali.

    Ritorna sempre vuoto. Serve solo a evitare che vecchi entrypoint o vecchi
    workflow possano ripopolare data/offers_mobile.json usando curated_mobile.yaml.
    """
    report(
        "mobile_legacy",
        "disabilitato",
        "dataset mobile curated disabilitato: usare workflow mobile-* + aggregate",
        n=0,
    )
    return {
        "updated": now_iso(),
        "source": "disabled_curated_mobile",
        "offers": [],
    }
