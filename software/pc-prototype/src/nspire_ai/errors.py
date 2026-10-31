"""Domain-specific exceptions."""


class NspireAIError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(NspireAIError):
    """Raised when runtime configuration is invalid."""


class ProviderError(NspireAIError):
    """Sanitized provider failure with a stable, non-sensitive category code."""

    def __init__(self, message: str, *, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code


class ConversationError(NspireAIError):
    """Base class for safe conversation API errors."""


class ConversationNotFoundError(ConversationError):
    """Raised when a conversation ID is unknown or has been deleted."""


class ConversationProviderError(ConversationError):
    """Safe conversation failure retaining the provider's stable category code."""

    def __init__(self, message: str, *, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code


class ContextLimitError(ConversationError):
    """Raised when required context does not fit configured limits."""


class ConversationStorageError(ConversationError):
    """Raised when conversation storage cannot safely complete an operation."""


class ConversationStorageCorruptionError(ConversationStorageError):
    """Raised when persisted conversation data fails integrity or validation checks."""


class ConversationStorageConflictError(ConversationStorageError):
    """Raised when another engine changed a conversation during provider execution."""
