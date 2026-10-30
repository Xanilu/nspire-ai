"""Domain-specific exceptions."""


class NspireAIError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(NspireAIError):
    """Raised when runtime configuration is invalid."""


class ProviderError(NspireAIError):
    """Raised when a provider cannot process a request."""
