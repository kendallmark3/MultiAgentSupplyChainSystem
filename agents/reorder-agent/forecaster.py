import json
import logging
from pathlib import Path
import pandas as pd
from prophet import Prophet

logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

USAGE_DATA_PATH = Path(__file__).parent / "data" / "usage_history.json"

STATUS_CRITICAL = "CRITICAL"  # stockout before delivery arrives
STATUS_LOW      = "LOW"       # below min_stock but delivery arrives in time  
STATUS_OK       = "OK"        # stock is healthy

def load_usage_data():
    with open(USAGE_DATA_PATH) as f:
        return json.load(f)

def forecast_daily_usage(history):
    """
    Give Prophet the 30 days of history.
    It learns the trend + weekly pattern.
    Returns: predicted units used per day going forward.
    """
    df = pd.DataFrame(history)
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = df["y"].astype(float)

    model = Prophet(
        weekly_seasonality=True,   # learns weekday vs weekend pattern
        daily_seasonality=False,
        yearly_seasonality=False,
    )
    model.fit(df)

    # Predict 7 days into the future
    future = model.make_future_dataframe(periods=7, freq="D")
    forecast = model.predict(future)

    # Average of just the future predictions
    predicted_daily = max(0.1, forecast.tail(7)["yhat"].mean())
    return round(predicted_daily, 2)

def find_closest_part(part_name: str, usage_data: dict) -> str:
    """
    Semantic match using Vertex AI text-embedding-005.
    Falls back to difflib if Vertex AI is unavailable.
    """
    keys = list(usage_data.keys())
    if part_name in keys:
        return part_name
    try:
        import sys as _s
        from pathlib import Path as _P
        _matcher_path = str(_P(__file__).resolve().parent)
        if _matcher_path not in _s.path:
            _s.path.insert(0, _matcher_path)
        from embedding_matcher import find_best_match
        best, score = find_best_match(part_name, keys)
        print(f"Semantic match: {part_name} -> {best} (score: {score:.3f})")
        return best
    except Exception as e:
        print(f"Semantic match failed: {e} - using difflib fallback")
        import difflib
        matches = difflib.get_close_matches(part_name, keys, n=1, cutoff=0.3)
        if matches:
            return matches[0]
        return max(keys, key=lambda k: difflib.SequenceMatcher(None, part_name.lower(), k.lower()).ratio())


def assess_reorder(part_name, current_stock, lead_time_days, usage_data=None):
    """
    The core decision:
    - How many days until we run out?
    - Does the delivery arrive before that?
    - Should we order?
    """
    if usage_data is None:
        usage_data = load_usage_data()

    part_name = find_closest_part(part_name, usage_data)

    item = usage_data[part_name]
    min_stock = item["min_stock"]

    # Ask Prophet: how many units per day?
    predicted_daily = forecast_daily_usage(item["history"])

    # How many days until shelf is empty?
    days_until_stockout = round(current_stock / predicted_daily, 1)

    # Minimum units needed to cover delivery wait
    reorder_point = round(predicted_daily * lead_time_days)

    # Order enough for lead time + 30 more days
    recommended_qty = round(predicted_daily * (lead_time_days + 30))

    # The decision
    if days_until_stockout <= lead_time_days:
        status = STATUS_CRITICAL
        should_order = True
        reason = f"Stockout in {days_until_stockout} days but delivery takes {lead_time_days} days — order NOW"
    elif current_stock < min_stock:
        status = STATUS_LOW
        should_order = True
        reason = f"Stock {current_stock} below minimum {min_stock} — order soon"
    else:
        status = STATUS_OK
        should_order = False
        reason = f"Stock healthy — {days_until_stockout} days of supply remaining"

    return {
        "status": status,
        "days_until_stockout": days_until_stockout,
        "reorder_point": reorder_point,
        "recommended_qty": recommended_qty,
        "predicted_daily_usage": predicted_daily,
        "predicted_by": "prophet",
        "should_order": should_order,
        "reason": reason,
        "current_stock": current_stock,
        "min_stock": min_stock,
        "lead_time_days": lead_time_days,
    }

if __name__ == "__main__":
    usage_data = load_usage_data()

    tests = [
        ("Bearing 6204",             8,   4),  # CRITICAL
        ("Cardboard Shipping Box Large", 30, 2),  # LOW
        ("Cable Tie Pack 200mm",     600, 2),  # OK
        ("Zip Lock Bag 30x40cm",     20,  2),  # CRITICAL
    ]

    print("\n" + "="*60)
    for part, stock, lead in tests:
        r = assess_reorder(part, stock, lead, usage_data)
        icon = "🔴" if r["status"] == STATUS_CRITICAL else "🟡" if r["status"] == STATUS_LOW else "🟢"
        print(f"{icon} {part}")
        print(f"   Stock: {stock} | Lead time: {lead}d | Prophet predicts: {r['predicted_daily_usage']}/day")
        print(f"   Status: {r['status']} — {r['reason']}")
        if r["should_order"]:
            print(f"   → ORDER {r['recommended_qty']} units")
        print()