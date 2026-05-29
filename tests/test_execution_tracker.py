"""
ExecutionTracker Tests
Run with: pytest tests/test_execution_tracker.py -v
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "agents"))

from execution_tracker import ExecutionTracker, WEGAStage, StageStatus


def test_start_session():
    tracker = ExecutionTracker()
    tracker.start_session("count cardboard boxes and assess reorder", session_id="test001")
    assert tracker.session_id == "test001"
    assert tracker.intent == "count cardboard boxes and assess reorder"
    assert tracker.started_at is not None
    assert tracker.stages[WEGAStage.PLANNER].status == StageStatus.RUNNING


def test_all_stages_complete():
    tracker = ExecutionTracker()
    tracker.start_session("count boxes and reorder if critical")
    tracker.complete_planner("cardboard boxes")
    tracker.start_builder()
    tracker.complete_builder(17, "cardboard boxes", "high", "Storage Systems Ltd", "Warehouse Shelf Boxes")
    tracker.complete_validator("high", 86.3, True)
    tracker.complete_evaluator("CRITICAL", 1.4, 51, True, "Stockout in 1.4 days - order NOW")
    tracker.complete_reporter("$58.50", "FedEx Express", "3 business days", True, True, True)
    assert tracker.stages[WEGAStage.PLANNER].status   == StageStatus.PASSED
    assert tracker.stages[WEGAStage.BUILDER].status   == StageStatus.PASSED
    assert tracker.stages[WEGAStage.VALIDATOR].status == StageStatus.PASSED
    assert tracker.stages[WEGAStage.EVALUATOR].status == StageStatus.PASSED
    assert tracker.stages[WEGAStage.REPORTER].status  == StageStatus.PASSED
    assert tracker.overall_status == "passed"


def test_failed_stage():
    tracker = ExecutionTracker()
    tracker.start_session("count boxes")
    tracker.complete_planner("boxes")
    tracker.start_builder()
    tracker.fail_stage(WEGAStage.BUILDER, "Vision agent timeout")
    assert tracker.stages[WEGAStage.BUILDER].status == StageStatus.FAILED
    assert tracker.stages[WEGAStage.BUILDER].error  == "Vision agent timeout"
    assert tracker.overall_status == "failed"


def test_evidence_stored():
    tracker = ExecutionTracker()
    tracker.start_session("count boxes")
    tracker.complete_planner("cardboard boxes", expected_count=20)
    tracker.start_builder()
    tracker.complete_builder(17, "cardboard boxes", "high", "Storage Systems Ltd", "Warehouse Shelf Boxes")
    evidence = tracker.stages[WEGAStage.BUILDER].evidence
    assert evidence["item_count"] == 17
    assert evidence["confidence"] == "high"
    assert evidence["supplier"]   == "Storage Systems Ltd"


def test_to_dict_has_all_stages():
    tracker = ExecutionTracker()
    tracker.start_session("count boxes")
    result = tracker.to_dict()
    assert "Planner"   in result["stages"]
    assert "Builder"   in result["stages"]
    assert "Validator" in result["stages"]
    assert "Evaluator" in result["stages"]
    assert "Reporter"  in result["stages"]
    assert result["overall_status"] == "running"


def test_duration_calculated():
    tracker = ExecutionTracker()
    tracker.start_session("count boxes")
    tracker.complete_planner("boxes")
    tracker.start_builder()
    time.sleep(0.05)
    tracker.complete_builder(10, "boxes", "high", "Supplier X", "Part Y")
    duration = tracker.stages[WEGAStage.BUILDER].duration_ms
    assert duration is not None
    assert duration >= 40