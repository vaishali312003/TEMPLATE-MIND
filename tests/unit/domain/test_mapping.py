import pytest
from pydantic import ValidationError

from app.domain.enums import ColumnSourceKind, ContentSourceKind, StatisticKey
from app.domain.mapping import (
    ColumnAssignment,
    ContentReference,
    FieldAssignment,
    MappingResult,
    SectionMapping,
)


def detail_ref(key: str = "event_name") -> ContentReference:
    return ContentReference(kind=ContentSourceKind.DETAIL, detail_key=key)


def stat_ref(
    statistic: StatisticKey = StatisticKey.TOTAL_PARTICIPANTS,
    kind: ContentSourceKind = ContentSourceKind.ATTENDANCE_STATISTICS,
) -> ContentReference:
    return ContentReference(kind=kind, statistic=statistic)


# ------------------------------------------------------------------ ContentReference


def test_detail_reference_requires_a_key() -> None:
    with pytest.raises(ValidationError, match="detail_key is required"):
        ContentReference(kind=ContentSourceKind.DETAIL)


@pytest.mark.parametrize(
    "kind",
    [
        ContentSourceKind.ATTENDANCE_TABLE,
        ContentSourceKind.ATTENDANCE_STATISTICS,
        ContentSourceKind.IMAGES,
        ContentSourceKind.FEEDBACK_STATISTICS,
        ContentSourceKind.FEEDBACK_SUMMARY,
    ],
)
def test_detail_key_is_only_allowed_for_details(kind: ContentSourceKind) -> None:
    with pytest.raises(ValidationError, match="detail_key is required"):
        ContentReference(kind=kind, detail_key="event_name")


def test_block_references_need_no_statistic() -> None:
    assert ContentReference(kind=ContentSourceKind.ATTENDANCE_TABLE).statistic is None
    assert ContentReference(kind=ContentSourceKind.FEEDBACK_SUMMARY).statistic is None


def test_statistic_must_belong_to_the_referenced_block() -> None:
    assert (
        stat_ref(StatisticKey.ATTENDANCE_PERCENTAGE).statistic is StatisticKey.ATTENDANCE_PERCENTAGE
    )
    assert (
        stat_ref(
            StatisticKey.OVERALL_AVERAGE_RATING, ContentSourceKind.FEEDBACK_STATISTICS
        ).statistic
        is StatisticKey.OVERALL_AVERAGE_RATING
    )
    with pytest.raises(ValidationError, match="does not belong"):
        stat_ref(StatisticKey.OVERALL_AVERAGE_RATING, ContentSourceKind.ATTENDANCE_STATISTICS)
    with pytest.raises(ValidationError, match="does not belong"):
        stat_ref(StatisticKey.TOTAL_PARTICIPANTS, ContentSourceKind.FEEDBACK_STATISTICS)


def test_statistic_is_not_allowed_on_other_kinds() -> None:
    with pytest.raises(ValidationError, match="does not belong"):
        ContentReference(
            kind=ContentSourceKind.DETAIL,
            detail_key="event_name",
            statistic=StatisticKey.TOTAL_PARTICIPANTS,
        )
    with pytest.raises(ValidationError, match="does not belong"):
        ContentReference(kind=ContentSourceKind.IMAGES, statistic=StatisticKey.PRESENT_COUNT)


# ----------------------------------------------------------------- FieldAssignment


def test_field_can_be_filled_by_a_detail_or_a_named_statistic() -> None:
    assert FieldAssignment(field_key="event_name", source=detail_ref(), confidence=0.9)
    assert FieldAssignment(field_key="participants", source=stat_ref(), confidence=1)


@pytest.mark.parametrize(
    "source",
    [
        ContentReference(kind=ContentSourceKind.ATTENDANCE_STATISTICS),
        ContentReference(kind=ContentSourceKind.ATTENDANCE_TABLE),
        ContentReference(kind=ContentSourceKind.IMAGES),
        ContentReference(kind=ContentSourceKind.FEEDBACK_SUMMARY),
    ],
)
def test_field_cannot_be_filled_by_a_whole_block(source: ContentReference) -> None:
    with pytest.raises(ValidationError, match="single field"):
        FieldAssignment(field_key="venue", source=source, confidence=0.5)


@pytest.mark.parametrize("confidence", [-0.1, 1.01])
def test_confidence_is_a_probability(confidence: float) -> None:
    with pytest.raises(ValidationError):
        FieldAssignment(field_key="venue", source=detail_ref("venue"), confidence=confidence)


# ---------------------------------------------------------------- ColumnAssignment


def test_attendance_column_assignment_needs_a_column_key() -> None:
    assignment = ColumnAssignment(
        template_column_index=1,
        source_kind=ColumnSourceKind.ATTENDANCE_COLUMN,
        attendance_column_key="name",
    )

    assert assignment.attendance_column_key == "name"
    with pytest.raises(ValidationError, match="attendance_column_key is required"):
        ColumnAssignment(template_column_index=1, source_kind=ColumnSourceKind.ATTENDANCE_COLUMN)


def test_row_number_assignment_must_not_have_a_column_key() -> None:
    assert (
        ColumnAssignment(
            template_column_index=0, source_kind=ColumnSourceKind.ROW_NUMBER
        ).attendance_column_key
        is None
    )
    with pytest.raises(ValidationError, match="attendance_column_key is required"):
        ColumnAssignment(
            template_column_index=0,
            source_kind=ColumnSourceKind.ROW_NUMBER,
            attendance_column_key="name",
        )


def test_column_index_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        ColumnAssignment(template_column_index=-1, source_kind=ColumnSourceKind.ROW_NUMBER)


# ------------------------------------------------------- SectionMapping / MappingResult


def test_section_rejects_duplicate_field_assignments() -> None:
    assignment = FieldAssignment(field_key="venue", source=detail_ref("venue"), confidence=0.8)

    with pytest.raises(ValidationError, match="duplicate field assignment: venue"):
        SectionMapping(
            section_id="event_overview", field_assignments=[assignment, assignment], confidence=0.8
        )


def test_section_rejects_duplicate_column_indexes() -> None:
    column = ColumnAssignment(template_column_index=0, source_kind=ColumnSourceKind.ROW_NUMBER)

    with pytest.raises(ValidationError, match="duplicate column assignment index"):
        SectionMapping(section_id="attendance", column_assignments=[column, column], confidence=1)


def test_mapping_result_rejects_duplicate_sections_and_document_fields() -> None:
    section = SectionMapping(section_id="feedback", confidence=0.9)
    assignment = FieldAssignment(field_key="title", source=detail_ref(), confidence=0.9)

    with pytest.raises(ValidationError, match="duplicate section mapping: feedback"):
        MappingResult(sections=[section, section])
    with pytest.raises(ValidationError, match="duplicate document field assignment"):
        MappingResult(document_field_assignments=[assignment, assignment])


def test_realistic_mapping_survives_a_json_round_trip() -> None:
    original = MappingResult(
        document_field_assignments=[
            FieldAssignment(field_key="report_title", source=detail_ref(), confidence=0.95)
        ],
        sections=[
            SectionMapping(
                section_id="event_overview",
                content=[detail_ref("description")],
                field_assignments=[
                    FieldAssignment(
                        field_key="event_date", source=detail_ref("event_date"), confidence=0.97
                    ),
                    FieldAssignment(
                        field_key="participant_count",
                        source=stat_ref(),
                        confidence=0.9,
                        rationale="The template asks for the number of participants.",
                    ),
                ],
                confidence=0.93,
            ),
            SectionMapping(
                section_id="attendance",
                content=[ContentReference(kind=ContentSourceKind.ATTENDANCE_TABLE)],
                column_assignments=[
                    ColumnAssignment(
                        template_column_index=0, source_kind=ColumnSourceKind.ROW_NUMBER
                    ),
                    ColumnAssignment(
                        template_column_index=1,
                        source_kind=ColumnSourceKind.ATTENDANCE_COLUMN,
                        attendance_column_key="name",
                    ),
                ],
                confidence=0.9,
            ),
            SectionMapping(
                section_id="feedback",
                content=[
                    ContentReference(kind=ContentSourceKind.FEEDBACK_STATISTICS),
                    ContentReference(kind=ContentSourceKind.FEEDBACK_SUMMARY),
                ],
                confidence=0.88,
            ),
        ],
    )

    restored = MappingResult.model_validate(original.model_dump(mode="json"))

    assert restored == original
