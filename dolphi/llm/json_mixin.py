from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class JsonGeneratingClient:
    def generate(self, prompt: str, system: Optional[str] = None, temperature: float = 0.3) -> str:
        raise NotImplementedError

    @staticmethod
    def _repair_truncated_json(raw: str) -> str:
        in_string = False
        escape = False
        for c in raw:
            if escape:
                escape = False
                continue
            if c == "\\" and in_string:
                escape = True
                continue
            if c == '"':
                in_string = not in_string

        if in_string:
            raw += '"'

        open_curly = raw.count("{") - raw.count("}")
        open_square = raw.count("[") - raw.count("]")

        if open_curly > 0:
            raw += "}" * open_curly
        if open_square > 0:
            raw += "]" * open_square

        return raw

    @staticmethod
    def _strip_markdown_fence(raw: str) -> str:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        return raw.strip()

    def generate_json(self, prompt: str, system: Optional[str] = None, temperature: float = 0.3) -> dict[str, Any]:
        json_prompt = (
            f"{prompt}\n\n"
            "Respond with ONLY valid JSON, no markdown, no extra text. "
            "The JSON must be parseable by json.loads()."
        )
        raw = self.generate(json_prompt, system=system, temperature=temperature)
        raw = self._strip_markdown_fence(raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        repaired = self._repair_truncated_json(raw)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if brace_match:
            candidate = self._repair_truncated_json(brace_match.group(0))
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        logger.warning("LLM did not return valid JSON. Raw (first 300): %s", raw[:300])
        return {"error": "Invalid JSON response", "raw": raw[:500]}
