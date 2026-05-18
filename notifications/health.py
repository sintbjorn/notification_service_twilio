from django.core.cache import cache
from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.decorators import api_view

from .serializers import HealthLiveSerializer, HealthReadySerializer


@extend_schema(
    tags=["System"],
    summary="Liveness probe",
    description="Returns 200 when the Django process is running.",
    auth=[],
    responses={
        200: OpenApiResponse(HealthLiveSerializer, description="Process is alive."),
    },
    examples=[
        OpenApiExample(
            "Live",
            value={"status": "ok"},
            response_only=True,
            status_codes=["200"],
        )
    ],
)
@api_view(["GET"])
def health_live(request):
    return JsonResponse({"status": "ok"})


@extend_schema(
    tags=["System"],
    summary="Readiness probe",
    description="Checks database and cache/broker connectivity.",
    auth=[],
    responses={
        200: OpenApiResponse(HealthReadySerializer, description="Service is ready."),
        503: OpenApiResponse(
            HealthReadySerializer,
            description="A required dependency is unavailable.",
        ),
    },
    examples=[
        OpenApiExample(
            "Ready",
            value={"status": "ok", "checks": {"database": True, "cache": True}},
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Dependency unavailable",
            value={"status": "error", "checks": {"database": True, "cache": False}},
            response_only=True,
            status_codes=["503"],
        ),
    ],
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
