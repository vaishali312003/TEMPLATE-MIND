"""Domain exception hierarchy.

Every layer raises these errors instead of bare exceptions. Each error carries:

* ``category``: how the failure should be treated by the API layer (the HTTP mapping lives in
  ``app/api/middleware/error_handlers.py`` and never in this module).
* ``code``: a stable machine-readable identifier clients can rely on.
* ``details``: structured, non-secret context for logs and, for client errors, for responses.

Messages of non-client errors (``upstream`` and ``internal``) may contain operational detail and
must not be returned to API clients verbatim.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, ClassVar


class ErrorCategory(StrEnum):
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UPSTREAM = "upstream"
    INTERNAL = "internal"


_CLIENT_CATEGORIES = frozenset(
    {ErrorCategory.INVALID_INPUT, ErrorCategory.NOT_FOUND, ErrorCategory.CONFLICT}
)


class AppError(Exception):
    """Base class of all application errors."""

    category: ClassVar[ErrorCategory] = ErrorCategory.INTERNAL
    default_code: ClassVar[str] = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.default_code
        self.details: dict[str, Any] = dict(details) if details else {}

    @property
    def is_client_error(self) -> bool:
        """True when the message is safe and useful to show to the API caller."""
        return self.category in _CLIENT_CATEGORIES

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


class ConfigurationError(AppError):
    """The application is misconfigured (missing or invalid settings)."""

    default_code = "configuration_error"


# --------------------------------------------------------------------------------------------
# Client errors
# --------------------------------------------------------------------------------------------


class InvalidInputError(AppError):
    """The request or an uploaded file is invalid."""

    category = ErrorCategory.INVALID_INPUT
    default_code = "invalid_input"


class UploadError(InvalidInputError):
    """An uploaded file was rejected."""

    default_code = "upload_error"


class UnsupportedFileTypeError(UploadError):
    default_code = "unsupported_file_type"


class FileTooLargeError(UploadError):
    default_code = "file_too_large"


class CorruptedFileError(UploadError):
    """The file content does not match its declared type or cannot be opened."""

    default_code = "corrupted_file"


class DocumentParsingError(InvalidInputError):
    """A template or document could not be parsed into blocks."""

    default_code = "document_parsing_error"


class UnprocessableContentError(InvalidInputError):
    """Uploaded content (attendance, feedback, event data) is readable but unusable."""

    default_code = "unprocessable_content"


class NotFoundError(AppError):
    category = ErrorCategory.NOT_FOUND
    default_code = "not_found"


class ConflictError(AppError):
    category = ErrorCategory.CONFLICT
    default_code = "conflict"


class InvalidStateError(ConflictError):
    """The operation is not allowed in the entity's current state."""

    default_code = "invalid_state"


# --------------------------------------------------------------------------------------------
# Upstream errors (external systems)
# --------------------------------------------------------------------------------------------


class ExternalServiceError(AppError):
    """An external system (LLM, OCR, LibreOffice, storage, ...) failed."""

    category = ErrorCategory.UPSTREAM
    default_code = "external_service_error"


class LLMError(ExternalServiceError):
    default_code = "llm_error"


class LLMOutputValidationError(LLMError):
    """The LLM response could not be validated against the required schema."""

    default_code = "llm_output_invalid"


class EmbeddingError(ExternalServiceError):
    default_code = "embedding_error"


class VisionError(ExternalServiceError):
    default_code = "vision_error"


class OCRError(ExternalServiceError):
    default_code = "ocr_error"


class LibreOfficeError(ExternalServiceError):
    default_code = "libreoffice_error"


class StorageError(ExternalServiceError):
    default_code = "storage_error"


# --------------------------------------------------------------------------------------------
# Internal errors
# --------------------------------------------------------------------------------------------


class ProcessingError(AppError):
    """A pipeline step failed for a reason that is not the caller's fault."""

    default_code = "processing_error"


class TemplateSchemaError(ProcessingError):
    default_code = "template_schema_error"


class MappingError(ProcessingError):
    default_code = "mapping_error"


class RenderingError(ProcessingError):
    default_code = "rendering_error"


class PersistenceError(AppError):
    """A database operation failed."""

    default_code = "persistence_error"
