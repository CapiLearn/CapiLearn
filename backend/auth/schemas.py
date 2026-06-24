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
    display_name: str
    role: UserRole


class AuthPrincipal(AuthBaseModel):
    clerk_id: str
    role: UserRole


class ClerkAuthClaims(BaseModel):
    clerk_id: str
    claims: dict


def current_user_to_principal(
    current_user: CurrentUser,
    *,
    role: UserRole | None = None,
) -> AuthPrincipal:
    return AuthPrincipal(
        clerk_id=current_user.clerk_id,
        role=role or current_user.role,
    )
