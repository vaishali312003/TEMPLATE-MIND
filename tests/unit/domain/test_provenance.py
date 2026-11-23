from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import FileRole, ProvenanceMethod
from app.domain.provenance import (
    FieldProvenance,
    SourceReference,
    document_field_path,
    event_detail_path,
    section_field_path,
)

FILE_METHODS = [
    ProvenanceMethod.PARSED,
    ProvenanceMethod.EXTRACTED,
    ProvenanceMethod.COMPUTED,
    ProvenanceMethod.SUMMARIZED,
    ProvenanceMethod.CLASSIFIED,
]


def user_edit() -> SourceReference:
    return SourceReference(method=ProvenanceMethod.USER_EDIT)


def test_file_based_reference_is_valid() -> None:
    reference = SourceReference(
        file_id=uuid4(),
        file_role=FileRole.ATTENDANCE,
        method=ProvenanceMethod.PARSED,
        locator="sheet=Attendance;row=5",
    )

    assert reference.method is ProvenanceMethod.PARSED
    assert reference.locator == "sheet=Attendance;row=5"


@pytest.mark.parametrize("method", FILE_METHODS)
def test_file_methods_require_file_id_and_role(method: ProvenanceMethod) -> None:
    with pytest.raises(ValidationError, match="required unless"):
        SourceReference(method=method)
    with pytest.raises(ValidationError, match="required unless"):
        SourceReference(file_id=uuid4(), method=method)
    with pytest.raises(ValidationError, match="required unless"):
        SourceReference(file_role=FileRole.IMAGE, method=method)


def test_user_edit_without_file_is_valid() -> None:
    assert user_edit().file_id is None


def test_user_edit_must_not_reference_a_file() -> None:
    with pytest.raises(ValidationError, match="must not reference a source file"):
        SourceReference(
            file_id=uuid4(), file_role=FileRole.EVENT_DOCUMENT, method=ProvenanceMethod.USER_EDIT
        )


def test_template_is_not_a_content_source() -> None:
    with pytest.raises(ValidationError, match="not 'template'"):
        SourceReference(
            file_id=uuid4(), file_role=FileRole.TEMPLATE, method=ProvenanceMethod.PARSED
        )


def test_locator_length_is_limited() -> None:
    with pytest.raises(ValidationError):
        SourceReference(
            file_id=uuid4(),
            file_role=FileRole.EVENT_DOCUMENT,
            method=ProvenanceMethod.EXTRACTED,
            locator="x" * 256,
        )


def test_field_provenance_requires_at_least_one_source() -> None:
    with pytest.raises(ValidationError):
        FieldProvenance(field_path="details.event_name", sources=[])


@pytest.mark.parametrize(
    "path", ["", "Details.event_name", "details..x", ".details", "details.event name", "1a.b"]
)
def test_field_path_must_follow_the_convention(path: str) -> None:
    with pytest.raises(ValidationError):
        FieldProvenance(field_path=path, sources=[user_edit()])


def test_path_helpers_build_valid_conventional_paths() -> None:
    paths = [
        event_detail_path("event_name"),
        section_field_path("event_overview", "venue"),
        document_field_path("report_title"),
    ]

    assert paths == [
        "details.event_name",
        "sections.event_overview.fields.venue",
        "document.fields.report_title",
    ]
    for path in paths:
        assert FieldProvenance(field_path=path, sources=[user_edit()]).field_path == path


def test_json_round_trip() -> None:
    original = FieldProvenance(
        field_path="attendance.statistics.total_participants",
        sources=[
            SourceReference(
                file_id=uuid4(),
                file_role=FileRole.ATTENDANCE,
                method=ProvenanceMethod.COMPUTED,
            )
        ],
        note="counted from rows",
    )

    restored = FieldProvenance.model_validate(original.model_dump(mode="json"))

    assert restored == original
