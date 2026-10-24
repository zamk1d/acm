from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredFile:
    name: str
    size: int


class FileStorage(Protocol):
    """Where uploaded files live. Services depend on this, not on the disk.

    Today it is a local folder; tomorrow it can be S3 without touching any service.
    """

    async def save(
        self, chunks: AsyncIterator[bytes], *, extension: str, max_bytes: int
    ) -> StoredFile: ...

    def path_for(self, name: str) -> Path | None:
        """Absolute path of a stored file, or None if it doesn't exist."""
        ...

    def new_path(self, extension: str) -> Path:
        """A fresh, not-yet-existing path inside the storage (for ffmpeg / yt-dlp output)."""
        ...

    async def delete(self, name: str) -> None: ...