"""Reference helper to copy into Cosmic Tools after a registration is saved."""
import hashlib
import hmac
import json
import time
import uuid
from urllib.request import Request, urlopen

def notify_landing_manager(*, journey_token, submission_id, completed_at, endpoint, shared_secret):
    payload = json.dumps({
        "journey_token": journey_token,
        "submission_id": str(submission_id),
        "event_id": str(uuid.uuid4()),
        "completed_at": completed_at.isoformat(),
    }, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(shared_secret.encode(), timestamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
    request = Request(endpoint, data=payload, method="POST", headers={
        "Content-Type": "application/json",
        "X-Cosmic-Timestamp": timestamp,
        "X-Cosmic-Signature": f"sha256={signature}",
    })
    with urlopen(request, timeout=10) as response:
        return response.status == 200
