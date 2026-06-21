from __future__ import annotations

import logging
from typing import Optional
import requests
from requests import Session

from Field import Field
from data_structures import Direction, ItemKind

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SnakeFieldAPI:
    def __init__(
        self,
        base_url: str,
        teamname: str,
        game_name: str,
        password: str,
        *,
        timeout: float = 0.5,
        session: Optional[Session] = None,
    ) -> None:
        self.team_name = teamname
        self.game_name = game_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

        self.session.auth = (teamname, password)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def get_field(self) -> Field:
        url = self._url(f"/games/{self.game_name}/state")
        resp = self.session.get(url, timeout=self.timeout)

        if resp.status_code != 200:
            return None

        return Field.from_dict(resp.json())

    def set_direction(self, direction: Direction) -> None:
        url = self._url(f"/games/{self.game_name}/snake/direction")
        self.session.post(url, json={"direction": direction}, timeout=self.timeout)

    def activate_item(self, item: ItemKind) -> None:
        url = self._url(f"/games/{self.game_name}/snake/activate")
        self.session.post(url, json={"item": item}, timeout=self.timeout)