"""
Monitor Kleinanzeigen.de (Niemcy) -> samochody (w tym uszkodzone), rolnictwo, opony.
Porownuje cene z Niemiec z SerpApi (wyszukiwanie cen w Polsce, po tlumaczeniu
tytulu na polski) - a gdy SerpApi nie znajdzie wystarczajaco danych, uzywa
recznie wpisanej ref_price_pln jako fallback. Wysyla powiadomienie Telegram,
gdy szacowany zysk >= MIN_PROFIT_PLN.

UWAGA (przeczytaj koniecznie):
- kleinanzeigen.de moze w kazdej chwili zmienic uklad strony (HTML). Jesli
  skrypt przestanie znajdowac oferty, trzeba poprawic selektory w funkcji
  search_kleinanzeigen().
- Cena polska z SerpApi to szacunek na podstawie fragmentow wynikow
  wyszukiwania Google - moze byc niedokladna. ref_price_pln to TWOJA WLASNA
  ocena, uzywana gdy SerpApi zawiedzie.
- Kalkulacja zysku NIE uwzglednia: akcyzy przy sprowadzaniu samochodow z UE,
  kosztow rejestracji/przegladu/tlumaczen, ani stanu technicznego pojazdu.
  Dostosuj TRANSPORT_COST_PLN i ref_price_pln dla kazdej kategorii ponizej.
- Darmowy limit SerpApi to 250 wyszukiwan miesiecznie.
- seen_ids.json to zwykly plik tekstowy (jedno ID na linie), NIE lista JSON.
- Odsiewa oczywiste zabawki/foteliki/czesci (slowa typu "kinder", "autositz").
- MIN_PRICE_EUR podniesione do 200 - prawdziwe pojazdy nie sa "za darmo",
  a oferty "zu verschenken" to w praktyce prawie zawsze smieci.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests
import cloudscraper
from bs4 import BeautifulSoup

# ---------- KONFIGURACJA - EDYTUJ WEDLUG POTRZEB ----------
CATEGORIES = [
    {"name": "Samochod", "query": "auto", "ref_price_pln": 15000},
    {"name": "Samochod uszkodzony", "query": "auto unfallwagen", "ref_price_pln": 8000},
    {"name": "Samochod z zepsutym silnikiem", "query": "auto motorschaden", "ref_price_pln": 6000},
    {"name": "Zepsute sprzegło", "query": "kupplung defekt", "ref_price_pln": 7000},
    {"name": "Rolnictwo", "query": "landwirtschaft", "ref_price_pln": 20000},
    {"name": "Pojazdy rolnicze", "query": "agrarfahrzeuge", "ref_price_pln": 20000},
    {"name": "Opony", "query": "reifen", "ref_price_pln": 800},
    {"name": "Przetrzasarka (Kreiselheuer)", "query": "kreiselheuer", "ref_price_pln": 8000},
    {"name": "Zgrabiarka (Schwader)", "query": "schwader", "ref_price_pln": 9000},
    {"name": "Plug (Pflug)", "query": "pflug", "ref_price_pln": 6000},
    {"name": "Maszyna rolnicza uszkodzona (Schaden)", "query": "landmaschine schaden", "ref_price_pln": 5000},
    {"name": "Maszyna rolnicza uszkodzona (Defekt)", "query": "landmaschine defekt", "ref_price_pln": 5000},
]

MIN_PRICE_EUR = 200
MAX_PRICE_EUR = 8000
MIN_PROFIT_PLN = 1000
TRANSPORT_COST_PLN = 1500

SEEN_FILE = Path(__file__).parent / "seen_ids.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,pl;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "DNT": "1",
}

NBP_API = "https://api.nbp.pl/api/exchangerates/rates/a/eur/?format=json"

SCRAPER = cloudscraper.create_scraper(browser={"custom": HEADERS["User-Agent"]})


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
            lines = SEEN_FILE.read_text().splitlines()
            return set(line.strip() for line in lines if line.strip())
        except Exception:
            return set()
    return set()


def append_seen(new_ids):
    """Dopisuje TYLKO nowe ID (po jednym na linie) na koniec pliku - nie
    nadpisuje calego pliku, dzieki czemu Git moze bezpiecznie laczyc zmiany
    z kilku rownoleglych przebiegow bez konfliktow."""
    if not new_ids:
        return
    with open(SEEN_FILE, "a") as f:
        for ad_id in new_ids:
            f.write(f"{ad_id}\n")


def search_kleinanzeigen(query, page=1):
    """Zwraca liste ofert: [{id, title, price_eur, url}, ...]"""
    url = f"https://www.kleinanzeigen.de/s-seite:{page}/{quote_plus(query)}/k0"
    try:
        r = SCRAPER.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"Blad pobierania kleinanzeigen dla '{query}': {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    print(f"    [debug] kod statusu: {r.status_code}, dlugosc: {len(r.text)} znakow")

    results = []
    for item in soup.select("article[data-adid]"):
        try:
            ad_id = item.get("data-adid")
            href = item.get("data-href")

            title = None
            script_tag = item.select_one('script[type="application/ld+json"]')
            if script_tag and script_tag.string:
                try:
                    ld_data = json.loads(script_tag.string)
                    title = ld_data.get("title")
                except Exception:
                    title = None
            if not title and href:
                slug = href.strip("/").split("/")
                if len(slug) > 1:
                    title = slug[1].replace("-", " ")

            text = item.get_text(" ", strip=True)
            if "verschenken" in text.lower():
                price_eur = 0
            else:
                m = re.search(r"([\d.]+)\s*€", text)
                if m:
                    digits = re.sub(r"[^\d]", "", m.group(1))
                    price_eur = int(digits) if digits else None
                else:
                    price_eur = None

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


def translate_de_to_pl(text):
    """Tlumaczy tekst z niemieckiego na polski (darmowy, nieoficjalny endpoint
    Google Translate - bez klucza/konta). Jesli sie nie uda, zwraca oryginal."""
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "de", "tl": "pl", "dt": "t", "q": text},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return "".join(seg[0] for seg in data[0])
    except Exception as e:
        print(f"Blad tlumaczenia '{text}': {e}, uzywam oryginalu")
        return text


def estimate_polish_price_pln(title, ref_price_pln):
    """Uzywa SerpApi.com (darmowy plan) do znalezienia fragmentow tekstu z
    cenami dla podobnego przedmiotu w Polsce. Tlumaczy tytul na polski przed
    wyszukaniem. Zwraca mediane cen w PLN, lub ref_price_pln jako fallback."""
    if not SERPAPI_KEY:
        return ref_price_pln

    title_pl = translate_de_to_pl(title)
    print(f"    [debug-PL] tlumaczenie: '{title}' -> '{title_pl}'")

    query = f"{title_pl} cena"
    try:
        r = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google",
                "q": query,
                "api_key": SERPAPI_KEY,
                "gl": "pl",
                "hl": "pl",
                "num": 10,
            },
            timeout=30,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"Blad zapytania do SerpApi dla '{title}': {e}, uzywam ref_price_pln")
        return ref_price_pln

    data = r.json()
    if "error" in data:
        print(f"SerpApi zwrocilo blad dla '{title}': {data['error']}, uzywam ref_price_pln")
        return ref_price_pln

    items = data.get("organic_results", [])
    print(f"    [debug-PL] SerpApi zwrocilo {len(items)} wynikow dla '{query}'")

    combined_text = " ".join(
        (item.get("title", "") + " " + item.get("snippet", "")) for item in items
    )

    matches = re.findall(r"(\d[\d\s]{1,8})\s*zł", combined_text)
    prices = []
    for m in matches:
        digits = re.sub(r"[^\d]", "", m)
        if digits:
            val = int(digits)
            if 10 <= val <= 500000:
                prices.append(val)

    print(f"    [debug-PL] znaleziono {len(prices)} pasujacych cen w wynikach")

    if len(prices) < 3:
        return ref_price_pln

    prices.sort()
    mid = len(prices) // 2
    return prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2


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

    newly_found_ids = []
    found_any = False

    for cat in CATEGORIES:
        print(f"--- Szukam: {cat['name']} ---")
        for page in (1, 2):
            l
