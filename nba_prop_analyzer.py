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

from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="NBA Prop Hit-Rate Analyzer",
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


def american_odds_to_implied_prob(odds: int) -> float:
    """Convert American odds (e.g. -110, +150) to implied breakeven probability."""
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    return 100.0 / (odds + 100.0)


def analyze_player_thresholds(
    logs_df: pd.DataFrame,
    pts_threshold: int,
    ast_threshold: int,
    reb_threshold: int,
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

    df["HIT_PTS"] = df["PTS"] >= pts_threshold
    df["HIT_AST"] = df["AST"] >= ast_threshold
    df["HIT_REB"] = df["REB"] >= reb_threshold

    summary = (
        df.groupby(["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"], as_index=False)
        .agg(
            GP=("GAME_ID", "count"),
            AVG_MIN=("MIN_NUM", "mean"),
            AVG_PTS=("PTS", "mean"),
            PTS_HITS=("HIT_PTS", "sum"),
            PTS_RATE=("HIT_PTS", "mean"),
            AVG_AST=("AST", "mean"),
            AST_HITS=("HIT_AST", "sum"),
            AST_RATE=("HIT_AST", "mean"),
            AVG_REB=("REB", "mean"),
            REB_HITS=("HIT_REB", "sum"),
            REB_RATE=("HIT_REB", "mean"),
        )
    )

    summary = summary[summary["GP"] >= min_games_played].copy()
    if summary.empty:
        return summary

    for stat in ("PTS", "AST", "REB"):
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
            "AVG_MIN": "Avg MIN",
            "AVG_PTS": "Avg PTS",
            "AVG_AST": "Avg AST",
            "AVG_REB": "Avg REB",
        }
    )

    for col in ("Avg MIN", "Avg PTS", "Avg AST", "Avg REB"):
        summary[col] = summary[col].round(1)

    return summary.reset_index(drop=True)


def render_stat_table(
    summary: pd.DataFrame,
    stat: str,
    breakeven_pct: float,
) -> None:
    """Render a clean, focused table for a single stat category."""
    avg_col = f"Avg {stat}"
    hits_col = f"{stat} Hits"
    pct_col = f"{stat} %"
    odds_col = f"{stat} Fair Odds"

    view = (
        summary[["Player", "Team", "GP", "Avg MIN", avg_col, hits_col, pct_col, odds_col]]
        .rename(
            columns={
                avg_col: "Avg",
                hits_col: "Hits",
                pct_col: "Hit Rate",
                odds_col: "Fair Odds",
            }
        )
        .sort_values(["Hit Rate", "Avg"], ascending=[False, False])
        .reset_index(drop=True)
    )
    view["Value"] = view["Hit Rate"].apply(
        lambda x: "Beats Line" if x >= breakeven_pct else "Below Line"
    )

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Player": st.column_config.TextColumn(width="medium"),
            "Team": st.column_config.TextColumn(width="small"),
            "GP": st.column_config.NumberColumn(width="small"),
            "Avg MIN": st.column_config.NumberColumn(format="%.1f", width="small"),
            "Avg": st.column_config.NumberColumn(format="%.1f", width="small"),
            "Hits": st.column_config.TextColumn(width="small"),
            "Hit Rate": st.column_config.ProgressColumn(
                format="%.1f%%",
                min_value=0,
                max_value=100,
                width="medium",
            ),
            "Fair Odds": st.column_config.TextColumn(width="small"),
            "Value": st.column_config.TextColumn(width="small"),
        },
    )


def render_overview_table(summary: pd.DataFrame) -> None:
    """Render a compact all-stats comparison table."""
    view = (
        summary[["Player", "Team", "GP", "Avg MIN", "PTS %", "AST %", "REB %"]]
        .sort_values(["PTS %", "AST %", "REB %"], ascending=False)
        .reset_index(drop=True)
    )
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Avg MIN": st.column_config.NumberColumn(format="%.1f"),
            "PTS %": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
            "AST %": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
            "REB %": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
        },
    )


def main() -> None:
    st.title("NBA Player Prop Hit-Rate Analyzer")

    with st.sidebar:
        st.header("Data Source")
        use_demo = st.toggle("Use offline sample data", value=False)
        if st.button("Reload CSV", use_container_width=True):
            st.cache_data.clear()

        st.divider()
        st.header("Prop Thresholds")
        pts_line = st.slider("Points (PTS >=", min_value=5, max_value=45, value=15, step=1)
        ast_line = st.slider("Assists (AST >=", min_value=1, max_value=15, value=4, step=1)
        reb_line = st.slider("Rebounds (REB >=", min_value=1, max_value=18, value=5, step=1)

        st.divider()
        st.header("Sample & Filters")
        use_full_season = st.checkbox("Use full season", value=False)
        last_n = (
            None
            if use_full_season
            else st.slider("Last N games", min_value=3, max_value=40, value=10, step=1)
        )
        min_minutes = st.slider("Minimum minutes played", min_value=0, max_value=30, value=10)
        book_odds = st.number_input(
            "Sportsbook odds to beat (American)",
            value=-110,
            step=5,
            help="Marks players whose hit rate beats this line's breakeven probability.",
        )

    if use_demo:
        logs_df = build_demo_logs()
        st.caption("Showing built-in sample data.")
    elif LOGS_CSV.exists():
        logs_df = load_csv_logs(str(LOGS_CSV), LOGS_CSV.stat().st_mtime)
        latest_game = pd.to_datetime(logs_df["GAME_DATE"]).max().strftime("%Y-%m-%d")
        st.caption(f"Loaded `nba_logs.csv` ({len(logs_df):,} player-games, latest game: {latest_game}).")
    else:
        st.warning(
            "`nba_logs.csv` was not found in this repo. Run `python update_nba_data.py` "
            "on your PC and upload `nba_logs.csv`, or toggle **Use offline sample data**."
        )
        return

    all_teams = sorted(logs_df["TEAM_ABBREVIATION"].dropna().unique().tolist())

    col1, col2 = st.columns([2, 1])
    with col1:
        matchup_options = ["All Teams"]
        matchup_map: dict[str, list[str]] = {}
        if not use_demo and MATCHUPS_CSV.exists():
            for away, home in load_csv_matchups(
                str(MATCHUPS_CSV), MATCHUPS_CSV.stat().st_mtime
            ):
                label = f"{away} @ {home}"
                matchup_options.append(label)
                matchup_map[label] = [away, home]

        selected_matchup = st.selectbox("Matchup", options=matchup_options)
        default_teams = matchup_map.get(selected_matchup, [])
        selected_teams = st.multiselect(
            "Or filter specific teams",
            options=all_teams,
            default=default_teams,
        )

    with col2:
        player_query = st.text_input("Search player name", placeholder="e.g. Brunson")
        breakeven_pct = american_odds_to_implied_prob(int(book_odds)) * 100.0
        st.metric(
            label=f"Breakeven Hit Rate at {int(book_odds):+d}",
            value=f"{breakeven_pct:.1f}%",
        )

    result = analyze_player_thresholds(
        logs_df,
        pts_threshold=pts_line,
        ast_threshold=ast_line,
        reb_threshold=reb_line,
        teams=selected_teams or None,
        player_query=player_query,
        last_n_games=last_n,
        min_minutes=min_minutes,
    )

    if result.empty:
        st.info("No players matched your current filters. Try lowering minimum minutes or widening teams.")
        return

    tab_pts, tab_ast, tab_reb, tab_all = st.tabs(
        [
            f"Points ({pts_line}+)",
            f"Assists ({ast_line}+)",
            f"Rebounds ({reb_line}+)",
            "All Stats (Compact)",
        ]
    )

    with tab_pts:
        render_stat_table(result, "PTS", breakeven_pct)
    with tab_ast:
        render_stat_table(result, "AST", breakeven_pct)
    with tab_reb:
        render_stat_table(result, "REB", breakeven_pct)
    with tab_all:
        render_overview_table(result)


if __name__ == "__main__":
    main()
