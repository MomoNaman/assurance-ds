"""Accès minimal au modèle (HTTP direct, sans dépendance). Optionnel : tout le reste tourne sans clé.

LLM_PROVIDER = anthropic | openai | replay ; LLM_MODEL ; LLM_API_KEY ; LLM_BASE_URL (optionnel).
`replay` rejoue des réponses fournies par un dictionnaire (tests, démonstration hors ligne).
"""
from __future__ import annotations

import json
import os
import urllib.request


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, provider: str | None = None, replay: dict[str, dict] | None = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "anthropic")).lower()
        self.model = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
        self.key = os.getenv("LLM_API_KEY", "")
        self.base = os.getenv("LLM_BASE_URL", "")
        self.replay = replay or {}

    def json(self, system: str, user: str, max_tokens: int = 1500) -> dict:
        if self.provider == "replay":
            for cle, rep in self.replay.items():
                if cle in user:
                    return rep
            raise LLMError("aucune réponse enregistrée pour cette question")
        if not self.key:
            raise LLMError("LLM_API_KEY manquant")
        if self.provider == "anthropic":
            url = (self.base or "https://api.anthropic.com") + "/v1/messages"
            hdr = {"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            body = {"model": self.model, "max_tokens": max_tokens, "temperature": 0, "system": system,
                    "messages": [{"role": "user", "content": user}]}
            raw = "".join(b.get("text", "") for b in self._post(url, hdr, body).get("content", []))
        else:
            url = (self.base or "https://api.openai.com/v1") + "/chat/completions"
            hdr = {"authorization": f"Bearer {self.key}", "content-type": "application/json"}
            body = {"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            raw = self._post(url, hdr, body)["choices"][0]["message"]["content"]
        a, b = raw.find("{"), raw.rfind("}")
        if a < 0:
            raise LLMError(f"réponse non JSON : {raw[:200]!r}")
        return json.loads(raw[a:b + 1])

    @staticmethod
    def _post(url, hdr, body):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hdr, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise LLMError(f"HTTP {e.code} : {e.read()[:300]!r}") from e
