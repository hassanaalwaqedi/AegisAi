#!/usr/bin/env python3
"""
AegisAI - Deploy to Hugging Face Spaces

This script automates deployment to HF Spaces:
1. Creates a new HF Space (Docker SDK)
2. Prepares files (copies Dockerfile.hf -> Dockerfile, creates README.md)
3. Pushes code to the Space
"""

import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path

# Configuration
HF_USERNAME = "Hassanali2025"
SPACE_NAME = "AegisAI"
SPACE_ID = f"{HF_USERNAME}/{SPACE_NAME}"
PROJECT_DIR = Path(__file__).parent

# Files/dirs to exclude from the Space upload
EXCLUDE = {
    ".git", "__pycache__", "venv312", "venv", ".venv", "ENV",
    ".deploypkg", "node_modules", ".pytest_cache", "htmlcov",
    ".mypy_cache", ".tox", "camera_run_stderr.log", "camera_run_stdout.log",
    "deploy_to_hf.py", "Dockerfile.hf",
    # Large/unnecessary files
    "data",
}

# Files that should not be copied (by extension)
EXCLUDE_EXT = {".mp4", ".avi", ".mov", ".mkv", ".log", ".pyc"}


def check_hf_cli():
    """Check if huggingface_hub is installed."""
    try:
        import huggingface_hub
        print(f"✓ huggingface_hub {huggingface_hub.__version__} found")
        return True
    except ImportError:
        print("✗ huggingface_hub not found, installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        return True


def create_space_readme():
    """Generate HF Space README.md content."""
    return """---
title: AegisAI - Smart City Risk Intelligence
emoji: 🛡️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# AegisAI - Smart City Risk Intelligence System

**Production-ready AI-powered surveillance and risk assessment platform.**

## Architecture — Phase 1 (Edge / CPU)

- **YOLO 11n Detection** — Real-time object detection (persons, vehicles, weapons)
- **ByteTrack Tracking** — CPU-optimized multi-object tracking (IoU-based)
- **Proximity Risk Engine** — Rule-based risk scoring (person+weapon proximity, temporal stability)
- **Event-Based Escalation** — Only suspicious frames sent to cloud
- **REST API** — Full FastAPI backend with Swagger docs
- **Live Dashboard** — Real-time security operations monitoring UI

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API info |
| `/status` | GET | System health |
| `/events` | GET | Risk events |
| `/tracks` | GET | Active tracks |
| `/statistics` | GET | System stats |
| `/dashboard` | GET | Live monitoring UI |
| `/webcam` | GET | Browser webcam detection |
| `/docs` | GET | Swagger API docs |

## Authentication
All API endpoints require an `X-API-Key` header.
Set the `AEGIS_API_KEY` secret in the Space settings.

## Built With
- [Ultralytics YOLO11](https://ultralytics.com/)
- [Supervision (ByteTrack)](https://github.com/roboflow/supervision)
- [FastAPI](https://fastapi.tiangolo.com/)
"""


def deploy():
    """Main deployment function."""
    print("=" * 60)
    print("  AegisAI → Hugging Face Spaces Deployment")
    print("=" * 60)
    print()

    # Step 1: Check CLI
    print("[1/5] Checking huggingface_hub...")
    check_hf_cli()

    from huggingface_hub import HfApi, create_repo

    api = HfApi()

    # Step 2: Check login
    print("[2/5] Checking HF authentication...")
    try:
        user_info = api.whoami()
        print(f"✓ Logged in as: {user_info['name']}")
    except Exception:
        print("✗ Not logged in. Please run: huggingface-cli login")
        print("  Then paste your token and re-run this script.")
        sys.exit(1)

    # Step 3: Create Space
    print(f"[3/5] Creating Space: {SPACE_ID}...")
    try:
        repo_url = create_repo(
            repo_id=SPACE_ID,
            repo_type="space",
            space_sdk="docker",
            exist_ok=True,
            private=False
        )
        print(f"✓ Space created/exists: {repo_url}")
    except Exception as e:
        print(f"✗ Failed to create space: {e}")
        sys.exit(1)

    # Step 4: Prepare files in a temp directory
    print("[4/5] Preparing files for upload...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Copy project files, excluding unnecessary ones
        for item in PROJECT_DIR.iterdir():
            if item.name in EXCLUDE:
                continue
            if item.suffix in EXCLUDE_EXT:
                continue
            if item.name.startswith("."):
                # Allow .env.example and .dockerignore
                if item.name not in (".env.example", ".dockerignore"):
                    continue

            dst = tmp_path / item.name
            if item.is_dir():
                shutil.copytree(item, dst, ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "*.pyo", ".git", "venv*",
                    "*.mp4", "*.avi", "*.mov", "*.log", "*.pt", "*.pth"
                ))
            else:
                shutil.copy2(item, dst)

        # Copy Dockerfile.hf as Dockerfile (HF requirement)
        hf_dockerfile = PROJECT_DIR / "Dockerfile.hf"
        shutil.copy2(hf_dockerfile, tmp_path / "Dockerfile")

        # Create the Space README.md
        readme_content = create_space_readme()
        (tmp_path / "README.md").write_text(readme_content, encoding="utf-8")

        # Create a .env file with defaults for the space
        env_content = """# AegisAI HF Space Environment
AEGIS_DEBUG=true
AEGIS_API_HOST=0.0.0.0
AEGIS_API_PORT=7860
DATABASE_URL=sqlite:///data/aegis.db
"""
        (tmp_path / ".env").write_text(env_content, encoding="utf-8")

        # Ensure data directories exist
        (tmp_path / "data" / "input").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "output").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "input" / ".gitkeep").touch()
        (tmp_path / "data" / "output" / ".gitkeep").touch()

        # Count files
        file_count = sum(1 for _ in tmp_path.rglob("*") if _.is_file())
        print(f"  Prepared {file_count} files for upload")

        # Step 5: Upload to HF Space
        print(f"[5/5] Uploading to {SPACE_ID}...")
        try:
            api.upload_folder(
                folder_path=str(tmp_path),
                repo_id=SPACE_ID,
                repo_type="space",
                commit_message="Deploy AegisAI v4.2.0 to HF Spaces",
            )
            print(f"✓ Upload complete!")
        except Exception as e:
            print(f"✗ Upload failed: {e}")
            sys.exit(1)

    # Done!
    print()
    print("=" * 60)
    print(f"  ✅ Deployment successful!")
    print(f"  🌐 Space URL: https://huggingface.co/spaces/{SPACE_ID}")
    print(f"  📡 API URL:   https://{HF_USERNAME.lower()}-{SPACE_NAME.lower()}.hf.space")
    print()
    print("  ⚠️  IMPORTANT: Set your API key as a Space secret:")
    print(f"     1. Go to https://huggingface.co/spaces/{SPACE_ID}/settings")
    print(f"     2. Scroll to 'Repository secrets'")
    print(f"     3. Add: AEGIS_API_KEY = <your-secret-key>")
    print("=" * 60)


if __name__ == "__main__":
    deploy()
