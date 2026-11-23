from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.enums import (
    ContentType,
    DocumentFormat,
    DocumentRegion,
    FieldValueType,
    SemanticType,
)
from app.domain.template_schema import (
    BoundingBox,
    FormattingConstraints,
    ImageLayout,
    SourceLocation,
    TableColumn,
    TableDefinition,
    TemplateDocument,
    TemplateField,
    TemplateSchema,
    TemplateSection,
)


def location(start: int, end: int | None = None) -> SourceLocation:
    return SourceLocation(element_start=start, element_end=end)


def event_overview() -> TemplateSection:
    return TemplateSection(
        id="event_overview",
        semantic_type=SemanticType.EVENT_DETAILS,
        order=1,
        heading="Event Overview",
        content_types=[ContentType.TEXT, ContentType.KEY_VALUE],
        source_location=location(2, 8),
        fields=[
            TemplateField(key="event_name", label="Name of the Event", source_location=location(3)),
            TemplateField(
                key="event_date",
                label="Date",
                value_type=FieldValueType.DATE,
                source_location=location(4),
            ),
            TemplateField(key="venue", label="Venue", required=False, source_location=location(5)),
        ],
    )


def attendance_section() -> TemplateSection:
    return TemplateSection(
        id="attendance",
        semantic_type=SemanticType.ATTENDANCE,
        order=2,
        content_types=[ContentType.TABLE],
        source_location=location(9),
        table=TableDefinition(
            columns=[
                TableColumn(header="Sr. No.", key="serial_number"),
                TableColumn(header="Name", key="name"),
                TableColumn(header="Department"),
            ]
        ),
    )


def photos_section() -> TemplateSection:
    return TemplateSection(
        id="photos",
        semantic_type=SemanticType.ACTIVITY_IMAGES,
        order=3,
        content_types=[ContentType.IMAGE_GRID],
        source_location=location(10, 11),
        image_layout=ImageLayout(columns=2, max_images=6, image_width_cm=7.5, has_captions=True),
    )


def feedback_section() -> TemplateSection:
    return TemplateSection(
        id="feedback",
        semantic_type=SemanticType.FEEDBACK,
        order=4,
        content_types=[ContentType.TEXT, ContentType.STATISTICS],
        source_location=location(12),
    )


def full_schema() -> TemplateSchema:
    return TemplateSchema(
        document=TemplateDocument(
            title="Activity Report",
            source_format=DocumentFormat.DOCX,
            fields=[
                TemplateField(
                    key="report_title",
                    label="Activity Report",
                    source_location=SourceLocation(region=DocumentRegion.HEADER, element_start=0),
                )
            ],
            sections=[event_overview(), attendance_section(), photos_section(), feedback_section()],
        )
    )


def text_section(**overrides: Any) -> TemplateSection:
    values: dict[str, Any] = {
        "id": "objectives",
        "semantic_type": SemanticType.OBJECTIVES,
        "order": 1,
        "content_types": [ContentType.TEXT],
        "source_location": location(1),
    }
    values.update(overrides)
    return TemplateSection(**values)


def document(sections: list[TemplateSection], **overrides: Any) -> TemplateDocument:
    values: dict[str, Any] = {
        "title": "Report",
        "source_format": DocumentFormat.DOCX,
        "sections": sections,
    }
    values.update(overrides)
    return TemplateDocument(**values)


# ------------------------------------------------------------------------ valid schemas


def test_four_core_sections_form_a_valid_schema() -> None:
    schema = full_schema()

    assert schema.schema_version == 1
    assert [s.semantic_type for s in schema.document.sections] == [
        SemanticType.EVENT_DETAILS,
        SemanticType.ATTENDANCE,
        SemanticType.ACTIVITY_IMAGES,
        SemanticType.FEEDBACK,
    ]
    assert schema.document.sections[2].image_layout is not None
    assert schema.document.sections[1].table is not None


def test_json_shape_matches_the_specification_example() -> None:
    dumped = full_schema().model_dump(mode="json")

    section = dumped["document"]["sections"][0]
    assert dumped["document"]["title"] == "Activity Report"
    assert section["id"] == "event_overview"
    assert section["semantic_type"] == "event_details"
    assert section["order"] == 1
    assert section["content_types"] == ["text", "key_value"]


def test_json_round_trip_preserves_everything() -> None:
    original = full_schema()

    restored = TemplateSchema.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert restored.document.sections[0].fields[1].value_type is FieldValueType.DATE
    assert restored.document.fields[0].source_location.region is DocumentRegion.HEADER


def test_get_section() -> None:
    schema = full_schema()

    assert schema.get_section("attendance") is schema.document.sections[1]
    assert schema.get_section("missing") is None


def test_schema_version_must_be_known() -> None:
    with pytest.raises(ValidationError):
        TemplateSchema(schema_version=2, document=full_schema().document)  # type: ignore[arg-type]


# --------------------------------------------------------------- section consistency


def test_table_content_type_requires_a_table_definition() -> None:
    with pytest.raises(ValidationError, match="table definition is required"):
        text_section(content_types=[ContentType.TABLE])


def test_table_definition_requires_the_table_content_type() -> None:
    with pytest.raises(ValidationError, match="table definition is required"):
        text_section(table=TableDefinition(columns=[TableColumn(header="Name")]))


def test_image_grid_content_type_requires_an_image_layout() -> None:
    with pytest.raises(ValidationError, match="image layout is required"):
        text_section(content_types=[ContentType.IMAGE_GRID])


def test_image_layout_requires_the_image_grid_content_type() -> None:
    with pytest.raises(ValidationError, match="image layout is required"):
        text_section(image_layout=ImageLayout(columns=2))


def test_key_value_content_type_requires_fields() -> None:
    with pytest.raises(ValidationError, match="fields are required"):
        text_section(content_types=[ContentType.KEY_VALUE])


def test_fields_require_the_key_value_content_type() -> None:
    field = TemplateField(key="venue", label="Venue", source_location=location(2))

    with pytest.raises(ValidationError, match="fields are required"):
        text_section(fields=[field])


def test_duplicate_content_types_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate content type"):
        text_section(content_types=[ContentType.TEXT, ContentType.TEXT])


def test_empty_content_types_are_rejected() -> None:
    with pytest.raises(ValidationError):
        text_section(content_types=[])


def test_duplicate_field_keys_in_a_section_are_rejected() -> None:
    fields = [
        TemplateField(key="venue", label="Venue", source_location=location(2)),
        TemplateField(key="venue", label="Place", source_location=location(3)),
    ]

    with pytest.raises(ValidationError, match="duplicate field key: venue"):
        text_section(content_types=[ContentType.KEY_VALUE], fields=fields)


def test_section_order_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        text_section(order=0)


# --------------------------------------------------------------- document consistency


def test_duplicate_section_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate section id: objectives"):
        document([text_section(), text_section(order=2)])


@pytest.mark.parametrize("orders", [[2, 3], [1, 3], [2, 1], [1, 1]])
def test_section_orders_must_be_contiguous_and_match_list_order(orders: list[int]) -> None:
    sections = [text_section(id=f"section_{i}", order=order) for i, order in enumerate(orders)]

    with pytest.raises(ValidationError, match=r"order values must be 1\.\.n"):
        document(sections)


def test_document_requires_at_least_one_section() -> None:
    with pytest.raises(ValidationError):
        document([])


def test_duplicate_document_field_keys_are_rejected() -> None:
    fields = [
        TemplateField(key="report_title", label="A", source_location=location(0)),
        TemplateField(key="report_title", label="B", source_location=location(1)),
    ]

    with pytest.raises(ValidationError, match="duplicate document field key"):
        document([text_section()], fields=fields)


def test_duplicate_table_column_keys_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate table column key: name"):
        TableDefinition(
            columns=[TableColumn(header="A", key="name"), TableColumn(header="B", key="name")]
        )


def test_columns_without_keys_may_repeat() -> None:
    table = TableDefinition(columns=[TableColumn(header="A"), TableColumn(header="B")])

    assert len(table.columns) == 2


def test_table_requires_columns() -> None:
    with pytest.raises(ValidationError):
        TableDefinition(columns=[])


# ------------------------------------------------------------------ source location


def test_docx_location_with_element_range() -> None:
    assert SourceLocation(element_start=3, element_end=3).element_end == 3


def test_pdf_location_with_page_and_box() -> None:
    result = SourceLocation(page=2, bounding_box=BoundingBox(x0=10, y0=20, x1=200, y1=80.5))

    assert result.region is DocumentRegion.BODY
    assert result.bounding_box is not None


def test_location_requires_a_locator() -> None:
    with pytest.raises(ValidationError, match="needs element_start"):
        SourceLocation()


def test_element_end_requires_start() -> None:
    with pytest.raises(ValidationError, match="element_end requires element_start"):
        SourceLocation(page=1, element_end=3)


def test_element_end_must_not_precede_start() -> None:
    with pytest.raises(ValidationError, match="must not precede"):
        SourceLocation(element_start=5, element_end=4)


def test_bounding_box_requires_a_page() -> None:
    with pytest.raises(ValidationError, match="bounding_box requires page"):
        SourceLocation(element_start=1, bounding_box=BoundingBox(x0=0, y0=0, x1=10, y1=10))


def test_page_numbers_start_at_one() -> None:
    with pytest.raises(ValidationError):
        SourceLocation(page=0)


@pytest.mark.parametrize(
    "coordinates",
    [
        {"x0": 10, "y0": 0, "x1": 10, "y1": 5},
        {"x0": 10, "y0": 0, "x1": 5, "y1": 5},
        {"x0": 0, "y0": 9, "x1": 5, "y1": 9},
        {"x0": -1, "y0": 0, "x1": 5, "y1": 5},
    ],
)
def test_bounding_box_must_have_positive_extent(coordinates: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        BoundingBox(**coordinates)


# ------------------------------------------------------------- layout and formatting


@pytest.mark.parametrize("columns", [0, 13])
def test_image_layout_column_bounds(columns: int) -> None:
    with pytest.raises(ValidationError):
        ImageLayout(columns=columns)


@pytest.mark.parametrize("size", [0, -1, 401])
def test_font_size_bounds(size: float) -> None:
    with pytest.raises(ValidationError):
        FormattingConstraints(font_size_pt=size)


def test_formatting_constraints_accept_valid_values() -> None:
    formatting = FormattingConstraints(
        style_name="Heading 1",
        font_family="Calibri",
        font_size_pt=14,
        bold=True,
        alignment="center",
    )

    assert formatting.alignment == "center"
