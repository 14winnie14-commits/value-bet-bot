import requests
import time
import os
import json
from datetime import datetime, timezone, timedelta

# Leggi le variabili d'ambiente (impostate su Railway)
ODDS_API_KEY = os.environ["ODDS_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])

THRESHOLD = 1.20
MIN_ODDS = 1.50
HOURS_MIN, HOURS_MAX = 3, 24
CHECK_INTERVAL = 600  # 10 minuti

try:
    from zoneinfo import ZoneInfo
except:
    from datetime import timezone as ZoneInfo
    ZoneInfo = lambda tz: timezone.utc

LOCAL_TZ = ZoneInfo("Europe/Rome")

SPORTS = [
    "soccer_italy_serie_a", "soccer_italy_serie_b", "soccer_epl",
    "soccer_spain_la_liga", "soccer_france_ligue_one", "soccer_germany_bundesliga",
    "soccer_uefa_champs_league", "soccer_uefa_europa_league", "soccer_uefa_conference_league"
]
MARKETS = ["h2h", "totals"]
BOOKMAKERS = ["bet365", "snai", "betway", "bwin", "williamhill"]

LEAGUE_NAMES = {
    "soccer_italy_serie_a": "Serie A", "soccer_italy_serie_b": "Serie B",
    "soccer_epl": "Premier", "soccer_spain_la_liga": "La Liga",
    "soccer_france_ligue_one": "Ligue 1", "soccer_germany_bundesliga": "Bundesliga",
    "soccer_uefa_champs_league": "Champions", "soccer_uefa_europa_league": "Europa",
    "soccer_uefa_conference_league": "Conference"
}

# Carica seen alerts se esiste
seen_file = "seen.json"
seen = set()
if os.path.exists(seen_file):
    try:
        with open(seen_file) as f:
            seen = set(json.load(f))
    except:
        pass

def build_link(bk, h, a):
    q = f"{h.replace(' ', '+')}+vs+{a.replace(' ', '+')}"
    return {
        "bet365": "https://www.bet365.it/#/AC/B1/C1/D13/E42945728/F2/",
        "snai": f"https://www.snai.it/sport?search={q}",
        "betway": f"https://sports.betway.it/it/sports?search={q}",
        "bwin": f"https://sports.bwin.it/it/sports#search={q}",
        "williamhill": f"https://sports.williamhill.it/betting/it-it#search={q}",
    }.get(bk, f"https://www.{bk}.com")

def send_msg(text, btns=None):
    try:
        import telegram
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        markup = InlineKeyboardMarkup(btns) if btns else None
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode=telegram.ParseMode.HTML, reply_markup=markup)
    except Exception as e:
        print(f"❌ Telegram error: {e}")

def in_window(t):
    try:
        start = datetime.fromisoformat(t.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return timedelta(hours=HOURS_MIN) <= (start - now) <= timedelta(hours=HOURS_MAX)
    except:
        return False

print("✅ Bot avviato su Railway. Controllo ogni 10 minuti.")

# Ciclo infinito (Railway lo mantiene attivo)
while True:
    alerts = 0
    events_in_window = 0
    
    for sport in SPORTS:
        try:
            res = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
                params={
                    "apiKey": ODDS_API_KEY,
                    "regions": "eu",
                    "markets": ",".join(MARKETS),
                    "oddsFormat": "decimal",
                    "bookmakers": ",".join(BOOKMAKERS)
                },
                timeout=10
            )
            if res.status_code != 200:
                continue
                
            for ev in res.json():
                if not in_window(ev.get("commence_time", "")):
                    continue
                events_in_window += 1
                
                home, away = ev["home_team"], ev["away_team"]
                bks = {b["key"]: b for b in ev.get("bookmakers", [])}
                if "bet365" not in bks:
                    continue
                    
                for market in MARKETS:
                    try:
                        bet365_outcomes = {o["name"]: o["price"] for o in next(m["outcomes"] for m in bks["bet365"]["markets"] if m["key"] == market)}
                    except:
                        continue
                        
                    for bk_key, bk in bks.items():
                        if bk_key == "bet365":
                            continue
                        try:
                            other_outcomes = next(m["outcomes"] for m in bk["markets"] if m["key"] == market)
                            for out in other_outcomes:
                                name, price = out["name"], out["price"]
                                if name in bet365_outcomes:
                                    b365_price = bet365_outcomes[name]
                                    if b365_price >= MIN_ODDS and price >= b365_price * THRESHOLD:
                                        key = f"{sport}|{home}|{away}|{market}|{name}|{bk_key}|{price}"
                                        if key in seen:
                                            continue
                                        seen.add(key)
                                        
                                        utc_start = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
                                        local_start = utc_start.astimezone(LOCAL_TZ).strftime("%d/%m %H:%M")
                                        
                                        msg = (
                                            f"📈 <b>VALUE BET!</b>\n"
                                            f"🔹 {LEAGUE_NAMES.get(sport, sport)}\n"
                                            f"🔹 {home} vs {away}\n"
                                            f"🔹 Inizio: {local_start}\n"
                                            f"🔹 Bet365: {b365_price} → {bk_key.title()}: {price}\n"
                                            f"🔹 +{round((price/b365_price-1)*100,1)}%"
                                        )
                                        try:
                                            from telegram import InlineKeyboardButton
                                            btns = [
                                                [InlineKeyboardButton("🟦 Bet365", url=build_link("bet365", home, away))],
                                                [InlineKeyboardButton(f"💰 {bk_key.title()}", url=build_link(bk_key, home, away))]
                                            ]
                                        except:
                                            btns = None
                                        send_msg(msg, btns)
                                        alerts += 1
                        except:
                            continue
        except:
            continue

    if alerts == 0 and events_in_window == 0 and int(time.time()) % 3600 < 600:
        send_msg("ℹ️ Nessuna partita nei prossimi 3–24h. Il bot è attivo.")
    
    # Salva seen alerts
    with open(seen_file, "w") as f:
        json.dump(list(seen), f)
    
    time.sleep(CHECK_INTERVAL)
