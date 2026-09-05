# Monitor okazji: Kleinanzeigen -> Polska

Program co 30 minut sprawdza niemieckiego Kleinanzeigen (maszyny rolnicze, ciągniki,
opony rolnicze, samochody), porównuje cenę z medianą podobnych ofert na OLX.pl,
i jeśli szacowany zysk (po odjęciu kosztu transportu) wynosi min. 4000 zł —
wysyła Ci powiadomienie na Telegrama z linkiem do ogłoszenia.

Wszystko działa **za darmo w chmurze GitHuba**, więc nie musisz zostawiać
niczego włączonego. Powiadomienia dostajesz w aplikacji Telegram na telefonie.

## Zanim zaczniesz — ważne ograniczenia

- To jest pierwsze automatyczne przesianie ofert, **nie traktuj wyniku jako
  pewnika**. Zawsze sprawdź ogłoszenie ręcznie przed kontaktem ze sprzedawcą.
- Dopasowanie ceny polskiej odbywa się po tytule ogłoszenia (prosty tekst),
  więc czasem może się pomylić (np. inny model, inny stan techniczny).
- Kalkulacja **nie uwzględnia**: akcyzy przy sprowadzaniu samochodów z UE,
  kosztów rejestracji/przeglądu/tłumaczeń dokumentów, ani realnego stanu
  technicznego maszyny. Dla samochodów te koszty bywają wysokie — doliczaj je
  sam do progu 4000 zł.
- Strony internetowe (Kleinanzeigen, OLX) mogą zmienić wygląd i skrypt
  przestanie działać — wtedy trzeba poprawić kod (napisz do mnie, pomogę).
- Automatyczne pobieranie danych z tych serwisów może naruszać ich regulamin.
  Skrypt celowo działa wolno (przerwy między zapytaniami) i sprawdza tylko
  publicznie dostępne ogłoszenia — używaj na własną odpowiedzialność.

## Krok 1: Załóż konto na Telegramie (jeśli nie masz)

Zainstaluj aplikację Telegram na telefonie ze sklepu z aplikacjami.

## Krok 2: Stwórz swojego bota Telegram (2 minuty)

1. W Telegramie wyszukaj **@BotFather** i wejdź w rozmowę.
2. Wyślij komendę `/newbot`.
3. Podaj nazwę bota (dowolna, np. "Moje okazje") i login kończący się na `bot`
   (np. `moje_okazje_bot`).
4. BotFather odeśle Ci **token** — długi ciąg znaków typu
   `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`. **Zapisz go** — to jest `TELEGRAM_TOKEN`.

## Krok 3: Znajdź swój Chat ID

1. W Telegramie wyszukaj **@userinfobot** i napisz do niego cokolwiek (np. "cześć").
2. Odpowie Ci wiadomością zawierającą `Id: 123456789` — to jest Twój `TELEGRAM_CHAT_ID`.
3. Teraz wróć do bota, którego stworzyłeś w Kroku 2, i napisz mu dowolną
   wiadomość (np. "start") — to konieczne, żeby bot mógł Ci w ogóle pisać.

## Krok 4: Załóż konto na GitHub (za darmo)

Wejdź na https://github.com i załóż darmowe konto (jeśli nie masz).

## Krok 5: Wgraj ten projekt na GitHub

1. Na GitHubie kliknij **New repository** (zielony przycisk).
2. Nazwij je np. `kleinanzeigen-monitor`, ustaw jako **Public** (żeby Actions
   było całkowicie darmowe), kliknij **Create repository**.
3. Na stronie repozytorium kliknij **Add file → Upload files**.
4. Przeciągnij tam WSZYSTKIE pliki i foldery z tego paczki (łącznie z folderem
   `.github` — musi zachować swoją strukturę!).
5. Kliknij **Commit changes**.

## Krok 6: Dodaj swoje sekrety (token i chat ID)

1. W repozytorium wejdź w **Settings → Secrets and variables → Actions**.
2. Kliknij **New repository secret**.
   - Nazwa: `TELEGRAM_TOKEN`, wartość: token z Kroku 2. Zapisz.
   - Kliknij ponownie **New repository secret**.
   - Nazwa: `TELEGRAM_CHAT_ID`, wartość: numer z Kroku 3. Zapisz.

## Krok 7: Włącz i uruchom

1. Wejdź w zakładkę **Actions** w repozytorium.
2. Jeśli GitHub pyta, kliknij **I understand my workflows, go ahead and enable them**.
3. Kliknij workflow **"Monitor okazji Kleinanzeigen"** po lewej.
4. Kliknij **Run workflow** (żeby przetestować od razu, nie czekając 30 minut).
5. Po ok. 1-2 minutach sprawdź Telegram — jeśli znajdzie okazję, dostaniesz wiadomość.

Od teraz program uruchamia się **sam, co 30 minut**, bez Twojego udziału.

## Jak dostosować program do siebie

Otwórz plik `scraper.py` na GitHubie (ikona ołówka = edycja) i zmień na górze:

- `CATEGORIES` — dodaj/zmień słowa kluczowe wyszukiwania (np. konkretną markę).
- `MIN_PROFIT_PLN` — próg zysku (domyślnie 4000 zł).
- `TRANSPORT_COST_PLN` — Twój szacunkowy koszt transportu z Niemiec.
- `MIN_PRICE_EUR` / `MAX_PRICE_EUR` — zakres cen, które Cię interesują.

Po zapisaniu zmian (Commit changes) program automatycznie użyje nowych ustawień
przy następnym uruchomieniu.
