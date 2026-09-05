"""
Monitor Kleinanzeigen.de (Niemcy) -> maszyny rolnicze, samochody, opony rolnicze.
Porownuje z medianowa cena podobnych ofert na OLX.pl i wysyla powiadomienie
Telegram, gdy szacowany zysk >= MIN_PROFIT_PLN.

UWAGA (przeczytaj koniecznie):
- kleinanzeigen.de i OLX.pl moga w kazdej chwili zmienic uklad strony (HTML).
  Jesli skrypt przestanie znajdowac oferty, trzeba poprawic selektory CSS
  w funkcjach search_kleinanzeigen() i estimate_polish_price_pln().
- Dopasowanie ceny polskiej odbywa sie po tytule ogloszenia (prosty tekst),
  wiec bywa niedokladne - to szacunek, nie pewnik. Zawsze sprawdz oferte
  recznie przed zakupem.
- Kalkulacja zysku NIE uwzglednia: akcyzy przy sprowadzaniu samochodow z UE,
  kosztow rejestracji/przegladu/tlumaczen, ani stanu technicznego maszyny.
  Dostosuj TRANSPORT_COST_PLN i traktuj wynik jako pierwsze przesianie ofert,
  nie ostateczna decyzje.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

# ---------- KONFIGURACJA - EDYTUJ WEDLUG POTRZEB ----------
CATEGORIES = [
    {"name": "Ciagniki rolnicze", "query": "traktor landwirtschaft"},
    {"name": "Maszyny rolnicze", "query": "landmaschine"},
    {"name": "Opony rolnicze", "query": "reifen traktor"},
    {"name": "Samochody", "query": "auto"},
]

MIN_PRICE_EUR = 0          # 0 = uwzglednia tez oferty "zu verschenken" (za darmo)
MAX_PRICE_EUR = 60000
MIN_PROFIT_PLN = 4000
TRANSPORT_COST_PLN = 1500  # szacunkowy koszt transportu z Niemiec - dopasuj sam

SEEN_FILE = Path(__file__).parent / "seen_ids.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9",
}

NBP_API = "https://api.nbp.pl/api/exchangerates/rates/a/eur/?format=json"


def get_eur_pln_rate():
    try:
        r = requests.get(NBP_API, timeout=15)
        r.raise_for_status()
        return r.json()["rates"][0]["mid"]
    except Exception as e:
        print(f"Blad pobierania kursu EUR/PLN, uzywam 4.3 jako fallback: {e}")
        return 4.3


def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen)))


def search_kleinanzeigen(query, page=1):
    """Zwraca liste ofert: [{id, title, price_eur, url}, ...]"""
    url = f"https://www.kleinanzeigen.de/s-seite:{page}/{quote_plus(query)}/k0"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"Blad pobierania kleinanzeigen dla '{query}': {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    print(f"    [debug] dlugosc odpowiedzi HTML: {len(r.text)} znakow, "
          f"kod statusu: {r.status_code}")
    results = []
    for item in soup.select("article.aditem"):
        try:
            ad_id = item.get("data-adid")
            link_tag = item.select_one("a.ellipsis")
            title = link_tag.get_text(strip=True) if link_tag else None
            href = link_tag["href"] if link_tag else None
            price_tag = item.select_one("p.aditem-main--middle--price-shipping--price")
            price_text = price_tag.get_text(strip=True) if price_tag else ""

            if "verschenken" in price_text.lower():
                price_eur = 0
            else:
                digits = re.sub(r"[^\d]", "", price_text)
                price_eur = int(digits) if digits else None

            if not (ad_id and title and href and price_eur is not None):
                continue

            results.append({
                "id": ad_id,
                "title": title,
                "price_eur": price_eur,
                "url": "https://www.kleinanzeigen.de" + href,
            })
        except Exception:
            continue
    return results


def estimate_polish_price_pln(title):
    """Szuka podobnych ofert na OLX.pl i zwraca mediane ceny w PLN (lub None)."""
    query = quote_plus(title)
    url = f"https://www.olx.pl/oferty/q-{query}/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"Blad pobierania OLX dla '{title}': {e}")
        return None

    soup = BeautifulSoup(r.text, "lxml")
    prices = []
    for price_tag in soup.select("[data-testid='ad-price']"):
        digits = re.sub(r"[^\d]", "", price_tag.get_text())
        if digits:
            prices.append(int(digits))

    if len(prices) < 3:
        return None  # za malo danych porownawczych, nie ryzykuj falszywego alarmu

    prices.sort()
    mid = len(prices) // 2
    median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
    return median


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Brak TELEGRAM_TOKEN / TELEGRAM_CHAT_ID - wypisuje w konsoli zamiast wysylac:")
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }, timeout=15)
    except Exception as e:
        print(f"Blad wysylania Telegram: {e}")


def main():
    seen = load_seen()
    rate = get_eur_pln_rate()
    print(f"Kurs EUR/PLN: {rate}")

    new_seen = set(seen)
    found_any = False

    for cat in CATEGORIES:
        print(f"--- Szukam: {cat['name']} ---")
        for page in (1, 2):
            listings = search_kleinanzeigen(cat["query"], page=page)
            print(f"    -> znaleziono {len(listings)} ofert na stronie {page}")
            time.sleep(2)  # nie przeciazaj serwera
            for ad in listings:
                if ad["id"] in seen:
                    continue
                new_seen.add(ad["id"])

                if not (MIN_PRICE_EUR <= ad["price_eur"] <= MAX_PRICE_EUR):
                    continue

                price_pln_de = ad["price_eur"] * rate
                pl_price = estimate_polish_price_pln(ad["title"])
                time.sleep(2)

                if pl_price is None:
                    continue

                profit = pl_price - price_pln_de - TRANSPORT_COST_PLN

                if profit >= MIN_PROFIT_PLN:
                    found_any = True
                    msg = (
                        f"🚜 <b>Okazja: {cat['name']}</b>\n"
                        f"{ad['title']}\n\n"
                        f"Cena w Niemczech: {ad['price_eur']} EUR (~{price_pln_de:.0f} zl)\n"
                        f"Szac. cena w PL: ~{pl_price:.0f} zl\n"
                        f"Szac. zysk (po transporcie {TRANSPORT_COST_PLN} zl): "
                        f"<b>{profit:.0f} zl</b>\n\n"
                        f"{ad['url']}"
                    )
                    send_telegram(msg)
                    print(msg)

    save_seen(new_seen)
    if not found_any:
        print("Brak nowych okazji w tym przebiegu.")


if __name__ == "__main__":
    sys.exit(main() or 0)
