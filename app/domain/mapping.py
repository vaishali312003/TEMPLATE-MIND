"""Result of semantic mapping: which Event Data content belongs in which template slot.

The mapper (LLM) fills these models; the renderer only follows them. All references are
closed enums or identifiers so the LLM cannot point at content that does not exist as a type.
Checking that referenced section ids and field keys exist in a given TemplateSchema is the
job of the mapper and the validation module, because it needs both objects.
"""

from typing import Self

from pydantic import Field, model_validator

from app.domain.base import DomainModel, Identifier, LongText, ensure_unique
from app.domain.enums import ColumnSourceKind, ContentSourceKind, StatisticKey

ATTENDANCE_STATISTIC_KEYS = frozenset(
    {
        StatisticKey.TOTAL_PARTICIPANTS,
        StatisticKey.PRESENT_COUNT,
        StatisticKey.ABSENT_COUNT,
        StatisticKey.ATTENDANCE_PERCENTAGE,
    }
)
FEEDBACK_STATISTIC_KEYS = frozenset(
    {StatisticKey.FEEDBACK_RESPONSE_COUNT, StatisticKey.OVERALL_AVERAGE_RATING}
)
_STATISTICS_BY_KIND: dict[ContentSourceKind, frozenset[StatisticKey]] = {
    ContentSourceKind.ATTENDANCE_STATISTICS: ATTENDANCE_STATISTIC_KEYS,
    ContentSourceKind.FEEDBACK_STATISTICS: FEEDBACK_STATISTIC_KEYS,
}


class ContentReference(DomainModel):
    """A pointer into Event Data."""

    kind: ContentSourceKind
    detail_key: Identifier | None = None  # required exactly for kind == detail
    statistic: StatisticKey | None = None  # one named statistic; None means the whole block

    @model_validator(mode="after")
    def _validate_reference(self) -> Self:
        if (self.kind is ContentSourceKind.DETAIL) != (self.detail_key is not None):
            raise ValueError("detail_key is required exactly when kind is 'detail'")
        if self.statistic is not None:
            allowed = _STATISTICS_BY_KIND.get(self.kind)
            if allowed is None or self.statistic not in allowed:
                raise ValueError(f"statistic '{self.statistic}' does not belong to '{self.kind}'")
        return self


class FieldAssignment(DomainModel):
    """Fill one template field with one value."""

    field_key: Identifier
    source: ContentReference
    confidence: float = Field(ge=0, le=1)
    rationale: LongText | None = None

    @model_validator(mode="after")
    def _validate_single_value(self) -> Self:
        if self.source.kind is not ContentSourceKind.DETAIL and self.source.statistic is None:
            raise ValueError("a single field can only be filled by a detail or one named statistic")
        return self


class ColumnAssignment(DomainModel):
    """Fill one table column."""

    template_column_index: int = Field(ge=0)
    source_kind: ColumnSourceKind
    attendance_column_key: Identifier | None = None  # required exactly for attendance_column

    @model_validator(mode="after")
    def _validate_source(self) -> Self:
        is_column = self.source_kind is ColumnSourceKind.ATTENDANCE_COLUMN
        if is_column != (self.attendance_column_key is not None):
            raise ValueError(
                "attendance_column_key is required exactly when source_kind is 'attendance_column'"
            )
        return self


class SectionMapping(DomainModel):
    section_id: Identifier
    # Content placed in the section as a whole, in rendering order.
    content: list[ContentReference] = Field(default_factory=list)
    field_assignments: list[FieldAssignment] = Field(default_factory=list)
    column_assignments: list[ColumnAssignment] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _validate_uniqueness(self) -> Self:
        ensure_unique((a.field_key for a in self.field_assignments), "field assignment")
        ensure_unique(
            (str(c.template_column_index) for c in self.column_assignments),
            "column assignment index",
        )
        return self


class MappingResult(DomainModel):
    document_field_assignments: list[FieldAssignment] = Field(default_factory=list)
    sections: list[SectionMapping] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_uniqueness(self) -> Self:
        ensure_unique(
            (a.field_key for a in self.document_field_assignments), "document field assignment"
        )
        ensure_unique((s.section_id for s in self.sections), "section mapping")
        return self
