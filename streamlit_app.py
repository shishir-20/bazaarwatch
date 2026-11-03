"""BazaarWatch - community market price tracker (Streamlit + SQLAlchemy + pandas)."""
import os
import random
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import (Column, DateTime, Float, Integer, MetaData, String, Table,
                        create_engine, insert, select)

# ---------- Settings (edit these lists for your own town) ----------
ITEMS = ["Tomato", "Onion", "Potato", "Banana", "Carrot", "Coconut", "Rice", "Green Chilli"]
MARKETS = ["Central Market", "Town Bazaar", "Weekly Market", "Farmers' Stall"]

st.set_page_config(page_title="BazaarWatch", page_icon="🥬", layout="wide")


# ---------- Database ----------
def database_url() -> str:
    """Cloud PostgreSQL if DATABASE_URL is set (Streamlit secrets), else a local SQLite file."""
    url = None
    try:
        url = st.secrets["DATABASE_URL"]
    except Exception:
        url = os.environ.get("DATABASE_URL")
    if not url:
        return "sqlite:///bazaarwatch.db"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


metadata = MetaData()
reports = Table(
    "price_reports", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("item", String(50), nullable=False, index=True),
    Column("market", String(80), nullable=False),
    Column("price_per_kg", Float, nullable=False),
    Column("reporter", String(60)),
    Column("created_at", DateTime, nullable=False, index=True),
)


@st.cache_resource
def get_engine():
    engine = create_engine(database_url(), pool_pre_ping=True)
    metadata.create_all(engine)          # table is created automatically on first run
    return engine


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def add_report(item, market, price, reporter):
    with get_engine().begin() as conn:
        conn.execute(insert(reports).values(item=item, market=market, price_per_kg=price,
                                            reporter=reporter or None, created_at=now_utc()))


def load_reports() -> pd.DataFrame:
    with get_engine().connect() as conn:
        df = pd.read_sql(select(reports).order_by(reports.c.created_at), conn)
    df = df.rename(columns={"price_per_kg": "price"})
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["reporter"] = df["reporter"].fillna("Anonymous")
    return df


def add_demo_data():
    random.seed(7)
    base = {"Tomato": 40, "Onion": 35, "Potato": 30, "Banana": 55, "Carrot": 60,
            "Coconut": 45, "Rice": 52, "Green Chilli": 80}
    rows, now = [], now_utc()
    for day in range(21):
        for item in ITEMS:
            for _ in range(random.randint(1, 3)):
                price = round(base[item] * random.uniform(0.92, 1.08), 1)
                if random.random() < 0.02:           # a few deliberate typos
                    price *= 10
                rows.append(dict(item=item, market=random.choice(MARKETS), price_per_kg=price,
                                 reporter=random.choice(["Asha", "Ravi", "Meena", None]),
                                 created_at=now - timedelta(days=21 - day, hours=random.randint(0, 10))))
    with get_engine().begin() as conn:
        conn.execute(insert(reports), rows)


# ---------- Analytics (pandas) ----------
def flag_outliers(df: pd.DataFrame, k: float = 3.5) -> pd.DataFrame:
    """Modified z-score from median and MAD. Needs at least 5 reports per item."""
    df = df.copy()
    df["unusual"] = False
    for _, g in df.groupby("item"):
        if len(g) < 5:
            continue
        med = g["price"].median()
        mad = (g["price"] - med).abs().median()
        if mad == 0:
            continue
        df.loc[g.index, "unusual"] = (0.6745 * (g["price"] - med) / mad).abs() > k
    return df


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    clean, now, out = df[~df["unusual"]], df["created_at"].max(), []
    for item, g in clean.groupby("item"):
        last = g[g["created_at"] > now - pd.Timedelta(days=7)]["price"]
        prev = g[(g["created_at"] <= now - pd.Timedelta(days=7)) &
                 (g["created_at"] > now - pd.Timedelta(days=14))]["price"]
        change = round((last.mean() - prev.mean()) / prev.mean() * 100, 1) if len(last) and len(prev) else None
        out.append({"Item": item, "Average (Rs/kg)": round(g["price"].mean(), 2),
                    "Lowest": g["price"].min(), "Highest": g["price"].max(),
                    "7-day change (%)": change,
                    "Cheapest market": g.groupby("market")["price"].mean().idxmin(),
                    "Reports": len(g)})
    return pd.DataFrame(out)


# ---------- Page ----------
st.title("🥬 BazaarWatch")
st.caption("Daily vegetable and grocery prices, reported by people who shop at your local markets.")

# Sidebar: report form
with st.sidebar:
    st.header("Report today's price")
    with st.form("report_form", clear_on_submit=True):
        item = st.selectbox("Item", ITEMS)
        market = st.selectbox("Market", MARKETS)
        price = st.number_input("Price per kg (Rs)", min_value=1.0, max_value=5000.0, value=40.0, step=0.5)
        reporter = st.text_input("Your name (optional)", max_chars=60)
        submitted = st.form_submit_button("Save price", width="stretch")
    if submitted:
        add_report(item, market, float(price), reporter.strip())
        st.success(f"Saved: {item} at Rs {price:g}/kg in {market}")
    with st.expander("Testing tools"):
        if st.button("Add demo data"):
            add_demo_data()
            st.success("Demo data added")

df = load_reports()
if df.empty:
    st.info("No prices yet. Add the first one using the form on the left, or use *Testing tools > Add demo data*.")
    st.stop()

df = flag_outliers(df)
c1, c2, c3 = st.columns(3)
c1.metric("Reports", len(df))
c2.metric("Items tracked", df["item"].nunique())
c3.metric("Flagged as unusual", int(df["unusual"].sum()))

tab1, tab2, tab3 = st.tabs(["Price board", "Trend", "Latest reports"])

with tab1:
    st.dataframe(summarise(df), hide_index=True, width="stretch")
    st.caption("Averages exclude reports flagged as unusual (median/MAD outlier rule).")

with tab2:
    chosen = st.selectbox("Item", ITEMS, key="trend_item")
    g = df[(df["item"] == chosen) & (~df["unusual"])]
    if g.empty:
        st.info("Not enough data for this item yet.")
    else:
        daily = g.groupby(g["created_at"].dt.date)["price"].mean().round(2)
        st.line_chart(daily, y_label="Average Rs per kg", x_label="Date")

with tab3:
    latest = df.sort_values("created_at", ascending=False).head(25).copy()
    latest["created_at"] = latest["created_at"].dt.strftime("%d %b, %H:%M")
    latest["Status"] = latest["unusual"].map({True: "Unusual - excluded", False: "OK"})
    st.dataframe(latest[["item", "market", "price", "reporter", "created_at", "Status"]]
                 .rename(columns={"item": "Item", "market": "Market", "price": "Price (Rs/kg)",
                                  "reporter": "Reporter", "created_at": "Time"}),
                 hide_index=True, width="stretch")
