from dataclasses import dataclass
from typing import Any
from enum import Enum

from pydantic import BaseModel, Field



@dataclass
class ApiResponse:
    data: Any
    status: int
    message: str


class AudioFormat(str, Enum):
    WAV = "wav"
