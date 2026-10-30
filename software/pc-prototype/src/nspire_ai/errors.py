"""Domain-specific exceptions."""


class NspireAIError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(NspireAIError):
    """Raised when runtime configuration is invalid."""


class ProviderError(NspireAIError):
    """Raised when a provider cannot process a request."""


class ConversationError(NspireAIError):
    """Base class for safe conversation API errors."""


class ConversationNotFoundError(ConversationError):
    """Raised when a conversation ID is unknown or has been deleted."""


class ConversationProviderError(ConversationError):
    """Raised when a provider cannot complete a conversation turn."""


class ContextLimitError(ConversationError):
    """Raised when required context does not fit configured limits."""
