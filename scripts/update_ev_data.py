from __future__ import annotations
import csv, io, json, re
from datetime import datetime, timezone
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/'data'
OUT=DATA/'vehicle_cost_inputs.json'
CFG=DATA/'ev_config.json'
ENERGY=DATA/'offers_energy.json'
COMM=DATA/'history'/'commodity_history.json'

def now(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def load(p,f):
    try: return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return f

def fnum(x):
    m=re.search(r'(\d{1,3})(?:[,.](\d{1,3}))?',str(x or ''))
    return float(m.group(1)+'.'+(m.group(2) or '0')) if m else None

def fuel(seed):
    old=seed.get('fuel',{})
    # endpoint pubblico MIMIT/MiSE; fallback se non raggiungibile
    url='https://'+'www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv'
    try:
        txt=requests.get(url,headers={'User-Agent':'TariffaRadarEV/1.0'},timeout=25).text
        dialect=csv.Sniffer().sniff(txt[:2048],delimiters=';,\t')
        rows=csv.DictReader(io.StringIO(txt),dialect=dialect)
        b=[]; d=[]
        for r in rows:
            low=' '.join(str(v).lower() for v in r.values())
            p=None
            for k,v in r.items():
                if 'prezzo' in k.lower(): p=fnum(v)
            if not p or 'servito' in low or 'special' in low or 'premium' in low: continue
            if 'benzina' in low: b.append(p)
            if 'gasolio' in low or 'diesel' in low: d.append(p)
        if b and d:
            return {'source':'MIMIT open data carburanti','url':url,'benzina_eur_l':round(sum(b)/len(b),3),'diesel_eur_l':round(sum(d)/len(d),3),'status':'ok'}
    except Exception as exc:
        print('fuel fallback',exc)
    return {'source':old.get('source','fallback'),'benzina_eur_l':old.get('benzina_eur_l',1.85),'diesel_eur_l':old.get('diesel_eur_l',1.75),'status':'fallback'}

def home(seed):
    vals=[]
    for o in load(ENERGY,{}).get('offers',[]):
        if o.get('commodity')=='luce' and o.get('prezzo_energia'):
            vals.append(float(o['prezzo_energia'])+0.14)
    if vals: return {'status':'estimated_from_offers','estimated_all_in_eur_kwh':round(sum(vals)/len(vals),3),'note':'Media offerte luce + proxy costi regolati.'}
    pun=None
    for r in reversed(load(COMM,[])):
        if r.get('pun_eur_kwh'):
            pun=float(r['pun_eur_kwh']); break
    if pun: return {'status':'estimated_from_pun','estimated_all_in_eur_kwh':round(pun+0.18,3),'note':'PUN/proxy + costi regolati stimati.'}
    old=seed.get('home_charging',{})
    return {'status':'fallback','estimated_all_in_eur_kwh':old.get('estimated_all_in_eur_kwh',0.30),'note':'Fallback: inserire il proprio prezzo all-in.'}

def public(seed):
    nets=seed.get('public_charging',{}).get('networks',[])
    if not nets:
        nets=[{'network':'Enel X Way','ac_eur_kwh':0.69,'dc_eur_kwh':0.89,'hpc_eur_kwh':0.99},{'network':'A2A e-moving','ac_eur_kwh':0.65,'dc_eur_kwh':0.80,'hpc_eur_kwh':0.90},{'network':'Plenitude','ac_eur_kwh':0.65,'dc_eur_kwh':0.90,'hpc_eur_kwh':0.95},{'network':'Atlante','ac_eur_kwh':0.59,'dc_eur_kwh':0.79,'hpc_eur_kwh':0.89},{'network':'Tesla Supercharger','ac_eur_kwh':None,'dc_eur_kwh':0.55,'hpc_eur_kwh':0.60}]
    ac=[n['ac_eur_kwh'] for n in nets if n.get('ac_eur_kwh')]; dc=[n['dc_eur_kwh'] for n in nets if n.get('dc_eur_kwh')]; hp=[n['hpc_eur_kwh'] for n in nets if n.get('hpc_eur_kwh')]
    avga=sum(ac)/len(ac); avgd=sum(dc)/len(dc); avgh=sum(hp)/len(hp)
    return {'status':'fallback','method':'media pesata AC 55% / DC 30% / HPC 15%','average_ac_eur_kwh':round(avga,3),'average_dc_eur_kwh':round(avgd,3),'average_hpc_eur_kwh':round(avgh,3),'weighted_public_eur_kwh':round(avga*.55+avgd*.30+avgh*.15,3),'networks':nets}

def main():
    seed=load(OUT,{})
    payload={'updated':now(),'fuel':fuel(seed),'home_charging':home(seed),'public_charging':public(seed),'defaults':load(CFG,{})}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=1),encoding='utf-8')
    print('vehicle inputs updated')
if __name__=='__main__': main()
