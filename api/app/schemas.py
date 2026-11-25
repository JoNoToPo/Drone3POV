"""Shapes shared by several routers."""

from pydantic import BaseModel, ConfigDict


class ErrorOut(BaseModel):
    """Every error response has this shape."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"detail": "Log in to use this service."}]})

    detail: str


def error(description: str) -> dict:
    """An OpenAPI `responses` entry for an error status code."""
    return {"description": description, "model": ErrorOut}
