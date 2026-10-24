import uuid
from pathlib import Path

from sqlalchemy import select
from fastapi import HTTPException
from acm.models import TikTokAccount
from acm.models.video import Video
from acm.repositories.base import BaseRepository

UPLOAD_DIR = Path("uploads")


class VideoRepository(BaseRepository[Video]):
    model = Video

    async def get_by_name(self, video_name: str, account_id: int) -> list[Video]:
        result = await self._session.execute(select(Video).where(Video.video_name == video_name, Video.account_id == account_id))
        return list(result.scalars())

    async def get_by_filename(self, filename: str):
        result = await self._session.execute(select(Video).where(Video.file_name == filename))
        return result.scalar_one_or_none()

    async def get_videos_list(self, account_id: int, user_id: uuid.UUID):
        stmt = (
            select(Video)
            .join(TikTokAccount, TikTokAccount.id == Video.account_id)
            .where(
                Video.account_id == account_id,
                TikTokAccount.user_id == user_id,
                Video.status != "published"
            )
            .order_by(Video.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


    async def get_draft_file(
            self, account_id: int, user_id: uuid.UUID, file_name: str
    ) -> Path:
        stmt = (
            select(Video.file_name)
            .join(TikTokAccount, TikTokAccount.id == Video.account_id)
            .where(
                Video.account_id == account_id,
                Video.file_name == file_name,
                TikTokAccount.user_id == user_id,
            )
        )
        stored = (await self._session.execute(stmt)).scalar_one_or_none()
        if stored is None:
            raise HTTPException(status_code=404, detail="File not found")

        upload_dir = Path(UPLOAD_DIR)
        path = (upload_dir / stored).resolve()
        upload_root = upload_dir.resolve()
        if not path.is_relative_to(upload_root) or not path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return path