

# ELTE GTK órarend sync

Ez egy vibecode-olt shitass webscraper ami felrakja az epp aktualis GTK-s orarendedet a google naptaradba, hogy ne nezzen ki olyan ocsmanyul mint az eredeti. Nem vallalok felelosseget a hasznalataert, nekem csak hasznos mert utalom h egy f*szom tablazatot kell hasznalnom orarendnek amit minden masodik nap atrendeznek. 🙂

Innentol ai a readme, have fun haverdak!

## Fájlok
- `scraper.py`: belépés, órarend oldal letöltése, dátumozott HTML mentése
- `parser.py`: órarend táblából események készítése
- `sync_calendar.py`: Google Naptár szinkron (OAuth)
- `emailer.py`: futási összefoglaló e-mail küldése (Gmail API)
- `main.py`: teljes folyamat futtatása
- `config.example.json`: konfigurációs minta

## Telepítés
1. Telepítsd a függőségeket:
   ```powershell
   python -m pip install -r requirements.txt
   ```
2. Másold le a mintát:
   - `config.example.json` -> `config.json`
3. Töltsd ki a `config.json`-t:
   - `login_url`: az ELTE belépési URL (a hosszú, `ReturnTo` paraméteres).
   - `credentials.username` és `credentials.password`.
   - `credentials.username_field` / `credentials.password_field`: ha a beviteli mezők neve eltér.
   - `calendar_id` vagy `calendar_name`: cél naptár azonosító vagy név.
   - `lecture_group_letter`: Csak az ilyen csoportbetűs előadásokat tartja meg a script (pl. `K`). Ha üres, nincs szűrés.
   - Opcionális: `orarend_url`, ha az automatikus felismerés nem működik.
4. Titkos adatok ne kerüljenek Git-be:
   - `config.json`, `credentials.json`, `token.json`, `token_gmail.json`.

## Google Cloud + OAuth (Google Naptár + Gmail API)
Az OAuth kliens JSON (`credentials.json`) ugyanazt a fájlt használja a naptár- és e-mail funkcióhoz.

1. Google Cloud Console-ben hozz létre egy projektet.
2. Engedélyezd az API-kat:
   - `Google Calendar API`
   - `Gmail API` (csak ha e-mailt is szeretnél)
3. Állítsd be az OAuth Consent Screen-t (External), és add hozzá a saját Google fiókodat teszt felhasználóként.
4. Készíts OAuth kliens azonosítót:
   - Típus: **Desktop app**
5. Töltsd le a kliens JSON-t, nevezd át `credentials.json`-ra, és tedd a projekt mappájába.
6. Első futtatáskor a böngészőben jóvá kell hagynod a hozzáférést.
   - Naptár token: `token.json`
   - Gmail token: `token_gmail.json`

Ha a jogosultságok változnak, töröld a token fájlokat és futtasd újra az appot.

## E-mail funkció (Gmail API)
Az app futás végén összefoglaló e-mailt küld. Hibánál is tud küldeni.

`config.json` -> `email` rész:
- `enabled`: `true`/`false`
- `send_on_failure`: ha `true`, hibánál is küld
- `from_addr`: feladó (jellemzően ugyanaz a Gmail fiók)
- `to_addr`: címzett
- `subject_prefix`: tárgy prefix
- `credentials_file`: OAuth kliens JSON fájl neve (alapértelmezett: `credentials.json`)
- `token_file`: Gmail token fájl neve (alapértelmezett: `token_gmail.json`)

## Futtatás
```powershell
python main.py
```

## Ütemezés (Windows Task Scheduler)
Hozz létre egy napi feladatot, például **01:00** időpontra:
- Program: `python`
- Arguments: `main.py`
- Start in: a projekt mappája (ahol a `main.py` található)

## Megjegyzések
- Pillanatképek a `data/snapshots` mappában, és csak az utolsó `keep_snapshots` marad meg.
- Időzóna: `Europe/Budapest`.
- Ha a belépési űrlap változik, frissítsd a `credentials.username_field` / `credentials.password_field` mezőket, vagy add hozzá a `credentials.extra_fields` értékeket.
