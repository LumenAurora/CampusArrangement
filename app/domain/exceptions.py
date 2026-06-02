class DomainError(Exception):
    pass


class PermissionDenied(DomainError):
    pass


class CapacityExceeded(DomainError):
    pass


class ValidationError(DomainError):
    pass


class ConflictError(DomainError):
    pass
