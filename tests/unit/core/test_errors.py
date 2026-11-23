import pytest

from app.core import errors
from app.core.errors import AppError, ErrorCategory


def _all_subclasses(cls: type[AppError]) -> list[type[AppError]]:
    found: list[type[AppError]] = []
    for subclass in cls.__subclasses__():
        found.append(subclass)
        found.extend(_all_subclasses(subclass))
    return found


def test_base_error_defaults() -> None:
    error = AppError("something broke")

    assert str(error) == "something broke"
    assert error.message == "something broke"
    assert error.code == "internal_error"
    assert error.category is ErrorCategory.INTERNAL
    assert error.details == {}
    assert error.is_client_error is False


def test_code_can_be_overridden_per_instance() -> None:
    error = errors.NotFoundError("template 7 not found", code="template_not_found")

    assert error.code == "template_not_found"
    assert error.category is ErrorCategory.NOT_FOUND


def test_details_are_copied_not_shared() -> None:
    source = {"field": "event_date"}
    error = errors.UnprocessableContentError("bad date", details=source)
    source["field"] = "mutated"

    assert error.details == {"field": "event_date"}


def test_to_dict_returns_independent_copy() -> None:
    error = errors.InvalidInputError("bad input", details={"a": 1})
    payload = error.to_dict()
    payload["details"]["a"] = 2

    assert error.details == {"a": 1}
    assert error.to_dict() == {
        "code": "invalid_input",
        "message": "bad input",
        "details": {"a": 1},
    }


@pytest.mark.parametrize(
    ("error_class", "category", "code", "is_client"),
    [
        (errors.ConfigurationError, ErrorCategory.INTERNAL, "configuration_error", False),
        (errors.InvalidInputError, ErrorCategory.INVALID_INPUT, "invalid_input", True),
        (
            errors.UnsupportedFileTypeError,
            ErrorCategory.INVALID_INPUT,
            "unsupported_file_type",
            True,
        ),
        (errors.FileTooLargeError, ErrorCategory.INVALID_INPUT, "file_too_large", True),
        (errors.CorruptedFileError, ErrorCategory.INVALID_INPUT, "corrupted_file", True),
        (errors.DocumentParsingError, ErrorCategory.INVALID_INPUT, "document_parsing_error", True),
        (
            errors.UnprocessableContentError,
            ErrorCategory.INVALID_INPUT,
            "unprocessable_content",
            True,
        ),
        (errors.NotFoundError, ErrorCategory.NOT_FOUND, "not_found", True),
        (errors.ConflictError, ErrorCategory.CONFLICT, "conflict", True),
        (errors.InvalidStateError, ErrorCategory.CONFLICT, "invalid_state", True),
        (errors.LLMError, ErrorCategory.UPSTREAM, "llm_error", False),
        (errors.LLMOutputValidationError, ErrorCategory.UPSTREAM, "llm_output_invalid", False),
        (errors.OCRError, ErrorCategory.UPSTREAM, "ocr_error", False),
        (errors.LibreOfficeError, ErrorCategory.UPSTREAM, "libreoffice_error", False),
        (errors.StorageError, ErrorCategory.UPSTREAM, "storage_error", False),
        (errors.RenderingError, ErrorCategory.INTERNAL, "rendering_error", False),
        (errors.PersistenceError, ErrorCategory.INTERNAL, "persistence_error", False),
    ],
)
def test_error_contract(
    error_class: type[AppError], category: ErrorCategory, code: str, is_client: bool
) -> None:
    error = error_class("message")

    assert error.category is category
    assert error.code == code
    assert error.is_client_error is is_client


def test_hierarchy_allows_catching_by_base_class() -> None:
    assert issubclass(errors.UnsupportedFileTypeError, errors.UploadError)
    assert issubclass(errors.UploadError, errors.InvalidInputError)
    assert issubclass(errors.LLMOutputValidationError, errors.LLMError)
    assert issubclass(errors.LLMError, errors.ExternalServiceError)
    assert issubclass(errors.InvalidStateError, errors.ConflictError)
    assert issubclass(errors.MappingError, errors.ProcessingError)

    with pytest.raises(errors.UploadError):
        raise errors.FileTooLargeError("too big")
    with pytest.raises(AppError):
        raise errors.StorageError("disk unavailable")


def test_default_codes_are_unique_across_the_hierarchy() -> None:
    codes = [AppError.default_code] + [cls.default_code for cls in _all_subclasses(AppError)]

    assert len(codes) == len(set(codes))
