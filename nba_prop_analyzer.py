"""
NBA Player Prop Hit-Rate Dashboard (Streamlit — CSV-First)
-----------------------------------------------------------
Loads pre-fetched `nba_logs.csv` (and optional `today_matchups.csv`) directly
from the repository so the dashboard boots in <1 second on Streamlit Community
Cloud without hitting stats.nba.com from cloud IPs.

Requirements:
    pip install streamlit pandas

Run locally:
    python -m streamlit run nba_prop_app.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="NBA Prop Analyzer",
    page_icon="🏀",
    layout="wide",
)

LOGS_CSV = Path("nba_logs.csv")
MATCHUPS_CSV = Path("today_matchups.csv")


@st.cache_data(ttl=300)
def load_csv_logs(path_str: str, mtime: float) -> pd.DataFrame:
    """Load player game logs from CSV; `mtime` busts cache when CSV updates."""
    _ = mtime
    return pd.read_csv(path_str, parse_dates=["GAME_DATE"])


@st.cache_data(ttl=300)
def load_csv_matchups(path_str: str, mtime: float) -> list[tuple[str, str]]:
    """Load today's (away, home) matchups from CSV if present."""
    _ = mtime
    df = pd.read_csv(path_str)
    if df.empty or not {"AWAY", "HOME"}.issubset(df.columns):
        return []
    return list(zip(df["AWAY"].astype(str), df["HOME"].astype(str)))


@st.cache_data(ttl=1800)
def fetch_nba_injuries() -> dict[str, str]:
    """
    Fetch current NBA injury statuses from ESPN's public endpoint.
    Returns {lowercase_player_name: '❌ Out' / '⚠️ Day-To-Day' / ...}.
    """
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}

    injuries: dict[str, str] = {}
    for team_entry in data.get("injuries", []):
        for item in team_entry.get("injuries", []):
            name = (
                item.get("athlete", {}).get("displayName", "")
                .strip()
                .lower()
            )
            status = str(item.get("status", "")).strip()
            if not name or not status:
                continue
            status_lower = status.lower()
            if "out" in status_lower:
                badge = f"❌ {status}"
            elif any(k in status_lower for k in ("day-to-day", "questionable", "doubtful")):
                badge = f"⚠️ {status}"
            else:
                badge = f"🤕 {status}"
            injuries[name] = badge
    return injuries


def get_player_streak_badges(
    logs_df: pd.DataFrame,
    min_streak: int = 3,
    min_minutes: int = 10,
) -> dict[str, str]:
    """Return {lowercase_player_name: '🔥 PTS, AST'} for active streaks."""
    streaks_df = compute_heater_streaks(
        logs_df,
        stat_filter="All",
        min_streak=min_streak,
        min_minutes=min_minutes,
    )
    if streaks_df.empty:
        return {}

    badges: dict[str, str] = {}
    for player_name, group in streaks_df.groupby("Player", sort=False):
        stats_list = group["Stat"].tolist()
        badges[str(player_name).strip().lower()] = "🔥 " + ", ".join(stats_list)
    return badges


def tag_player_badges(
    df: pd.DataFrame,
    streak_badges: dict[str, str],
    injuries: dict[str, str],
) -> pd.DataFrame:
    """Append streak (🔥) and injury (❌/⚠️) badges to matching player names."""
    if df.empty or "Player" not in df.columns or (not streak_badges and not injuries):
        return df

    def format_name(name: str) -> str:
        key = str(name).strip().lower()
        parts = [str(name)]
        if key in streak_badges:
            parts.append(f"({streak_badges[key]})")
        if key in injuries:
            parts.append(f"({injuries[key]})")
        return " ".join(parts)

    out = df.copy()
    out["Player"] = out["Player"].apply(format_name)
    return out


def build_demo_logs() -> pd.DataFrame:
    """Sample dataset for instant offline testing."""
    rows = [
        *[
            {
                "PLAYER_ID": 1628973,
                "PLAYER_NAME": "Jalen Brunson",
                "TEAM_ABBREVIATION": "NYK",
                "GAME_ID": f"00226000{i:02d}",
                "GAME_DATE": pd.Timestamp("2026-11-13") - pd.Timedelta(days=i * 2),
                "MIN": 35,
                "PTS": pts,
                "AST": ast,
                "REB": reb,
            }
            for i, (pts, ast, reb) in enumerate(
                [
                    (28, 7, 3),
                    (24, 6, 4),
                    (31, 8, 2),
                    (19, 5, 3),
                    (26, 9, 4),
                    (14, 4, 2),
                    (33, 6, 5),
                    (22, 7, 3),
                    (27, 5, 3),
                    (9, 3, 2),
                ]
            )
        ],
        *[
            {
                "PLAYER_ID": 1628369,
                "PLAYER_NAME": "Jayson Tatum",
                "TEAM_ABBREVIATION": "BOS",
                "GAME_ID": f"00226001{i:02d}",
                "GAME_DATE": pd.Timestamp("2026-11-13") - pd.Timedelta(days=i * 2),
                "MIN": 36,
                "PTS": pts,
                "AST": ast,
                "REB": reb,
            }
            for i, (pts, ast, reb) in enumerate(
                [
                    (30, 5, 9),
                    (27, 4, 8),
                    (22, 6, 10),
                    (34, 5, 7),
                    (18, 3, 6),
                    (29, 7, 9),
                    (25, 4, 11),
                    (31, 6, 8),
                    (16, 2, 5),
                    (28, 5, 8),
                ]
            )
        ],
    ]
    return pd.DataFrame(rows)


def hit_rate_to_american_odds(hit_rate: float) -> str:
    """Convert a 0.0-1.0 hit probability into fair American odds."""
    if hit_rate <= 0.0:
        return "N/A"
    if hit_rate >= 1.0:
        return "-inf"
    if hit_rate >= 0.5:
        return f"{-round((hit_rate / (1.0 - hit_rate)) * 100)}"
    return f"+{round(((1.0 - hit_rate) / hit_rate) * 100)}"


def analyze_player_thresholds(
    logs_df: pd.DataFrame,
    pts_threshold: int,
    ast_threshold: int,
    reb_threshold: int,
    fg3m_threshold: int = 2,
    teams: list[str] | None = None,
    player_query: str = "",
    last_n_games: int | None = 10,
    min_minutes: int = 10,
    min_games_played: int = 3,
) -> pd.DataFrame:
    """Vectorized hit-rate and fair-odds computation."""
    df = logs_df.copy()

    if df["MIN"].dtype == object:
        df["MIN_NUM"] = (
            df["MIN"]
            .astype(str)
            .str.split(":")
            .str[0]
            .pipe(pd.to_numeric, errors="coerce")
            .fillna(0.0)
        )
    else:
        df["MIN_NUM"] = pd.to_numeric(df["MIN"], errors="coerce").fillna(0.0)

    df = df[df["MIN_NUM"] >= min_minutes]

    if teams:
        team_set = {t.upper() for t in teams}
        df = df[df["TEAM_ABBREVIATION"].str.upper().isin(team_set)]

    if player_query.strip():
        df = df[
            df["PLAYER_NAME"].str.contains(player_query.strip(), case=False, na=False)
        ]

    if df.empty:
        return pd.DataFrame()

    df = df.sort_values(["PLAYER_ID", "GAME_DATE"], ascending=[True, False])
    if last_n_games is not None and last_n_games > 0:
        df = df.groupby("PLAYER_ID", group_keys=False).head(last_n_games)

    if "FG3M" not in df.columns:
        df["FG3M"] = 0

    df["HIT_PTS"] = df["PTS"] >= pts_threshold
    df["HIT_AST"] = df["AST"] >= ast_threshold
    df["HIT_REB"] = df["REB"] >= reb_threshold
    df["HIT_3PM"] = df["FG3M"] >= fg3m_threshold

    summary = (
        df.groupby(["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"], as_index=False)
        .agg(
            GP=("GAME_ID", "count"),
            AVG_PTS=("PTS", "mean"),
            PTS_HITS=("HIT_PTS", "sum"),
            PTS_RATE=("HIT_PTS", "mean"),
            AVG_AST=("AST", "mean"),
            AST_HITS=("HIT_AST", "sum"),
            AST_RATE=("HIT_AST", "mean"),
            AVG_REB=("REB", "mean"),
            REB_HITS=("HIT_REB", "sum"),
            REB_RATE=("HIT_REB", "mean"),
            AVG_3PM=("FG3M", "mean"),
            FG3M_HITS=("HIT_3PM", "sum"),
            FG3M_RATE=("HIT_3PM", "mean"),
        )
    )
    summary = summary.rename(columns={"FG3M_HITS": "3PM_HITS", "FG3M_RATE": "3PM_RATE"})

    summary = summary[summary["GP"] >= min_games_played].copy()
    if summary.empty:
        return summary

    for stat in ("PTS", "AST", "REB", "3PM"):
        summary[f"{stat} %"] = (summary[f"{stat}_RATE"] * 100).round(1)
        summary[f"{stat} Hits"] = (
            summary[f"{stat}_HITS"].astype(int).astype(str)
            + "/"
            + summary["GP"].astype(int).astype(str)
        )
        summary[f"{stat} Fair Odds"] = summary[f"{stat}_RATE"].map(
            hit_rate_to_american_odds
        )

    summary = summary.rename(
        columns={
            "PLAYER_NAME": "Player",
            "TEAM_ABBREVIATION": "Team",
            "AVG_PTS": "Avg PTS",
            "AVG_AST": "Avg AST",
            "AVG_REB": "Avg REB",
            "AVG_3PM": "Avg 3PM",
        }
    )

    for col in ("Avg PTS", "Avg AST", "Avg REB", "Avg 3PM"):
        summary[col] = summary[col].round(1)

    return summary.reset_index(drop=True)


@st.dialog("Player Profile")
def show_player_profile(
    player_name: str,
    logs_df: pd.DataFrame,
    injuries: dict[str, str],
    streak_badges: dict[str, str],
) -> None:
    """Display season averages, injury status, streaks, and last 5 games."""
    player_logs = logs_df[
        logs_df["PLAYER_NAME"].str.strip().str.lower() == player_name.strip().lower()
    ].copy()

    if player_logs.empty:
        st.warning(f"No game logs found for {player_name}.")
        return

    player_logs["GAME_DATE"] = pd.to_datetime(player_logs["GAME_DATE"])
    player_logs = player_logs.sort_values("GAME_DATE", ascending=False)
    team = str(player_logs.iloc[0]["TEAM_ABBREVIATION"])

    st.subheader(f"{player_name} ({team})")

    key = player_name.strip().lower()
    if key in injuries:
        st.warning(f"Injury Status: {injuries[key]}")
    else:
        st.success("Injury Status: Healthy / Not on injury report")

    if key in streak_badges:
        st.info(f"Active Streak: {streak_badges[key]}")

    if player_logs["MIN"].dtype == object:
        player_logs["MIN_NUM"] = (
            player_logs["MIN"]
            .astype(str)
            .str.split(":")
            .str[0]
            .pipe(pd.to_numeric, errors="coerce")
            .fillna(0.0)
        )
    else:
        player_logs["MIN_NUM"] = pd.to_numeric(
            player_logs["MIN"], errors="coerce"
        ).fillna(0.0)

    played = player_logs[player_logs["MIN_NUM"] > 0]
    avg_src = played if not played.empty else player_logs

    if "FG3M" not in avg_src.columns:
        avg_src = avg_src.copy()
        avg_src["FG3M"] = 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Season PTS", f"{avg_src['PTS'].mean():.1f}")
    c2.metric("Season AST", f"{avg_src['AST'].mean():.1f}")
    c3.metric("Season REB", f"{avg_src['REB'].mean():.1f}")
    c4.metric("Season 3PM", f"{avg_src['FG3M'].mean():.1f}")

    st.markdown("**Last 5 Games**")
    last5 = player_logs.head(5).copy()
    if "FG3M" not in last5.columns:
        last5["FG3M"] = 0
    matchup_col = (
        last5["MATCHUP"].astype(str)
        if "MATCHUP" in last5.columns
        else last5["TEAM_ABBREVIATION"].astype(str)
    )
    last5_view = pd.DataFrame(
        {
            "Date": last5["GAME_DATE"].dt.strftime("%m-%d-%Y"),
            "Matchup": matchup_col,
            "MIN": last5["MIN_NUM"].map(lambda x: f"{int(round(x))}"),
            "PTS": last5["PTS"].map(lambda x: f"{int(x)}"),
            "AST": last5["AST"].map(lambda x: f"{int(x)}"),
            "REB": last5["REB"].map(lambda x: f"{int(x)}"),
            "3PM": last5["FG3M"].map(lambda x: f"{int(x)}"),
        }
    )
    st.dataframe(last5_view, width="stretch", hide_index=True)


def handle_row_selection(
    event: object,
    display_df: pd.DataFrame,
    table_key: str,
    logs_df: pd.DataFrame,
    injuries: dict[str, str],
    streak_badges: dict[str, str],
) -> None:
    """Open the player profile dialog when a table row is newly tapped."""
    rows = event.selection.rows if event and hasattr(event, "selection") else []
    prev_rows = st.session_state.get(f"prev_{table_key}", [])
    st.session_state[f"prev_{table_key}"] = list(rows)
    if rows and list(rows) != prev_rows:
        idx = rows[0]
        if 0 <= idx < len(display_df):
            raw_name = str(display_df.iloc[idx]["Player"])
            clean_name = raw_name.split(" (")[0].strip()
            show_player_profile(clean_name, logs_df, injuries, streak_badges)


def render_stat_table(
    summary: pd.DataFrame,
    stat: str,
    logs_df: pd.DataFrame,
    injuries: dict[str, str],
    streak_badges: dict[str, str],
) -> None:
    """Render a clean 5-column table with row-tap player profile support."""
    avg_col = f"Avg {stat}"
    hits_col = f"{stat} Hits"
    pct_col = f"{stat} %"
    odds_col = f"{stat} Fair Odds"

    sorted_df = summary.sort_values([pct_col, avg_col], ascending=[False, False]).reset_index(drop=True)
    view = pd.DataFrame(
        {
            "Player": sorted_df["Player"],
            "Team": sorted_df["Team"],
            "Avg": sorted_df[avg_col].round(1),
            "Hit Rate": sorted_df[pct_col].map(lambda x: f"{x:.1f}%") + " (" + sorted_df[hits_col] + ")",
            "Fair Odds": sorted_df[odds_col],
        }
    )

    table_key = f"table_{stat.lower()}"
    event = st.dataframe(
        view,
        key=table_key,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Player": st.column_config.TextColumn(width="medium"),
            "Team": st.column_config.TextColumn(width="small"),
            "Avg": st.column_config.NumberColumn(format="%.1f", width="small"),
            "Hit Rate": st.column_config.TextColumn(width="small"),
            "Fair Odds": st.column_config.TextColumn(width="small"),
        },
    )
    handle_row_selection(event, view, table_key, logs_df, injuries, streak_badges)


def compute_heater_streaks(
    logs_df: pd.DataFrame,
    stat_filter: str = "All",
    min_streak: int = 3,
    min_heat_pct: float = 15.0,
    teams: list[str] | None = None,
    player_query: str = "",
    min_minutes: int = 10,
    min_games_played: int = 4,
) -> pd.DataFrame:
    """
    Find players on an active streak of outperforming their own season average
    in consecutive most-recent games.
    """
    df = logs_df.copy()

    if df["MIN"].dtype == object:
        df["MIN_NUM"] = (
            df["MIN"]
            .astype(str)
            .str.split(":")
            .str[0]
            .pipe(pd.to_numeric, errors="coerce")
            .fillna(0.0)
        )
    else:
        df["MIN_NUM"] = pd.to_numeric(df["MIN"], errors="coerce").fillna(0.0)

    df = df[df["MIN_NUM"] >= min_minutes]

    if teams:
        team_set = {t.upper() for t in teams}
        df = df[df["TEAM_ABBREVIATION"].str.upper().isin(team_set)]

    if player_query.strip():
        df = df[
            df["PLAYER_NAME"].str.contains(player_query.strip(), case=False, na=False)
        ]

    if df.empty:
        return pd.DataFrame()

    if "FG3M" not in df.columns:
        df["FG3M"] = 0

    df = df.sort_values(["PLAYER_ID", "GAME_DATE"], ascending=[True, False])
    stat_col_map = {"PTS": "PTS", "AST": "AST", "REB": "REB", "3PM": "FG3M"}
    stats = ["PTS", "AST", "REB", "3PM"] if stat_filter == "All" else [stat_filter]

    hot_rows: list[dict[str, object]] = []
    for (_, player_name, team_abbr), group in df.groupby(
        ["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"], sort=False
    ):
        if len(group) < min_games_played:
            continue

        for stat in stats:
            col_name = stat_col_map[stat]
            vals = group[col_name].astype(float).tolist()
            season_avg = sum(vals) / len(vals)
            if season_avg <= 0:
                continue
            streak = 0
            for v in vals:
                if v > season_avg:
                    streak += 1
                else:
                    break

            if streak >= min_streak:
                streak_vals = vals[:streak]
                streak_avg = sum(streak_vals) / len(streak_vals)
                heat_pct = ((streak_avg - season_avg) / season_avg) * 100.0
                if heat_pct < min_heat_pct:
                    continue
                hot_rows.append(
                    {
                        "Player": player_name,
                        "Team": team_abbr,
                        "Stat": stat,
                        "Season Avg": round(season_avg, 1),
                        "Streak": int(streak),
                        "Streak Avg": round(streak_avg, 1),
                        "Heat %": round(heat_pct, 1),
                        "Recent Games": ", ".join(str(int(v)) for v in reversed(streak_vals)),
                        "_streak_num": streak,
                        "_heat_num": heat_pct,
                    }
                )

    if not hot_rows:
        return pd.DataFrame()

    out = (
        pd.DataFrame(hot_rows)
        .sort_values(["_streak_num", "_heat_num"], ascending=[False, False])
        .drop(columns=["_streak_num", "_heat_num"])
        .reset_index(drop=True)
    )
    return out


def render_overview_table(
    summary: pd.DataFrame,
    logs_df: pd.DataFrame,
    injuries: dict[str, str],
    streak_badges: dict[str, str],
) -> None:
    """Render a compact all-stats comparison table with row-tap profile support."""
    view = (
        summary[["Player", "Team", "PTS %", "AST %", "REB %", "3PM %"]]
        .sort_values(["PTS %", "AST %", "REB %", "3PM %"], ascending=False)
        .reset_index(drop=True)
    )
    table_key = "table_all"
    event = st.dataframe(
        view,
        key=table_key,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "PTS %": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
            "AST %": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
            "REB %": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
            "3PM %": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
        },
    )
    handle_row_selection(event, view, table_key, logs_df, injuries, streak_badges)


def main() -> None:
    st.title("NBA Stats Prop")

    if not LOGS_CSV.exists():
        st.warning("`nba_logs.csv` was not found in this repo. Run `python update_nba_data.py` and upload `nba_logs.csv`.")
        return

    logs_df = load_csv_logs(str(LOGS_CSV), LOGS_CSV.stat().st_mtime)
    latest_game = pd.to_datetime(logs_df["GAME_DATE"]).max().strftime("%m-%d-%Y")
    st.caption(f"{len(logs_df):,} games played, latest game: {latest_game}")

    all_teams = sorted(logs_df["TEAM_ABBREVIATION"].dropna().unique().tolist())

    matchup_options = ["All Teams"]
    matchup_map: dict[str, list[str]] = {}
    today_teams: list[str] = []
    if MATCHUPS_CSV.exists():
        matchups_list = load_csv_matchups(
            str(MATCHUPS_CSV), MATCHUPS_CSV.stat().st_mtime
        )
        if matchups_list:
            today_teams = sorted(
                {abbr for pair in matchups_list for abbr in pair}
            )
            for away, home in matchups_list:
                label = f"{away} @ {home}"
                matchup_options.append(label)
                matchup_map[label] = [away, home]

    st.session_state.setdefault("playing_today_only", False)
    playing_today_active = bool(st.session_state["playing_today_only"]) and bool(today_teams)

    c1, c2, c3 = st.columns(3)
    with c1:
        selected_matchup = st.selectbox(
            "Matchup",
            options=matchup_options,
            disabled=playing_today_active,
        )
    with c2:
        default_teams = (
            today_teams
            if playing_today_active
            else matchup_map.get(selected_matchup, [])
        )
        selected_teams = st.multiselect(
            "Filter specific teams",
            options=all_teams,
            default=default_teams,
            disabled=playing_today_active,
        )
    with c3:
        player_query = st.text_input("Search player name", placeholder="e.g. Brunson")

    t1, t2, t3, t4 = st.columns([1, 1, 1, 2])
    with t1:
        playing_today_only = st.toggle(
            "Playing today",
            disabled=not bool(today_teams),
            key="playing_today_only",
            help="Show all players on teams playing today.",
        )
    with t2:
        hide_injured = st.toggle(
            "Remove injured players",
            value=False,
            help="Hide players currently listed on the NBA injury report.",
        )
    with t3:
        use_full_season = st.toggle("Full Season", value=True)
    with t4:
        min_minutes = st.slider("Minutes Played", min_value=0, max_value=30, value=15)
        last_n = (
            None
            if use_full_season
            else st.slider("Last N games", min_value=3, max_value=40, value=10, step=1)
        )

    active_teams = today_teams if playing_today_only else (selected_teams or None)

    st.session_state.setdefault("pts_line", 15)
    st.session_state.setdefault("ast_line", 4)
    st.session_state.setdefault("reb_line", 5)
    st.session_state.setdefault("fg3m_line", 2)
    pts_line = int(st.session_state["pts_line"])
    ast_line = int(st.session_state["ast_line"])
    reb_line = int(st.session_state["reb_line"])
    fg3m_line = int(st.session_state["fg3m_line"])

    injuries = fetch_nba_injuries()
    active_min_streak = int(st.session_state.get("heater_min_streak", 3))
    streak_badges = get_player_streak_badges(
        logs_df, min_streak=active_min_streak, min_minutes=min_minutes
    )

    result = analyze_player_thresholds(
        logs_df,
        pts_threshold=pts_line,
        ast_threshold=ast_line,
        reb_threshold=reb_line,
        fg3m_threshold=fg3m_line,
        teams=active_teams,
        player_query=player_query,
        last_n_games=last_n,
        min_minutes=min_minutes,
    )
    if hide_injured and injuries and not result.empty:
        result = result[
            ~result["Player"].astype(str).str.strip().str.lower().isin(injuries)
        ].reset_index(drop=True)
    result = tag_player_badges(result, streak_badges, injuries)

    if result.empty:
        st.info("No players matched your current filters. Try lowering minimum minutes or widening teams.")
        return

    tab_pts, tab_ast, tab_reb, tab_3pm, tab_all, tab_heater = st.tabs(
        [
            f"Points ({pts_line}+)",
            f"Assists ({ast_line}+)",
            f"Rebounds ({reb_line}+)",
            f"3-Pointers ({fg3m_line}+)",
            "All Stats (Compact)",
            "🔥 Heater Meter",
        ]
    )

    with tab_pts:
        st.slider("Points (PTS >=)", min_value=5, max_value=45, step=1, key="pts_line")
        render_stat_table(result, "PTS", logs_df, injuries, streak_badges)
    with tab_ast:
        st.slider("Assists (AST >=)", min_value=1, max_value=15, step=1, key="ast_line")
        render_stat_table(result, "AST", logs_df, injuries, streak_badges)
    with tab_reb:
        st.slider("Rebounds (REB >=)", min_value=1, max_value=18, step=1, key="reb_line")
        render_stat_table(result, "REB", logs_df, injuries, streak_badges)
    with tab_3pm:
        st.slider("3-Pointers (3PM >=)", min_value=1, max_value=10, step=1, key="fg3m_line")
        render_stat_table(result, "3PM", logs_df, injuries, streak_badges)
    with tab_all:
        render_overview_table(result, logs_df, injuries, streak_badges)
    with tab_heater:
        heater_stat = st.radio(
            "Stat",
            options=["All", "PTS", "AST", "REB", "3PM"],
            horizontal=True,
        )
        h_col1, h_col2 = st.columns(2)
        with h_col1:
            min_streak = st.slider(
                "Minimum streak",
                min_value=2,
                max_value=10,
                value=3,
                step=1,
                key="heater_min_streak",
            )
        with h_col2:
            min_heat_pct = st.slider(
                "Min Heat Margin (%)",
                min_value=0,
                max_value=60,
                value=15,
                step=5,
            )

        heater_df = compute_heater_streaks(
            logs_df,
            stat_filter=heater_stat,
            min_streak=min_streak,
            min_heat_pct=float(min_heat_pct),
            teams=active_teams,
            player_query=player_query,
            min_minutes=min_minutes,
        )
        if hide_injured and injuries and not heater_df.empty:
            heater_df = heater_df[
                ~heater_df["Player"].astype(str).str.strip().str.lower().isin(injuries)
            ].reset_index(drop=True)
        heater_df = tag_player_badges(heater_df, streak_badges, injuries)
        if heater_df.empty:
            st.info(
                f"No players matched {min_streak}+ games and {min_heat_pct}%+ heat."
            )
        else:
            heater_event = st.dataframe(
                heater_df,
                key="table_heater",
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    "Player": st.column_config.TextColumn(width="medium"),
                    "Team": st.column_config.TextColumn(width="small"),
                    "Stat": st.column_config.TextColumn(width="small"),
                    "Season Avg": st.column_config.NumberColumn(format="%.1f", width="small"),
                    "Streak": st.column_config.NumberColumn(format="%d games", width="small"),
                    "Streak Avg": st.column_config.NumberColumn(format="%.1f", width="small"),
                    "Heat %": st.column_config.NumberColumn(format="+%.1f%%", width="small"),
                    "Recent Games": st.column_config.TextColumn(width="medium"),
                },
            )
            handle_row_selection(
                heater_event, heater_df, "table_heater", logs_df, injuries, streak_badges
            )


if __name__ == "__main__":
    main()