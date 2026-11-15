# NBA Player Prop Hit-Rate Analyzer

An interactive [Streamlit](https://streamlit.io/) dashboard that pulls NBA player game logs via [`nba_api`](https://github.com/swar/nba_api) and uses vectorized `pandas` operations to calculate historical hit rates, fair implied American odds, and breakeven value edges for customizable **Points**, **Assists**, and **Rebounds** thresholds.

## Features

* **Real-Time Prop Sliders:** Dynamically adjust Points, Assists, Rebounds, sample window (`Last N` games or full season), and minimum minutes played.

* **Clean Per-Stat Views:** Dedicated tabs for **Points**, **Assists**, **Rebounds**, and **All Stats (Compact)** with visual hit-rate progress bars.

* **Today's Matchup Filter:** Automatically loads today's NBA slate via `ScoreboardV2` alongside team multi-select and player name search.

* **Fair Odds & Value Check:** Converts each player's historical hit rate into zero-vig fair American odds and flags lines that beat your target sportsbook odds.

* **Efficient Caching:** Fetches the full season's player logs in a single `LeagueGameLog` request and caches it in memory so slider updates run instantaneously.

* **Offline Demo Mode:** Includes a built-in sample dataset toggle for testing without network access.

## Project Structure

```
nba-prop-analyzer/
├── nba_prop_app.py      # Main Streamlit dashboard
├── requirements.txt     # Python dependencies (streamlit, nba-api, pandas)
└── README.md            # Project documentation

```

## Quick Start

1. **Install dependencies:**

   ```
   pip install -r requirements.txt
   
   ```

2. **Run the dashboard locally:**

   ```
   python -m streamlit run nba_prop_app.py
   
   ```

3. **Access from your phone on the same Wi-Fi (optional):**

   ```
   python -m streamlit run nba_prop_app.py --server.address 0.0.0.0
   
   ```

   Open the **Network URL** printed in your terminal from your phone's browser.

## Deployment

This app can be deployed directly to [Streamlit Community Cloud](https://share.streamlit.io/) by connecting this repository and setting `nba_prop_app.py` as the main file path.