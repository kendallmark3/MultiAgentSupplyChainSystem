import sys
import pytest
from datetime import datetime, timedelta

sys.path.insert(0, "agents/reorder-agent")
from forecaster import assess_reorder, forecast_daily_usage, STATUS_CRITICAL, STATUS_LOW, STATUS_OK

def make_history(avg_daily, days=30):
    from datetime import datetime, timedelta
    import random
    random.seed(42)
    history = []
    today = datetime.today().date()
    start = today - timedelta(days=days)
    for i in range(days):
        date = start + timedelta(days=i)
        usage = max(0, round(avg_daily * random.uniform(0.8, 1.2)))
        history.append({"ds": date.isoformat(), "y": usage})
    return history

def make_data(name, stock, min_stock, lead_time, avg_daily):
    return {
        name: {
            "part_name": name,
            "stock_level": stock,
            "min_stock": min_stock,
            "lead_time_days": lead_time,
            "avg_daily_usage": avg_daily,
            "history": make_history(avg_daily),
        }
    }

# Test 1 — critical when stockout before delivery
def test_critical_status():
    data = make_data("Bearing", stock=4, min_stock=12, lead_time=4, avg_daily=2)
    r = assess_reorder("Bearing", current_stock=4, lead_time_days=4, usage_data=data)
    assert r["status"] == STATUS_CRITICAL
    assert r["should_order"] is True

# Test 2 — ok when stock is healthy
def test_ok_status():
    data = make_data("Cable Ties", stock=600, min_stock=150, lead_time=2, avg_daily=30)
    r = assess_reorder("Cable Ties", current_stock=600, lead_time_days=2, usage_data=data)
    assert r["status"] == STATUS_OK
    assert r["should_order"] is False

# Test 3 — low when below min_stock but delivery arrives in time
def test_low_status():
    data = make_data("Widget", stock=25, min_stock=80, lead_time=2, avg_daily=5)
    r = assess_reorder("Widget", current_stock=25, lead_time_days=2, usage_data=data)
    assert r["status"] == STATUS_LOW
    assert r["should_order"] is True

# Test 4 — all required keys are returned
def test_required_keys():
    data = make_data("Part", stock=50, min_stock=20, lead_time=3, avg_daily=5)
    r = assess_reorder("Part", current_stock=50, lead_time_days=3, usage_data=data)
    for key in ["status", "days_until_stockout", "reorder_point", "recommended_qty", "predicted_by", "should_order", "reason"]:
        assert key in r

# Test 5 — prophet is doing the prediction
def test_predicted_by_prophet():
    data = make_data("Sensor", stock=30, min_stock=10, lead_time=2, avg_daily=3)
    r = assess_reorder("Sensor", current_stock=30, lead_time_days=2, usage_data=data)
    assert r["predicted_by"] == "prophet"