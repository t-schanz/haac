"""Async client for Home Assistant WebSocket + REST APIs."""

import json

import httpx
import websockets


class HAClient:
    def __init__(self, url: str, token: str):
        self.base_url = url.rstrip("/")
        self.token = token
        self._ws = None
        self._msg_id = 0
        self._http = None

    async def connect(self):
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        self._ws = await websockets.connect(f"{ws_url}/api/websocket")
        await self._ws.recv()
        await self._ws.send(json.dumps({
            "type": "auth",
            "access_token": self.token,
        }))
        auth_result = json.loads(await self._ws.recv())
        if auth_result.get("type") != "auth_ok":
            raise ConnectionError(f"HA auth failed: {auth_result}")
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=30,
        )

    async def close(self):
        if self._ws:
            await self._ws.close()
        if self._http:
            await self._http.aclose()

    async def ws_command(self, command: str, **kwargs) -> dict:
        self._msg_id += 1
        msg = {"id": self._msg_id, "type": command, **kwargs}
        await self._ws.send(json.dumps(msg))
        result = json.loads(await self._ws.recv())
        if not result.get("success", False):
            raise RuntimeError(f"WS command failed: {command} — {result}")
        return result.get("result", {})

    async def rest_get(self, path: str) -> dict:
        r = await self._http.get(f"/api/{path}")
        r.raise_for_status()
        return r.json()

    async def rest_post(self, path: str, data: dict) -> dict:
        r = await self._http.post(f"/api/{path}", json=data)
        r.raise_for_status()
        return r.json() if r.content else {}

    async def rest_delete(self, path: str) -> dict:
        r = await self._http.delete(f"/api/{path}")
        r.raise_for_status()
        return r.json() if r.content else {}

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()
