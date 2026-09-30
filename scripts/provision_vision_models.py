"""Provision approved vision assets during the Docker image build.

Application runtime accepts only local checkpoints and, for prompted YOLOE,
only precomputed local embeddings. Network-backed prompt initialization is
strictly a build-time concern.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from ultralytics import YOLO, YOLOE


MODEL_DIRECTORY = Path("/app/models")


def names(configured_path_env: str, candidates_env: str) -> list[str]:
    configured = Path(os.environ[configured_path_env]).name
    candidates = os.environ.get(candidates_env, "").split()
    return list(dict.fromkeys(name for name in [configured, *candidates] if name))


def provision_checkpoint(checkpoint_name: str, model_class) -> Path:
    destination = MODEL_DIRECTORY / checkpoint_name
    if destination.is_file() and destination.stat().st_size > 0:
        return destination
    model_class(checkpoint_name)
    downloaded = Path(checkpoint_name)
    if not downloaded.is_file() or downloaded.stat().st_size == 0:
        raise RuntimeError(f"Ultralytics did not create checkpoint: {checkpoint_name}")
    if downloaded.resolve() != destination.resolve():
        shutil.move(str(downloaded), destination)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"Checkpoint provisioning failed: {destination}")
    print(f"Provisioned checkpoint: {destination}")
    return destination


def threat_prompts() -> list[str]:
    prompts = json.loads(os.environ["AEGIS_THREAT_CLASSES_JSON"])
    if not isinstance(prompts, list) or not prompts or not all(isinstance(item, str) and item for item in prompts):
        raise ValueError("AEGIS_THREAT_CLASSES_JSON must be a non-empty JSON string list")
    return prompts


def threat_embedding_path(checkpoint: Path) -> Path:
    if checkpoint.name == Path(os.environ["AEGIS_THREAT_MODEL_PATH"]).name:
        return Path(os.environ["AEGIS_THREAT_PROMPT_EMBEDDINGS_PATH"])
    return MODEL_DIRECTORY / f"{checkpoint.stem}.threat-prompts.npz"


def provision_yoloe() -> None:
    prompts = threat_prompts()
    for checkpoint_name in names("AEGIS_THREAT_MODEL_PATH", "AEGIS_THREAT_BENCHMARK_MODEL_NAMES"):
        checkpoint = provision_checkpoint(checkpoint_name, YOLOE)
        embeddings = threat_embedding_path(checkpoint)
        if embeddings.is_file() and embeddings.stat().st_size > 0:
            print(f"Using provisioned YOLOE prompt embeddings: {embeddings}")
            continue
        model = YOLOE(str(checkpoint))
        # Sole set_classes call: build-time only. It downloads mobileclip2_b.ts
        # and creates a checkpoint-bound embedding profile in /app/models.
        model.set_classes(prompts)
        model.save_prompt_embeddings(embeddings)
        if not embeddings.is_file() or embeddings.stat().st_size == 0:
            raise RuntimeError(f"YOLOE prompt embedding provisioning failed: {embeddings}")
        print(f"Provisioned YOLOE prompt embeddings: {embeddings}")


def main() -> None:
    MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    os.chdir(MODEL_DIRECTORY)
    for checkpoint_name in names("AEGIS_DETECTION_MODEL_PATH", "AEGIS_BENCHMARK_MODEL_NAMES"):
        provision_checkpoint(checkpoint_name, YOLO)
    provision_yoloe()


if __name__ == "__main__":
    main()
