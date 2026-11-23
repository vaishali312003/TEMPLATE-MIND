"""Shared base class and constrained types for all domain models."""

from collections.abc import Iterable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

# Machine-readable names (section ids, field keys, column keys): lower snake_case.
IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"

Identifier = Annotated[str, StringConstraints(pattern=IDENTIFIER_PATTERN)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=255)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=10_000)]


class DomainModel(BaseModel):
    """Base class: strict about unknown fields, validated on construction and assignment."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )


def ensure_unique(values: Iterable[str], what: str) -> None:
    """Raise ``ValueError`` naming the first duplicated value (for use inside validators)."""
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {what}: {value}")
        seen.add(value)
