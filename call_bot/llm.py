import json
import logging
import re
from datetime import date

import httpx

logger = logging.getLogger(__name__)

_SYSTEM = """Ты ассистент по анализу деловых звонков. Извлекаешь структурированные данные из расшифровок переговоров.
Отвечай строго в формате JSON — никакого лишнего текста."""

_USER_TMPL = """Проанализируй расшифровку звонка и извлеки задачи и договорённости.

Сегодня: {today}

Расшифровка:
{transcript}

Верни JSON в ТОЧНО таком формате (ничего лишнего):
{{
  "summary": "краткое содержание звонка — 2-3 предложения",
  "tasks": [
    {{
      "title": "конкретное название задачи, готовое для трекера",
      "description": "подробности или пустая строка",
      "due_date": "YYYY-MM-DD или null"
    }}
  ]
}}

Включай только МОИ задачи (задачи говорящего). Относительные дедлайны («к четвергу», «до конца недели») переводи в точные даты. Если дедлайна нет — null."""


class HermesClient:
    def __init__(self, base_url: str, model: str):
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._http = httpx.AsyncClient(timeout=300.0)

    async def extract_tasks(self, transcript: str) -> dict:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": _USER_TMPL.format(
                        today=date.today().isoformat(),
                        transcript=transcript,
                    ),
                },
            ],
            "stream": False,
            "format": "json",
        }

        resp = await self._http.post(self._url, json=payload)
        resp.raise_for_status()
        raw = resp.json()["message"]["content"]
        logger.debug("LLM raw response: %s", raw[:500])
        return _parse_json(raw)

    async def close(self) -> None:
        await self._http.aclose()


def _parse_json(text: str) -> dict:
    text = text.strip()

    # Strip markdown code fence if present
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)

    # Try direct parse
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fall back: grab first {...} block
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON found in LLM output: {text[:300]!r}")
        data = json.loads(m.group(0))

    data.setdefault("summary", "")
    data.setdefault("tasks", [])
    return data
