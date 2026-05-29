import re
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    filename="governance_audit.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Policy configuration
MAX_IMAGE_SIZE_MB = 5
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]
BLOCKED_PATTERNS = [
    "ignore previous instructions",
    "forget your instructions",
    "you are now",
    "act as",
    "jailbreak",
    "bypass",
    "disregard",
]

def validate_image(image_bytes: bytes, content_type: str) -> dict:
    """Validate image size and type."""
    size_mb = len(image_bytes) / (1024 * 1024)
    
    if content_type not in ALLOWED_IMAGE_TYPES:
        return {"allowed": False, "reason": f"Image type '{content_type}' not allowed"}
    
    if size_mb > MAX_IMAGE_SIZE_MB:
        return {"allowed": False, "reason": f"Image size {size_mb:.1f}MB exceeds {MAX_IMAGE_SIZE_MB}MB limit"}
    
    return {"allowed": True, "reason": "Image validated successfully"}

def check_prompt_injection(text: str) -> dict:
    """Check for prompt injection attempts."""
    text_lower = text.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in text_lower:
            return {"safe": False, "reason": f"Blocked pattern detected: '{pattern}'"}
    return {"safe": True, "reason": "No injection patterns detected"}

def enforce_policy(request: dict) -> dict:
    """
    Main governance entry point.
    Every request must pass through this before agents run.
    """
    request_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    
    logging.info(f"[{request_id}] Governance check started | type={request.get('type')} | user={request.get('user', 'anonymous')}")
    
    # 1. Validate image if present
    if "image" in request:
        image_check = validate_image(
            request["image"],
            request.get("content_type", "")
        )
        if not image_check["allowed"]:
            logging.warning(f"[{request_id}] Image validation FAILED | reason={image_check['reason']}")
            return {"approved": False, "request_id": request_id, "reason": image_check["reason"]}
    
    # 2. Check for prompt injection in any text fields
    for field in ["query", "notes", "description"]:
        if field in request:
            injection_check = check_prompt_injection(request[field])
            if not injection_check["safe"]:
                logging.warning(f"[{request_id}] Prompt injection BLOCKED | field={field} | reason={injection_check['reason']}")
                return {"approved": False, "request_id": request_id, "reason": injection_check["reason"]}
    
    # 3. Risk check - flag high volume requests
    if request.get("quantity", 0) > 1000:
        logging.warning(f"[{request_id}] High risk order flagged | quantity={request.get('quantity')}")
        return {
            "approved": False,
            "request_id": request_id,
            "reason": "Order quantity exceeds policy limit. Human approval required."
        }
    
    logging.info(f"[{request_id}] Governance check PASSED | request approved")
    return {"approved": True, "request_id": request_id, "reason": "All checks passed"}

