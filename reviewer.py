from __future__ import annotations
import os


import json
import logging
import re
import time
from typing import Any
from google import genai
import streamlit as st
if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL = "gemini-2.5-flash"
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2.0
LOW_CONFIDENCE_THRESHOLD = 50

VALID_CATEGORIES = {"bug", "security", "performance", "style"}
VALID_SEVERITIES = {"high", "medium", "low"}

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt engineering
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an expert code reviewer specialising in bugs,
security vulnerabilities, performance issues, and code style.

You will be given a single function or code snippet. Identify the SINGLE
most important issue (if any exists).

STRICT OUTPUT CONTRACT — return ONLY a JSON object, nothing else:
{
  "category":   "<bug|security|performance|style>",
  "severity":   "<high|medium|low>",
  "comment":    "<clear description of the issue, max 200 chars>",
  "suggestion": "<concrete fix or improvement, max 200 chars>",
  "confidence": <integer 0-100>
}

Confidence guide:
  90-100 : textbook issue, unambiguous
  60-89  : likely issue, context-dependent
  40-59  : possible issue, needs human judgement
  0-39   : speculative

If there is no meaningful issue, return:
{"category":"style","severity":"low","comment":"No significant issues found.",
 "suggestion":"Code looks clean.","confidence":95}

Do NOT wrap in markdown fences. Do NOT add any text outside the JSON object."""


def _build_user_prompt(
    file_path: str,
    function_name: str,
    language: str,
    code: str,
    complexity: str,
    line_start: int,
    line_end: int,
) -> str:
    return (
        f"File: {file_path}\n"
        f"Language: {language}\n"
        f"Function: {function_name}\n"
        f"Lines: {line_start}–{line_end}\n"
        f"Cyclomatic complexity: {complexity}\n\n"
        f"```{language}\n{code}\n```\n\n"
        "Return ONLY the JSON object as specified."
    )


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_claude(user_prompt: str, client) -> str:
    last_exc = None
    full_prompt = _SYSTEM_PROMPT + "\n\n" + user_prompt

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=full_prompt
            )
            return response.text
        except Exception as exc:
            wait = RETRY_BASE_DELAY ** attempt
            logger.warning("Gemini error attempt %d/%d: %s", attempt, RETRY_ATTEMPTS, exc)
            last_exc = exc
            time.sleep(wait)

    raise RuntimeError(f"Gemini API failed after {RETRY_ATTEMPTS} attempts.") from last_exc


# ---------------------------------------------------------------------------
# JSON parsing & validation
# ---------------------------------------------------------------------------

def _parse_llm_response(raw: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        logger.error("No JSON object found in LLM response: %.200s", raw)
        return None

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as exc:
        logger.error("JSON decode error: %s | raw: %.200s", exc, raw)
        return None

    category = str(data.get("category", "style")).lower()
    if category not in VALID_CATEGORIES:
        category = "style"

    severity = str(data.get("severity", "low")).lower()
    if severity not in VALID_SEVERITIES:
        severity = "low"

    try:
        confidence = max(0, min(100, int(data.get("confidence", 50))))
    except (TypeError, ValueError):
        confidence = 50

    return {
        "category":   category,
        "severity":   severity,
        "comment":    str(data.get("comment", ""))[:200],
        "suggestion": str(data.get("suggestion", ""))[:200],
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Fallback comment (on API failure)
# ---------------------------------------------------------------------------

def _error_comment(
    file_path: str,
    function_name: str,
    line_start: int,
    error_msg: str,
) -> dict[str, Any]:
    return {
        "file":       file_path,
        "function":   function_name,
        "category":   "style",
        "severity":   "low",
        "comment":    f"Review skipped due to API error: {error_msg[:120]}",
        "suggestion": "Retry with a valid API key and stable connection.",
        "confidence": 0,
        "verify":     True,
        "line":       line_start,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def review_code(parsed_output: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise KeyError("GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key)

    parsed_files: list[dict] | None = parsed_output.get("parsed_files")
    if parsed_files is None:
        raise ValueError("parsed_output must contain a 'parsed_files' key.")

    reviews: list[dict[str, Any]] = []

    for file_info in parsed_files:
        file_path: str        = file_info.get("path", "unknown")
        language:  str        = file_info.get("language", "python")
        functions: list[dict] = file_info.get("functions", [])

        if not functions:
            logger.info("No functions found in %s — skipping.", file_path)
            continue

        for func in functions:
            func_name:  str = func.get("name", "anonymous")
            line_start: int = int(func.get("line_start", 0))
            line_end:   int = int(func.get("line_end", 0))
            code:       str = func.get("code", "")
            complexity: str = str(func.get("complexity", "unknown"))

            if not code.strip():
                continue

            logger.info("Reviewing %s → %s() (lines %d–%d)",
                file_path, func_name, line_start, line_end)

            user_prompt = _build_user_prompt(
                file_path, func_name, language,
                code, complexity, line_start, line_end,
            )

            try:
                raw_response = _call_claude(user_prompt, client)
            except RuntimeError as exc:
                logger.error("Skipping %s:%s — %s", file_path, func_name, exc)
                reviews.append(_error_comment(file_path, func_name, line_start, str(exc)))
                continue

            parsed_comment = _parse_llm_response(raw_response)
            if parsed_comment is None:
                reviews.append(_error_comment(
                    file_path, func_name, line_start,
                    "Malformed LLM response; could not parse JSON.",
                ))
                continue

            reviews.append({
                "file":       file_path,
                "function":   func_name,
                "category":   parsed_comment["category"],
                "severity":   parsed_comment["severity"],
                "comment":    parsed_comment["comment"],
                "suggestion": parsed_comment["suggestion"],
                "confidence": parsed_comment["confidence"],
                "verify":     parsed_comment["confidence"] < LOW_CONFIDENCE_THRESHOLD,
                "line":       line_start,
            })

    total_issues         = len(reviews)
    high_severity        = sum(1 for r in reviews if r["severity"] == "high")
    low_confidence_count = sum(1 for r in reviews if r["verify"])

    return {
        "reviews":              reviews,
        "total_issues":         total_issues,
        "high_severity":        high_severity,
        "low_confidence_count": low_confidence_count,
    }


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

    _sample: dict[str, Any] = {
        "parsed_files": [{
            "path": "auth/login.py",
            "language": "python",
            "functions": [
                {
                    "name": "authenticate_user",
                    "line_start": 12,
                    "line_end": 26,
                    "complexity": "high",
                    "code": (
                        "def authenticate_user(username, password):\n"
                        "    query = f\"SELECT * FROM users WHERE username='{username}'\"\n"
                        "    result = db.execute(query)\n"
                        "    if result:\n"
                        "        token = str(random.randint(1000, 9999))\n"
                        "        return token\n"
                        "    return None\n"
                    ),
                },
            ],
            "chunks": [],
        }]
    }

    result = review_code(_sample)
    print(f"\nTotal issues: {result['total_issues']}")
    for rev in result["reviews"]:
        print(f"\n[{rev['severity'].upper()}] {rev['file']} → {rev['function']}()")
        print(f"  Comment    : {rev['comment']}")
        print(f"  Suggestion : {rev['suggestion']}")
        print(f"  Confidence : {rev['confidence']}%")
