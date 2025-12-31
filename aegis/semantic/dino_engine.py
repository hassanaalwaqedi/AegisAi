"""
AegisAI - Grounding DINO Engine
Language-Guided Object Detection Wrapper

This module provides a production-ready wrapper for Grounding DINO,
enabling natural language object detection with lazy loading and
automatic device selection (GPU-first, CPU fallback).

Features:
- Lazy model loading (deferred until first inference)
- Auto device detection with override support
- Standardized output format compatible with YOLO detections
"""

import logging
from typing import List, Optional, Tuple, NamedTuple
from pathlib import Path

import numpy as np

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# Configure module logger
logger = logging.getLogger(__name__)


class SemanticDetection(NamedTuple):
    """
    Semantic detection result container.
    
    Attributes:
        bbox: Bounding box coordinates (x1, y1, x2, y2) in pixels
        confidence: Detection confidence score [0.0, 1.0]
        phrase: The matched text phrase from the prompt
        matched_text: Original text that was matched
    """
    bbox: Tuple[int, int, int, int]
    confidence: float
    phrase: str
    matched_text: str


class DinoEngine:
    """
    Grounding DINO inference engine with lazy loading.
    
    Provides language-guided object detection using Grounding DINO.
    Model is loaded lazily on first inference to optimize startup time.
    
    Attributes:
        config: Semantic configuration parameters
        model: Loaded Grounding DINO model (lazy)
        device: Compute device (cpu/cuda)
        
    Example:
        >>> engine = DinoEngine(config.semantic)
        >>> detections = engine.infer(frame, "person carrying a bag")
        >>> for det in detections:
        ...     print(f"{det.phrase}: {det.confidence:.2f}")
    """
    
    def __init__(self, config):
        """
        Initialize the Grounding DINO engine.
        
        Args:
            config: SemanticConfig instance with model parameters
        """
        self._config = config
        self._model = None
        self._processor = None
        self._device = None
        self._model_loaded = False
        
        logger.info(
            f"DinoEngine initialized with model={config.model_name}, "
            f"box_threshold={config.box_threshold}, "
            f"text_threshold={config.text_threshold}"
        )
    
    @property
    def device(self) -> str:
        """Get the compute device being used."""
        if self._device is None:
            self._device = self._resolve_device()
        return self._device
    
    def _resolve_device(self) -> str:
        """
        Resolve the compute device to use.
        
        Returns:
            Device string ('cuda' or 'cpu')
        """
        if self._config.device_override:
            device = self._config.device_override
            logger.info(f"Using device override: {device}")
            return device
        
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available, using CPU")
            return "cpu"
        
        # GPU-first, CPU fallback
        if torch.cuda.is_available():
            logger.info("CUDA available, using GPU")
            return "cuda"
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            logger.info("MPS available, using Apple Silicon GPU")
            return "mps"
        else:
            logger.info("No GPU available, using CPU")
            return "cpu"
    
    def load_model(self) -> bool:
        """
        Load the Grounding DINO model.
        
        Returns:
            True if model loaded successfully, False otherwise
        """
        if self._model_loaded:
            return True
        
        if not TORCH_AVAILABLE:
            logger.error("PyTorch is required for Grounding DINO")
            return False
        
        try:
            logger.info(f"Loading Grounding DINO model on device: {self.device}")
            
            # Try to import groundingdino
            try:
                from groundingdino.util.inference import load_model, predict
                from groundingdino.util.inference import load_image
                
                # Default model paths - user should set these via environment
                import os
                config_path = os.environ.get(
                    "DINO_CONFIG_PATH",
                    "GroundingDINO/groundingdino/config/GroundingDINO_SwinT_OGC.py"
                )
                weights_path = os.environ.get(
                    "DINO_WEIGHTS_PATH",
                    "weights/groundingdino_swint_ogc.pth"
                )
                
                if Path(config_path).exists() and Path(weights_path).exists():
                    self._model = load_model(config_path, weights_path, device=self.device)
                    self._model_loaded = True
                    logger.info("Grounding DINO model loaded successfully")
                    return True
                else:
                    logger.warning(
                        f"Grounding DINO model files not found. "
                        f"Config: {config_path}, Weights: {weights_path}. "
                        f"Using fallback mode."
                    )
                    return self._load_fallback_model()
                    
            except ImportError:
                logger.warning(
                    "groundingdino package not installed. "
                    "Install with: pip install groundingdino-py"
                )
                return self._load_fallback_model()
                
        except Exception as e:
            logger.error(f"Failed to load Grounding DINO: {e}")
            return False
    
    def _load_fallback_model(self) -> bool:
        """
        Load a fallback/mock model for testing without DINO installed.
        
        Returns:
            True indicating fallback mode is active
        """
        logger.info("Using fallback mode - semantic detection will be simulated")
        self._model = "FALLBACK"
        self._model_loaded = True
        return True
    
    def infer(
        self,
        image: np.ndarray,
        prompt: str,
        box_threshold: Optional[float] = None,
        text_threshold: Optional[float] = None
    ) -> List[SemanticDetection]:
        """
        Perform semantic detection on an image with a text prompt.
        
        Args:
            image: Input image as numpy array (BGR format, HWC layout)
            prompt: Natural language text prompt (e.g., "person with bag")
            box_threshold: Override default box confidence threshold
            text_threshold: Override default text matching threshold
            
        Returns:
            List of SemanticDetection objects for matched regions
        """
        if not self._model_loaded:
            if not self.load_model():
                logger.error("Model not loaded, cannot perform inference")
                return []
        
        box_thresh = box_threshold or self._config.box_threshold
        text_thresh = text_threshold or self._config.text_threshold
        
        # Handle fallback mode
        if self._model == "FALLBACK":
            return self._fallback_infer(image, prompt)
        
        try:
            from groundingdino.util.inference import predict
            import torch
            from PIL import Image
            import cv2
            
            # Convert BGR to RGB
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(image_rgb)
            
            # Normalize prompt
            caption = prompt.lower().strip()
            if not caption.endswith("."):
                caption += "."
            
            # Run inference
            boxes, logits, phrases = predict(
                model=self._model,
                image=pil_image,
                caption=caption,
                box_threshold=box_thresh,
                text_threshold=text_thresh,
                device=self.device
            )
            
            # Convert to standard format
            h, w = image.shape[:2]
            detections = []
            
            for box, logit, phrase in zip(boxes, logits, phrases):
                # Convert normalized coordinates to pixels
                cx, cy, bw, bh = box.tolist()
                x1 = int((cx - bw / 2) * w)
                y1 = int((cy - bh / 2) * h)
                x2 = int((cx + bw / 2) * w)
                y2 = int((cy + bh / 2) * h)
                
                # Clamp to image bounds
                x1 = max(0, min(x1, w - 1))
                y1 = max(0, min(y1, h - 1))
                x2 = max(0, min(x2, w))
                y2 = max(0, min(y2, h))
                
                detection = SemanticDetection(
                    bbox=(x1, y1, x2, y2),
                    confidence=float(logit),
                    phrase=phrase,
                    matched_text=prompt
                )
                detections.append(detection)
            
            logger.debug(f"DINO detected {len(detections)} matches for '{prompt}'")
            return detections
            
        except Exception as e:
            logger.error(f"Grounding DINO inference failed: {e}")
            return []
    
    def _fallback_infer(
        self,
        image: np.ndarray,
        prompt: str
    ) -> List[SemanticDetection]:
        """
        Fallback inference for testing without actual DINO model.
        
        Returns empty list in production, simulated results in debug mode.
        """
        import os
        if os.environ.get("AEGIS_DEBUG", "").lower() == "true":
            # In debug mode, return a simulated detection for testing
            h, w = image.shape[:2]
            logger.debug(f"Fallback: Simulating detection for '{prompt}'")
            return [
                SemanticDetection(
                    bbox=(w // 4, h // 4, 3 * w // 4, 3 * h // 4),
                    confidence=0.75,
                    phrase=prompt.split()[0] if prompt else "object",
                    matched_text=prompt
                )
            ]
        return []
    
    def warmup(self, image_size: Tuple[int, int] = (640, 480)) -> None:
        """
        Perform a warmup inference to initialize model and CUDA kernels.
        
        Args:
            image_size: (width, height) for warmup image
        """
        if not self.load_model():
            logger.warning("Cannot warmup - model not loaded")
            return
        
        w, h = image_size
        dummy_frame = np.zeros((h, w, 3), dtype=np.uint8)
        
        logger.info("Performing DINO warmup...")
        _ = self.infer(dummy_frame, "test warmup")
        logger.info("DINO warmup complete")
    
    def __repr__(self) -> str:
        return (
            f"DinoEngine(model={self._config.model_name}, "
            f"device={self.device}, "
            f"loaded={self._model_loaded})"
        )
