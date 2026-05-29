import logging
import time
import uuid
from datetime import datetime
from typing import Optional

# Configure structured logging
logging.basicConfig(
    filename="agent_audit.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# In-memory trace store (would be a DB in production)
_traces = []

class AgentTrace:
    """Tracks a single agent's execution."""
    
    def __init__(self, agent_name: str, workflow_id: str):
        self.agent_name = agent_name
        self.workflow_id = workflow_id
        self.trace_id = str(uuid.uuid4())[:8]
        self.start_time = time.time()
        self.end_time = None
        self.status = "running"
        self.input_summary = None
        self.output_summary = None
        self.error = None
        self.duration_ms = None

    def complete(self, output_summary: str):
        """Mark agent as successfully completed."""
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status = "success"
        self.output_summary = output_summary
        self._log()

    def fail(self, error: str):
        """Mark agent as failed."""
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status = "failed"
        self.error = error
        self._log()

    def _log(self):
        """Write to audit log and trace store."""
        log_entry = {
            "workflow_id": self.workflow_id,
            "trace_id": self.trace_id,
            "agent": self.agent_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "input": self.input_summary,
            "output": self.output_summary,
            "error": self.error,
            "timestamp": datetime.utcnow().isoformat()
        }
        _traces.append(log_entry)

        if self.status == "success":
            logging.info(
                f"[{self.workflow_id}] Agent={self.agent_name} | "
                f"Status=SUCCESS | Duration={self.duration_ms}ms | "
                f"Output={self.output_summary}"
            )
        else:
            logging.error(
                f"[{self.workflow_id}] Agent={self.agent_name} | "
                f"Status=FAILED | Duration={self.duration_ms}ms | "
                f"Error={self.error}"
            )


def start_workflow() -> str:
    """Generate a unique workflow ID to trace across all agents."""
    workflow_id = f"wf-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4]}"
    logging.info(f"[{workflow_id}] Workflow started")
    return workflow_id


def end_workflow(workflow_id: str, status: str = "completed"):
    """Mark workflow as done."""
    logging.info(f"[{workflow_id}] Workflow {status}")


def get_workflow_trace(workflow_id: str) -> list:
    """Return full trace for a given workflow."""
    return [t for t in _traces if t["workflow_id"] == workflow_id]


def get_all_traces() -> list:
    """Return all traces (for audit/dashboard)."""
    return _traces

