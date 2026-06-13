"""Helper per i prezzi energia: notazioni €/kWh, centesimi, spread PUN/PSV."""
from __future__ import annotations
import re

_DIRECT = {"luce": re.compile(r"(\d+[.,]\d+)\s*(?:€|euro)\s*(?:/|al?\s|per\s)?\s*kWh", re.I),
           "gas":  re.compile(r"(\d+[.,]\d+)\s*(?:€|euro)\s*(?:/|al?\s|per\s)?\s*Smc", re.I)}
_CENTS  = {"luce": re.compile(r"(\d+[.,]\d+)\s*(?:c€|cent(?:esimi)?(?:\s*di\s*euro)?)\s*/?\s*kWh", re.I),
           "gas":  re.compile(r"(\d+[.,]\d+)\s*(?:c€|cent(?:esimi)?(?:\s*di\s*euro)?)\s*/?\s*Smc", re.I)}
_SPREAD = {"luce": re.compile(r"PUN\s*\+\s*(\d+[.,]\d+)", re.I),
           "gas":  re.compile(r"PSV\s*\+\s*(\d+[.,]\d+)", re.I)}


def energy_price(text: str, commodity: str):
    """Ritorna (valore, indice): indice='PUN'/'PSV' se a spread, altrimenti None."""
    if m := _SPREAD[commodity].search(text or ""):
        return float(m.group(1).replace(",", ".")), ("PUN" if commodity == "luce" else "PSV")
    if m := _CENTS[commodity].search(text or ""):
        return round(float(m.group(1).replace(",", ".")) / 100, 5), None
    if m := _DIRECT[commodity].search(text or ""):
        return float(m.group(1).replace(",", ".")), None
    return None, None
