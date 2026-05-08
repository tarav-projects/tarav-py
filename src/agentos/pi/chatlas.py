from __future__ import annotations


PI_CHATLAS_DEFAULT_INCLUDES = (
    "sessions/**",
    "settings.json",
)

PI_CHATLAS_DEFAULT_EXCLUDES = (
    "auth.json",
    "bin/",
)


__all__ = [
    "PI_CHATLAS_DEFAULT_EXCLUDES",
    "PI_CHATLAS_DEFAULT_INCLUDES",
]
