"""Chunk planning for TikTok's Media Transfer Guide (chunk upload rules)."""

import mimetypes
from dataclasses import dataclass
from pathlib import Path

MIN_CHUNK = 5 * 1024 * 1024
MAX_CHUNK = 64 * 1024 * 1024
TARGET_CHUNK = 10 * 1024 * 1024
WHOLE_FILE_MAX = 64 * 1024 * 1024  # ≤ 64 MB → upload as one chunk


@dataclass(frozen=True, slots=True)
class ChunkPlan:
    video_size: int
    chunk_size: int
    total_chunk_count: int

    def ranges(self):
        """Yields inclusive byte ranges (start, end) for every chunk."""
        offset = 0
        for _ in range(self.total_chunk_count):
            end = min(offset + self.chunk_size, self.video_size) - 1
            yield offset, end
            offset = end + 1


def plan_chunks(video_size: int) -> ChunkPlan:
    """
    TikTok requires `total_chunk_count = video_size // chunk_size` (floor), not ceil.
    Videos ≤ 64 MB are sent in one chunk; larger ones are split into 10 MB chunks.
    """
    if video_size <= WHOLE_FILE_MAX:
        return ChunkPlan(video_size, video_size, 1)
    chunk_size = min(TARGET_CHUNK, MAX_CHUNK)
    count = max(1, video_size // chunk_size)
    return ChunkPlan(video_size, chunk_size, count)


def mime_for(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"