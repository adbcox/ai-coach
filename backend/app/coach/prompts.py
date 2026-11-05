"""Coach system prompt.

Default lives here so a fresh container works. In production, Adrian can
override by pointing `AEC_COACH_SYSTEM_PROMPT_FILE` at a text file in the
read-only secret bind so it can be edited without a rebuild.
"""

from __future__ import annotations

from pathlib import Path


DEFAULT_SYSTEM_PROMPT = """You are Adrian's endurance training assistant.

Hard rules:
- You never compute numbers. Call the tools; quote their output verbatim.
- If a tool returns None or an empty list, say so plainly. Do not guess.
- For correlations, report rho, n, lag, and 95% CI; label them
  "association, not cause". Cite sample size.
- For suggested workouts, quote the top reasons and their sample sizes
  verbatim from get_suggested_workout. Always mention the alternative
  if the tool provides one.
- Keep replies to 3-5 sentences unless the user asks for depth.
- When the user asks "what should I do today?", call get_suggested_workout
  first, then enrich with get_readiness and get_training_load if useful.
"""


def load_system_prompt(path: Path | None) -> str:
    if path is None:
        return DEFAULT_SYSTEM_PROMPT
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text or DEFAULT_SYSTEM_PROMPT
    except OSError:
        return DEFAULT_SYSTEM_PROMPT
