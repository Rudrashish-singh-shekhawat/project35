#!/usr/bin/env python3
"""Create a zip archive from generated PDF files."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


ENTRY_SEPARATOR = "::"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zip generated PDF files")
    parser.add_argument("--output", required=True, help="Output zip path")
    parser.add_argument(
        "--entry",
        action="append",
        default=[],
        help="Zip entry in the form: source_path::archive_name",
    )
    return parser.parse_args()


def parse_entry(raw_entry: str) -> tuple[Path, str]:
    source_part, separator, archive_name = str(raw_entry or "").partition(ENTRY_SEPARATOR)
    if not separator:
        raise ValueError("Invalid --entry format. Expected source_path::archive_name")

    source_path = Path(source_part).resolve()
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"Entry source file not found: {source_path}")

    safe_archive_name = Path(archive_name).name
    if not safe_archive_name:
        raise ValueError("Archive entry name cannot be empty")

    return source_path, safe_archive_name


def main() -> None:
    args = parse_args()

    if not args.entry:
        raise ValueError("At least one --entry argument is required")

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for raw_entry in args.entry:
            source_path, archive_name = parse_entry(raw_entry)
            archive.write(source_path, arcname=archive_name)

    print(str(output_path))


if __name__ == "__main__":
    main()
