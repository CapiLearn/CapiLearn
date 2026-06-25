"""Pydantic schemas shared by auth routes, dependencies, and services."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class AuthBaseModel(BaseModel):
    """Base schema using API camelCase aliases and ORM attribute loading."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class UserRole(StrEnum):
    """Roles recognized by auth dependency checks and database constraints."""

    STUDENT = "student"
    INSTRUCTOR = "instructor"
    ADMIN = "admin"


class CurrentUser(AuthBaseModel):
    """User projection returned to authenticated clients."""

    id: UUID
    clerk_id: str
    display_name: str
    role: UserRole


class AuthPrincipal(AuthBaseModel):
    """Minimal role-bearing identity used for authorization checks."""

    clerk_id: str
    role: UserRole


class ClerkAuthClaims(BaseModel):
    """Normalized Clerk token payload after request verification."""

    clerk_id: str
    claims: dict


class DemoAdminSignInTokenResponse(AuthBaseModel):
    token: str


def current_user_to_principal(
    current_user: CurrentUser,
    *,
    role: UserRole | None = None,
) -> AuthPrincipal:
    """Convert a client-facing current user projection into an auth principal."""
    return AuthPrincipal(
        clerk_id=current_user.clerk_id,
        role=role or current_user.role,
    )
