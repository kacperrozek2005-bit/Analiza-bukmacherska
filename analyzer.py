import math
import sqlite3
import requests
from datetime import datetime

# ==================== KONFIGURACJA KLUCZY API ====================
APISPORTS_KEY = fabfcbfe4763db2cd50bdd222e33d637
ODDS_API_KEY = beda5816bff5043839eec9127d5ed4a0
TELEGRAM_BOT_TOKEN = HTTP API:8866199770:AAHtgJOkSyxNzJiTExkrNC7abrPdA1c_rAs
TELEGRAM_CHAT_ID = 6326526350

HEADERS_APISPORTS = {
    "x-apisports-key": APISPORTS_KEY
}

def init_db():
    conn = sqlite3.connect("bets.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            match_name TEXT,
            market TEXT,
            odds REAL,
            stake REAL,
            status TEXT DEFAULT 'PENDING',
            profit REAL DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()

def save_bet(match_name, market, odds, stake):
    conn = sqlite3.connect("bets.db")
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO bets (date, match_name, market, odds, stake)
        VALUES (?, ?, ?, ?, ?)
    """, (today, match_name, market, odds, stake))
    conn.commit()
    conn.close()

def update_bet_status(bet_id, status, odds, stake):
    conn = sqlite3.connect("bets.db")
    cursor = conn.cursor()
    profit = 0.0
    if status == 'WON':
        profit = round((stake * odds) - stake, 2)
    elif status == 'LOST':
        profit = -stake

    cursor.execute("""
        UPDATE bets SET status = ?, profit = ? WHERE id = ?
    """, (status, profit, bet_id))
    conn.commit()
    conn.close()

def get_all_bets():
    conn = sqlite3.connect("bets.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, date, match_name, market, odds, stake, status, profit FROM bets ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def calculate_yield_stats():
    bets = get_all_bets()
    settled_bets = [b for b in bets if b[6] in ['WON', 'LOST']]
    if not settled_bets:
        return {"total_bets": len(bets), "yield": 0.0, "profit": 0.0, "win_rate": 0.0, "total_staked": 0.0}

    total_staked = sum(b[5] for b in settled_bets)
    total_profit = sum(b[7] for b in settled_bets)
    wins = len([b for b in settled_bets if b[6] == 'WON'])
    win_rate = round((wins / len(settled_bets)) * 100, 1)
    yield_val = round((total_profit / total_staked) * 100, 2) if total_staked > 0 else 0.0

    return {
        "total_bets": len(bets),
        "total_staked": round(total_staked, 2),
        "total_profit": round(total_profit, 2),
        "win_rate": win_rate,
        "yield": yield_val
    }

def get_team_id(team_name):
    url = "https://v3.football.api-sports.io/teams"
    try:
        response = requests.get(url, headers=HEADERS_APISPORTS, params={"search": team_name}, timeout=10)
        data = response.json()
        if data.get("response"):
            return data["response"][0]["team"]["id"]
    except Exception as e:
        print(f"Błąd zespołu: {e}")
    return None

def fetch_team_xg_stats(team_id, last_matches=5):
    url = "https://v3.football.api-sports.io/fixtures"
    try:
        response = requests.get(url, headers=HEADERS_APISPORTS, params={"team": team_id, "last": last_matches}, timeout=10)
        data = response.json()
        if not data.get("response"):
            return 1.35, 1.35

        total_xg_for, total_xg_against, count = 0.0, 0.0, 0
        for match in data["response"]:
            fixture_id = match["fixture"]["id"]
            stats_url = "https://v3.football.api-sports.io/fixtures/statistics"
            stats_res = requests.get(stats_url, headers=HEADERS_APISPORTS, params={"fixture": fixture_id}, timeout=10).json()
            if stats_res.get("response") and len(stats_res["response"]) == 2:
                is_home = match["teams"]["home"]["id"] == team_id
                team_stats = stats_res["response"][0] if is_home else stats_res["response"][1]
                opp_stats = stats_res["response"][1] if is_home else stats_res["response"][0]
                
                xg_for = next((s["value"] for s in team_stats["statistics"] if s["type"] == "expected_goals"), None)
                xg_against = next((s["value"] for s in opp_stats["statistics"] if s["type"] == "expected_goals"), None)
                if xg_for and xg_against:
                    total_xg_for += float(xg_for)
                    total_xg_against += float(xg_against)
                    count += 1
        if count > 0:
            return round(total_xg_for / count, 2), round(total_xg_against / count, 2)
    except Exception as e:
        print(f"Błąd xG: {e}")
    return 1.35, 1.35

def fetch_live_odds(sport_key="soccer_epl", home_team="Arsenal", away_team="Chelsea"):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "h2h,totals", "oddsFormat": "decimal"}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        for match in data:
            if home_team.lower() in match["home_team"].lower() or away_team.lower() in match["away_team"].lower():
                if match.get("bookmakers"):
                    bookie = match["bookmakers"][0]
                    parsed = {'home': 0.0, 'draw': 0.0, 'away': 0.0, 'over_2_5': 0.0, 'under_2_5': 0.0}
                    for market in bookie["markets"]:
                        if market["key"] == "h2h":
                            for o in market["outcomes"]:
                                if o["name"] == match["home_team"]: parsed['home'] = o["price"]
                                elif o["name"] == match["away_team"]: parsed['away'] = o["price"]
                                elif o["name"].lower() == "draw": parsed['draw'] = o["price"]
                        if market["key"] == "totals":
                            for o in market["outcomes"]:
                                if o.get("point") == 2.5:
                                    if o["name"].lower() == "over": parsed['over_2_5'] = o["price"]
                                    elif o["name"].lower() == "under": parsed['under_2_5'] = o["price"]
                    return parsed, bookie["title"]
    except Exception as e:
        print(f"Błąd kursów: {e}")
    return None, None

def poisson_pmf(k, l_param):
    return (math.pow(l_param, k) * math.exp(-l_param)) / math.factorial(k)

def calculate_match_probabilities(home_att, home_def, away_att, away_def, avg_xg=1.35):
    exp_home = (home_att / avg_xg) * (away_def / avg_xg) * avg_xg
    exp_away = (away_att / avg_xg) * (home_def / avg_xg) * avg_xg
    home_win, draw, away_win, over_2_5 = 0.0, 0.0, 0.0, 0.0

    for h in range(6):
        for a in range(6):
            p = poisson_pmf(h, exp_home) * poisson_pmf(a, exp_away)
            if h > a: home_win += p
            elif h == a: draw += p
            else: away_win += p
            if (h + a) > 2.5: over_2_5 += p

    return {
        "home_win": round(home_win * 100, 1),
        "draw": round(draw * 100, 1),
        "away_win": round(away_win * 100, 1),
        "over_2_5": round(over_2_5 * 100, 1),
        "under_2_5": round((1 - over_2_5) * 100, 1)
    }

def calculate_kelly_stake(my_prob_pct, odds, kelly_fraction=0.25):
    p = my_prob_pct / 100.0
    q = 1.0 - p
    b = odds - 1.0
    if b <= 0 or p <= 0: return 0.0
    fk = (b * p - q) / b
    return round(fk * kelly_fraction * 100, 2) if fk > 0 else 0.0

def generate_tips_with_value(probs, odds, home_team, away_team, bankroll=1000.0, kelly_fraction=0.25):
    markets = [
        ('home', f"Wygrana {home_team}", probs['home_win']),
        ('draw', "Remis", probs['draw']),
        ('away', f"Wygrana {away_team}", probs['away_win']),
        ('over_2_5', "Powyżej 2.5 bramki (Over)", probs['over_2_5']),
        ('under_2_5', "Poniżej 2.5 bramki (Under)", probs['under_2_5']),
    ]
    value_bets = []
    for key, name, my_prob in markets:
        b_odds = odds.get(key, 0.0)
        if b_odds > 1.0:
            b_prob = round((1 / b_odds) * 100.0, 1)
            ev = round((((my_prob / 100.0) * b_odds) - 1) * 100, 2)
            if ev > 3.0:
                stake_pct = calculate_kelly_stake(my_prob, b_odds, kelly_fraction)
                stake_amt = round((stake_pct / 100.0) * bankroll, 2)
                value_bets.append({
                    "market": name, "my_prob": my_prob, "bookie_odds": b_odds,
                    "bookie_prob": b_prob, "ev": ev, "stake_pct": stake_pct, "stake_amount": stake_amt
                })
    value_bets.sort(key=lambda x: x["ev"], reverse=True)
    return value_bets

def send_telegram_notification(match_name, market, odds, ev, stake_amount, my_prob):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return False
    msg = (
        f"🚨 **WYKRYTO VALUE BET!** 🚨\n\n"
        f"⚽ **Mecz:** {match_name}\n"
        f"🎯 **Typ:** `{market}`\n"
        f"📈 **Kurs:** `{odds}`\n"
        f"📊 **Szansa wg xG:** `{my_prob}%`\n"
        f"💎 **EV:** `+{ev}%`\n"
        f"💰 **Stawka:** `{stake_amount} PLN`"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        return res.status_code == 200
    except Exception as e:
        print(f"Błąd Telegram: {e}")
        return False
