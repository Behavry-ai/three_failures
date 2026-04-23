import json
import re
from models import ToolRequest, InjectionResult

# Patterns scanned in request params before forwarding
_REQUEST_PATTERNS = [
    (re.compile(r"/etc/(crontab|passwd|shadow|sudoers)"), "sensitive_path"),
    (re.compile(r"\|(\s*)(bash|sh|zsh|fish)\b"), "shell_pipe"),
    (re.compile(r"curl\s+\S+\s*\|\s*(bash|sh)\b"), "curl_shell"),
    (re.compile(r"wget\s+\S+\s*\|\s*(bash|sh)\b"), "wget_shell"),
    (re.compile(r"/var/spool/cron\b"), "cron_path"),
    (re.compile(r"chmod\s+[0-7]{3,4}\s+"), "chmod_cmd"),
]

# Patterns scanned in response bodies from targets
_RESPONSE_PATTERNS = [
    (re.compile(r"<!--\s*SYSTEM\s*:", re.IGNORECASE), "system_directive_comment"),
    (re.compile(r"<!--\s*INSTRUCTION\s*:", re.IGNORECASE), "instruction_comment"),
    (re.compile(r"<!--\s*(redirect|execute|run|eval)\s", re.IGNORECASE), "action_comment"),
]

_PAYLOAD_RE = re.compile(r"<!--\s*SYSTEM\s*:(.*?)-->", re.IGNORECASE | re.DOTALL)


async def scan(request: ToolRequest) -> InjectionResult:
    params_str = json.dumps(request.params)
    for pattern, name in _REQUEST_PATTERNS:
        m = pattern.search(params_str)
        if m:
            return InjectionResult(
                found=True,
                pattern=name,
                evidence={"matched": m.group(), "params": request.params},
            )
    return InjectionResult(found=False)


async def scan_response(tool_name: str, response_body: dict) -> InjectionResult:
    body_str = json.dumps(response_body)
    for pattern, name in _RESPONSE_PATTERNS:
        m = pattern.search(body_str)
        if m:
            payload_match = _PAYLOAD_RE.search(body_str)
            payload = payload_match.group(1).strip() if payload_match else m.group()
            return InjectionResult(
                found=True,
                pattern=name,
                evidence={"tool": tool_name, "payload": payload, "matched": m.group()},
            )
    return InjectionResult(found=False)
