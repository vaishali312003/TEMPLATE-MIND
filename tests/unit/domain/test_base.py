import pytest
from pydantic import ValidationError

from app.domain.base import DomainModel, Identifier, ShortText, ensure_unique


class Sample(DomainModel):
    key: Identifier
    label: ShortText


def test_valid_values_are_accepted_and_whitespace_is_stripped() -> None:
    sample = Sample(key="event_name", label="  Event name  ")

    assert sample.key == "event_name"
    assert sample.label == "Event name"


@pytest.mark.parametrize(
    "key", ["Event", "1event", "event-name", "event name", "", "_event", "a" * 65]
)
def test_identifier_rejects_invalid_values(key: str) -> None:
    with pytest.raises(ValidationError):
        Sample(key=key, label="x")


def test_identifier_accepts_maximum_length() -> None:
    assert Sample(key="a" * 64, label="x").key == "a" * 64


@pytest.mark.parametrize("label", ["", "   ", "x" * 256])
def test_short_text_bounds(label: str) -> None:
    with pytest.raises(ValidationError):
        Sample(key="a", label=label)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Sample(key="a", label="b", unexpected=1)  # type: ignore[call-arg]


def test_assignment_is_validated() -> None:
    sample = Sample(key="a", label="b")

    with pytest.raises(ValidationError):
        sample.key = "Bad Key"


def test_ensure_unique_accepts_unique_values() -> None:
    ensure_unique(["a", "b", "c"], "thing")


def test_ensure_unique_names_the_first_duplicate() -> None:
    with pytest.raises(ValueError, match="duplicate thing: b"):
        ensure_unique(["a", "b", "b", "a"], "thing")
