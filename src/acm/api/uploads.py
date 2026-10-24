from collections.abc import AsyncIterator

from fastapi import UploadFile

CHUNK_SIZE = 1024 * 1024


async def iter_upload(file: UploadFile) -> AsyncIterator[bytes]:
    """Adapts FastAPI's UploadFile to a plain async byte stream (keeps services framework-free)."""
    while chunk := await file.read(CHUNK_SIZE):
        yield chunk