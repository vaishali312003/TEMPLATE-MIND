"""Traceability (rule 6): which input source produced each generated field."""

from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.domain.base import DomainModel, ShortText
from app.domain.enums import FileRole, ProvenanceMethod

FIELD_PATH_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$"
FieldPath = Annotated[str, StringConstraints(pattern=FIELD_PATH_PATTERN, max_length=255)]

# Files whose content can be the source of a value; the template is not a content source.
CONTENT_FILE_ROLES = frozenset(FileRole) - {FileRole.TEMPLATE}


class SourceReference(DomainModel):
    """One piece of evidence for a value: a file, where in it, and how it was read."""

    file_id: UUID | None = None
    file_role: FileRole | None = None
    method: ProvenanceMethod
    locator: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None

    @model_validator(mode="after")
    def _validate_source(self) -> Self:
        if self.method is ProvenanceMethod.USER_EDIT:
            if self.file_id is not None or self.file_role is not None:
                raise ValueError("a user edit must not reference a source file")
            return self
        if self.file_id is None or self.file_role is None:
            raise ValueError("file_id and file_role are required unless the method is user_edit")
        if self.file_role not in CONTENT_FILE_ROLES:
            raise ValueError("file_role must be a content role, not 'template'")
        return self


class FieldProvenance(DomainModel):
    """All sources behind one field, addressed by a dotted path.

    Path conventions (build them with the helpers below):
      * Event Data:      ``details.<key>``, ``attendance.statistics.total_participants`` ...
      * Document field:  ``document.fields.<key>``
      * Section field:   ``sections.<section_id>.fields.<key>``
    """

    field_path: FieldPath
    sources: list[SourceReference] = Field(min_length=1)
    note: ShortText | None = None


def event_detail_path(key: str) -> str:
    return f"details.{key}"


def document_field_path(key: str) -> str:
    return f"document.fields.{key}"


def section_field_path(section_id: str, field_key: str) -> str:
    return f"sections.{section_id}.fields.{field_key}"
