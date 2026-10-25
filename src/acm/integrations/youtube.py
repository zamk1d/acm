"""YouTube download via yt-dlp. Blocking code: call it through asyncio.to_thread()."""

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import DownloadError

from acm.core.exceptions import InvalidInputError

# yt-dlp understands thousands of sites; letting users point the server at arbitrary URLs
# is an SSRF risk, so only YouTube hosts are accepted.
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}

MAX_HEIGHT = 1080
MP4_COMPATIBLE = {"mp4", "mov", "m4v"}


@dataclass(frozen=True, slots=True)
class AudioTrack:
    language: str
    language_name: str
    format_id: str
    is_original: bool


@dataclass(frozen=True, slots=True)
class VideoProbe:
    title: str
    duration: float | None
    audio_tracks: list[AudioTrack] = field(default_factory=list)
    default_language: str | None = None


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


def probe_youtube(url: str) -> VideoProbe:
    """Metadata only: title, duration, and the list of audio tracks. No download."""
    url = validate_youtube_url(url)
    opts = {"quiet": True, "no_warnings": True, "socket_timeout": 20}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise InvalidInputError(
            f"Could not read the video: {str(exc).removeprefix('ERROR: ')[:300]}"
        ) from exc

    tracks: dict[str, AudioTrack] = {}
    for fmt in info.get("formats") or []:
        if fmt.get("vcodec") != "none":
            continue
        lang = fmt.get("language")
        if not lang:
            continue
        is_original = "original" in (fmt.get("format_note") or "").lower()
        tbr = fmt.get("tbr") or 0
        prev = tracks.get(lang)
        if (
            prev is None
            or (is_original and not prev.is_original)
            or (is_original == prev.is_original and tbr > 0 and prev.format_id == "")
        ):
            tracks[lang] = AudioTrack(
                language=lang,
                language_name=_language_name(lang),
                format_id=fmt["format_id"],
                is_original=is_original,
            )

    ordered = sorted(tracks.values(), key=lambda t: (not t.is_original, t.language))
    return VideoProbe(
        title=str(info.get("title") or ""),
        duration=info.get("duration"),
        audio_tracks=ordered,
        default_language=ordered[0].language if ordered else None,
    )


def download_youtube(
    url: str,
    stem: Path,
    max_bytes: int,
    on_progress: Callable[[float], None] | None = None,
    *,
    audio_language: str | None = None,
    metadata_language: str | None = None,
) -> Downloaded:
    """Download `url` to `<stem>.<ext>`. `on_progress` gets 0..1 (called from this thread).

    `audio_language` — BCP-47 code ("ru", "en-US"); selects the matching audio track.
    `metadata_language` — same code; makes yt-dlp return title/description in that language.
    """
    state = {"total": 0, "done": {}}

    def hook(d: dict) -> None:
        name = d.get("filename") or ""
        if d.get("status") == "downloading":
            state["done"][name] = d.get("downloaded_bytes") or 0
        elif d.get("status") == "finished":
            state["done"][name] = d.get("total_bytes") or state["done"].get(name, 0)
        if on_progress and state["total"]:
            on_progress(min(sum(state["done"].values()) / state["total"], 0.99))

    opts: dict = {
        "outtmpl": str(stem).replace("%", "%%") + ".%(ext)s",
        "format": _build_format(audio_language),
        # mkv as a safety net: mp4 can't hold VP9/opus, and we'd rather remux locally
        # than fail the whole import. _ensure_mp4() converts afterwards.
        "merge_output_format": "mp4/mkv",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "retries": 3,
        "http_chunk_size": 10 * 1024 * 1024,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [hook],
    }
    if metadata_language:
        opts["extractor_args"] = {"youtube": {"lang": [metadata_language]}}

    def leftovers() -> list[Path]:
        return [p for p in stem.parent.iterdir() if p.name.startswith(stem.name + ".")]

    def clean() -> None:
        for p in leftovers():
            p.unlink(missing_ok=True)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            parts = info.get("requested_formats") or [info]
            state["total"] = sum(p.get("filesize") or p.get("filesize_approx") or 0 for p in parts)
            if state["total"] > max_bytes:
                raise InvalidInputError(
                    f"The video is too large (~{state['total'] // 2**20} MB, "
                    f"limit {max_bytes // 2**20} MB)"
                )
            ydl.process_ie_result(info, download=True)

        files = [p for p in leftovers() if p.suffix not in {".part", ".ytdl"}]
        if not files:
            raise InvalidInputError("The video could not be downloaded")
        title = str(info.get("title") or "YouTube video")

        # Format selector sometimes collapses to a video-only stream (e.g. when none
        # of the (video, audio) pairs matched). Detect and recover with a muxed fallback.
        if not _has_audio_stream(files[0]):
            clean()
            fallback = dict(opts, format=f"b[height<={MAX_HEIGHT}]/b")
            with yt_dlp.YoutubeDL(fallback) as ydl2:
                ydl2.download([url])
            files = [p for p in leftovers() if p.suffix not in {".part", ".ytdl"}]
            if not files or not _has_audio_stream(files[0]):
                clean()
                raise InvalidInputError(
                    "The downloaded video has no audio track. Try another link."
                )

        # Final container fix: TikTok accepts mp4/mov/webm, but yt-dlp may have merged
        # into .mkv (VP9/opus). _ensure_mp4() tries copy → aac-audio → full transcode.
        mp4_path = _ensure_mp4(files[0])
        return Downloaded(path=mp4_path, title=title)
    except DownloadError as exc:
        clean()
        raise InvalidInputError(
            f"Could not download the video: {str(exc).removeprefix('ERROR: ')[:300]}"
        ) from exc
    except BaseException:
        clean()
        raise


def _build_format(audio_language: str | None) -> str:
    """Selector with explicit fallbacks. yt-dlp evaluates / and + left-to-right.

    Preference order, most specific first:
      1. mp4 video + AAC audio in the chosen language (no transcoding needed)
      2. any video + AAC audio in the chosen language
      3. mp4 video + any audio in the chosen language (may end up as mkv)
      4. any video + any audio in the chosen language
      5. mp4 video + AAC in any language (wrong language, but keeps the container clean)
      6. mp4 video + any audio
      7. any video + any audio
      8. single-file (muxed) fallback
    """
    video_mp4 = f"bv*[height<={MAX_HEIGHT}][ext=mp4]"
    video_any = f"bv*[height<={MAX_HEIGHT}]"
    single_mp4 = f"b[height<={MAX_HEIGHT}][ext=mp4]"
    single_any = f"b[height<={MAX_HEIGHT}]"

    if audio_language:
        lang_aac = f"ba[language^={audio_language}][ext=m4a]"
        lang_any = f"ba[language^={audio_language}]"
        return (
            f"{video_mp4}+{lang_aac}"
            f"/{video_any}+{lang_aac}"
            f"/{video_mp4}+{lang_any}"
            f"/{video_any}+{lang_any}"
            f"/{video_mp4}+ba[ext=m4a]"
            f"/{video_mp4}+ba"
            f"/{video_any}+ba"
            f"/{single_mp4}"
            f"/{single_any}"
        )
    return (
        f"{video_mp4}+ba[ext=m4a]"
        f"/{video_any}+ba[ext=m4a]"
        f"/{video_mp4}+ba"
        f"/{video_any}+ba"
        f"/{single_mp4}"
        f"/{single_any}"
    )


def _ensure_mp4(path: Path) -> Path:
    """Return an .mp4 file. If `path` is already mp4/mov, return as-is.

    Otherwise, try (in order):
      1. remux with `-c copy`      — fastest, works for h264+aac/hevc+aac in mkv
      2. copy video, transcode audio to AAC — works for h264+opus
      3. full transcode to h264/aac        — last resort (VP9/AV1 video)
    """
    if path.suffix.removeprefix(".").lower() in MP4_COMPATIBLE:
        return path

    out = path.with_suffix(".mp4")
    attempts = (
        ["-c", "copy"],
        ["-c:v", "copy", "-c:a", "aac", "-b:a", "128k"],
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k"],
    )
    for args in attempts:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), *args,
             "-movflags", "+faststart", str(out)],
            capture_output=True, timeout=600,
        )
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 0:
            path.unlink(missing_ok=True)
            return out
        out.unlink(missing_ok=True)  # partial file from a failed attempt
    raise InvalidInputError("Could not convert the downloaded video to MP4")


def _has_audio_stream(path: Path) -> bool:
    """ffprobe: does the file contain at least one audio stream?"""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
            capture_output=True, timeout=30,
        )
        return bool(proc.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return True  # don't block on ffprobe failures


# Small display map; extend as needed. Unknown codes just show the raw code.
_LANG_NAMES = {
    "en": "English", "en-US": "English (US)", "en-GB": "English (UK)",
    "ru": "Russian", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "pt-BR": "Portuguese (BR)",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "zh-Hans": "Chinese (Simplified)",
    "zh-Hant": "Chinese (Traditional)", "ar": "Arabic", "hi": "Hindi",
    "tr": "Turkish", "pl": "Polish", "uk": "Ukrainian", "nl": "Dutch",
}


def _language_name(code: str) -> str:
    return _LANG_NAMES.get(code, code)