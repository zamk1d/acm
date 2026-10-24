import os
import uuid
from pathlib import Path
from typing import Callable

from fastapi import UploadFile, HTTPException

from acm.db.uow import UnitOfWork
from acm.integrations.tiktok import TikTokClient
from acm.models.video import Video
from acm.schemas.video import VideoRead, VideoListRead

UPLOAD_DIR = "uploads"

class StudioService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        tiktok: TikTokClient
    ):
        self.uow_factory = uow_factory
        self.tiktok = tiktok

    async def get_tiktok_videos_list(self, account_id: int, user_id: uuid.UUID):
        async with self.uow_factory() as uow:
            account = await uow.tiktok_accounts.get_for_user(
                account_id=account_id, user_id=user_id
            )
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        return await self.tiktok.get_user_videos(
            access_token=account.access_token,
            fields=["id", "title", "cover_image_url", "embed_link"],
        )

    async def get_videos_list(self, account_id: int, user_id: uuid.UUID) -> list[VideoListRead]:
        async with self.uow_factory() as uow:
            videos = await uow.videos.get_videos_list(account_id=account_id, user_id=user_id)
        return list(VideoListRead.model_validate(video) for video in videos)


    async def upload_video(self, file: UploadFile, account_id: int, title: str, desc: str) -> VideoRead:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        if not file.content_type or not file.content_type.startswith("video/"):
            raise HTTPException(status_code=400, detail="No video provided")
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "mp4"
        unique_name = f"{uuid.uuid4()}.{ext}"
        filepath = os.path.join(UPLOAD_DIR, unique_name)

        with open(filepath, "wb") as buffer:
            while contents := await file.read(1024 * 1024):
                buffer.write(contents)

        video = Video(
            video_name=str(file.filename),
            file_name=unique_name,
            account_id=account_id,
            title=title,
            description=desc
        )

        async with self.uow_factory() as uow:
            uow.videos.add(video)
            await uow.commit()

        return VideoRead.model_validate(video)

    async def get_draft_file(
        self, account_id: int, user_id: uuid.UUID, file_name: str
    ) -> Path:
        async with self.uow_factory() as uow:
            return await uow.videos.get_draft_file(
                account_id=account_id, user_id=user_id, file_name=file_name
            )
