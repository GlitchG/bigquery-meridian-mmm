import logging
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.clickup.com/api/v2"


class ClickUpClient:
    def __init__(self, token: str, default_list_id: str):
        self._list_id = default_list_id
        self._http = httpx.AsyncClient(
            headers={"Authorization": token, "Content-Type": "application/json"},
            timeout=30.0,
        )

    async def create_task(
        self,
        name: str,
        description: str = "",
        due_date: Optional[str] = None,  # "YYYY-MM-DD"
    ) -> dict:
        """Create a task in the default list and return the ClickUp task dict."""
        body: dict = {"name": name, "description": description}

        if due_date:
            # ClickUp expects due_date as Unix timestamp in milliseconds
            dt = datetime.strptime(due_date, "%Y-%m-%d")
            body["due_date"] = int(dt.timestamp() * 1000)

        resp = await self._http.post(f"{_BASE}/list/{self._list_id}/task", json=body)
        resp.raise_for_status()
        task = resp.json()
        logger.info("Created ClickUp task: %s (%s)", task["name"], task["id"])
        return task

    async def close(self) -> None:
        await self._http.aclose()
