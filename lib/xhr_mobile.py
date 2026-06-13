"""lib/xhr_mobile.py — estrae offerte mobile dai payload JSON delle API interne
catturati da fetch_rendered() (utile per le SPA: 1Mobile, Lyca, ecc.).
Prende tutte le offerte; il flag rete_5g distingue ma non filtra."""
from __future__ import annotations
import json, re
from lib.base import Offer

PRICE_KEYS = ("price","prezzo","amount","canone","monthlyprice","monthly_price","costo","importo")
GB_KEYS = ("gb","giga","gigabyte","data","dataamount","data_amount")
NAME_KEYS = ("name","nome","title","titolo","label","displayname")


def _walk(node):
    stack=[node]
    while stack:
        n=stack.pop()
        if isinstance(n,dict):
            yield n; stack.extend(v for v in n.values() if isinstance(v,(dict,list)))
        elif isinstance(n,list):
            stack.extend(x for x in n if isinstance(x,(dict,list)))


def _pick(d,keys):
    low={str(k).lower().replace("-","").replace("_",""):v for k,v in d.items()}
    for k in keys:
        kk=k.replace("_","")
        if kk in low and low[kk] not in (None,""): return low[kk]
    return None


def _f(v):
    if isinstance(v,(int,float)): return float(v)
    if isinstance(v,str):
        m=re.search(r"(\d+[.,]?\d*)",v)
        if m: return float(m.group(1).replace(",","."))
    return None


def _g(v):
    if isinstance(v,(int,float)) and 1<=v<=2000: return int(v)
    if isinstance(v,str):
        m=re.search(r"(\d{1,4})",v)
        if m:
            g=int(m.group(1))
            return g if 1<=g<=2000 else None
    return None


def mine_xhr_mobile(payloads: list, operator: str, url: str) -> list[Offer]:
    out, seen = [], set()
    for payload in payloads or []:
        for node in _walk(payload):
            price=_f(_pick(node,PRICE_KEYS)); giga=_g(_pick(node,GB_KEYS))
            if price is None or giga is None: continue
            if not (1<=price<=80) or not (1<=giga<=2000): continue
            name=_pick(node,NAME_KEYS)
            blob=json.dumps(node,ensure_ascii=False)
            key=(round(price,2),giga)
            if key in seen: continue
            seen.add(key)
            out.append(Offer(
                operatore=operator, offerta=(str(name)[:80] if name else f"{giga} GB"),
                url=url, prezzo_mese=round(price,2), giga=giga,
                minuti="illimitati" if re.search(r"illimitat",blob,re.I) else "",
                sms=(re.search(r"(\d{2,4})\s*SMS",blob,re.I).group(1) if re.search(r"(\d{2,4})\s*SMS",blob,re.I) else ""),
                rete_5g=bool(re.search(r"\b5G\b",blob)),
                fonte="API interna",
            ))
    return out
