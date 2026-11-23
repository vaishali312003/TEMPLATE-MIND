from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import FileRole, ProvenanceMethod
from app.domain.event_data import (
    ActivityImage,
    AttendanceColumn,
    AttendanceData,
    AttendanceStatistics,
    DateRangeValue,
    DateValue,
    EventData,
    EventDetail,
    ExcludedImage,
    FeedbackData,
    FeedbackSummary,
    ImageData,
    ImageGroup,
    IntegerValue,
    ParticipantRecord,
    RatingQuestionStatistics,
    TextValue,
)
from app.domain.provenance import SourceReference


def source(
    role: FileRole = FileRole.EVENT_DOCUMENT,
    method: ProvenanceMethod = ProvenanceMethod.EXTRACTED,
    locator: str | None = None,
) -> SourceReference:
    return SourceReference(file_id=uuid4(), file_role=role, method=method, locator=locator)


def detail(key: str = "event_name", value: Any = None) -> EventDetail:
    return EventDetail(
        key=key,
        label="Event name",
        value=value or TextValue(value="Smart India Hackathon"),
        sources=[source()],
    )


def make_attendance(**overrides: Any) -> AttendanceData:
    values: dict[str, Any] = {
        "columns": [
            AttendanceColumn(key="name", header="Name"),
            AttendanceColumn(key="status", header="Status"),
        ],
        "records": [
            ParticipantRecord(
                row_number=1, values={"name": "Asha", "status": "Present"}, present=True
            ),
            ParticipantRecord(
                row_number=2, values={"name": "Ravi", "status": "Present"}, present=True
            ),
            ParticipantRecord(
                row_number=3, values={"name": "Meera", "status": "Absent"}, present=False
            ),
        ],
        "statistics": AttendanceStatistics(
            total_participants=3, present_count=2, absent_count=1, attendance_percentage=66.67
        ),
        "sources": [source(FileRole.ATTENDANCE, ProvenanceMethod.PARSED, "sheet=Attendance")],
    }
    values.update(overrides)
    return AttendanceData(**values)


def make_image(**overrides: Any) -> ActivityImage:
    values: dict[str, Any] = {
        "id": uuid4(),
        "file_id": uuid4(),
        "storage_key": "images/processed/photo-1.jpg",
        "width_px": 1600,
        "height_px": 1200,
        "sources": [source(FileRole.IMAGE, ProvenanceMethod.CLASSIFIED)],
    }
    values.update(overrides)
    return ActivityImage(**values)


def make_question(**overrides: Any) -> RatingQuestionStatistics:
    values: dict[str, Any] = {
        "question": "Overall, how was the event?",
        "response_count": 10,
        "average": 4.2,
        "minimum": 3,
        "maximum": 5,
        "distribution": {3: 1, 4: 6, 5: 3},
    }
    values.update(overrides)
    return RatingQuestionStatistics(**values)


def make_feedback(**overrides: Any) -> FeedbackData:
    values: dict[str, Any] = {
        "response_count": 10,
        "rating_questions": [make_question()],
        "overall_average_rating": 4.2,
        "summary": FeedbackSummary(
            overview="Participants rated the event highly.",
            highlights=["Good speakers"],
            suggestions=["Longer breaks"],
        ),
        "sources": [source(FileRole.FEEDBACK, ProvenanceMethod.PARSED)],
    }
    values.update(overrides)
    return FeedbackData(**values)


# --------------------------------------------------------------------- event details


def test_details_parse_each_value_kind_from_json() -> None:
    sources = [{"method": "user_edit"}]
    payloads = {
        "event_name": {"kind": "text", "value": "Hackathon"},
        "event_date": {"kind": "date", "value": "2026-03-14"},
        "event_period": {"kind": "date_range", "start": "2026-03-14", "end": "2026-03-15"},
        "expected_participants": {"kind": "integer", "value": 120},
    }

    parsed = {
        key: EventDetail.model_validate({"key": key, "value": value, "sources": sources})
        for key, value in payloads.items()
    }

    assert isinstance(parsed["event_name"].value, TextValue)
    assert parsed["event_date"].value == DateValue(value=date(2026, 3, 14))
    assert parsed["event_period"].value == DateRangeValue(
        start=date(2026, 3, 14), end=date(2026, 3, 15)
    )
    assert parsed["expected_participants"].value == IntegerValue(value=120)


def test_unknown_value_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EventDetail.model_validate(
            {
                "key": "x",
                "value": {"kind": "float", "value": 1.5},
                "sources": [{"method": "user_edit"}],
            }
        )


def test_date_range_end_must_not_precede_start() -> None:
    with pytest.raises(ValidationError, match="end date must not precede"):
        DateRangeValue(start=date(2026, 3, 15), end=date(2026, 3, 14))


def test_single_day_range_is_valid() -> None:
    assert DateRangeValue(start=date(2026, 3, 14), end=date(2026, 3, 14)).end.day == 14


def test_text_value_cannot_be_blank() -> None:
    with pytest.raises(ValidationError):
        TextValue(value="   ")


def test_detail_requires_a_source() -> None:
    with pytest.raises(ValidationError):
        EventDetail(key="venue", value=TextValue(value="Hall 3"), sources=[])


def test_event_data_detail_keys_must_match_dictionary_keys() -> None:
    with pytest.raises(ValidationError, match="different key"):
        EventData(details={"venue": detail("event_name")})


def test_empty_event_data_is_valid_and_has_no_invented_content() -> None:
    data = EventData()

    assert data.details == {}
    assert data.attendance is None
    assert data.images is None
    assert data.feedback is None


# ------------------------------------------------------------------------ attendance


def test_valid_attendance() -> None:
    attendance = make_attendance()

    assert attendance.statistics.total_participants == len(attendance.records)


def test_total_must_equal_record_count() -> None:
    with pytest.raises(ValidationError, match="must equal the number of records"):
        make_attendance(
            statistics=AttendanceStatistics(
                total_participants=4, present_count=2, absent_count=1, attendance_percentage=50
            )
        )


def test_records_must_use_known_columns() -> None:
    records = [ParticipantRecord(row_number=1, values={"email": "a@b.c"})]

    with pytest.raises(ValidationError, match="unknown columns"):
        make_attendance(records=records, statistics=AttendanceStatistics(total_participants=1))


def test_row_numbers_must_be_unique() -> None:
    records = [
        ParticipantRecord(row_number=1, values={"name": "A"}),
        ParticipantRecord(row_number=1, values={"name": "B"}),
    ]

    with pytest.raises(ValidationError, match="duplicate row number"):
        make_attendance(records=records, statistics=AttendanceStatistics(total_participants=2))


def test_attendance_requires_columns_and_sources() -> None:
    with pytest.raises(ValidationError):
        make_attendance(columns=[])
    with pytest.raises(ValidationError):
        make_attendance(sources=[])


def test_duplicate_column_keys_are_rejected() -> None:
    columns = [AttendanceColumn(key="name", header="A"), AttendanceColumn(key="name", header="B")]

    with pytest.raises(ValidationError, match="duplicate attendance column key"):
        make_attendance(columns=columns)


def test_zero_participants_is_valid_without_percentage() -> None:
    attendance = make_attendance(records=[], statistics=AttendanceStatistics(total_participants=0))

    assert attendance.statistics.attendance_percentage is None


def test_percentage_requires_at_least_one_participant() -> None:
    with pytest.raises(ValidationError, match="requires present_count"):
        AttendanceStatistics(total_participants=0, present_count=0, attendance_percentage=0)


def test_percentage_requires_present_count() -> None:
    with pytest.raises(ValidationError, match="requires present_count"):
        AttendanceStatistics(total_participants=3, attendance_percentage=50)


def test_percentage_must_match_counts() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        AttendanceStatistics(total_participants=4, present_count=2, attendance_percentage=75)


def test_percentage_tolerates_rounding_to_two_decimals() -> None:
    stats = AttendanceStatistics(total_participants=3, present_count=1, attendance_percentage=33.33)

    assert stats.attendance_percentage == 33.33


@pytest.mark.parametrize(
    "counts",
    [
        {"present_count": 5},
        {"absent_count": 5},
        {"present_count": 3, "absent_count": 2},
    ],
)
def test_counts_must_not_exceed_total(counts: dict[str, int]) -> None:
    with pytest.raises(ValidationError, match="exceed total_participants"):
        AttendanceStatistics(total_participants=4, **counts)


def test_unknown_presence_is_allowed() -> None:
    stats = AttendanceStatistics(total_participants=4, present_count=2, absent_count=1)

    assert stats.attendance_percentage is None


# --------------------------------------------------------------------------- images


def test_valid_images_with_groups_and_exclusions() -> None:
    first, second, third = make_image(), make_image(), make_image()
    data = ImageData(
        images=[first, second, third],
        groups=[
            ImageGroup(label="Inauguration", image_ids=[first.id, second.id]),
            ImageGroup(label="Workshop", image_ids=[third.id]),
        ],
        excluded=[ExcludedImage(file_id=uuid4(), reason="Not an activity photograph")],
    )

    assert len(data.images) == 3


def test_duplicate_image_ids_are_rejected() -> None:
    image = make_image()

    with pytest.raises(ValidationError, match="duplicate image id"):
        ImageData(images=[image, image])


def test_group_must_reference_known_images() -> None:
    with pytest.raises(ValidationError, match="unknown image"):
        ImageData(images=[make_image()], groups=[ImageGroup(label="G", image_ids=[uuid4()])])


def test_image_cannot_belong_to_two_groups() -> None:
    image = make_image()

    with pytest.raises(ValidationError, match="more than one group"):
        ImageData(
            images=[image],
            groups=[
                ImageGroup(label="A", image_ids=[image.id]),
                ImageGroup(label="B", image_ids=[image.id]),
            ],
        )


def test_group_cannot_repeat_an_image_or_a_label() -> None:
    image = make_image()

    with pytest.raises(ValidationError, match="duplicate image id in group"):
        ImageData(images=[image], groups=[ImageGroup(label="A", image_ids=[image.id, image.id])])
    with pytest.raises(ValidationError, match="duplicate image group label"):
        other = make_image()
        ImageData(
            images=[image, other],
            groups=[
                ImageGroup(label="A", image_ids=[image.id]),
                ImageGroup(label="A", image_ids=[other.id]),
            ],
        )


@pytest.mark.parametrize(
    "key", ["../secret.jpg", "/abs/photo.jpg", "a/../b.jpg", "a\\b.jpg", "a//b.jpg", "a/./b.jpg"]
)
def test_unsafe_storage_keys_are_rejected(key: str) -> None:
    with pytest.raises(ValidationError, match="storage_key"):
        make_image(storage_key=key)


def test_image_dimensions_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make_image(width_px=0)


# ------------------------------------------------------------------------- feedback


def test_valid_feedback() -> None:
    assert make_feedback().overall_average_rating == 4.2


def test_feedback_without_summary_is_valid() -> None:
    assert make_feedback(summary=None).summary is None


def test_feedback_without_ratings_is_valid() -> None:
    feedback = make_feedback(rating_questions=[], overall_average_rating=None)

    assert feedback.rating_questions == []


def test_overall_average_is_required_exactly_when_questions_exist() -> None:
    with pytest.raises(ValidationError, match="overall_average_rating is required"):
        make_feedback(overall_average_rating=None)
    with pytest.raises(ValidationError, match="overall_average_rating is required"):
        make_feedback(rating_questions=[], overall_average_rating=4.0)


def test_question_cannot_exceed_total_responses() -> None:
    with pytest.raises(ValidationError, match="more responses"):
        make_feedback(response_count=5)


def test_distribution_must_add_up_to_response_count() -> None:
    with pytest.raises(ValidationError, match="add up"):
        make_question(distribution={3: 1, 4: 6, 5: 2})


def test_minimum_and_maximum_must_match_distribution() -> None:
    with pytest.raises(ValidationError, match="minimum and maximum"):
        make_question(minimum=1)


def test_average_must_match_distribution() -> None:
    with pytest.raises(ValidationError, match="average does not match"):
        make_question(average=3.0)


def test_distribution_rejects_zero_counts_and_empty_distributions() -> None:
    with pytest.raises(ValidationError, match="observed ratings"):
        make_question(distribution={3: 0, 4: 7, 5: 3}, minimum=4)
    with pytest.raises(ValidationError):
        make_question(distribution={})


def test_summary_overview_is_required() -> None:
    with pytest.raises(ValidationError):
        FeedbackSummary(overview="  ")


# ------------------------------------------------------------------------ round trip


def test_complete_event_data_survives_a_json_round_trip() -> None:
    image = make_image()
    original = EventData(
        details={
            "event_name": detail(),
            "event_date": detail(
                "event_date",
                DateRangeValue(start=date(2026, 3, 14), end=date(2026, 3, 15)),
            ),
        },
        attendance=make_attendance(),
        images=ImageData(
            images=[image], groups=[ImageGroup(label="Inauguration", image_ids=[image.id])]
        ),
        feedback=make_feedback(),
    )

    dumped = original.model_dump(mode="json")
    restored = EventData.model_validate(dumped)

    assert restored == original
    assert dumped["details"]["event_date"]["value"]["kind"] == "date_range"
    assert dumped["feedback"]["rating_questions"][0]["distribution"] == {"3": 1, "4": 6, "5": 3}
    assert restored.feedback is not None
    assert restored.feedback.rating_questions[0].distribution == {3: 1, 4: 6, 5: 3}
