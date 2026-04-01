from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class InputType(StrEnum):
    USER_MODEL = "user_model"
    PARAMETER = "parameter"
    AUTH_INFO = "auth_info"
    USER_LINK = "user_link"


class Input(BaseModel, Generic[T]):
    type: InputType
    value: T

    model_config = ConfigDict(extra="allow")


class OutputType(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"


@dataclass
class Output:
    name: str
    type: OutputType
    path: str
