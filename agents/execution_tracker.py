"""
ExecutionTracker — WEGA Stage Evidence Layer
Tracks 5 pipeline stages: Planner, Builder, Validator, Evaluator, Reporter
Every agent decision is logged with timestamp, status, and evidence.
This turns the supply chain system into an auditable, intent-driven runtime.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StageStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    PASSED    = "passed"
    FAILED    = "failed"
    SKIPPED   = "skipped"


class WEGAStage(str, Enum):
    PLANNER   = "Planner"
    BUILDER   = "Builder"
    VALIDATOR = "Validator"
    EVALUATOR = "Evaluator"
    REPORTER  = "Reporter"


@dataclass
class StageEvidence:
    stage:       WEGAStage
    status:      StageStatus      = StageStatus.PENDING
    started_at:  Optional[float]  = None
    completed_at: Optional[float] = None
    agent:       Optional[str]    = None
    input_summary:  Optional[str] = None
    output_summary: Optional[str] = None
    evidence:    dict             = field(default_factory=dict)
    error:       Optional[str]    = None

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at and self.completed_at:
            return round((self.completed_at - self.started_at) * 1000)
        return None

    def to_dict(self) -> dict:
        return {
            "stage":          self.stage.value,
            "status":         self.status.value,
            "started_at":     self.started_at,
            "completed_at":   self.completed_at,
            "duration_ms":    self.duration_ms,
            "agent":          self.agent,
            "input_summary":  self.input_summary,
            "output_summary": self.output_summary,
            "evidence":       self.evidence,
            "error":          self.error,
        }


class ExecutionTracker:
    def __init__(self):
        self.session_id:  Optional[str] = None
        self.intent:      Optional[str] = None
        self.started_at:  Optional[float] = None
        self.completed_at: Optional[float] = None
        self.stages: dict[WEGAStage, StageEvidence] = {
            stage: StageEvidence(stage=stage)
            for stage in WEGAStage
        }

    def start_session(self, intent: str, session_id: str = None) -> None:
        import uuid
        self.session_id  = session_id or uuid.uuid4().hex[:8]
        self.intent      = intent
        self.started_at  = time.time()
        planner = self.stages[WEGAStage.PLANNER]
        planner.status        = StageStatus.RUNNING
        planner.started_at    = self.started_at
        planner.agent         = "Control Tower"
        planner.input_summary = f"Image uploaded - intent: {intent}"

    def complete_planner(self, item_type: str, expected_count: int = None) -> None:
        planner = self.stages[WEGAStage.PLANNER]
        planner.status         = StageStatus.PASSED
        planner.completed_at   = time.time()
        planner.output_summary = f"Intent declared: count {item_type} and assess reorder"
        planner.evidence       = {"item_type": item_type, "expected_count": expected_count}

    def start_builder(self) -> None:
        builder = self.stages[WEGAStage.BUILDER]
        builder.status     = StageStatus.RUNNING
        builder.started_at = time.time()
        builder.agent      = "Vision Agent + Supplier Agent + Reorder Agent"

    def complete_builder(self, item_count: int, item_type: str,
                         confidence: str, supplier: str, part: str) -> None:
        builder = self.stages[WEGAStage.BUILDER]
        builder.status         = StageStatus.PASSED
        builder.completed_at   = time.time()
        builder.input_summary  = "Warehouse shelf image"
        builder.output_summary = f"Counted {item_count} {item_type}, matched to {part} via {supplier}"
        builder.evidence       = {
            "item_count": item_count, "item_type": item_type,
            "confidence": confidence, "supplier": supplier, "part": part,
        }

    def complete_validator(self, confidence: str, supplier_confidence: float,
                           passed: bool, reason: str = None) -> None:
        validator = self.stages[WEGAStage.VALIDATOR]
        validator.status         = StageStatus.PASSED if passed else StageStatus.FAILED
        validator.started_at     = validator.started_at or time.time()
        validator.completed_at   = time.time()
        validator.agent          = "Governance Layer"
        validator.input_summary  = "Agent outputs"
        validator.output_summary = "Quality gates passed" if passed else f"Quality gate failed: {reason}"
        validator.evidence       = {
            "vision_confidence": confidence,
            "supplier_confidence": supplier_confidence,
            "gates_passed": passed, "reason": reason,
        }

    def complete_evaluator(self, status: str, days_until_stockout: float,
                           reorder_point: int, should_order: bool, reason: str) -> None:
        evaluator = self.stages[WEGAStage.EVALUATOR]
        evaluator.status         = StageStatus.PASSED if status != "ERROR" else StageStatus.FAILED
        evaluator.started_at     = evaluator.started_at or time.time()
        evaluator.completed_at   = time.time()
        evaluator.agent          = "Reorder Agent (Prophet ML)"
        evaluator.input_summary  = "Vision count + usage history"
        evaluator.output_summary = reason
        evaluator.evidence       = {
            "reorder_status": status, "days_until_stockout": days_until_stockout,
            "reorder_point": reorder_point, "should_order": should_order,
        }

    def complete_reporter(self, shipping_cost: str, carrier: str,
                          eta: str, email_sent: bool,
                          calendar_created: bool, sheet_logged: bool) -> None:
        reporter = self.stages[WEGAStage.REPORTER]
        reporter.status         = StageStatus.PASSED
        reporter.started_at     = reporter.started_at or time.time()
        reporter.completed_at   = time.time()
        self.completed_at       = reporter.completed_at
        reporter.agent          = "Logistics Agent + MCP Integrations"
        reporter.input_summary  = "Order details"
        reporter.output_summary = f"Shipped via {carrier}, ETA {eta}, cost {shipping_cost}"
        reporter.evidence       = {
            "shipping_cost": shipping_cost, "carrier": carrier, "eta": eta,
            "email_sent": email_sent, "calendar_created": calendar_created,
            "sheet_logged": sheet_logged,
        }

    def fail_stage(self, stage: WEGAStage, error: str) -> None:
        s = self.stages[stage]
        s.status       = StageStatus.FAILED
        s.completed_at = time.time()
        s.error        = error

    @property
    def total_duration_ms(self) -> Optional[int]:
        if self.started_at and self.completed_at:
            return round((self.completed_at - self.started_at) * 1000)
        return None

    @property
    def overall_status(self) -> str:
        statuses = [s.status for s in self.stages.values()]
        if any(s == StageStatus.FAILED for s in statuses):
            return "failed"
        if all(s == StageStatus.PASSED for s in statuses):
            return "passed"
        return "running"

    def to_dict(self) -> dict:
        return {
            "session_id":        self.session_id,
            "intent":            self.intent,
            "started_at":        self.started_at,
            "completed_at":      self.completed_at,
            "total_duration_ms": self.total_duration_ms,
            "overall_status":    self.overall_status,
            "stages": {
                stage.value: evidence.to_dict()
                for stage, evidence in self.stages.items()
            }
        }