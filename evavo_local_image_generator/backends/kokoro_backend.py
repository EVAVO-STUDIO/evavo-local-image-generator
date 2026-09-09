"""Quality-oriented Kokoro-FastAPI client for local EVAVO speech generation."""

from __future__ import annotations

import json
import math
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


class KokoroBackend:
    """Small OpenAI-compatible client for a local Kokoro-FastAPI service."""

    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = (
            endpoint
            or os.getenv("KOKORO_ENDPOINT")
            or os.getenv("EVAVO_KOKORO_ENDPOINT")
            or "http://127.0.0.1:8880"
        ).rstrip("/")

    def _open(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
        accept: str = "application/json",
    ):
        body = None
        headers = {"Accept": accept, "User-Agent": "EVAVO-Kokoro/2"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.endpoint}{path}", data=body, headers=headers, method=method)
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"KOKORO_HTTP_ERROR:{exc.code}:{detail or exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"KOKORO_CONNECTION_ERROR:{exc}") from exc

    def _json(self, path: str, *, timeout: float = 10.0) -> Any:
        with self._open(path, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("KOKORO_INVALID_JSON:server returned invalid JSON") from exc

    @staticmethod
    def _voice_names(payload: Any) -> List[str]:
        values = payload.get("voices", payload) if isinstance(payload, dict) else payload
        result: List[str] = []
        if not isinstance(values, list):
            return result
        for item in values:
            if isinstance(item, str) and item:
                result.append(item)
            elif isinstance(item, dict):
                value = item.get("id") or item.get("name") or item.get("voice")
                if isinstance(value, str) and value:
                    result.append(value)
        return result

    def voices(self) -> List[str]:
        return self._voice_names(self._json("/v1/audio/voices", timeout=15.0))

    def health(self) -> Dict[str, Any]:
        try:
            voices = self.voices()
            return {
                "healthy": True,
                "status": "ready",
                "endpoint": self.endpoint,
                "api": "openai-compatible",
                "voices": voices,
                "voice_count": len(voices),
            }
        except RuntimeError as voice_error:
            try:
                with self._open("/docs", timeout=3.0, accept="text/html,*/*") as response:
                    status = getattr(response, "status", 200)
                if 200 <= status < 500:
                    return {
                        "healthy": True,
                        "status": "ready-with-voice-warning",
                        "endpoint": self.endpoint,
                        "api": "openai-compatible",
                        "voices": [],
                        "voice_count": 0,
                        "warning": str(voice_error),
                    }
            except RuntimeError:
                pass
            raise voice_error

    def health_check(self) -> bool:
        try:
            return bool(self.health().get("healthy"))
        except RuntimeError:
            return False

    @staticmethod
    def _valid_audio_signature(data: bytes, response_format: str) -> bool:
        fmt = response_format.lower()
        if fmt == "wav":
            return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
        if fmt == "flac":
            return data.startswith(b"fLaC")
        if fmt == "mp3":
            return data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
        if fmt == "opus":
            return b"OpusHead" in data[:128] or data.startswith(b"OggS")
        if fmt in {"aac", "pcm"}:
            return bool(data)
        return False

    def synthesize(
        self,
        text: str,
        output_path: str | Path,
        *,
        voice: Optional[str] = None,
        speed: float = 1.0,
        response_format: str = "wav",
        model: str = "kokoro",
        timeout: float = 300.0,
        validate_voice: bool = True,
    ) -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        try:
            speed_value = float(speed)
        except (TypeError, ValueError) as exc:
            raise ValueError("speed must be a number") from exc
        if not math.isfinite(speed_value) or not 0.25 <= speed_value <= 4.0:
            raise ValueError("speed must be finite and between 0.25 and 4.0")

        fmt = str(response_format).strip().lower()
        if fmt not in {"wav", "flac", "mp3", "opus", "aac", "pcm"}:
            raise ValueError("response_format must be wav, flac, mp3, opus, aac, or pcm")

        selected_voice = (
            voice
            or os.getenv("EVAVO_KOKORO_VOICE")
            or os.getenv("KOKORO_DEFAULT_VOICE")
            or "af_heart"
        )
        selected_voice = str(selected_voice).strip()
        if not selected_voice:
            raise ValueError("voice must not be empty")

        if validate_voice:
            available = self.voices()
            if available and selected_voice not in available:
                raise RuntimeError(
                    f"KOKORO_VOICE_NOT_FOUND:{selected_voice}; available={','.join(available[:40])}"
                )

        payload = {
            "model": model,
            "input": text.strip(),
            "voice": selected_voice,
            "response_format": fmt,
            "speed": speed_value,
            "stream": False,
        }
        with self._open(
            "/v1/audio/speech",
            method="POST",
            payload=payload,
            timeout=timeout,
            accept="audio/*,application/octet-stream",
        ) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type")

        if not data:
            raise RuntimeError("KOKORO_EMPTY_AUDIO:service returned no audio bytes")
        if not self._valid_audio_signature(data, fmt):
            raise RuntimeError(f"KOKORO_INVALID_AUDIO:{fmt}:unexpected output signature")

        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".part", dir=str(target.parent))
        try:
            os.close(fd)
            Path(temp_name).write_bytes(data)
            os.replace(temp_name, target)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

        return {
            "ok": True,
            "status": "completed",
            "endpoint": self.endpoint,
            "voice": selected_voice,
            "speed": speed_value,
            "response_format": fmt,
            "content_type": content_type,
            "bytes": len(data),
            "output_path": str(target),
        }

    def __repr__(self) -> str:
        return f"KokoroBackend(endpoint={self.endpoint!r})"
