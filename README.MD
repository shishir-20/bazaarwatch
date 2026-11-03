# BazaarWatch - Community Market Price Tracker

A cloud-hosted web app where residents report prices of vegetables and groceries at local markets.
Reports are stored in a PostgreSQL database; the app removes unusual entries with a robust rule
(median/MAD modified z-score) and shows a price board, a trend chart and the latest reports.

**Problem:** prices differ between local markets and change weekly, with no shared source.
**Stack:** Python - Streamlit (web UI) - pandas (analytics) - SQLAlchemy - PostgreSQL (Neon) - Streamlit Community Cloud.

## Files
| File | Purpose |
|---|---|
| `streamlit_app.py` | Whole app: web page, database access, analytics |
| `requirements.txt` | Python dependencies |
| `.streamlit/config.toml` | Theme colour |
| `.streamlit/secrets.toml.example` | Shows the secret needed in the cloud (`DATABASE_URL`) |
| `README.md` | Documentation |

## Run locally
```bash
python -m venv venv
venv\Scripts\activate          # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```
Without `DATABASE_URL` it uses a local SQLite file (`bazaarwatch.db`).

## Deploy to the cloud (free)
1. **Database:** create a free PostgreSQL project at neon.tech and copy the connection string.
2. **GitHub:** push these files to a public repository.
3. **Streamlit Community Cloud** (share.streamlit.io): sign in with GitHub -> *Create app* ->
   pick the repo, branch `main`, main file `streamlit_app.py`.
4. *Advanced settings -> Secrets*: paste `DATABASE_URL = "postgresql://...your Neon string..."`.
5. Deploy. The table is created automatically on first run, and you get a public `streamlit.app` link.
   Free apps go to sleep when idle and wake on the next visit.

## Database
Table `price_reports(id, item, market, price_per_kg, reporter, created_at)`.
Streamlit Cloud's disk is temporary, which is why a separate cloud database (Neon) is used.

## Data-science component
For items with at least 5 reports: score = 0.6745 x (price - median) / MAD. |score| > 3.5 is flagged
"unusual" (for example 450 typed instead of 45) and excluded from averages and charts. Also computed:
lowest/highest, cheapest market, 7-day vs previous 7-day change.

## Customise
Edit `ITEMS` and `MARKETS` at the top of `streamlit_app.py`.

## Limitations / future work
No login (spam possible); free tier sleeps. Future: ARIMA price forecasts, user accounts, market map.
