from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=128)
    favorite_ids: list[Annotated[PositiveInt, Field(le=9223372036854775807)]] = Field(default_factory=list, max_length=20)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class SignupRequest(LoginRequest):
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password", mode="before")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        issues = []
        if len(value) < 8:
            issues.append("Le mot de passe doit contenir au moins 8 caractères.")
        if len(value) > 128:
            issues.append("Le mot de passe doit contenir au maximum 128 caractères.")
        has_uppercase = any(character.isalpha() and character.isupper() for character in value)
        has_digit = any(character in "0123456789" for character in value)
        has_special = any(not character.isalnum() and not character.isspace() for character in value)
        if not has_uppercase:
            issues.append("Il manque une lettre majuscule dans le mot de passe.")
        if not has_digit:
            issues.append("Il manque un chiffre dans le mot de passe.")
        if not has_special:
            issues.append("Il manque un caractère spécial dans le mot de passe (un espace ne compte pas).")
        if issues:
            raise ValueError(" ".join(issues))
        return value


class PublicUser(BaseModel):
    id: str
    username: str
    created_at: datetime


class AccountResponse(BaseModel):
    user: PublicUser | None = None
    favorite_ids: list[int] = Field(default_factory=list)


class FavoritesResponse(BaseModel):
    ids: list[int]
