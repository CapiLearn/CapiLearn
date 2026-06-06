from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class AuthBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class UserRole(StrEnum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    ADMIN = "admin"


class CurrentUser(AuthBaseModel):
    id: UUID
    clerk_id: str
    email: str | None = None
    display_name: str | None = None
    role: UserRole


class CurrentUserResponse(AuthBaseModel):
    id: UUID
    clerk_id: str
    email: str | None = None
    display_name: str | None = None
    role: UserRole


class ClerkAuthClaims(BaseModel):
    clerk_id: str
    email: str | None = None
    display_name: str | None = None
    claims: dict
