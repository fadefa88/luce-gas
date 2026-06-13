"""CoopVoce — offerte mobile.

Pagina: https://www.coopvoce.it/portale/offerte.html

Tecnica: il sito (Adobe AEM) incorpora i dati di OGNI offerta come blocchi
di coppie etichetta/valore nel markup, es.:
    Nome Offerta              -> TURBO 200
    [ PROMO GIGA ] Numero Giga -> 200
    Numero SMS                -> 1000
    Costo AL                  -> 7,90   (prezzo standard)
    Costo MNP                 -> 7,90   (prezzo con portabilita')
    Attivazione gratuita      -> true
E' molto piu' stabile del parsing visivo. Il 5G si riconosce dall'icona
"icona5g.svg" nel markup della card.

Filtro: offerte mobile con Giga numerici (5G e non) (escludiamo IoT, ConMe Casa/Alarm,
SIMPLE senza giga).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_rendered

URL = "https://www.coopvoce.it/portale/offerte.html"
CLICKS = []


def _field(text: str, label: str) -> str | None:
    """Valore sulla riga successiva a un'etichetta del blocco proprieta'."""
    m = re.search(re.escape(label) + r"\s*[\r\n]+\s*([^\r\n]+)", text)
    return m.group(1).strip() if m else None


def _euro(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"(\d{1,3})[.,](\d{2})", s)
    return float(f"{m.group(1)}.{m.group(2)}") if m else None


def _is_5g(html: str, nome: str) -> bool:
    """True se l'icona 5G appartiene alla CARD di questa offerta.

    Nel markup reale la card mostra prima il nome offerta e, subito sotto,
    l'icona (icona5g.svg per le 5G). Cerchiamo l'icona SOLO in avanti e fino
    al nome dell'offerta successiva, così non "rubiamo" l'icona di un'altra
    card (che causerebbe falsi positivi, es. EVO 30 marcata 5G per sbaglio).
    """
    up = html.upper()
    nome_u = nome.upper()
    # Cerchiamo l'occorrenza del nome NELLA CARD (vicino a "GIGA"/prezzo),
    # non nel blocco proprieta'. Prendiamo la PRIMA occorrenza del nome.
    idx = up.find(nome_u)
    if idx < 0:
        return False
    # finestra in avanti, troncata al prossimo "icona" o a 600 char (una card)
    forward = html[idx: idx + 600].lower()
    return "icona5g" in forward


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    soup = BeautifulSoup(html, "html.parser")
    full = soup.get_text("\n", strip=True)

    offers: list[Offer] = []
    seen: set[str] = set()

    for chunk in re.split(r"(?=Nome Offerta\s*[\r\n])", full):
        nome = _field(chunk, "Nome Offerta")
        if not nome:
            continue
        nome = nome.strip()
        if nome in seen:
            continue

        giga_raw = _field(chunk, "Numero Giga")
        giga_val = int(giga_raw) if giga_raw and giga_raw.isdigit() else None
        price = _euro(_field(chunk, "Costo AL")) or _euro(_field(chunk, "Costo MNP"))

        msg = _field(chunk, "Messaggio Promo") or ""
        sms = ""
        if (m := re.search(r"(\d+)\s*SMS", msg)):
            sms = m.group(1)
        elif (sraw := _field(chunk, "Numero SMS")) and sraw.isdigit():
            sms = sraw

        attiv_gratis = (_field(chunk, "Attivazione gratuita") or "").lower() == "true"
        promo_primo = (_field(chunk, "Primo mese gratuito") or "").lower() == "true"
        descr = _field(chunk, "Descrizione") or ""

        if giga_val is None or price is None:
            continue
        if not (1 <= price <= 60) or not (5 <= giga_val <= 2000):
            continue

        note = []
        if promo_primo:
            note.append("attivazione + primo mese gratuiti")
        if descr and "VALIDA" in descr.upper():
            note.append(descr)

        seen.add(nome)
        offers.append(Offer(
            operatore="CoopVoce",
            offerta=nome.title() if nome.isupper() else nome,
            url=URL,
            prezzo_mese=price,
            giga=giga_val,
            attivazione=0.0 if attiv_gratis else None,
            minuti="illimitati" if "ILLIMITAT" in msg.upper() else "",
            sms=sms,
            rete_5g=_is_5g(html, nome),
            note="; ".join(note),
            fonte="scraping",
        ))
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_rendered(URL, clicks=CLICKS)
    dump_debug("coopvoce", html)
    if not html:
        return []
    return parse_html(html, xhr)


if __name__ == "__main__":
    cli_main("mobile", "coopvoce", "CoopVoce", scrape)
