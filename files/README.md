# Indian Grocery Sales — Synthetic Time Series Dataset

**This is a synthetic (simulated) dataset, not real retail data.** It was generated
to mimic realistic patterns found in Indian grocery sales — trends, weekly cycles,
seasonality, festivals, regional preferences, and promotions — so it's suitable for
practicing/training time-series and demand-forecasting ML models. Festival dates are
approximate/representative (lunar-calendar festivals shift each year) and are meant
for simulation purposes, not historical record.

## Files

### `sales_data.csv` (913,000 rows) — main fact table
| Column | Description |
|---|---|
| `Date` | YYYY-MM-DD, daily, 2021-01-01 to 2025-12-31 (5 years) |
| `Store_ID` | Links to `stores.csv` |
| `Product_ID` | Links to `products.csv` |
| `Units_Sold` | Units sold that day (integer, can be 0 — occasional simulated stockouts) |
| `Price_INR` | Selling price per unit that day (includes inflation drift + any discount) |
| `Revenue_INR` | `Units_Sold x Price_INR` |
| `Is_Festival` | 1 if that exact date is a major festival |
| `Festival_Name` | Name of festival if `Is_Festival`=1, else blank |
| `Is_Promotion` | 1 if a promotional discount was active that day |
| `Discount_Percent` | % discount applied if on promotion, else 0 |

### `products.csv` (100 rows) — product master
`Product_ID, Product_Name, Category, Pack_Size, Base_Price_2021_INR`

14 categories: Rice & Grains, Atta & Flour, Pulses & Lentils, Cooking Oil & Ghee,
Spices & Masala, Sugar & Sweeteners, Tea/Coffee & Beverages, Dairy, Bakery,
Snacks & Namkeen, Dry Fruits & Nuts, Sauces & Pickles, Frozen & Ready-to-Eat,
Breakfast Cereals.

### `stores.csv` (5 rows) — store master
`Store_ID, Store_Name, City, Region` — one store each in North (Delhi), West (Mumbai),
South (Bangalore), East (Kolkata), Central (Bhopal).

## Patterns built into the data
- **Trend**: 2–10% annual growth, varying by product (packaged/snack categories grow faster than staples)
- **Weekly seasonality**: Fri–Sun higher than weekdays
- **Monthly seasonality**: salary-day rush (1st–5th of month)
- **Climate seasonality**: cold beverages peak Mar–Jun, hot beverages/tea peak Nov–Feb, light monsoon dip (Jul–Aug)
- **Festivals**: Diwali, Holi, Eid, Pongal, Raksha Bandhan, Ganesh Chaturthi, Dussehra, Christmas, New Year, Republic/Independence Day — with category-specific intensity (e.g., dry fruits/ghee/spices spike harder than dairy) and regional intensity (e.g., Pongal hits the South store hardest, Ganesh Chaturthi hits Mumbai hardest)
- **Regional preference**: e.g., Atta sells much more in the North, rice more in South/East, coffee more in South, tea more in North/East
- **Promotions**: ~8% of product-days carry a random 10–30% discount with a corresponding demand lift
- **Noise**: random day-to-day variation + ~0.5% simulated stockout days (0 units)

## Quick start (Python)
```python
import pandas as pd

sales = pd.read_csv("sales_data.csv", parse_dates=["Date"])
products = pd.read_csv("products.csv")
stores = pd.read_csv("stores.csv")

df = sales.merge(products, on="Product_ID").merge(stores, on="Store_ID")

# Useful calendar features for ML (not pre-included, derive as needed):
df["DayOfWeek"] = df["Date"].dt.dayofweek
df["Month"] = df["Date"].dt.month
df["Year"] = df["Date"].dt.year
df["IsWeekend"] = df["DayOfWeek"].isin([5, 6]).astype(int)

# Example: single product+store time series for forecasting
ts = df[(df.Product_ID == "P001") & (df.Store_ID == "ST01")].set_index("Date")["Units_Sold"]
```

## Suggested next steps for modeling
- Add lag features (`Units_Sold` shifted 1/7/14/30 days) and rolling means
- One-hot or embed `Category`, `Region`
- Treat `Is_Festival`/`Is_Promotion` as known future regressors (you'd know promo calendars in advance in a real deployment)
- Consider per-product or per-category models vs. one global model with `Product_ID`/`Store_ID` as categorical features (e.g., for LightGBM/XGBoost) or as embeddings (for a neural model)
