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
