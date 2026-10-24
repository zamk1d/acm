# acm/schemas/video.py
from pydantic import BaseModel, ConfigDict

class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_name: str
    file_name: str
    account_id: int
    title: str
    description: str | None = None

class VideoRequest(BaseModel):
    title: str
    description: str

class VideoListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    video_name: str
    file_name: str
    status: str
    title: str
    description: str | None = None