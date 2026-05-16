from django.core.cache import cache
from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.decorators import api_view


@extend_schema(
    tags=["System"],
    summary="Liveness probe",
    description="Returns 200 when the Django process is running.",
    responses={200: OpenApiResponse(description="Process is alive.")},
)
@api_view(["GET"])
def health_live(request):
    return JsonResponse({"status": "ok"})


@extend_schema(
    tags=["System"],
    summary="Readiness probe",
    description="Checks database and cache/broker connectivity.",
    responses={
        200: OpenApiResponse(description="Service is ready."),
        503: OpenApiResponse(description="A required dependency is unavailable."),
    },
)
@api_view(["GET"])
def health_ready(request):
    checks = {
        "database": _database_ready(),
        "cache": _cache_ready(),
    }
    status_code = 200 if all(checks.values()) else 503
    return JsonResponse(
        {"status": "ok" if status_code == 200 else "error", "checks": checks},
        status=status_code,
    )


def _database_ready() -> bool:
    try:
        connections["default"].ensure_connection()
    except OperationalError:
        return False
    return True


def _cache_ready() -> bool:
    try:
        cache.set("health-ready", "ok", timeout=5)
        return cache.get("health-ready") == "ok"
    except Exception:
        return False
