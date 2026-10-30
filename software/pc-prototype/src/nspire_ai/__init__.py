"""Provider-neutral foundation for the NSPIRE AI PC prototype."""

from nspire_ai.config import Settings
from nspire_ai.errors import ConfigurationError, ProviderError, NspireAIError
from nspire_ai.providers.base import AIProvider, ProviderResponse
from nspire_ai.protocol import (
    PROTOCOL_VERSION,
    ProtocolRequest,
    ProtocolResponse,
    ProtocolValidationError,
)

__all__ = [
    "AIProvider",
    "ConfigurationError",
    "NspireAIError",
    "ProviderError",
    "ProviderResponse",
    "PROTOCOL_VERSION",
    "ProtocolRequest",
    "ProtocolResponse",
    "ProtocolValidationError",
    "Settings",
]
