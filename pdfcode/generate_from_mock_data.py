#!/usr/bin/env python3
"""Connect mock student data to pdf_generator operations.

This script performs all download-side operations in one place:
- validate input filters against mock_students.json
- match the requested student record
- generate PDF using pdf_generator.make_pdf
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from pdf_generator import DEFAULT_LOGO_PATH, DEFAULT_SEMESTER, make_pdf


DEFAULT_WIDTH_JSON_PATH = Path(__file__).resolve().parent / "width.json"

ROLL_NO_KEYS = ("rollNo", "roll_no", "University_RollNo", "universityRollNo")
ENROLLMENT_NO_KEYS = ("enrollmentNo", "enrollment_no", "Enrollment_No", "EnrollmentNo")
STUDENT_NAME_KEYS = ("studentName", "student_name", "Student_Name")
FATHER_NAME_KEYS = ("fatherName", "father_name", "Father_Name")
MOTHER_NAME_KEYS = ("motherName", "mother_name", "Mother_Name")
SESSION_KEYS = ("session", "Session")
EXAM_CATEGORY_KEYS = ("examCategory", "exam_category", "Exam_Category")
DEGREE_KEYS = ("degree", "Degree")
SEMESTER_KEYS = ("semester", "Semester")
SEMESTER_SECTION_KEYS = ("semesterSection", "semester_section", "semestor")
SHARED_METADATA_KEYS = (
    "session",
    "examCategory",
    "degree",
    "semester",
    "semesterSection",
    "universityName",
    "collegeName",
    "examName",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate marksheet PDF from mock data")
    parser.add_argument("--json", required=True, help="Path to mock_students.json")
    parser.add_argument("--roll", required=True, help="Roll number")
    parser.add_argument("--father", required=True, help="Father name")
    parser.add_argument("--mother", default="", help="Mother name")
    parser.add_argument("--session", default="", help="Session filter")
    parser.add_argument("--exam-category", default="", help="Exam category filter")
    parser.add_argument("--degree", default="", help="Degree filter")
    parser.add_argument("--semester", default="", help="Semester filter")
    parser.add_argument("--output", required=True, help="Output PDF path")
    parser.add_argument("--logo", default=DEFAULT_LOGO_PATH, help="Logo image path")
    return parser.parse_args()


def normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def pick_record_value(
    record: dict[str, Any],
    keys: tuple[str, ...],
    shared_defaults: dict[str, Any] | None = None,
) -> Any:
    for key in keys:
        if key not in record:
            continue

        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue

        return value

    if isinstance(shared_defaults, dict):
        for key in keys:
            if key not in shared_defaults:
                continue

            value = shared_defaults.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue

            return value

    return None


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


def load_width_table(width_json_path: Path | str = DEFAULT_WIDTH_JSON_PATH) -> dict[str, Any]:
    path = Path(width_json_path)
    if not path.exists():
        raise ValueError("width.json not found")

    with path.open("r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)

    if not isinstance(data, dict):
        raise ValueError("Invalid width.json format")

    return data


def calculate_word_width(word: str, width_table: dict[str, Any], bold: bool = False) -> float:
    uppercase = width_table.get("uppercase") if isinstance(width_table.get("uppercase"), dict) else {}
    lowercase = width_table.get("lowercase") if isinstance(width_table.get("lowercase"), dict) else {}
    digits = width_table.get("digits") if isinstance(width_table.get("digits"), dict) else {}
    symbols = width_table.get("symbols") if isinstance(width_table.get("symbols"), dict) else {}

    default_width = float(digits.get("0", 5.004))
    space_width = float(symbols.get(",", 2.007))

    total = 0.0
    for char in str(word or ""):
        if char == " ":
            total += space_width
            continue

        if char in uppercase:
            total += float(uppercase[char])
            continue

        if char in lowercase:
            total += float(lowercase[char])
            continue

        if char in digits:
            total += float(digits[char])
            continue

        if char in symbols:
            total += float(symbols[char])
            continue

        total += default_width

    if bold:
        total *= float(width_table.get("bold_factor", 1.0))

    return round(total, 3)


def load_students(json_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not json_path.exists():
        raise ValueError("mock_students.json not found")

    with json_path.open("r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)

    shared_defaults: dict[str, Any] = {}

    if isinstance(data, list):
        students = data
    elif isinstance(data, dict):
        students = data.get("students")
        for key in SHARED_METADATA_KEYS:
            if key not in data:
                continue

            value = data.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue

            shared_defaults[key] = value
    else:
        students = None

    if not isinstance(students, list):
        raise ValueError("Invalid mock_students.json format")

    return [row for row in students if isinstance(row, dict)], shared_defaults


def match_filters(
    record: dict[str, Any],
    args: argparse.Namespace,
    shared_defaults: dict[str, Any],
) -> bool:
    if args.session and normalize(pick_record_value(record, SESSION_KEYS, shared_defaults)) != normalize(args.session):
        return False
    if args.exam_category and normalize(pick_record_value(record, EXAM_CATEGORY_KEYS, shared_defaults)) != normalize(args.exam_category):
        return False
    if args.degree and normalize(pick_record_value(record, DEGREE_KEYS, shared_defaults)) != normalize(args.degree):
        return False
    if args.semester and normalize(pick_record_value(record, SEMESTER_KEYS, shared_defaults)) != normalize(args.semester):
        return False
    return True


def find_student(
    students: list[dict[str, Any]],
    args: argparse.Namespace,
    shared_defaults: dict[str, Any],
) -> dict[str, Any]:
    roll_no = normalize(args.roll)
    father_input = normalize(args.father)
    mother_input = normalize(args.mother)

    if not roll_no:
        raise ValueError("Roll No. is required !")
    if not father_input and not mother_input:
        raise ValueError("Mother Or Father Name is required !")

    if (father_input and len(father_input) <= 3) or (mother_input and len(mother_input) <= 3):
        raise ValueError("Please enter at least the first 4 characters of your Father  Name!")

    roll_matches = [row for row in students if normalize(pick_record_value(row, ROLL_NO_KEYS)) == roll_no]
    if not roll_matches:
        raise ValueError("Result not found for this Roll No.")

    detailed_matches = [row for row in roll_matches if match_filters(row, args, shared_defaults)]
    if not detailed_matches:
        raise ValueError("No result found for selected Session, Exam Category, Degree, and Semester")

    provided_names = [value for value in (father_input, mother_input) if value]

    for row in detailed_matches:
        father_value = normalize(pick_record_value(row, FATHER_NAME_KEYS))
        mother_value = normalize(pick_record_value(row, MOTHER_NAME_KEYS))
        if any(name in father_value or name in mother_value for name in provided_names):
            return row

    raise ValueError("Parent name does not match record")


def pick_subject_text(subject: dict[str, Any], keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        if key not in subject:
            continue
        value = subject.get(key)
        if value is None:
            return default
        text = str(value).strip()
        return text or default
    return default


def pick_subject_mark(subject: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key not in subject:
            continue
        value = subject.get(key)
        if value is None:
            return "-"
        text = str(value).strip()
        return text or "-"
    return ""


def extract_course_rows(matched_student: dict[str, Any]) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    course_titles: list[str] = []
    course_codes: list[str] = []
    midterm_marks: list[str] = []
    endterm_marks: list[str] = []
    grades: list[str] = []

    subjects = matched_student.get("subjects")
    if not isinstance(subjects, list):
        return course_titles, course_codes, midterm_marks, endterm_marks, grades

    for subject in subjects:
        if not isinstance(subject, dict):
            continue

        course_titles.append(
            pick_subject_text(subject, ("title", "course_title", "courseTitle", "subject_title"), "-")
        )
        course_codes.append(
            pick_subject_text(subject, ("code", "course_code", "courseCode", "subject_code"), "-")
        )
        midterm_marks.append(
            pick_subject_mark(subject, ("midterm", "marks_midterm", "midTerm", "marksMidterm"))
        )
        endterm_marks.append(
            pick_subject_mark(subject, ("endterm", "marks_endterm", "endTerm", "marksEndterm"))
        )
        grades.append(
            pick_subject_text(subject, ("grade", "result_grade", "letter_grade"), "-")
        )

    return course_titles, course_codes, midterm_marks, endterm_marks, grades


def main() -> None:
    args = parse_args()

    students, shared_defaults = load_students(Path(args.json).resolve())
    matched_student = find_student(students, args, shared_defaults)

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logo_path = str(Path(args.logo).resolve()) if args.logo else DEFAULT_LOGO_PATH
    roll_no = str(pick_record_value(matched_student, ROLL_NO_KEYS) or args.roll).strip()
    enrollment_no = str(pick_record_value(matched_student, ENROLLMENT_NO_KEYS) or "-").strip() or "-"
    student_name = str(pick_record_value(matched_student, STUDENT_NAME_KEYS) or "-").strip() or "-"
    father_name = str(pick_record_value(matched_student, FATHER_NAME_KEYS) or args.father).strip() or "-"
    semester_source = (
        pick_record_value(matched_student, SEMESTER_SECTION_KEYS, shared_defaults)
        or pick_record_value(matched_student, SEMESTER_KEYS, shared_defaults)
        or args.semester
    )
    semester = extract_semester_section(semester_source) or DEFAULT_SEMESTER

    course_titles, course_codes, midterm_marks, endterm_marks, grades = extract_course_rows(matched_student)

    make_pdf(
        str(output_path),
        logo_path=logo_path,
        roll_no=roll_no,
        enrollment_no=enrollment_no,
        student_name=student_name,
        father_name=father_name,
        semester=semester,
        course_titles=course_titles,
        course_codes=course_codes,
        midterm_marks=midterm_marks,
        endterm_marks=endterm_marks,
        grades=grades,
    )

    print(str(output_path))


if __name__ == "__main__":
    main()
