"""Scopes and the /user/info/ fields each one unlocks (a field without its scope fails)."""

from collections.abc import Iterable

SCOPE_USER_INFO_BASIC = "user.info.basic"
SCOPE_USER_INFO_PROFILE = "user.info.profile"
SCOPE_USER_INFO_STATS = "user.info.stats"
SCOPE_VIDEO_LIST = "video.list"
SCOPE_VIDEO_PUBLISH = "video.publish"    # direct post
SCOPE_VIDEO_UPLOAD = "video.upload"      # inbox / drafts

STATS_FIELDS = ("follower_count", "following_count", "likes_count", "video_count")

_FIELDS_BY_SCOPE: dict[str, tuple[str, ...]] = {
    SCOPE_USER_INFO_BASIC: (
        "open_id",
        "union_id",
        "avatar_url",
        "avatar_url_100",
        "avatar_large_url",
        "display_name",
    ),
    SCOPE_USER_INFO_PROFILE: (
        "bio_description",
        "profile_deep_link",
        "is_verified",
        "username",
    ),
    SCOPE_USER_INFO_STATS: (
        "follower_count",
        "following_count",
        "likes_count",
        "video_count",
    ),
}


def fields_for_scopes(scopes: Iterable[str]) -> list[str]:
    fields: list[str] = []
    for scope in scopes:
        for field in _FIELDS_BY_SCOPE.get(scope, ()):
            if field not in fields:
                fields.append(field)
    return fields or list(_FIELDS_BY_SCOPE[SCOPE_USER_INFO_BASIC])
