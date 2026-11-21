"""
Daily NBA CSV Updater (Run on your home PC)
------------------------------------------
Fetches the latest season player game logs and today's matchups from NBA.com
using your home IP, then saves `nba_logs.csv` and `today_matchups.csv` so your
Streamlit Cloud app loads instantaneously with zero timeouts.

Requirements:
    pip install nba-api pandas

Usage:
    # 1. Update the two CSV files in the current folder:
    python update_nba_data.py

    # 2. Update the CSVs AND automatically push them to GitHub (if git is set up):
    python update_nba_data.py --push
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import LeagueGameLog, ScoreboardV2


def get_current_nba_season(reference_date: pd.Timestamp | None = None) -> str:
    ts = reference_date or pd.Timestamp.today()
    start_year = ts.year if ts.month >= 10 else ts.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def update_csvs(season: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {season} player game logs...")
    log = LeagueGameLog(
        season=season,
        season_type_all_star="Regular Season",
        player_or_team_abbreviation="P",
        sorter="DATE",
        direction="DESC",
        timeout=30,
    )
    logs_df = log.get_data_frames()[0]
    logs_path = out_dir / "nba_logs.csv"
    logs_df.to_csv(logs_path, index=False)
    print(f"Saved {len(logs_df):,} rows to {logs_path}")

    today_str = pd.Timestamp.today().strftime("%Y-%m-%d")
    print(f"Fetching matchups for {today_str}...")
    sb = ScoreboardV2(game_date=today_str, league_id="00", day_offset=0, timeout=30)
    line_score = sb.line_score.get_data_frame()

    matchups: list[dict[str, str]] = []
    if not line_score.empty:
        for _, group in line_score.groupby("GAME_ID", sort=False):
            abbrs = group["TEAM_ABBREVIATION"].tolist()
            if len(abbrs) == 2:
                matchups.append({"AWAY": abbrs[0], "HOME": abbrs[1]})

    matchups_path = out_dir / "today_matchups.csv"
    pd.DataFrame(matchups, columns=["AWAY", "HOME"]).to_csv(matchups_path, index=False)
    print(f"Saved {len(matchups)} matchups to {matchups_path}")


def git_push(repo_dir: Path) -> None:
    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    subprocess.run(["git", "add", "nba_logs.csv", "today_matchups.csv"], cwd=repo_dir, check=True)
    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_dir,
    )
    if status.returncode == 0:
        print("No new data changes to push.")
        return
    subprocess.run(
        ["git", "commit", "-m", f"Daily NBA data update ({timestamp})"],
        cwd=repo_dir,
        check=True,
    )
    subprocess.run(["git", "push"], cwd=repo_dir, check=True)
    print("Pushed updated CSVs to GitHub.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update NBA CSV files for Streamlit.")
    parser.add_argument("--season", default=get_current_nba_season(), help="e.g. 2026-27")
    parser.add_argument("--push", action="store_true", help="Commit & push CSVs to GitHub")
    args = parser.parse_args()

    repo_dir = Path(__file__).resolve().parent
    update_csvs(args.season, repo_dir)
    if args.push:
        git_push(repo_dir)


if __name__ == "__main__":
    main()