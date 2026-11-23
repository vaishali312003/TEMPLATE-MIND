"""Event Data JSON: structured content extracted from the raw event files.

Statistics stored here are computed by Python (rule 3). Values the inputs do not contain are
simply absent (rule 7): nothing in this module has a "guessed" or default value.
"""

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.base import DomainModel, Identifier, ShortText, ensure_unique
from app.domain.provenance import SourceReference

# --------------------------------------------------------------------------- event details


class TextValue(DomainModel):
    kind: Literal["text"] = "text"
    value: str = Field(min_length=1, max_length=10_000)


class DateValue(DomainModel):
    kind: Literal["date"] = "date"
    value: date


class DateRangeValue(DomainModel):
    kind: Literal["date_range"] = "date_range"
    start: date
    end: date

    @model_validator(mode="after")
    def _validate_order(self) -> Self:
        if self.end < self.start:
            raise ValueError("end date must not precede start date")
        return self


class IntegerValue(DomainModel):
    kind: Literal["integer"] = "integer"
    value: int


FieldValue = Annotated[
    TextValue | DateValue | DateRangeValue | IntegerValue,
    Field(discriminator="kind"),
]


class EventDetail(DomainModel):
    key: Identifier
    label: ShortText | None = None
    value: FieldValue
    sources: list[SourceReference] = Field(min_length=1)


# ---------------------------------------------------------------------------- attendance


class AttendanceColumn(DomainModel):
    key: Identifier
    header: ShortText


class ParticipantRecord(DomainModel):
    row_number: int = Field(ge=1)  # 1-based data row in the source file, header excluded
    values: dict[Identifier, str | None] = Field(default_factory=dict)
    present: bool | None = None


class AttendanceStatistics(DomainModel):
    total_participants: int = Field(ge=0)
    present_count: int | None = Field(default=None, ge=0)
    absent_count: int | None = Field(default=None, ge=0)
    attendance_percentage: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _validate_consistency(self) -> Self:
        total = self.total_participants
        for count in (self.present_count, self.absent_count):
            if count is not None and count > total:
                raise ValueError("present and absent counts must not exceed total_participants")
        if (
            self.present_count is not None
            and self.absent_count is not None
            and self.present_count + self.absent_count > total
        ):
            raise ValueError("present_count + absent_count must not exceed total_participants")
        if self.attendance_percentage is not None:
            if self.present_count is None or total == 0:
                raise ValueError(
                    "attendance_percentage requires present_count and at least one participant"
                )
            expected = self.present_count / total * 100
            if abs(expected - self.attendance_percentage) > 0.01:
                raise ValueError("attendance_percentage does not match present_count/total")
        return self


class AttendanceData(DomainModel):
    columns: list[AttendanceColumn] = Field(min_length=1)
    records: list[ParticipantRecord] = Field(default_factory=list)
    statistics: AttendanceStatistics
    sources: list[SourceReference] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_consistency(self) -> Self:
        ensure_unique((c.key for c in self.columns), "attendance column key")
        ensure_unique((str(r.row_number) for r in self.records), "row number")
        known_columns = {c.key for c in self.columns}
        for record in self.records:
            unknown = set(record.values) - known_columns
            if unknown:
                raise ValueError(
                    f"row {record.row_number} has values for unknown columns: {sorted(unknown)}"
                )
        if self.statistics.total_participants != len(self.records):
            raise ValueError("statistics.total_participants must equal the number of records")
        return self


# ------------------------------------------------------------------------------- images


class ActivityImage(DomainModel):
    id: UUID
    file_id: UUID  # the original uploaded file
    storage_key: ShortText  # the processed (resized/cropped) image in storage
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)
    caption: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    sources: list[SourceReference] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_storage_key(self) -> Self:
        key = self.storage_key
        segments = key.split("/")
        if key.startswith("/") or "\\" in key or any(s in {"", ".", ".."} for s in segments):
            raise ValueError("storage_key must be a relative key without '.', '..' or empty parts")
        return self


class ImageGroup(DomainModel):
    label: ShortText
    image_ids: list[UUID] = Field(min_length=1)


class ExcludedImage(DomainModel):
    """An uploaded image that was not used, kept so the decision is traceable."""

    file_id: UUID
    reason: ShortText


class ImageData(DomainModel):
    # List order is the display order.
    images: list[ActivityImage] = Field(default_factory=list)
    groups: list[ImageGroup] = Field(default_factory=list)
    excluded: list[ExcludedImage] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_consistency(self) -> Self:
        ensure_unique((str(i.id) for i in self.images), "image id")
        ensure_unique((g.label for g in self.groups), "image group label")
        known_ids = {image.id for image in self.images}
        assigned: set[UUID] = set()
        for group in self.groups:
            ensure_unique((str(i) for i in group.image_ids), f"image id in group '{group.label}'")
            for image_id in group.image_ids:
                if image_id not in known_ids:
                    raise ValueError(f"group '{group.label}' references unknown image {image_id}")
                if image_id in assigned:
                    raise ValueError(f"image {image_id} belongs to more than one group")
                assigned.add(image_id)
        return self


# ----------------------------------------------------------------------------- feedback


class RatingQuestionStatistics(DomainModel):
    question: str = Field(min_length=1, max_length=500)
    response_count: int = Field(ge=1)
    average: float
    minimum: int
    maximum: int
    # Observed rating value -> number of responses (only values that occurred).
    distribution: dict[int, int]

    @model_validator(mode="after")
    def _validate_consistency(self) -> Self:
        if not self.distribution or any(count < 1 for count in self.distribution.values()):
            raise ValueError("distribution must contain only observed ratings with count >= 1")
        if sum(self.distribution.values()) != self.response_count:
            raise ValueError("distribution counts must add up to response_count")
        if min(self.distribution) != self.minimum or max(self.distribution) != self.maximum:
            raise ValueError("minimum and maximum must match the distribution")
        rating_total = sum(value * count for value, count in self.distribution.items())
        expected_average = rating_total / self.response_count
        if abs(expected_average - self.average) > 0.01:
            raise ValueError("average does not match the distribution")
        return self


class FeedbackSummary(DomainModel):
    overview: str = Field(min_length=1, max_length=10_000)
    highlights: list[ShortText] = Field(default_factory=list)
    suggestions: list[ShortText] = Field(default_factory=list)


class FeedbackData(DomainModel):
    response_count: int = Field(ge=0)
    rating_questions: list[RatingQuestionStatistics] = Field(default_factory=list)
    overall_average_rating: float | None = Field(default=None, ge=0)
    summary: FeedbackSummary | None = None
    sources: list[SourceReference] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_consistency(self) -> Self:
        if any(q.response_count > self.response_count for q in self.rating_questions):
            raise ValueError("a question cannot have more responses than response_count")
        if bool(self.rating_questions) != (self.overall_average_rating is not None):
            raise ValueError(
                "overall_average_rating is required exactly when rating_questions exist"
            )
        return self


# ------------------------------------------------------------------------------ top level


class EventData(DomainModel):
    # Open-ended on purpose: templates ask for different fields. Keys are normalised
    # identifiers; the keys named by the specification are listed in ``CoreDetailKey``.
    details: dict[Identifier, EventDetail] = Field(default_factory=dict)
    attendance: AttendanceData | None = None
    images: ImageData | None = None
    feedback: FeedbackData | None = None

    @model_validator(mode="after")
    def _validate_detail_keys(self) -> Self:
        for key, detail in self.details.items():
            if detail.key != key:
                raise ValueError(f"details['{key}'] has a different key: '{detail.key}'")
        return self
