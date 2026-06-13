"""TIM — offerte mobile reali dalla pagina ufficiale.

Pagina: https://www.tim.it/fisso-e-mobile/mobile/passa-a-tim

Niente fallback manuali. TIM pubblica molte sezioni descrittive e condizioni
legali; inoltre il markup puo' spezzare heading, prezzo e bundle su righe
separate. Questo scraper legge:
- sezioni "Attiva TIM ... a X,XX€";
- bundle immediatamente successivi tipo "300 Giga, Minuti illimitati e 200 SMS";
- eventuali dettagli costi/attivazione nel blocco.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from lib.base import Offer, cli_main, dump_debug, fetch_mobile_page, fetch_rendered
from lib.parse_cards import parse_cards
from lib.xhr_mobile import mine_xhr_mobile

URL = "https://www.tim.it/fisso-e-mobile/mobile/passa-a-tim"
OPERATORE = "TIM"

HEADER = re.compile(r"Attiva\s+(TIM[^\n#]+?)\s+a\s+(\d{1,3})\s*[,\.]\s*(\d{2})\s*€", re.I)
GB_LINE = re.compile(r"^(\d{1,4})\s*Giga,?\s*Minuti\s+illimitati\s+e\s+200\s*SMS", re.I)
GB_ANY = re.compile(r"(\d{1,4})\s*Giga,?\s*Minuti\s+illimitati\s+e\s+200\s*SMS", re.I)
ACTIVATION_FREE = re.compile(r"Attivazione\s+offerta\s*:\s*0\s*€", re.I)
SIM_COST = re.compile(r"Importo\s+una\s+tantum\s+SIM\s*:\s*(?:\s*)?(\d{1,3})\s*€", re.I)
STOP = re.compile(r"Attiva\s+TIM|Hai\s+bisogno|Perchè\s+scegliere|Dettaglio\s+Costi|Condizioni\sd'Uso", re.I)

# Regex globale per quando BeautifulSoup/Playwright non mantengono righe utili.
GLOBAL_HEADER = re.compile(
    r"Attiva\s+(TIM.{0,90}?)\s+a\s+(\d{1,3})\s*[,\.]\s*(\d{2})\s*€"
    r"(?P<body>.{0,1800}?)(?=Attiva\s+TIM|Hai\s+bisogno|Perchè\s+scegliere|Condizioni\sd'Uso|$)",
    re.I | re.S,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _lines(html: str) -> list[str]:
    soup = _soup(html)
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return [
        x for x in (_clean(v).lstrip("# ") for v in soup.get_text("\n", strip=True).splitlines())
        if x and x not in {"*", "•"}
    ]


def _text(html: str) -> str:
    soup = _soup(html)
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return _clean(soup.get_text(" ", strip=True).lstrip("# "))


def _activation(block: str) -> float | None:
    if ACTIVATION_FREE.search(block):
        return 0.0
    if re.search(r"attivazione[^.;]{0,80}(gratis|gratuit)", block, re.I):
        return 0.0
    return None


def _sim_note(block: str) -> str:
    if m := SIM_COST.search(block):
        return f"SIM {float(m.group(1)):.2f}€ una tantum"
    if re.search(r"SIM[^.;]{0,80}10\s*€", block, re.I):
        return "SIM 10.00€ una tantum"
    return ""


def _make_offer(plan_name: str, price: float, giga: int, block: str, payment_note: str = "") -> Offer | None:
    if not (1 <= price <= 80 and 1 <= giga <= 2000):
        return None
    notes = []
    if payment_note:
        notes.append(payment_note)
    sim_note = _sim_note(block)
    if sim_note:
        notes.append(sim_note)
    if re.search(r"primo\s+mese\s+gratuito", block, re.I):
        notes.append("primo mese gratuito")
    return Offer(
        operatore=OPERATORE,
        offerta=f"{_clean(plan_name)} {giga} GB",
        url=URL,
        prezzo_mese=price,
        giga=giga,
        giga_illimitati=False,
        attivazione=_activation(block),
        minuti="illimitati",
        sms="200",
        rete_5g=True,
        note="; ".join(notes),
        fonte="scraping",
    )


def _parse_by_lines(html: str) -> list[Offer]:
    lines = _lines(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for i, line in enumerate(lines):
        hm = HEADER.search(line)
        if not hm:
            continue
        plan_name = _clean(hm.group(1))
        price = float(f"{hm.group(2)}.{hm.group(3)}")

        end = len(lines)
        for j in range(i + 1, len(lines)):
            if j > i + 1 and HEADER.search(lines[j]):
                end = j
                break
            # Non fermarti subito a Dettaglio Costi: serve per note SIM/attivazione.
            if j > i + 80 and STOP.search(lines[j]):
                end = j
                break

        block_lines = lines[i:end]
        block = _clean(" ".join(block_lines))
        for idx, candidate in enumerate(block_lines):
            gm = GB_LINE.search(candidate)
            if not gm:
                continue
            giga = int(gm.group(1))
            payment_note = ""
            # Di solito la riga dopo distingue carta/ricarica automatica vs credito residuo.
            if idx + 1 < len(block_lines) and "Pagamento" in block_lines[idx + 1]:
                payment_note = _clean(block_lines[idx + 1])
            offer = _make_offer(plan_name, price, giga, block, payment_note)
            if not offer:
                continue
            key = (round(price, 2), giga, plan_name.lower(), payment_note.lower())
            if key in seen:
                continue
            seen.add(key)
            offers.append(offer)

    return offers


def _parse_global(html: str) -> list[Offer]:
    text = _text(html)
    offers: list[Offer] = []
    seen: set[tuple] = set()

    for hm in GLOBAL_HEADER.finditer(text):
        plan_name = _clean(hm.group(1))
        price = float(f"{hm.group(2)}.{hm.group(3)}")
        body = _clean(hm.group("body"))
        block = _clean(hm.group(0))
        for gm in GB_ANY.finditer(body):
            giga = int(gm.group(1))
            around = body[gm.start(): min(len(body), gm.end() + 170)]
            payment_note = ""
            if "Ricarica Automatica" in around:
                payment_note = "Pagamento mensile con TIM Ricarica Automatica"
            elif "credito residuo" in around:
                payment_note = "Pagamento mensile su credito residuo"
            offer = _make_offer(plan_name, price, giga, block, payment_note)
            if not offer:
                continue
            key = (round(price, 2), giga, plan_name.lower(), payment_note.lower())
            if key in seen:
                continue
            seen.add(key)
            offers.append(offer)

    return offers


def parse_html(html: str, xhr: list | None = None) -> list[Offer]:
    offers = _parse_by_lines(html)
    if offers:
        return offers

    offers = _parse_global(html)
    if offers:
        return offers

    offers = parse_cards(html, OPERATORE, URL)
    if offers:
        # Evita prodotti/accessori: tieni solo offerte con minuti/SMS o GB >= 50.
        return [o for o in offers if o.giga_illimitati or (o.giga is not None and o.giga >= 50)]

    if xhr:
        offers = mine_xhr_mobile(xhr, OPERATORE, URL)
    return offers


def scrape() -> list[Offer]:
    html, xhr = fetch_mobile_page(URL)
    dump_debug("tim", html)
    if html:
        offers = parse_html(html, xhr)
        if offers:
            return offers

    # Fallback tecnico: se l'HTML statico non contiene le card parseabili,
    # forza rendering. Non usa dati manuali.
    rendered, rendered_xhr = fetch_rendered(URL)
    dump_debug("tim_rendered", rendered)
    if not rendered:
        return []
    return parse_html(rendered, rendered_xhr)


if __name__ == "__main__":
    cli_main("mobile", "tim", OPERATORE, scrape)
