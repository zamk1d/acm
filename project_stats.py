
#!/usr/bin/env python3
"""
Статистика проекта.

Запуск:
    python project_stats.py
    python project_stats.py /path/to/project
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


# Папки, которые не нужно анализировать
EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "site-packages",
}

# Расширения текстовых файлов, которые анализируем
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".css", ".scss",
    ".yaml", ".yml", ".json", ".toml",
    ".ini", ".cfg", ".conf",
    ".md", ".txt", ".rst",
    ".sql", ".sh", ".bash",
    ".env", ".gitignore",
}

# Файлы без расширения, которые тоже считаем текстовыми
TEXT_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "Procfile",
}


@dataclass
class FileStats:
    path: Path
    lines: int = 0
    code: int = 0
    comments: int = 0
    blank: int = 0
    bytes_size: int = 0


@dataclass
class ProjectStats:
    files: int = 0
    lines: int = 0
    code: int = 0
    comments: int = 0
    blank: int = 0
    bytes_size: int = 0


def is_text_file(path: Path) -> bool:
    """Проверяет, стоит ли анализировать файл."""
    if path.name in TEXT_FILENAMES:
        return True

    return path.suffix.lower() in TEXT_EXTENSIONS


def classify_line(line: str, extension: str) -> str:
    """
    Грубая классификация строк.

    Не является полноценным парсером Python/JS и т.д.
    """
    stripped = line.strip()

    if not stripped:
        return "blank"

    # Однострочные комментарии
    if stripped.startswith(("#", "//", "--", ";")):
        return "comment"

    # HTML-комментарии
    if stripped.startswith("<!--") and stripped.endswith("-->"):
        return "comment"

    return "code"


def analyze_file(path: Path) -> FileStats | None:
    """Анализирует один текстовый файл."""
    if not is_text_file(path):
        return None

    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    stats = FileStats(
        path=path,
        bytes_size=len(data),
    )

    for line in text.splitlines():
        stats.lines += 1

        category = classify_line(line, path.suffix.lower())

        if category == "code":
            stats.code += 1
        elif category == "comment":
            stats.comments += 1
        elif category == "blank":
            stats.blank += 1

    return stats


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"

    if size < 1024**2:
        return f"{size / 1024:.1f} KB"

    if size < 1024**3:
        return f"{size / 1024**2:.2f} MB"

    return f"{size / 1024**3:.2f} GB"


def print_file_stats(stats: FileStats, root: Path) -> None:
    relative = stats.path.relative_to(root)

    print(
        f"{str(relative):<55} "
        f"{format_number(stats.lines):>7} строк | "
        f"код {format_number(stats.code):>6} | "
        f"комм. {format_number(stats.comments):>5} | "
        f"пустых {format_number(stats.blank):>5}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Статистика файлов и строк проекта"
    )

    parser.add_argument(
        "project",
        nargs="?",
        default=".",
        help="Путь к проекту (по умолчанию текущая папка)",
    )

    args = parser.parse_args()

    root = Path(args.project).resolve()

    if not root.is_dir():
        raise SystemExit(f"Папка не найдена: {root}")

    total = ProjectStats()
    by_extension: dict[str, ProjectStats] = defaultdict(ProjectStats)
    by_directory: dict[Path, ProjectStats] = defaultdict(ProjectStats)
    all_files: list[FileStats] = []

    for current_root, dirs, filenames in os.walk(root):
        # Не заходим в исключённые папки
        dirs[:] = sorted(
            d for d in dirs
            if d not in EXCLUDED_DIRS
        )

        current_path = Path(current_root)

        for filename in sorted(filenames):
            path = current_path / filename

            stats = analyze_file(path)

            if stats is None:
                continue

            all_files.append(stats)

            # Общая статистика
            total.files += 1
            total.lines += stats.lines
            total.code += stats.code
            total.comments += stats.comments
            total.blank += stats.blank
            total.bytes_size += stats.bytes_size

            # По расширениям
            ext = path.suffix.lower() or "[без расширения]"
            ext_stats = by_extension[ext]

            ext_stats.files += 1
            ext_stats.lines += stats.lines
            ext_stats.code += stats.code
            ext_stats.comments += stats.comments
            ext_stats.blank += stats.blank
            ext_stats.bytes_size += stats.bytes_size

            # По папкам
            relative_dir = path.parent.relative_to(root)
            dir_stats = by_directory[relative_dir]

            dir_stats.files += 1
            dir_stats.lines += stats.lines
            dir_stats.code += stats.code
            dir_stats.comments += stats.comments
            dir_stats.blank += stats.blank
            dir_stats.bytes_size += stats.bytes_size

    # Заголовок
    print("=" * 100)
    print(f"СТАТИСТИКА ПРОЕКТА: {root.name}")
    print(f"Путь: {root}")
    print("=" * 100)

    print("\nОБЩАЯ СТАТИСТИКА")
    print("-" * 100)
    print(f"Файлов:              {format_number(total.files)}")
    print(f"Всего строк:         {format_number(total.lines)}")
    print(f"Строк кода:          {format_number(total.code)}")
    print(f"Строк комментариев:  {format_number(total.comments)}")
    print(f"Пустых строк:        {format_number(total.blank)}")
    print(f"Размер текста:       {format_size(total.bytes_size)}")

    if total.lines:
        code_percent = total.code / total.lines * 100
        comment_percent = total.comments / total.lines * 100
        blank_percent = total.blank / total.lines * 100

        print(f"\nДОЛИ ОТ ВСЕХ СТРОК")
        print(f"Код:                 {code_percent:.1f}%")
        print(f"Комментарии:         {comment_percent:.1f}%")
        print(f"Пустые:              {blank_percent:.1f}%")

    # По расширениям
    print("\nПО РАСШИРЕНИЯМ")
    print("-" * 100)
    print(
        f"{'Расширение':<20} "
        f"{'Файлов':>8} "
        f"{'Строк':>10} "
        f"{'Код':>10} "
        f"{'Комм.':>10} "
        f"{'Размер':>12}"
    )

    for ext, stats in sorted(
        by_extension.items(),
        key=lambda item: item[1].lines,
        reverse=True,
    ):
        print(
            f"{ext:<20} "
            f"{stats.files:>8} "
            f"{stats.lines:>10} "
            f"{stats.code:>10} "
            f"{stats.comments:>10} "
            f"{format_size(stats.bytes_size):>12}"
        )

    # По папкам
    print("\nПО ПАПКАМ")
    print("-" * 100)
    print(
        f"{'Папка':<40} "
        f"{'Файлов':>8} "
        f"{'Строк':>10} "
        f"{'Код':>10} "
        f"{'Комм.':>10}"
    )

    for directory, stats in sorted(
        by_directory.items(),
        key=lambda item: item[1].lines,
        reverse=True,
    ):
        directory_name = str(directory) if str(directory) != "." else "(корень)"

        print(
            f"{directory_name:<40} "
            f"{stats.files:>8} "
            f"{stats.lines:>10} "
            f"{stats.code:>10} "
            f"{stats.comments:>10}"
        )

    # Самые большие файлы
    print("\nТОП-20 ФАЙЛОВ ПО КОЛИЧЕСТВУ СТРОК")
    print("-" * 100)

    for stats in sorted(
        all_files,
        key=lambda item: item.lines,
        reverse=True,
    )[:20]:
        print_file_stats(stats, root)

    print("\n" + "=" * 100)
    print("Анализ завершён.")
    print("=" * 100)


if __name__ == "__main__":
    main()