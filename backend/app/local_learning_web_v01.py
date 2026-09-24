"""URPP 14D-2C: loopback-only local web entrypoint over the existing API.

Developer-only single-user UI. It does not add authentication, general-answer
routing, or any new learning-state writes. The API/workspace remain authoritative.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.llm.local_ollama_professor_gateway_v01 import LocalOllamaProfessorGatewayV01
from app.local_learning_api_v01 import create_local_learning_api_v01
from app.services.course_knowledge.local_learning_workspace_v01 import (
    LocalLearningWorkspaceV01,
)

ASSETS = Path(__file__).with_name("local_learning_web_assets_v01")
DEFAULT_DATA_ROOT = (
    Path.home() / "Library" / "Application Support" / "URPP" / "local-learning-demo-v01"
)


def create_local_learning_web_v01(
    *, workspace: LocalLearningWorkspaceV01, allow_test_host: bool = False
) -> FastAPI:
    """Attach fixed local UI assets to the existing, guarded local API."""
    app = create_local_learning_api_v01(
        workspace=workspace, allow_test_host=allow_test_host
    )

    @app.get("/", include_in_schema=False)
    def homepage():
        return FileResponse(
            ASSETS / "index.html",
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-store",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": (
                    "default-src 'none'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; base-uri 'none'; "
                    "form-action 'none'; frame-ancestors 'none'"
                ),
            },
        )

    @app.get("/assets/local-learning.js", include_in_schema=False)
    def javascript():
        return FileResponse(
            ASSETS / "app.js", media_type="text/javascript; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/assets/local-learning-markdown.js", include_in_schema=False)
    def markdown_javascript():
        return FileResponse(
            ASSETS / "markdown_v01.js", media_type="text/javascript; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/assets/local-learning.css", include_in_schema=False)
    def stylesheet():
        return FileResponse(
            ASSETS / "style.css", media_type="text/css; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="URPP local single-user learning web demo")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Port must be 1024–65535.")

    os.umask(0o077)
    workspace = LocalLearningWorkspaceV01(
        data_root=args.data_root,
        gateway_factory=lambda: LocalOllamaProfessorGatewayV01(model="qwen3.5:4b"),
    )
    app = create_local_learning_web_v01(workspace=workspace)

    import uvicorn

    print(f"URPP local learning: http://127.0.0.1:{args.port}")
    print("Developer-only: do not expose this server to the LAN or Internet.")
    uvicorn.run(
        app, host="127.0.0.1", port=args.port,
        proxy_headers=False, access_log=False, reload=False, workers=1,
    )


if __name__ == "__main__":
    main()
