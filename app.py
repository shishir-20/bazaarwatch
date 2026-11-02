"""BazaarWatch – community market price tracker (single-file Flask app)."""
import os
from datetime import datetime, timezone

import pandas as pd
from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy

# ---------- Config (edit these lists for your own town) ----------
ITEMS = ["Tomato", "Onion", "Potato", "Banana", "Carrot", "Coconut", "Rice", "Green Chilli"]
MARKETS = ["Central Market", "Town Bazaar", "Weekly Market", "Farmers' Stall"]

db_url = os.environ.get("DATABASE_URL", "sqlite:///bazaarwatch.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app = Flask(__name__)
app.config.update(SQLALCHEMY_DATABASE_URI=db_url,
                  SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only"))
db = SQLAlchemy(app)


# ---------- Database model ----------
class PriceReport(db.Model):
    __tablename__ = "price_reports"
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(50), nullable=False, index=True)
    market = db.Column(db.String(80), nullable=False)
    price_per_kg = db.Column(db.Float, nullable=False)
    reporter = db.Column(db.String(60))
    created_at = db.Column(db.DateTime, nullable=False, index=True,
                           default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


with app.app_context():
    db.create_all()          # tables are created automatically on first start


# ---------- Analytics (pandas) ----------
def load_df(item=None):
    q = PriceReport.query.filter_by(item=item) if item else PriceReport.query
    rows = q.order_by(PriceReport.created_at).all()
    return pd.DataFrame([{"item": r.item, "market": r.market, "price": r.price_per_kg,
                          "reporter": r.reporter or "Anonymous", "created_at": r.created_at}
                         for r in rows])


def flag_outliers(df, k=3.5):
    """Modified z-score (median/MAD). Needs >= 5 reports per item."""
    df = df.copy()
    df["suspicious"] = False
    for _, g in df.groupby("item"):
        if len(g) < 5:
            continue
        med = g["price"].median()
        mad = (g["price"] - med).abs().median()
        if mad == 0:
            continue
        df.loc[g.index, "suspicious"] = (0.6745 * (g["price"] - med) / mad).abs() > k
    return df


def summarise(df):
    if df.empty:
        return []
    df = flag_outliers(df)
    clean, now, out = df[~df["suspicious"]], df["created_at"].max(), []
    for item, g in clean.groupby("item"):
        last = g[g["created_at"] > now - pd.Timedelta(days=7)]["price"]
        prev = g[(g["created_at"] <= now - pd.Timedelta(days=7)) &
                 (g["created_at"] > now - pd.Timedelta(days=14))]["price"]
        change = round((last.mean() - prev.mean()) / prev.mean() * 100, 1) if len(last) and len(prev) else None
        out.append(dict(item=item, avg=float(g["price"].mean()), lo=float(g["price"].min()),
                        hi=float(g["price"].max()), n=len(g), change=change,
                        cheapest=g.groupby("market")["price"].mean().idxmin()))
    return sorted(out, key=lambda r: r["item"])


# ---------- Routes ----------
@app.route("/")
def index():
    selected = request.args.get("item", ITEMS[0])
    df = load_df()
    recent = []
    if not df.empty:
        recent = flag_outliers(df).sort_values("created_at", ascending=False).head(12).to_dict("records")
    return render_template_string(PAGE, items=ITEMS, markets=MARKETS, selected=selected,
                                  summary=summarise(df), recent=recent)


@app.route("/report", methods=["POST"])
def report():
    item = request.form.get("item", "").strip()
    market = request.form.get("market", "").strip()
    reporter = request.form.get("reporter", "").strip()[:60] or None
    try:
        price = float(request.form.get("price", ""))
    except ValueError:
        price = None
    if item not in ITEMS or market not in MARKETS:
        flash("Please choose an item and a market from the lists.", "error")
    elif price is None or not (0 < price <= 5000):
        flash("Enter a price per kg between 1 and 5000.", "error")
    else:
        db.session.add(PriceReport(item=item, market=market, price_per_kg=price, reporter=reporter))
        db.session.commit()
        flash(f"Thanks! Recorded {item} at ₹{price:g}/kg in {market}.", "ok")
    return redirect(url_for("index", item=item if item in ITEMS else None))


@app.route("/api/trend/<item>")
def trend(item):
    df = load_df(item)
    if df.empty:
        return jsonify(labels=[], values=[])
    df = flag_outliers(df)
    df = df[~df["suspicious"]]
    daily = df.groupby(df["created_at"].dt.date)["price"].mean().round(2)
    return jsonify(labels=[str(d) for d in daily.index], values=daily.tolist())


@app.route("/health")
def health():
    return {"status": "ok"}


# ---------- Frontend (HTML + CSS in one template) ----------
PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>BazaarWatch – community market prices</title>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#f1f4f1;--card:#fff;--ink:#14231c;--muted:#5d6b63;--line:#dbe3dd;--leaf:#1f7a4d;--leafd:#165c39;--chilli:#c8321f;--turm:#b97f00}
@media(prefers-color-scheme:dark){:root{--bg:#0f1713;--card:#17221c;--ink:#e8f0ea;--muted:#9fb0a5;--line:#2a3a31;--leaf:#49b27a;--leafd:#6cc796;--chilli:#ff7a66;--turm:#e3b341}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "IBM Plex Sans",system-ui,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
h1{font:700 2.2rem/1.1 "Bricolage Grotesque",sans-serif;margin:28px 0 6px;color:var(--leafd)}
h2{font:600 1.15rem/1.3 "Bricolage Grotesque",sans-serif;margin:0 0 14px}
.sub{color:var(--muted);margin:0 0 8px;max-width:60ch}
.grid{display:grid;grid-template-columns:320px 1fr;gap:20px;margin:20px 0 32px;align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px}
.wide{grid-column:2}.grid>.card:first-child{grid-row:span 4;position:sticky;top:16px}
label{display:block;font-weight:500;margin:12px 0 4px;font-size:.92rem}
input,select{width:100%;padding:10px 12px;font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:6px}
:focus-visible{outline:3px solid var(--turm);outline-offset:2px}
button{margin-top:18px;width:100%;padding:12px;font:600 1rem inherit;cursor:pointer;background:var(--leaf);color:#fff;border:0;border-radius:6px}
button:hover{background:var(--leafd)}
.muted{color:var(--muted);font-size:.88rem}.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.95rem}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--muted);font-size:.85rem}.num{text-align:right;font-variant-numeric:tabular-nums}.b{font-weight:600}
a{color:var(--leafd);font-weight:500}.up{color:var(--chilli)}.down{color:var(--leaf)}
.chart{position:relative;height:280px}
ul{list-style:none;margin:0;padding:0}
li{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:baseline;padding:9px 0;border-bottom:1px solid var(--line)}
li .muted{margin-left:auto}
.tag{font-size:.8rem;color:var(--turm);border:1px solid var(--turm);padding:0 8px;border-radius:99px}
.flash{margin:16px 0 0;padding:12px 16px;border-radius:8px;border:1px solid}
.flash.ok{border-color:var(--leaf)}.flash.error{border-color:var(--chilli)}
@media(max-width:820px){.grid{grid-template-columns:1fr}.wide,.grid>.card:first-child{grid-column:1;grid-row:auto;position:static}}
</style></head><body><div class="wrap">
<h1>BazaarWatch</h1>
<p class="sub">Daily vegetable and grocery prices, reported by people who shop at your local markets.</p>
{% with msgs = get_flashed_messages(with_categories=true) %}{% for c, m in msgs %}<div class="flash {{ c }}" role="status">{{ m }}</div>{% endfor %}{% endwith %}
<div class="grid">
 <section class="card"><h2>Report today's price</h2>
  <form method="post" action="{{ url_for('report') }}">
   <label for="item">Item</label>
   <select id="item" name="item">{% for i in items %}<option {{ 'selected' if i == selected }}>{{ i }}</option>{% endfor %}</select>
   <label for="market">Market</label>
   <select id="market" name="market">{% for m in markets %}<option>{{ m }}</option>{% endfor %}</select>
   <label for="price">Price per kg (₹)</label>
   <input id="price" name="price" type="number" step="0.5" min="1" max="5000" required>
   <label for="reporter">Your name <span class="muted">(optional)</span></label>
   <input id="reporter" name="reporter" maxlength="60">
   <button type="submit">Save price</button>
  </form></section>

 <section class="card wide"><h2>Price board</h2>
 {% if summary %}<div class="scroll"><table>
  <tr><th>Item</th><th class="num">Average ₹/kg</th><th class="num">Low – High</th><th class="num">7-day change</th><th>Cheapest market</th><th class="num">Reports</th></tr>
  {% for r in summary %}<tr>
   <td><a href="{{ url_for('index', item=r.item) }}">{{ r.item }}</a></td>
   <td class="num b">{{ '%.2f'|format(r.avg) }}</td><td class="num">{{ '%g'|format(r.lo) }} – {{ '%g'|format(r.hi) }}</td>
   <td class="num">{% if r.change is none %}<span class="muted">–</span>{% elif r.change > 0 %}<span class="up">▲ {{ r.change }}%</span>{% elif r.change < 0 %}<span class="down">▼ {{ -r.change }}%</span>{% else %}0%{% endif %}</td>
   <td>{{ r.cheapest }}</td><td class="num">{{ r.n }}</td></tr>{% endfor %}
 </table></div>{% else %}<p class="muted">No prices yet. Be the first to report one.</p>{% endif %}</section>

 <section class="card wide"><h2>Price trend: {{ selected }}</h2>
  <div class="chart"><canvas id="trend" role="img" aria-label="Daily average price chart"></canvas></div>
  <p id="none" class="muted" hidden>Not enough data for this item yet.</p></section>

 <section class="card wide"><h2>Latest reports</h2>
 {% if recent %}<ul>{% for r in recent %}<li>
  <span><b>{{ r.item }}</b> at {{ r.market }}</span><span class="num b">₹{{ '%g'|format(r.price) }}</span>
  {% if r.suspicious %}<span class="tag">looks unusual – excluded from averages</span>{% endif %}
  <span class="muted">{{ r.reporter }} · {{ r.created_at.strftime('%d %b, %H:%M') }}</span></li>{% endfor %}</ul>
 {% else %}<p class="muted">Nothing reported yet.</p>{% endif %}</section>
</div></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
const item = {{ selected|tojson }};
fetch('/api/trend/' + encodeURIComponent(item)).then(r => r.json()).then(d => {
  if (!d.values.length) { document.getElementById('none').hidden = false; return; }
  new Chart(document.getElementById('trend'), {type:'line',
    data:{labels:d.labels,datasets:[{data:d.values,borderColor:'#1F7A4D',backgroundColor:'rgba(31,122,77,.12)',fill:true,tension:.25}]},
    options:{maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{title:{display:true,text:'₹ per kg'}}}}});
});
</script></body></html>"""

if __name__ == "__main__":
    app.run(debug=True)