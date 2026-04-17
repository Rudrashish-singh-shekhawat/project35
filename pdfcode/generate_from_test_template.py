#!/usr/bin/env python3
"""Bridge script: connect server download endpoint to pdf_generator.py.

Server currently invokes this script with template-style arguments.
This bridge validates lookup inputs against mock JSON and then calls
pdf_generator.make_pdf to produce the final PDF.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from pdf_generator import DEFAULT_SEMESTER, make_pdf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate marksheet PDF for server download route")
    parser.add_argument("--json", required=True, help="Path to mock_students.json")
    parser.add_argument("--template", required=False, default="", help="Path to test.tex template")
    parser.add_argument("--roll", required=True, help="Roll number")
    parser.add_argument("--father", required=True, help="Father name")
    parser.add_argument("--session", default="", help="Session filter")
    parser.add_argument("--exam-category", default="", help="Exam category filter")
    parser.add_argument("--degree", default="", help="Degree filter")
    parser.add_argument("--semester", default="", help="Semester filter")
    parser.add_argument("--output", required=True, help="Output PDF path")
    return parser.parse_args()


def normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def extract_semester_section(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    roman_match = re.search(r"\b([ivx]+)(?:st|nd|rd|th)?\b", text, flags=re.IGNORECASE)
    if roman_match:
        return roman_match.group(1).upper()

    number_match = re.search(r"\b(\d+)(?:st|nd|rd|th)?\b", text, flags=re.IGNORECASE)
    if number_match:
        return number_match.group(1)

    return text


def load_dataset(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or not isinstance(data.get("students"), list):
        raise ValueError("Invalid mock_students.json format")

    return data


def record_matches_filters(record: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.session and normalize(record.get("session")) != normalize(args.session):
        return False
    if args.exam_category and normalize(record.get("examCategory")) != normalize(args.exam_category):
        return False
    if args.degree and normalize(record.get("degree")) != normalize(args.degree):
        return False
    if args.semester and normalize(record.get("semester")) != normalize(args.semester):
        return False
    return True


def validate_record_exists(dataset: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    students = dataset.get("students", [])
    roll = normalize(args.roll)
    father = normalize(args.father)

    if not roll:
        raise ValueError("Roll No. is required !")
    if not father:
        raise ValueError("father name does not match")

    roll_matches = [s for s in students if normalize(s.get("rollNo")) == roll]
    if not roll_matches:
        raise ValueError("roll number not found")

    filtered = [s for s in roll_matches if record_matches_filters(s, args)]
    if not filtered:
        raise ValueError("No result found for selected Session, Exam Category, Degree, and Semester")

    for record in filtered:
        if father in normalize(record.get("fatherName")):
            return record

    raise ValueError("father name does not match")


def resolve_logo_path(args: argparse.Namespace) -> str:
    if args.template:
        template_dir = Path(args.template).resolve().parent
        logo_from_template = template_dir / "image" / "extracted-000.jpg"
        if logo_from_template.exists():
            return str(logo_from_template)

    fallback = Path(__file__).resolve().parent / "image" / "extracted-000.jpg"
    return str(fallback)


def main() -> None:
    args = parse_args()

    dataset = load_dataset(Path(args.json))
    matched_record = validate_record_exists(dataset, args)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logo_path = resolve_logo_path(args)
    make_pdf(
        str(output_path),
        logo_path=logo_path,
        semester=(
            extract_semester_section(
                matched_record.get("semesterSection")
                or matched_record.get("semester_section")
                or matched_record.get("semestor")
                or matched_record.get("semester")
                or args.semester
            )
            or DEFAULT_SEMESTER
        ),
    )

    print(str(output_path))


if __name__ == "__main__":
    main()
