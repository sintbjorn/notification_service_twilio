from .base import *  # noqa: F403

DEBUG = env_bool("DJANGO_DEBUG", True)  # noqa: F405
ALLOWED_HOSTS = env_list(  # noqa: F405
    "DJANGO_ALLOWED_HOSTS",
    ["localhost", "127.0.0.1", "0.0.0.0"],
)
CSRF_TRUSTED_ORIGINS = env_list(  # noqa: F405
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    ["http://localhost:8000", "http://127.0.0.1:8000"],
)

AUTH_PASSWORD_VALIDATORS = []
