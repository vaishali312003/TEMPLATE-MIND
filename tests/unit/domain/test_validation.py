import pytest
from pydantic import ValidationError

from app.domain.enums import ValidationCode, ValidationOrigin, ValidationSeverity
from app.domain.validation import ValidationIssue, ValidationReport


def issue(
    severity: ValidationSeverity = ValidationSeverity.ERROR,
    code: ValidationCode = ValidationCode.MISSING_REQUIRED_FIELD,
    **overrides: str,
) -> ValidationIssue:
    values = {"message": "Venue is required but missing", "section_id": "event_overview"}
    values.update(overrides)
    return ValidationIssue(code=code, severity=severity, origin=ValidationOrigin.RULE, **values)


def test_empty_report_has_no_errors() -> None:
    report = ValidationReport()

    assert report.issues == []
    assert report.errors == []
    assert report.warnings == []
    assert report.has_errors is False


def test_report_separates_errors_and_warnings() -> None:
    error = issue(ValidationSeverity.ERROR)
    warning = issue(ValidationSeverity.WARNING, ValidationCode.UNSUPPORTED_ELEMENT)
    report = ValidationReport(issues=[warning, error])

    assert report.errors == [error]
    assert report.warnings == [warning]
    assert report.has_errors is True


def test_warnings_alone_are_not_errors() -> None:
    report = ValidationReport(issues=[issue(ValidationSeverity.WARNING)])

    assert report.has_errors is False


def test_issue_message_is_required() -> None:
    with pytest.raises(ValidationError):
        issue(message="   ")


def test_issue_locations_must_be_identifiers() -> None:
    with pytest.raises(ValidationError):
        issue(section_id="Event Overview")
    with pytest.raises(ValidationError):
        issue(field_key="Venue")


def test_document_level_issue_needs_no_section() -> None:
    result = ValidationIssue(
        code=ValidationCode.SEMANTIC_INCONSISTENCY,
        severity=ValidationSeverity.WARNING,
        origin=ValidationOrigin.SEMANTIC,
        message="The report title does not match the event name.",
    )

    assert result.section_id is None
    assert result.field_key is None


def test_json_round_trip() -> None:
    original = ValidationReport(
        issues=[issue(field_key="venue"), issue(ValidationSeverity.WARNING)]
    )

    assert ValidationReport.model_validate(original.model_dump(mode="json")) == original
