from pydantic import BaseModel, ConfigDict, Field, field_validator


class OneCCategoryImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_1c_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    parent_external_1c_id: str | None = Field(default=None, max_length=100)
    is_active: bool = True
    sort_order: int = 0

    @field_validator("external_1c_id", "name", "slug", "parent_external_1c_id", mode="before")
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = " ".join(value.strip().split())
        return normalized_value or None


class OneCCategoryImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OneCCategoryImportItem]


class OneCImportItemErrorResponse(BaseModel):
    external_1c_id: str
    message: str
    field: str | None = None


class OneCImportResultResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[OneCImportItemErrorResponse]
