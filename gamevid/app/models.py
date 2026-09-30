"""project.json schema — the single source of truth for preview and render.

It stores inputs only. Absolute times, frame counts and clip pieces are derived
by timeline.build_timeline(), so preview and render can never disagree.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = 1

SectionKind = Literal["hook", "body", "payoff", "cta"]
TimingSource = Literal["estimated", "aligned", "manual"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Clip(BaseModel):
    source: str  # filename inside the project's footage/ folder
    t_in: float = Field(ge=0)
    t_out: float = Field(gt=0)
    crop_x: float = Field(0.5, ge=0, le=1)  # horizontal crop centre for 9:16 crop mode

    @field_validator("t_out")
    @classmethod
    def _out_after_in(cls, v, info):
        if "t_in" in info.data and v <= info.data["t_in"]:
            raise ValueError("t_out must be after t_in")
        return v


class SectionAudio(BaseModel):
    # Start of this section on the narration track. Sections are contiguous:
    # a section ends where the next one starts (the last ends with the narration).
    start: float = Field(ge=0)
    source: TimingSource = "aligned"


class Section(BaseModel):
    id: str
    kind: SectionKind = "body"
    text: str = ""
    audio: Optional[SectionAudio] = None
    clips: list[Clip] = []


class Narration(BaseModel):
    file: str  # relative to project dir
    duration: float
    sha: str


class Music(BaseModel):
    file: Optional[str] = None  # filename inside the global music/ folder
    volume_db: float = -18.0
    duck: bool = True


class CaptionStyle(BaseModel):
    enabled: bool = True
    font: str = "Arial"
    bold: bool = True
    color: str = "#FFFFFF"
    highlight: str = "#FFD400"
    outline_color: str = "#000000"
    outline: int = 6
    uppercase: bool = False
    size_vertical: int = 88
    size_horizontal: int = 64
    max_words_vertical: int = 3
    max_words_horizontal: int = 7
    # Distance of the caption baseline from the bottom, as a fraction of height.
    margin_vertical: float = 0.30
    margin_horizontal: float = 0.08


class Styles(BaseModel):
    fps: int = 30
    vertical_fill: Literal["crop", "blur"] = "crop"
    captions: CaptionStyle = CaptionStyle()


class StageState(BaseModel):
    input_hash: str = ""
    updated_at: str = ""
    output: Optional[dict] = None


class Project(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str
    title: str
    topic: str = ""
    bullets: list[str] = []
    created_at: str = Field(default_factory=now_iso)
    formats: list[Literal["vertical", "horizontal"]] = ["vertical", "horizontal"]
    sections: list[Section] = []
    narration: Optional[Narration] = None
    music: Music = Music()
    styles: Styles = Styles()
    # Last successful run of each stage and the input hash it ran against.
    stages: dict[str, StageState] = {}
    footage: dict[str, dict] = {}  # filename -> probe info (duration, width, height, fps)
