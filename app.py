"""
app.py — Legacy Streamlit Backend for SmartRetail AI
Maintained for backend administrative tasks.
Primary interface is dashboard.html served by serve_dashboard.py
"""

import streamlit as st
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

# ─── Page Config ───────────────────────────────────────────────
st.set_page_config(page_title="SmartRetail AI", page_icon="🛒", layout="wide")

# ─── Custom CSS ────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
.stApp {background: linear-gradient(135deg, #0f0c29, #1a1a3e, #24243e);}
[data-testid="stSidebar"] {background: rgba(255,255,255,0.05); backdrop-filter: blur(20px);}
.metric-card {background: rgba(255,255,255,0.08); backdrop-filter: blur(16px); border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; padding: 20px; margin: 8px 0;}
.alert-card {background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 12px; padding: 16px; margin: 8px 0;}
h1, h2, h3 {font-family: 'Inter', sans-serif !important;}
</style>""", unsafe_allow_html=True)

# ─── Festival Detection ───────────────────────────────────────
FESTIVALS = {
    "Pongal": [(1, 14), (1, 17)], "Thai Poosam": [(1, 25), (1, 25)],
    "Chithirai": [(4, 14), (4, 28)], "Aadi Perukku": [(7, 18), (7, 18)],
    "Vinayagar Chaturthi": [(9, 7), (9, 7)], "Navaratri": [(10, 3), (10, 12)],
    "Karthigai Deepam": [(11, 25), (11, 25)], "Diwali": [(10, 24), (11, 3)],
    "Christmas": [(12, 24), (12, 25)], "New Year": [(12, 31), (1, 2)],
    "Republic Day": [(1, 26), (1, 26)], "Holi": [(3, 14), (3, 14)],
    "Independence Day": [(8, 15), (8, 15)], "Dussehra": [(10, 12), (10, 12)],
}

def is_festival_period(date, window=5):
    for name, ((sm, sd), (em, ed)) in FESTIVALS.items():
        try:
            start = datetime(date.year, sm, sd) - timedelta(days=window)
            end = datetime(date.year, em, ed) + timedelta(days=window)
            if start <= date <= end:
                return True, name, 1.5
        except ValueError:
            continue
    return False, None, 1.0

# ─── Data Loading ─────────────────────────────────────────────
def load_demo_data():
    dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    products = ["Rice", "Wheat", "Sugar", "Tea", "Oil", "Biscuits", "Soap", "Shampoo"]
    records = []
    for d in dates:
        for p in products:
            base = {"Rice": 20, "Wheat": 16, "Sugar": 14, "Tea": 11, "Oil": 8, "Biscuits": 30, "Soap": 9, "Shampoo": 6}
            qty = base.get(p, 10) + np.random.randint(-3, 5)
            if d.weekday() >= 5: qty = int(qty * 1.15)
            is_fest, _, mult = is_festival_period(d)
            if is_fest: qty = int(qty * mult)
            records.append({"Date": d, "Product": p, "Sales_Qty": max(1, qty), "Stock_Qty": np.random.randint(50, 300)})
    return pd.DataFrame(records)

# ─── ML Training ──────────────────────────────────────────────
def train_ai_model(df):
    models = {}
    for product in df["Product"].unique():
        pdata = df[df["Product"] == product].copy()
        pdata["Year"] = pdata["Date"].dt.year
        pdata["Month"] = pdata["Date"].dt.month
        pdata["Day"] = pdata["Date"].dt.day
        pdata["DayOfWeek"] = pdata["Date"].dt.dayofweek
        X = pdata[["Year", "Month", "Day", "DayOfWeek"]]
        y = pdata["Sales_Qty"]
        if len(X) >= 10:
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X, y)
            models[product] = model
    return models

def predict_sales(models, product, date):
    if product not in models:
        return None
    features = np.array([[date.year, date.month, date.day, date.weekday()]])
    prediction = max(0, float(models[product].predict(features)[0]))
    is_fest, fest_name, mult = is_festival_period(date)
    if is_fest:
        prediction *= mult
    if date.weekday() >= 5:
        prediction *= 1.15
    return round(prediction, 1)

def get_stock_alerts(models, inventory, days=7):
    alerts = []
    today = datetime.now()
    for product, stock in inventory.items():
        total_demand = 0
        for i in range(days):
            pred = predict_sales(models, product, today + timedelta(days=i))
            if pred: total_demand += pred
        if stock < total_demand:
            alerts.append({"product": product, "stock": stock, "demand": round(total_demand), "shortage": round(total_demand - stock)})
    return alerts

# ─── Session State ────────────────────────────────────────────
PRICES = {"Rice": 50, "Wheat": 45, "Sugar": 42, "Tea": 200, "Oil": 155, "Biscuits": 30, "Soap": 35, "Shampoo": 120}

if "df" not in st.session_state:
    st.session_state.df = None
if "inventory" not in st.session_state:
    st.session_state.inventory = {}
if "billing_cart" not in st.session_state:
    st.session_state.billing_cart = []
if "models" not in st.session_state:
    st.session_state.models = {}

# ─── Sidebar ──────────────────────────────────────────────────
st.sidebar.markdown("## 🛒 SmartRetail AI")
st.sidebar.markdown("---")
page = st.sidebar.radio("Navigation", ["🏠 Dashboard", "🧮 Billing Calculator", "📦 Inventory Manager", "🤖 AI Predictions"])

uploaded = st.sidebar.file_uploader("📂 Upload CSV File", type=["csv"])
if uploaded:
    try:
        st.session_state.df = pd.read_csv(uploaded, parse_dates=["Date"])
        st.sidebar.success("✅ File uploaded!")
    except Exception as e:
        st.sidebar.error(f"❌ Error: {e}")
elif st.session_state.df is None:
    st.session_state.df = load_demo_data()
    st.sidebar.info("📊 Using Demo Dataset")

df = st.session_state.df

# Initialize inventory
if not st.session_state.inventory:
    for p in df["Product"].unique():
        latest = df[df["Product"] == p]["Stock_Qty"].iloc[-1] if "Stock_Qty" in df.columns else 150
        st.session_state.inventory[p] = int(latest)

# Train models
if not st.session_state.models:
    st.session_state.models = train_ai_model(df)

# ─── Dashboard ────────────────────────────────────────────────
if page == "🏠 Dashboard":
    st.markdown("# 🏠 Dashboard")
    alerts = get_stock_alerts(st.session_state.models, st.session_state.inventory)
    c1, c2, c3 = st.columns(3)
    total_rev = (df["Sales_Qty"] * df["Product"].map(PRICES)).sum()
    c1.metric("💰 Total Revenue", f"₹{total_rev:,.0f}")
    c2.metric("📦 Products", len(st.session_state.inventory))
    c3.metric("🚨 Low Stock", len(alerts))

    if alerts:
        st.markdown("### ⚠️ Stock Alerts")
        for a in alerts:
            st.markdown(f'<div class="alert-card">🚨 <b>{a["product"]}</b> — Stock: {a["stock"]} | Predicted Demand: {a["demand"]} | Shortage: {a["shortage"]}</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        daily = df.groupby("Date")["Sales_Qty"].sum().reset_index()
        fig = px.line(daily, x="Date", y="Sales_Qty", title="Sales Trend")
        fig.update_traces(line_color="#8b5cf6", line_width=3)
        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        stock_df = pd.DataFrame([{"Product": k, "Stock": v} for k, v in st.session_state.inventory.items()])
        fig2 = px.bar(stock_df, x="Product", y="Stock", title="Current Stock", color="Stock", color_continuous_scale=["#ef4444", "#f59e0b", "#10b981"])
        fig2.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)

# ─── Billing ──────────────────────────────────────────────────
elif page == "🧮 Billing Calculator":
    st.markdown("# 🧮 Billing Calculator")
    col1, col2 = st.columns(2)
    with col1:
        product = st.selectbox("Select Product", list(st.session_state.inventory.keys()))
        qty = st.number_input("Quantity", min_value=1, value=1)
        stock = st.session_state.inventory.get(product, 0)
        st.info(f"Available: {stock} units | Price: ₹{PRICES.get(product, 0)}/unit")
        if st.button("💰 Generate Bill"):
            if qty > stock:
                st.error("❌ Insufficient stock!")
            else:
                old = stock
                st.session_state.inventory[product] -= qty
                total = qty * PRICES.get(product, 0)
                st.success(f"✅ Bill: {product} × {qty} = ₹{total:,.0f}")
                st.info(f"Stock: {old} → {st.session_state.inventory[product]}")
                st.balloons()
    with col2:
        st.markdown("### 💰 Price List")
        for p, price in PRICES.items():
            st.markdown(f"**{p}**: ₹{price}/unit")

# ─── Inventory ────────────────────────────────────────────────
elif page == "📦 Inventory Manager":
    st.markdown("# 📦 Inventory Manager")
    inv_data = []
    for p, s in st.session_state.inventory.items():
        status = "🔴 Low" if s < 50 else "🟠 Warning" if s < 100 else "🔵 OK"
        inv_data.append({"Product": p, "Stock": s, "Price": f"₹{PRICES.get(p, 0)}", "Status": status})
    st.dataframe(pd.DataFrame(inv_data), use_container_width=True)
    st.markdown("### ➕ Restock")
    rp = st.selectbox("Product to restock", list(st.session_state.inventory.keys()), key="restock_p")
    rq = st.number_input("Quantity to add", min_value=1, value=50, key="restock_q")
    if st.button("⚠️ Restock Now"):
        st.session_state.inventory[rp] += rq
        st.success(f"✅ Restocked {rp}: +{rq} units (now {st.session_state.inventory[rp]})")

# ─── AI Predictions ───────────────────────────────────────────
elif page == "🤖 AI Predictions":
    st.markdown("# 🤖 AI Predictions")
    col1, col2 = st.columns(2)
    with col1:
        pred_product = st.selectbox("Product", list(st.session_state.models.keys()))
        pred_date = st.date_input("Prediction Date", datetime.now() + timedelta(days=1))
        if st.button("🔮 Predict Sales"):
            pred = predict_sales(st.session_state.models, pred_product, datetime.combine(pred_date, datetime.min.time()))
            if pred:
                is_fest, fest, _ = is_festival_period(datetime.combine(pred_date, datetime.min.time()))
                st.markdown(f'<div class="metric-card"><h2>{pred} units</h2><p>Predicted for {pred_product} on {pred_date}</p></div>', unsafe_allow_html=True)
                if is_fest:
                    st.warning(f"🎊 Festival Boost Active: {fest} (1.5x multiplier applied)")
    with col2:
        st.markdown("### 📊 7-Day Forecast")
        if pred_product:
            forecast = []
            for i in range(7):
                d = datetime.now() + timedelta(days=i+1)
                p = predict_sales(st.session_state.models, pred_product, d)
                is_fest, fest, _ = is_festival_period(d)
                forecast.append({"Date": d.strftime("%Y-%m-%d"), "Day": d.strftime("%A"), "Predicted": p or 0, "Festival": fest or "-"})
            fdf = pd.DataFrame(forecast)
            st.dataframe(fdf, use_container_width=True)
            fig = px.line(fdf, x="Date", y="Predicted", title=f"7-Day Forecast: {pred_product}", markers=True)
            fig.update_traces(line_color="#8b5cf6")
            fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
