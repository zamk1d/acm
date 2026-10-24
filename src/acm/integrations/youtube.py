"""YouTube download via yt-dlp. Blocking code: call it through asyncio.to_thread()."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import DownloadError

from acm.core.exceptions import InvalidInputError

# yt-dlp understands thousands of sites; letting users point the server at arbitrary URLs
# is an SSRF risk, so only YouTube hosts are accepted.
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}

MAX_HEIGHT = 1080  # TikTok doesn't need more, and 4K is 5-10x the bytes to download
# Prefer progressive/mp4 (no re-encode needed), capped at MAX_HEIGHT.
_FORMAT = (
    f"bv*[height<={MAX_HEIGHT}][ext=mp4]+ba[ext=m4a]/b[height<={MAX_HEIGHT}][ext=mp4]"
    f"/bv*[height<={MAX_HEIGHT}]+ba/b[height<={MAX_HEIGHT}]/b"
)


@dataclass(frozen=True, slots=True)
class Downloaded:
    path: Path
    title: str


def validate_youtube_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in _HOSTS:
        raise InvalidInputError("Only YouTube links are supported")
    return parsed.geturl()


def download_youtube(
    url: str,
    stem: Path,
    max_bytes: int,
    on_progress: Callable[[float], None] | None = None,
) -> Downloaded:
    """Download `url` to `<stem>.<ext>`. `on_progress` gets 0..1 (called from this thread)."""
    state = {"total": 0, "done": {}}

    def hook(d: dict) -> None:
        name = d.get("filename") or ""
        if d.get("status") == "downloading":
            state["done"][name] = d.get("downloaded_bytes") or 0
        elif d.get("status") == "finished":
            state["done"][name] = d.get("total_bytes") or state["done"].get(name, 0)
        if on_progress and state["total"]:
            on_progress(min(sum(state["done"].values()) / state["total"], 0.99))

    opts = {
        "outtmpl": str(stem).replace("%", "%%") + ".%(ext)s",
        "format": _FORMAT,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "retries": 3,
        # YouTube throttles long single-connection downloads; ranged 10 MB chunks avoid that.
        "http_chunk_size": 10 * 1024 * 1024,
        "concurrent_fragment_downloads": 4,  # for HLS/DASH formats
        "progress_hooks": [hook],
    }

    def leftovers() -> list[Path]:
        return [p for p in stem.parent.iterdir() if p.name.startswith(stem.name + ".")]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)  # metadata only: a few seconds
            parts = info.get("requested_formats") or [info]
            state["total"] = sum(p.get("filesize") or p.get("filesize_approx") or 0 for p in parts)
            if state["total"] > max_bytes:  # fail before downloading, not after
                raise InvalidInputError(
                    f"The video is too large (~{state['total'] // 2**20} MB, "
                    f"limit {max_bytes // 2**20} MB)"
                )
            ydl.process_ie_result(info, download=True)  # no second extraction
        files = [p for p in leftovers() if p.suffix not in {".part", ".ytdl"}]
        if not files:
            raise InvalidInputError("The video could not be downloaded")
        return Downloaded(path=files[0], title=str(info.get("title") or "YouTube video"))
    except DownloadError as exc:
        for p in leftovers():
            p.unlink(missing_ok=True)
        raise InvalidInputError(
            f"Could not download the video: {str(exc).removeprefix('ERROR: ')[:300]}"
        ) from exc
    except BaseException:
        for p in leftovers():
            p.unlink(missing_ok=True)
        raise