from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, StringConstraints
from pydantic.alias_generators import to_camel

CITATION_ID_PATTERN = r"^[1-9]\d*$"
CitationId = Annotated[
    str,
    StringConstraints(pattern=CITATION_ID_PATTERN, strict=True),
]


class CitationRecord(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        validate_by_alias=False,
        validate_by_name=True,
    )

    citation_id: CitationId
    source_path: str | None = None
    heading: str | None = None
    chunk_text: str

    @classmethod
    def model_validate_wire(cls, data: Any) -> Self:
        return cls.model_validate(data, by_alias=True, by_name=False)
