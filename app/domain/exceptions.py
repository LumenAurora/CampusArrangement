class DomainError(Exception):
    """Base domain exception."""


class PermissionDenied(DomainError):
    """Raised when user lacks permission."""


class CapacityExceeded(DomainError):
    """Raised when slot capacity is exceeded."""


class ValidationError(DomainError):
    """Raised when inputs are invalid."""
