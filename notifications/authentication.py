from dataclasses import dataclass

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication, exceptions


@dataclass(frozen=True)
class ServicePrincipal:
    name: str = "notification-service-client"
    pk: str = "notification-service-client"
    is_authenticated: bool = True


class APIKeyAuthentication(authentication.BaseAuthentication):
    keyword = "Api-Key"
    header = "HTTP_X_API_KEY"

    def authenticate(self, request):
        expected_key = getattr(settings, "NOTIFICATION_API_KEY", "")
        provided_key = request.META.get(self.header)

        if not provided_key:
            authorization = authentication.get_authorization_header(request).decode("utf-8")
            if authorization.startswith(f"{self.keyword} "):
                provided_key = authorization.removeprefix(f"{self.keyword} ").strip()

        if not provided_key:
            return None

        if not expected_key or provided_key != expected_key:
            raise exceptions.AuthenticationFailed(_("Invalid API key."))

        return ServicePrincipal(), None

    def authenticate_header(self, request):
        return self.keyword


class APIKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "notifications.authentication.APIKeyAuthentication"
    name = "ApiKeyAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": (
                "Service-to-service API key. Use the `X-API-Key` header for REST "
                "notification endpoints and protected operational endpoints."
            ),
        }
