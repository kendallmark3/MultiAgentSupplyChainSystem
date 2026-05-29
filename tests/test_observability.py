import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.observability import (
    AgentTrace,
    start_workflow,
    end_workflow,
    get_workflow_trace,
    get_all_traces
)

def test_successful_agent_trace():
    workflow_id = start_workflow()
    trace = AgentTrace("VisionAgent", workflow_id)
    trace.input_summary = "warehouse_shelf_image.jpg"
    time.sleep(0.1)  # simulate work
    trace.complete("Detected 12 boxes, generated query: 'cardboard shipping box large'")
    
    results = get_workflow_trace(workflow_id)
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert results[0]["agent"] == "VisionAgent"
    print(f"✅ test_successful_agent_trace PASSED | duration={results[0]['duration_ms']}ms")

def test_failed_agent_trace():
    workflow_id = start_workflow()
    trace = AgentTrace("SupplierAgent", workflow_id)
    trace.input_summary = "cardboard shipping box large"
    time.sleep(0.05)
    trace.fail("AlloyDB connection timeout after 30s")

    results = get_workflow_trace(workflow_id)
    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert results[0]["error"] is not None
    print(f"✅ test_failed_agent_trace PASSED | error={results[0]['error']}")

def test_full_workflow_trace():
    workflow_id = start_workflow()

    # Vision Agent
    vision = AgentTrace("VisionAgent", workflow_id)
    vision.input_summary = "shelf_image.png"
    time.sleep(0.05)
    vision.complete("Counted 8 items, query generated")

    # Supplier Agent
    supplier = AgentTrace("SupplierAgent", workflow_id)
    supplier.input_summary = "corrugated box medium warehouse"
    time.sleep(0.05)
    supplier.complete("Found match: 'Product Shipping Boxes' from Acme Packaging")

    end_workflow(workflow_id, "completed")

    results = get_workflow_trace(workflow_id)
    assert len(results) == 2
    assert results[0]["agent"] == "VisionAgent"
    assert results[1]["agent"] == "SupplierAgent"
    print(f"✅ test_full_workflow_trace PASSED | {len(results)} agents traced")

if __name__ == "__main__":
    print("\n🔍 Running Observability Tests...\n")
    test_successful_agent_trace()
    test_failed_agent_trace()
    test_full_workflow_trace()
    print("\n✅ All observability tests passed!\n")
