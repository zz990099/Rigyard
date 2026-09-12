"""Explicit references shared by feature configuration models."""

from pydantic import BaseModel, ConfigDict, field_validator

from .models import PARAMETER_NAME


class ParameterRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parameter: str

    @field_validator("parameter")
    @classmethod
    def valid_parameter_name(cls, value: str) -> str:
        if not PARAMETER_NAME.fullmatch(value):
            raise ValueError(f"invalid parameter name {value!r}")
        return value
