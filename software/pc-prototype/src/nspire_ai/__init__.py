"""Provider-neutral foundation for the NSPIRE AI PC prototype."""

from nspire_ai.config import Settings
from nspire_ai.conversations import ConversationEngine, create_conversation_engine
from nspire_ai.errors import (
    ConfigurationError,
    ContextLimitError,
    ConversationError,
    ConversationNotFoundError,
    ConversationProviderError,
    ConversationStorageConflictError,
    ConversationStorageCorruptionError,
    ConversationStorageError,
    ProviderError,
    NspireAIError,
)
from nspire_ai.messages import Message
from nspire_ai.providers.base import AIProvider, ProviderResponse
from nspire_ai.storage import ConversationSummary
from nspire_ai.protocol import (
    PROTOCOL_VERSION,
    ProtocolRequest,
    ProtocolResponse,
    ProtocolValidationError,
)

__all__ = [
    "AIProvider",
    "ConfigurationError",
    "ContextLimitError",
    "ConversationEngine",
    "ConversationError",
    "ConversationNotFoundError",
    "ConversationProviderError",
    "ConversationStorageConflictError",
    "ConversationStorageCorruptionError",
    "ConversationStorageError",
    "ConversationSummary",
    "NspireAIError",
    "Message",
    "ProviderError",
    "ProviderResponse",
    "PROTOCOL_VERSION",
    "ProtocolRequest",
    "ProtocolResponse",
    "ProtocolValidationError",
    "Settings",
    "create_conversation_engine",
]
