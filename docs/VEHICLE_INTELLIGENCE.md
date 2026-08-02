# Vehicle intelligence runtime

Vehicle enrichment is an optional sidecar for the existing live camera path:

```text
existing detector -> existing ByteTrack tracker -> existing risk logic
                                    -> optional vehicle sidecar
                                       -> quality gate -> scheduled enrichment
                                       -> candidate deduplication -> restricted evidence
```

It is called only after normal detection, tracking, and risk scoring have
completed. A disabled feature, missing model, missing OCR package, invalid
crop, or an enrichment exception cannot stop camera ingestion or alter a risk
result.

## Safe defaults

All vehicle features are disabled by default. Copy the documented values in
`.env.example` to a server-only `.env` only after supplying local models:

- `VEHICLE_ENRICHMENT_ENABLED=true` enables the sidecar.
- `PLATE_OCR_ENABLED=true` requires a configured `PLATE_DETECTOR_MODEL_PATH`
  and `PLATE_OCR_MODEL_DIR`. A generic vehicle detector is not used as a fake
  plate detector.
- `VEHICLE_COLOR_ENABLED=true` enables conservative HSV colour estimates.
- `VEHICLE_MAKE_MODEL_ENABLED=true` requires a specialist model, labels, and
  architecture in local paths. Without them its honest response is
  `model_not_configured`.
- `INFERENCE_BACKEND=torch` is the supported default. `tensorrt` is reserved
  for a separately validated deployment and is not required for development.

No model is downloaded automatically. Invalid OCR is never saved or emitted as
a plate value. Standard tracks and detections contain only sanitised enrichment
state; raw OCR candidates, plate text, fingerprints, stream URLs, and image
data are never in the metrics endpoint or operator payloads.

## PaddleOCR isolation

The primary Aegis runtime uses `opencv-python`. Current PaddleOCR dependency
resolution pulls `opencv-contrib-python`, which must not be installed alongside
it. For that reason PaddleOCR is declared in
`requirements-vehicle-ocr-isolated.txt` for an isolated OCR worker/service,
not the primary server environment. Configure a secure service boundary before
connecting that worker; the present adapter honestly returns unavailable until
an OCR provider and local model are configured.

## Rate limiting, quality, and deduplication

The scheduler retains only the sharpest accepted crop per internal
`camera_id`/tracker ID and runs at most once every
`VEHICLE_ENRICHMENT_INTERVAL_SECONDS` (default 1.5 seconds). Crops fail closed
when small, dark, blurry, or invalid. Near-identical candidate frames for the
same camera and tracked vehicle are suppressed using perceptual hashes; manual
and high-priority evidence bypass suppression. The cache is bounded and has a
TTL.

Prometheus metrics are available at protected `GET /metrics` for infrastructure
diagnostics only. They contain no labels, which prevents accidental plate,
camera, or URL disclosure.

## Privacy and accuracy limitations

The current restricted evidence store is process-local and bounded; it has no
RBAC-protected retrieval route, persistent audit trail, retention workflow, or
operator UI. It is therefore not a production plate-evidence system. Add a
reviewed RBAC/audit/retention service before exposing plate values. Colour is a
conservative estimate, and make/model output is unavailable without a
specialist, locally supplied and validated model. OCR and Turkish plate
validation are assistance signals, not identity verification.

## TensorRT decision

This machine has an RTX 5060 GPU and NVIDIA driver, but the active development
environment uses Python 3.14 with CPU-only PyTorch. TensorRT was deliberately
not installed because that combination is not a validated compatible runtime.
Use the existing PyTorch/Ultralytics path. A future TensorRT deployment must
pin a compatible Python, CUDA, TensorRT, PyTorch, and exported engine set in a
separate GPU environment.
