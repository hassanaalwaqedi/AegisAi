"""Pinned multilingual text encoder. Runtime never downloads model weights."""
from functools import lru_cache
import threading

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_KEY = f"{MODEL}@{REVISION}:mean-normalized-v1"


class EvidenceEncoder:
    def __init__(self):
        self.ready = False
        self._lock = threading.RLock()
        self._model = None
        self._tokenizer = None

    def load(self):
        with self._lock:
            if self.ready:
                return
            from transformers import AutoModel, AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, local_files_only=True)
            self._model = AutoModel.from_pretrained(MODEL, revision=REVISION, local_files_only=True, use_safetensors=True).eval()
            self.ready = True

    def encode(self, texts: list[str]) -> list[list[float]]:
        import torch
        self.load()
        with self._lock, torch.inference_mode():
            tokens = self._tokenizer(texts, padding=True, truncation=True, max_length=128, return_tensors="pt")
            output = self._model(**tokens).last_hidden_state
            mask = tokens["attention_mask"].unsqueeze(-1).expand(output.size()).float()
            pooled = (output * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            return torch.nn.functional.normalize(pooled, p=2, dim=1).tolist()

    @lru_cache(maxsize=128)
    def query(self, text: str) -> tuple[float, ...]:
        return tuple(self.encode([text])[0])
