# core/apps/__init__.py
"""Application registry, normalization, and installed application detection package."""

from core.apps.aliases import (
    APPLICATION_ALIASES,
    PLUGIN_ALIASES,
    WEBSITE_ALIASES,
)
from core.apps.detector import (
    InstalledAppDetector,
    InstalledAppInfo,
    get_installed_app_detector,
)
from core.apps.registry import (
    AppDefinition,
    ApplicationRegistry,
    get_application_registry,
)
from core.apps.resolver import (
    AppResolver,
    ResolvedApp,
    SYSTEM_APP_DEFINITIONS,
    SystemAppSpec,
    get_app_resolver,
)

__all__ = [
    "AppDefinition",
    "ApplicationRegistry",
    "get_application_registry",
    "InstalledAppDetector",
    "InstalledAppInfo",
    "get_installed_app_detector",
    "AppResolver",
    "ResolvedApp",
    "SYSTEM_APP_DEFINITIONS",
    "SystemAppSpec",
    "get_app_resolver",
    "APPLICATION_ALIASES",
    "WEBSITE_ALIASES",
    "PLUGIN_ALIASES",
]

