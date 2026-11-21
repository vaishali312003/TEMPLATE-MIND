"""Validation findings produced by the validation engine."""

from pydantic import Field

from app.domain.base import DomainModel, Identifier, LongText
from app.domain.enums import ValidationCode, ValidationOrigin, ValidationSeverity


class ValidationIssue(DomainModel):
    code: ValidationCode
    severity: ValidationSeverity
    origin: ValidationOrigin
    message: LongText
    section_id: Identifier | None = None
    field_key: Identifier | None = None


class ValidationReport(DomainModel):
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is ValidationSeverity.WARNING]

    @property
    def has_errors(self) -> bool:
        return any(i.severity is ValidationSeverity.ERROR for i in self.issues)
