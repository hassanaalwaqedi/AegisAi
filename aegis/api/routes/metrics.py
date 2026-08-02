"""Protected infrastructure metrics; intentionally not part of operator UI."""

from fastapi import APIRouter, Response

from aegis.video.metrics import metrics_payload

router = APIRouter(prefix="/metrics", tags=["diagnostics"])


@router.get("", include_in_schema=False)
def prometheus_metrics() -> Response:
    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type)
