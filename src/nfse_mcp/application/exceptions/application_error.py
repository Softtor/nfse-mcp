"""Application-level errors.

These are raised by Application Services and caught by presentation layers
(MCP, API, CLI) to be converted into appropriate response formats.
"""


class ApplicationError(Exception):
    """Base error for application layer."""

    def __init__(self, message: str, code: str = "APPLICATION_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ClientNotFoundError(ApplicationError):
    """Raised when a client is required but not found."""

    def __init__(self, document: str):
        super().__init__(
            f"Cliente com documento {document} nao encontrado.",
            code="CLIENT_NOT_FOUND",
        )


class ClientMissingDataError(ApplicationError):
    """Raised when client data is incomplete for an operation."""

    def __init__(self, document: str, field: str):
        super().__init__(
            f"Cliente {document} esta sem o campo obrigatorio: {field}.",
            code="CLIENT_MISSING_DATA",
        )


class InvoiceError(ApplicationError):
    """Raised when invoice issuance fails."""

    def __init__(self, message: str, errors: list[dict] | None = None):
        self.errors = errors or []
        super().__init__(message, code="INVOICE_ERROR")


class ParameterError(ApplicationError):
    """Raised when municipal parameter query fails."""

    def __init__(self, message: str):
        super().__init__(message, code="PARAMETER_ERROR")
