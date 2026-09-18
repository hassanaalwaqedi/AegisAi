"""Explicit one-time model provisioning. Runtime performs no downloads.

Run: python scripts/setup_evidence_search.py
Apply schema separately: python -m alembic upgrade head
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from huggingface_hub import snapshot_download
from aegis.semantic.embedding import MODEL, REVISION

if __name__ == "__main__":
    snapshot_download(MODEL, revision=REVISION, allow_patterns=[
        "config.json", "model.safetensors", "tokenizer*", "special_tokens_map.json", "sentencepiece.bpe.model",
    ])
    print("Pinned evidence encoder downloaded. Restart the API to index stored evidence.")
