import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://app.asana.com/api/1.0"


class AsanaClient:
    def __init__(self, token: str, workspace_gid: str, default_project_gid: str):
        self._workspace = workspace_gid
        self._project = default_project_gid
        self._http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30.0,
        )

    async def create_task(
        self,
        name: str,
        notes: str = "",
        due_on: Optional[str] = None,
    ) -> dict:
        """Create a task and return the Asana task data dict."""
        body: dict = {
            "data": {
                "name": name,
                "notes": notes,
                "workspace": self._workspace,
                "projects": [self._project],
            }
        }
        if due_on:
            body["data"]["due_on"] = due_on

        resp = await self._http.post(f"{_BASE}/tasks", json=body)
        resp.raise_for_status()
        task = resp.json()["data"]
        logger.info("Created Asana task: %s (%s)", task["name"], task["gid"])
        return task

    async def close(self) -> None:
        await self._http.aclose()
