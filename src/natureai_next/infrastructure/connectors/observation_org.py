"""Authenticated Observation.org exchange with explicit test/production selection."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class OAuthToken:
    access_token: str
    token_type: str = "Bearer"
    refresh_token: str | None = None
    expires_in: int | None = None


class ObservationOrgClient:
    """Small OAuth2 client; production use must be selected explicitly."""

    TEST_BASE = "https://test.observation.org"
    PRODUCTION_BASE = "https://observation.org"

    def __init__(self, *, access_token: str | None = None, production: bool = False,
                 base_url: str | None = None, timeout: float = 30):
        self.base_url = (base_url or (self.PRODUCTION_BASE if production else self.TEST_BASE)).rstrip("/")
        self.access_token = access_token
        self.timeout = timeout

    def authorization_url(self, *, client_id: str, redirect_uri: str, state: str,
                          scopes: tuple[str, ...] = ("read_observations", "write_observations")) -> str:
        query=urllib.parse.urlencode({"response_type":"code","client_id":client_id,"redirect_uri":redirect_uri,
                                     "scope":" ".join(scopes),"state":state})
        return f"{self.base_url}/o/authorize/?{query}"

    def exchange_code(self, *, code: str, client_id: str, client_secret: str,
                      redirect_uri: str) -> OAuthToken:
        payload={"grant_type":"authorization_code","code":code,"client_id":client_id,
                 "client_secret":client_secret,"redirect_uri":redirect_uri}
        data=self._request("POST","/o/token/",payload,authenticated=False)
        self.access_token=str(data["access_token"])
        return OAuthToken(self.access_token,str(data.get("token_type","Bearer")),data.get("refresh_token"),data.get("expires_in"))

    def create_observation(self, payload: dict) -> dict:
        required=("species","date","lat","lng")
        missing=[key for key in required if payload.get(key) in (None,"")]
        if missing: raise ValueError("Observation.org payload missing: "+", ".join(missing))
        return self._request("POST","/api/v1/observations/",payload)

    def observation(self, remote_id: str | int) -> dict:
        return self._request("GET",f"/api/v1/observations/{remote_id}/",None)

    def upload_media(self, observation_id: str | int, source: Path, *, field_name: str = "file") -> dict:
        source=Path(source)
        if not source.is_file(): raise FileNotFoundError(source)
        boundary="fieldora-"+hashlib.sha256(source.name.encode()).hexdigest()[:20]
        body=(f"--{boundary}\r\nContent-Disposition: form-data; name=\"observation\"\r\n\r\n{observation_id}\r\n"
              f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"; filename=\"{source.name}\"\r\n"
              f"Content-Type: application/octet-stream\r\n\r\n").encode()+source.read_bytes()+f"\r\n--{boundary}--\r\n".encode()
        return self._request("POST","/api/v1/observations/media/",body,content_type=f"multipart/form-data; boundary={boundary}")

    def _request(self, method: str, path: str, payload=None, *, authenticated: bool = True,
                 content_type: str = "application/json") -> dict:
        if authenticated and not self.access_token: raise PermissionError("Observation.org authentication is required")
        body=None if method == "GET" else payload if isinstance(payload,bytes) else json.dumps(payload or {}).encode()
        headers={"Accept":"application/json","Content-Type":content_type,"User-Agent":"Fieldora/5.2"}
        if authenticated: headers["Authorization"]=f"Bearer {self.access_token}"
        request=urllib.request.Request(self.base_url+path,data=body,headers=headers,method=method)
        with urllib.request.urlopen(request,timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))
