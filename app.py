import streamlit as st
import pandas as pd
from analyzer import (
    init_db, save_bet, update_bet_status, get_all_bets, calculate_yield_stats,
    get_team_id, fetch_team_xg_stats, calculate_match_probabilities,
    generate_tips_with_value, fetch_live_odds, send_telegram_notification
)

init_db()
st.set_page_config(page_title="Football Value Bet Analyzer", page_icon="⚽", layout="centered")

tab1, tab2 = st.tabs(["⚽ Analizator Meczowy", "📊 Historia & Yield"])

with tab1:
    st.title("⚽ Analizator Value Bet & xG")
    league_mapping = {
        "Anglia - Premier League": "soccer_epl",
        "Polska - Ekstraklasa": "soccer_poland_ekstraklasa",
        "Hiszpania - La Liga": "soccer_spain_la_liga",
        "Niemcy - Bundesliga": "soccer_germany_bundesliga",
        "Włochy - Serie A": "soccer_italy_serie_a",
        "Liga Mistrzów": "soccer_uefa_champs_league"
    }
    selected_league = st.selectbox("Wybierz Ligę", list(league_mapping.keys()))
    sport_key = league_mapping[selected_league]

    c1, c2 = st.columns(2)
    home_team = c1.text_input("Gospodarz", "Arsenal")
    away_team = c2.text_input("Gość", "Chelsea")

    st.markdown("---")
    cb1, cb2 = st.columns(2)
    user_bankroll = cb1.number_input("Twój Budżet (PLN)", value=1000.0, step=100.0)
    kelly_mode = cb2.selectbox("Tryb Kellego", ["1/4 Kellego (Bezpieczny)", "1/2 Kellego (Umiarkowany)", "Pełny Kelly (Agresywny)"])
    kelly_map = {"1/4 Kellego (Bezpieczny)": 0.25, "1/2 Kellego (Umiarkowany)": 0.50, "Pełny Kelly (Agresywny)": 1.00}

    if st.button("🚀 Przeanalizuj Mecz"):
        with st.spinner("Analizowanie meczu..."):
            live_odds, bookie_name = fetch_live_odds(sport_key, home_team, away_team)
            home_id = get_team_id(home_team)
            away_id = get_team_id(away_team)

            if not home_id or not away_id:
                st.error("Nie znaleziono zespołu w bazie xG. Sprawdź pisownię.")
            elif not live_odds:
                st.warning("Brak aktualnych kursów dla tego meczu.")
            else:
                h_att, h_def = fetch_team_xg_stats(home_id)
                a_att, a_def = fetch_team_xg_stats(away_id)
                probs = calculate_match_probabilities(h_att, h_def, a_att, a_def)
                value_bets = generate_tips_with_value(probs, live_odds, home_team, away_team, user_bankroll, kelly_map[kelly_mode])

                st.success(f"Kursy pobrane z: {bookie_name}")
                st.subheader("📊 Aktualne Kursy")
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("1", live_odds['home'])
                k2.metric("X", live_odds['draw'])
                k3.metric("2", live_odds['away'])
                k4.metric("Over 2.5", live_odds['over_2_5'])
                k5.metric("Under 2.5", live_odds['under_2_5'])

                st.markdown("---")
                st.header("💎 Wykryte Value Bety")
                if value_bets:
                    for i, bet in enumerate(value_bets):
                        st.success(
                            f"🔥 **{bet['market']}**\n\n"
                            f"- **Szansa xG vs Bukmacher:** `{bet['my_prob']}%` vs `{bet['bookie_prob']}%` (Kurs: **{bet['bookie_odds']}**)\n"
                            f"- **EV:** `+{bet['ev']}%`\n"
                            f"- **Stawka:** **{bet['stake_amount']} PLN** (`{bet['stake_pct']}%` budżetu)"
                        )
                        col_s, col_t = st.columns(2)
                        match_title = f"{home_team} vs {away_team}"
                        if col_s.button("📥 Zapisz w bazie", key=f"s_{i}"):
                            save_bet(match_title, bet['market'], bet['bookie_odds'], bet['stake_amount'])
                            st.toast("Zapisano!", icon="✅")
                        if col_t.button("📲 Wyślij na Telegram", key=f"t_{i}"):
                            sent = send_telegram_notification(match_title, bet['market'], bet['bookie_odds'], bet['ev'], bet['stake_amount'], bet['my_prob'])
                            st.toast("Wysłano!" if sent else "Błąd wysyłania!", icon="📲" if sent else "❌")
                else:
                    st.info("Brak opłacalnych typów (EV > +3%).")

with tab2:
    st.title("📊 Historia & Yield")
    stats = calculate_yield_stats()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Liczba Typów", stats["total_bets"])
    m2.metric("Win Rate", f"{stats['win_rate']}%")
    m3.metric("Zysk", f"{stats['total_profit']} PLN")
    m4.metric("Yield", f"{stats['yield']}%")

    st.markdown("---")
    raw_bets = get_all_bets()
    if raw_bets:
        pending = [b for b in raw_bets if b[6] == 'PENDING']
        if pending:
            for b in pending:
                b_id, b_date, match, market, odds, stake, status, profit = b
                st.write(f"⏳ **{match}** | `{market}` | Kurs: `{odds}` | Stawka: `{stake} PLN`")
                cw, cl, cv = st.columns(3)
                if cw.button("✅ Wygrana", key=f"w_{b_id}"):
                    update_bet_status(b_id, "WON", odds, stake)
                    st.rerun()
                if cl.button("❌ Przegrana", key=f"l_{b_id}"):
                    update_bet_status(b_id, "LOST", odds, stake)
                    st.rerun()
                if cv.button("🔄 Zwrot", key=f"v_{b_id}"):
                    update_bet_status(b_id, "VOID", odds, stake)
                    st.rerun()
                st.markdown("---")
        df = pd.DataFrame(raw_bets, columns=["ID", "Data", "Mecz", "Typ", "Kurs", "Stawka", "Status", "Zysk"])
        st.dataframe(df.drop(columns=["ID"]), use_container_width=True)
