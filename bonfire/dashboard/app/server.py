#!/usr/bin/env python3
"""Minimal read-only Bonfire dashboard HTTP server."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from lib import transformers  # type: ignore  # noqa

TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


class DashboardHandler(BaseHTTPRequestHandler):
    def _json_response(self, payload: Any) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _text_response(self, status: int, body: str, mime: str = "text/plain; charset=utf-8") -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, file_path: Path, mime: str) -> None:
        try:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self._text_response(404, "not found")

    def _safe_payload(self, handler):
        try:
            return handler()
        except Exception as exc:
            return {
                "error": f"{type(exc).__name__}: {exc}",
                "status": "failed",
                "message": "dashboard encountered an internal parsing issue",
            }

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/index.html"}:
            template = TEMPLATES_DIR / "index.html"
            self._send_file(template, "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            file_path = STATIC_DIR / path[len("/static/") :]
            mime, _ = mimetypes.guess_type(file_path.as_posix())
            self._send_file(file_path, mime or "application/octet-stream")
            return
        if path.startswith("/api/"):
            if path == "/api/overview":
                payload = self._safe_payload(transformers.summarize_overview)
            elif path == "/api/agents":
                payload = self._safe_payload(transformers.summarize_agents)
            elif path == "/api/economics":
                payload = self._safe_payload(transformers.summarize_economics)
            elif path == "/api/alerts":
                payload = self._safe_payload(transformers.summarize_alerts)
            elif path == "/api/runaway":
                payload = self._safe_payload(transformers.summarize_runaway_agents)
            elif path == "/api/burnrate":
                payload = self._safe_payload(transformers.summarize_burn_rate)
            elif path == "/api/model-timeline":
                payload = self._safe_payload(transformers.summarize_model_downgrades)
            elif path == "/api/heatmap":
                payload = self._safe_payload(transformers.summarize_agent_heatmap)
            elif path == "/api/model-efficiency":
                payload = self._safe_payload(transformers.summarize_model_efficiency)
            elif path == "/api/loops":
                payload = self._safe_payload(transformers.summarize_reasoning_loops)
            elif path == "/api/cost-anomalies":
                payload = self._safe_payload(transformers.summarize_cost_anomalies)
            else:
                self._text_response(404, "unknown endpoint")
                return
            self._json_response(payload)
            return
        self._text_response(404, "not found")


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = HTTPServer((host, port), DashboardHandler)
    try:
        print(f"Bonfire dashboard listening on http://{host}:{port}")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down Bonfire dashboard")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bonfire dashboard server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run(host=args.host, port=args.port)
