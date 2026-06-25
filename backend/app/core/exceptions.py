class ProviderConfigError(Exception):
    """Raised when a required API key or provider configuration is missing."""


class AudioValidationError(Exception):
    """Raised when an uploaded audio file fails validation."""
