"""Enumerations shared by the domain models, the database models and the API schemas."""

from enum import StrEnum


class DocumentFormat(StrEnum):
    DOCX = "docx"
    PDF = "pdf"


class DocumentRegion(StrEnum):
    """Part of a document a location refers to."""

    BODY = "body"
    HEADER = "header"
    FOOTER = "footer"


class SemanticType(StrEnum):
    """Purpose of a template section. ``UNKNOWN`` marks sections the system cannot fill."""

    EVENT_DETAILS = "event_details"
    OBJECTIVES = "objectives"
    ATTENDANCE = "attendance"
    ACTIVITY_IMAGES = "activity_images"
    FEEDBACK = "feedback"
    UNKNOWN = "unknown"


class ContentType(StrEnum):
    """Kind of content a template section expects."""

    TEXT = "text"
    KEY_VALUE = "key_value"
    TABLE = "table"
    IMAGE_GRID = "image_grid"
    STATISTICS = "statistics"


class FieldValueType(StrEnum):
    """Kind of value a template field expects."""

    TEXT = "text"
    DATE = "date"
    DATE_RANGE = "date_range"
    INTEGER = "integer"


class TextAlignment(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


class CoreDetailKey(StrEnum):
    """Event detail keys the specification names explicitly. Templates may use others."""

    EVENT_NAME = "event_name"
    EVENT_DATE = "event_date"
    VENUE = "venue"
    DESCRIPTION = "description"
    OBJECTIVES = "objectives"


class FileRole(StrEnum):
    """What an uploaded file is for."""

    TEMPLATE = "template"
    EVENT_DOCUMENT = "event_document"
    ATTENDANCE = "attendance"
    FEEDBACK = "feedback"
    IMAGE = "image"


class ProvenanceMethod(StrEnum):
    """How a value was produced from its source."""

    PARSED = "parsed"  # read deterministically from a file
    EXTRACTED = "extracted"  # extracted by an LLM
    COMPUTED = "computed"  # calculated by Python
    SUMMARIZED = "summarized"  # summarised by an LLM
    CLASSIFIED = "classified"  # classified or grouped (image processing)
    USER_EDIT = "user_edit"  # entered or corrected by the user during review


class ContentSourceKind(StrEnum):
    """Parts of Event Data a mapping may point at."""

    DETAIL = "detail"
    ATTENDANCE_TABLE = "attendance_table"
    ATTENDANCE_STATISTICS = "attendance_statistics"
    IMAGES = "images"
    FEEDBACK_STATISTICS = "feedback_statistics"
    FEEDBACK_SUMMARY = "feedback_summary"


class StatisticKey(StrEnum):
    """Single computed statistics that can fill one template field."""

    TOTAL_PARTICIPANTS = "total_participants"
    PRESENT_COUNT = "present_count"
    ABSENT_COUNT = "absent_count"
    ATTENDANCE_PERCENTAGE = "attendance_percentage"
    FEEDBACK_RESPONSE_COUNT = "feedback_response_count"
    OVERALL_AVERAGE_RATING = "overall_average_rating"


class ColumnSourceKind(StrEnum):
    """Where one table column's values come from."""

    ATTENDANCE_COLUMN = "attendance_column"
    ROW_NUMBER = "row_number"


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ValidationCode(StrEnum):
    MISSING_REQUIRED_FIELD = "missing_required_field"
    MISSING_SECTION_CONTENT = "missing_section_content"
    CONFLICTING_VALUES = "conflicting_values"
    INVALID_VALUE = "invalid_value"
    UNSUPPORTED_ELEMENT = "unsupported_element"
    SEMANTIC_INCONSISTENCY = "semantic_inconsistency"


class ValidationOrigin(StrEnum):
    """Deterministic Python rule, or the LLM semantic consistency check."""

    RULE = "rule"
    SEMANTIC = "semantic"


class ProcessingStatus(StrEnum):
    """Lifecycle of a template analysis or an event-submission processing run."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportStatus(StrEnum):
    """Lifecycle of a report. Final export is only possible after approval."""

    GENERATING = "generating"
    DRAFT = "draft"  # generated, waiting for human review
    APPROVED = "approved"
    EXPORTED = "exported"
    FAILED = "failed"
