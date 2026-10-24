import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from acm.core.exceptions import FileTooLargeError
from acm.storage.base import StoredFile


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    async def save(
        self, chunks: AsyncIterator[bytes], *, extension: str, max_bytes: int
    ) -> StoredFile:
        name = f"{uuid.uuid4().hex}.{extension}"
        path = self._root / name
        size = 0
        try:
            with path.open("wb") as fh:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise FileTooLargeError(
                            f"File is larger than {max_bytes // (1024 * 1024)} MB"
                        )
                    # disk write is blocking IO: keep it off the event loop
                    await asyncio.to_thread(fh.write, chunk)
        except BaseException:
            path.unlink(missing_ok=True)  # never leave half-written files behind
            raise
        return StoredFile(name=name, size=size)

    def path_for(self, name: str) -> Path | None:
        path = (self._root / name).resolve()
        if not path.is_relative_to(self._root) or not path.is_file():
            return None
        return path

    async def delete(self, name: str) -> None:
        path = self.path_for(name)
        if path is not None:
            await asyncio.to_thread(path.unlink, missing_ok=True)