from fastapi import APIRouter, Response

from app import __version__
from app.engine import get_engine
from app.observability.metrics import render_metrics

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    body = get_engine().health()
    body["version"] = __version__
    return body


@router.get("/metrics")
async def metrics() -> Response:
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
