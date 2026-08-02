#!/usr/bin/env python3
"""
AegisAI API Server Start Script

Entry point for starting the API server with uvicorn.
"""

# Suppress only the known numpy MINGW warning (Python 3.14 / Windows)
import warnings
warnings.filterwarnings('ignore', message='.*Numpy built with MINGW.*')

import os
import sys

from dotenv import load_dotenv


if __name__ == "__main__":
    import uvicorn
    from aegis.api.app import create_app

    # Nested Pydantic settings read process environment values. Load the
    # repository's server-only .env before the application constructs them so
    # Gemini Live settings work after a normal local backend restart.
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=False)

    if "--enable-semantic" in sys.argv:
        os.environ["SEMANTIC_ENABLED"] = "true"

    host = os.getenv("AEGIS_API_HOST", "127.0.0.1")
    port = int(os.getenv("AEGIS_API_PORT", "8080"))
    debug = os.getenv("AEGIS_DEBUG", "false").lower() == "true"

    print(f"Starting AegisAI API on http://{host}:{port}")
    if debug:
        uvicorn.run("aegis.api.app:create_app", host=host, port=port, reload=True, factory=True)
    else:
        app = create_app()
        uvicorn.run(app, host=host, port=port, reload=False)
