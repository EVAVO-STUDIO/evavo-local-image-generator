"""Loopback-only EVAVO ComfyUI control app and process launcher."""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from evavo_operations import ROOT
from .comfyui_runtime import ensure_comfyui, native_health, present_comfyui_ui

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770
MAX_BODY_BYTES = 64 * 1024
MAX_PROMPT_CHARS = 8_000
_GENERATION_LOCK = threading.Lock()

LOCAL_APP_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EVAVO Local Generation</title><style>
:root{color-scheme:dark;--text:#f7f7f7;--muted:#aaaab2;--panel:#17171b;--line:#313139;--accent:#ff244e;--ok:#47d47c}
*{box-sizing:border-box}body{margin:0;background:#0a0a0c;color:var(--text);font:14px/1.45 system-ui,sans-serif}
main{max-width:1040px;margin:auto;padding:22px}header,.bar{display:flex;align-items:center;justify-content:space-between;gap:14px}header{margin-bottom:16px}
.brand{display:flex;align-items:center;gap:11px}.mark{width:14px;height:40px;border-radius:3px;background:var(--accent);box-shadow:0 0 26px #ff244e55}
h1{font-size:22px;margin:0}.muted,label{color:var(--muted)}.muted{margin:2px 0 0}.state{display:flex;align-items:center;gap:8px}
.dot{width:9px;height:9px;border-radius:50%;background:#ffbd52}.dot.ok{background:var(--ok)}.dot.bad{background:var(--accent)}
.grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(300px,.75fr);gap:14px}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
label{display:block;font-size:12px;margin:0 0 6px}textarea,input{width:100%;background:#0d0d10;color:var(--text);border:1px solid var(--line);border-radius:9px;padding:10px;font:inherit}
textarea{min-height:145px;resize:vertical}textarea:focus,input:focus{outline:none;border-color:var(--accent)}.fields{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-top:10px}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}button{border:1px solid var(--line);border-radius:9px;background:#25252b;color:var(--text);padding:9px 12px;font-weight:650;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent)}button:disabled{opacity:.5;cursor:wait}.preview{min-height:330px;display:grid;place-items:center;background:#08080a;border:1px dashed var(--line);border-radius:10px;overflow:hidden}
.preview img{width:100%;height:auto;display:block}.log{margin-top:11px;padding:10px;background:#0d0d10;border-radius:9px;min-height:44px;color:var(--muted);white-space:pre-wrap;word-break:break-word}
@media(max-width:760px){.grid{grid-template-columns:1fr}.fields{grid-template-columns:1fr 1fr}}
</style></head><body><main>
<header><div class="brand"><span class="mark"></span><div><h1>EVAVO Local Generation</h1><p class="muted">Private ComfyUI control on this workstation</p></div></div><div class="state"><span id="dot" class="dot"></span><span id="status">Checking…</span></div></header>
<div class="bar card" style="margin-bottom:14px"><div><strong>ComfyUI node editor</strong><div class="muted">Full graph editor at the private loopback address.</div></div><button id="open">Open full ComfyUI</button></div>
<div class="grid"><section class="card"><label for="prompt">Prompt</label><textarea id="prompt" placeholder="Describe the image you want…"></textarea>
<div class="fields"><div><label for="width">Width</label><input id="width" type="number" min="64" max="4096" step="64" value="1024"></div><div><label for="height">Height</label><input id="height" type="number" min="64" max="4096" step="64" value="1024"></div><div><label for="steps">Steps</label><input id="steps" type="number" min="1" max="150" value="24"></div></div>
<div class="actions"><button id="generate" class="primary">Generate image</button><button id="health">Check backend</button></div><div id="log" class="log">Local app ready.</div></section>
<aside class="card"><label>Latest output</label><div id="preview" class="preview"><span class="muted">Generated output appears here.</span></div></aside></div>
</main><script>
(()=>{const $=id=>document.getElementById(id);
function state(label,kind=""){$("status").textContent=label;$("dot").className="dot"+(kind?" "+kind:"")}
function log(value){$("log").textContent=typeof value==="string"?value:JSON.stringify(value,null,2)}
async function api(path,options={}){const response=await fetch(path,{credentials:"same-origin",...options,headers:{"Content-Type":"application/json",...(options.headers||{})}});const data=await response.json();if(!response.ok)throw new Error(data.message||data.error||("HTTP "+response.status));return data}
async function health(){state("Checking…");try{const data=await api("/api/health");state(data.ok?"Backend ready":"Backend stopped",data.ok?"ok":"");log(data)}catch(e){state("Unavailable","bad");log(e.message)}}
$("health").addEventListener("click",health);
$("open").addEventListener("click",async()=>{const b=$("open");b.disabled=true;state("Opening…");try{const data=await api("/api/open",{method:"POST",body:"{}"});state("ComfyUI ready","ok");log(data)}catch(e){state("Open failed","bad");log(e.message)}finally{b.disabled=false}});
$("generate").addEventListener("click",async()=>{const prompt=$("prompt").value.trim();if(!prompt){$("prompt").focus();log("Enter a prompt first.");return}const b=$("generate");b.disabled=true;state("Generating…");log("Starting or reusing ComfyUI and generating locally…");try{const data=await api("/api/generate",{method:"POST",body:JSON.stringify({prompt,width:Number($("width").value),height:Number($("height").value),steps:Number($("steps").value)})});state(data.ok?"Complete":"Failed",data.ok?"ok":"bad");log(data);if(data.downloaded_files?.[0]){const img=document.createElement("img");img.alt="Generated image";img.src="/api/image?path="+encodeURIComponent(data.downloaded_files[0]);$("preview").replaceChildren(img)}}catch(e){state("Generation failed","bad");log(e.message)}finally{b.disabled=false}});
health()})();
</script></body></html>'''


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str).encode("utf-8")


class LocalControlServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, LocalControlHandler)
        self.session_token = secrets.token_urlsafe(32)
        self.expected_origin = f"http://{address[0]}:{address[1]}"


class LocalControlHandler(BaseHTTPRequestHandler):
    server: LocalControlServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _headers(self, status: int, content_type: str, length: int, *, cookie: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        if cookie:
            self.send_header("Set-Cookie", f"evavo_session={self.server.session_token}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()

    def _send_json(self, value: Any, status: int = HTTPStatus.OK) -> None:
        body = _json_bytes(value)
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _authorized(self, *, require_origin: bool) -> bool:
        cookies = self.headers.get("Cookie", "")
        supplied = ""
        for item in cookies.split(";"):
            name, separator, value = item.strip().partition("=")
            if separator and name == "evavo_session":
                supplied = value
                break
        if not hmac.compare_digest(supplied, self.server.session_token):
            return False
        if require_origin and self.headers.get("Origin") != self.server.expected_origin:
            return False
        return True

    def _read_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length)
        value = json.loads(raw or b"{}")
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/ping":
            self._send_json({"ok": True, "kind": "evavo-local-comfyui-control-v1"})
            return
        if parsed.path == "/":
            body = LOCAL_APP_HTML.encode("utf-8")
            self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body), cookie=True)
            self.wfile.write(body)
            return
        if not self._authorized(require_origin=False):
            self._send_json({"ok": False, "message": "local app session is not authorized"}, HTTPStatus.FORBIDDEN)
            return
        if parsed.path == "/api/health":
            health = native_health()
            self._send_json({"ok": health is not None, "status": "ready" if health else "stopped", "backend": health})
            return
        if parsed.path == "/api/image":
            query = urllib.parse.parse_qs(parsed.query)
            requested = (query.get("path") or [""])[0]
            try:
                from .mcp_server import _validated_output_image
                candidate = _validated_output_image(requested)
                body = candidate.read_bytes()
            except (OSError, ValueError) as exc:
                self._send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            content_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}[candidate.suffix.lower()]
            self._headers(HTTPStatus.OK, content_type, len(body))
            self.wfile.write(body)
            return
        self._send_json({"ok": False, "message": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if not self._authorized(require_origin=True):
            self._send_json({"ok": False, "message": "local app request is not authorized"}, HTTPStatus.FORBIDDEN)
            return
        try:
            payload = self._read_body()
            if parsed.path == "/api/open":
                backend = ensure_comfyui(wait_seconds=90.0, allow_start=True)
                presentation = present_comfyui_ui()
                self._send_json({"ok": True, "status": "ready", "backend": backend, **presentation})
                return
            if parsed.path == "/api/generate":
                prompt = str(payload.get("prompt") or "").strip()
                if not prompt or len(prompt) > MAX_PROMPT_CHARS:
                    raise ValueError(f"prompt must contain 1 to {MAX_PROMPT_CHARS} characters")
                if not _GENERATION_LOCK.acquire(blocking=False):
                    self._send_json({"ok": False, "message": "another local generation is already running"}, HTTPStatus.CONFLICT)
                    return
                try:
                    from .mcp_server import _generate_image_impl
                    result = asyncio.run(_generate_image_impl(
                        prompt,
                        project_name="local_app",
                        width=int(payload.get("width", 1024)),
                        height=int(payload.get("height", 1024)),
                        steps=int(payload.get("steps", 24)),
                        wait=True,
                        auto_start=True,
                    ))
                finally:
                    _GENERATION_LOCK.release()
                self._send_json(result, HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_GATEWAY)
                return
            self._send_json({"ok": False, "message": "not found"}, HTTPStatus.NOT_FOUND)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"ok": False, "message": f"{type(exc).__name__}: {exc}"}, HTTPStatus.BAD_GATEWAY)


def _ping(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/ping", timeout=timeout) as response:
            body = json.loads(response.read(4097).decode("utf-8"))
        return response.status == 200 and body.get("kind") == "evavo-local-comfyui-control-v1"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def ensure_local_control_app(port: int = DEFAULT_PORT, *, open_browser: bool = True, wait_seconds: float = 30.0) -> dict[str, Any]:
    if not 1 <= int(port) <= 65535:
        raise ValueError("port must be between 1 and 65535")
    url = f"http://{DEFAULT_HOST}:{int(port)}"
    started = False
    if not _ping(url):
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            [sys.executable, "-m", "evavo_local_image_generator.local_app", "--port", str(int(port))],
            cwd=str(ROOT),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=os.name != "nt",
            creationflags=flags,
        )
        started = True
        deadline = time.monotonic() + max(1.0, min(float(wait_seconds), 120.0))
        while time.monotonic() < deadline:
            if _ping(url):
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("LOCAL_CONTROL_APP_START_FAILED:loopback app did not become ready")
    opened = bool(webbrowser.open_new_tab(url)) if open_browser else False
    return {"ok": True, "status": "ready", "url": url, "started": started, "browser_opened": opened}


def main() -> None:
    parser = argparse.ArgumentParser(description="EVAVO loopback-only ComfyUI control app")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    if args.host != DEFAULT_HOST:
        parser.error("the local control app binds only to 127.0.0.1")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    server = LocalControlServer((args.host, args.port))
    if args.open:
        threading.Timer(0.3, webbrowser.open_new_tab, args=(f"http://{args.host}:{args.port}",)).start()
    server.serve_forever(poll_interval=0.25)


if __name__ == "__main__":
    main()
