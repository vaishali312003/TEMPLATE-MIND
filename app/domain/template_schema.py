"""Template Schema: the machine-readable intermediate representation of a report template.

The LLM never generates a document directly. Template analysis produces this schema, mapping
decides which content goes where, and the deterministic renderer fills the original template.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from app.domain.base import DomainModel, Identifier, ShortText, ensure_unique
from app.domain.enums import (
    ContentType,
    DocumentFormat,
    DocumentRegion,
    FieldValueType,
    SemanticType,
    TextAlignment,
)


class BoundingBox(DomainModel):
    """Rectangle on a PDF page, in points."""

    x0: float = Field(ge=0)
    y0: float = Field(ge=0)
    x1: float = Field(gt=0)
    y1: float = Field(gt=0)

    @model_validator(mode="after")
    def _validate_extent(self) -> Self:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("bounding box must have positive width and height")
        return self


class SourceLocation(DomainModel):
    """Where an element lives in the original template.

    DOCX: ``element_start``/``element_end`` are 0-based indexes into the ordered body
    elements (paragraphs and tables) of the ``region``. PDF: ``page`` (1-based) and
    optionally ``bounding_box``.
    """

    region: DocumentRegion = DocumentRegion.BODY
    element_start: int | None = Field(default=None, ge=0)
    element_end: int | None = Field(default=None, ge=0)
    page: int | None = Field(default=None, ge=1)
    bounding_box: BoundingBox | None = None

    @model_validator(mode="after")
    def _validate_locator(self) -> Self:
        if self.element_start is None and self.page is None:
            raise ValueError("a source location needs element_start (DOCX) or page (PDF)")
        if self.element_end is not None:
            if self.element_start is None:
                raise ValueError("element_end requires element_start")
            if self.element_end < self.element_start:
                raise ValueError("element_end must not precede element_start")
        if self.bounding_box is not None and self.page is None:
            raise ValueError("bounding_box requires page")
        return self


class FormattingConstraints(DomainModel):
    """Formatting the renderer must preserve for an element."""

    style_name: ShortText | None = None
    font_family: ShortText | None = None
    font_size_pt: float | None = Field(default=None, gt=0, le=400)
    bold: bool | None = None
    italic: bool | None = None
    alignment: TextAlignment | None = None


class TemplateField(DomainModel):
    """A single value slot in the template, for example the label "Venue"."""

    key: Identifier
    label: ShortText
    value_type: FieldValueType = FieldValueType.TEXT
    required: bool = True
    source_location: SourceLocation
    formatting: FormattingConstraints | None = None


class TableColumn(DomainModel):
    header: ShortText
    # Normalised meaning of the column ("name", "roll_number"); None when it cannot be told.
    key: Identifier | None = None
    formatting: FormattingConstraints | None = None


class TableDefinition(DomainModel):
    columns: list[TableColumn] = Field(min_length=1)
    header_row_count: int = Field(default=1, ge=0, le=10)
    style_name: ShortText | None = None

    @model_validator(mode="after")
    def _validate_columns(self) -> Self:
        ensure_unique((c.key for c in self.columns if c.key is not None), "table column key")
        return self


class ImageLayout(DomainModel):
    """How activity photographs are arranged in the template."""

    columns: int = Field(ge=1, le=12)
    max_images: int | None = Field(default=None, ge=1)
    image_width_cm: float | None = Field(default=None, gt=0)
    image_height_cm: float | None = Field(default=None, gt=0)
    has_captions: bool = False


class TemplateSection(DomainModel):
    id: Identifier
    semantic_type: SemanticType
    order: int = Field(ge=1)
    heading: ShortText | None = None
    content_types: list[ContentType] = Field(min_length=1)
    required: bool = True
    source_location: SourceLocation
    formatting: FormattingConstraints | None = None
    fields: list[TemplateField] = Field(default_factory=list)
    table: TableDefinition | None = None
    image_layout: ImageLayout | None = None

    @model_validator(mode="after")
    def _validate_content_consistency(self) -> Self:
        ensure_unique(self.content_types, "content type")
        content_types = set(self.content_types)
        if (ContentType.TABLE in content_types) != (self.table is not None):
            raise ValueError(
                "a table definition is required exactly when content_types contains 'table'"
            )
        if (ContentType.IMAGE_GRID in content_types) != (self.image_layout is not None):
            raise ValueError(
                "an image layout is required exactly when content_types contains 'image_grid'"
            )
        if (ContentType.KEY_VALUE in content_types) != bool(self.fields):
            raise ValueError("fields are required exactly when content_types contains 'key_value'")
        ensure_unique((f.key for f in self.fields), "field key")
        return self


class TemplateDocument(DomainModel):
    title: ShortText
    source_format: DocumentFormat
    # Fields that belong to the document as a whole (report title, header/footer values).
    fields: list[TemplateField] = Field(default_factory=list)
    sections: list[TemplateSection] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_sections(self) -> Self:
        ensure_unique((s.id for s in self.sections), "section id")
        if [s.order for s in self.sections] != list(range(1, len(self.sections) + 1)):
            raise ValueError("section order values must be 1..n, matching the list order")
        ensure_unique((f.key for f in self.fields), "document field key")
        return self


class TemplateSchema(DomainModel):
    schema_version: Literal[1] = 1
    document: TemplateDocument

    def get_section(self, section_id: str) -> TemplateSection | None:
        for section in self.document.sections:
            if section.id == section_id:
                return section
        return None
