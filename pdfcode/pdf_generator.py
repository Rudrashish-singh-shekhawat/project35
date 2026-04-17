"""
RTU B.Tech V Sem Marksheet PDF Generator
Replicates the LaTeX/TikZ fixed-layout PDF exactly using ReportLab.
Coordinate system: origin = bottom-left, y increases upward (same as LaTeX TikZ).
Units: big points (bp) == pt in ReportLab.
Includes width parameter extracted from \PdfWord macro.
"""

import argparse
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

PAGE_WIDTH  = 595   # bp
PAGE_HEIGHT = 842   # bp
DEFAULT_LOGO_PATH = os.path.join(os.path.dirname(__file__), "image", "extracted-000.jpg")
DEFAULT_ROLL_NO = "23EUCPC001"
DEFAULT_ENROLLMENT_NO = "23E1UCPCM30P001"
DEFAULT_STUDENT_NAME = "CHETAN SUMAN"
DEFAULT_FATHER_NAME = "NEMI CHAND SUMAN"
DEFAULT_SEMESTER = "V"
DEFAULT_COURSE_TITLES = [
    "Environmental Pollution Control",
    "Chemical Reaction Engineering -I",
    "Mass Transfer -II",
    "Process Equipment Design -I",
    "Petrochemical Technology",
    "Chemical Reaction Engineering Lab-I",
    "Mass Transfer Lab -II",
    "Environmental Engineering Lab",
    "Natural Gas Engineering",
    "Industrial Training",
    "Music",
]
DEFAULT_COURSE_CODES = [
    "5PC3-01",
    "5PC4-02",
    "5PC4-03",
    "5PC4-04",
    "5PC4-05",
    "5PC4-21",
    "5PC4-22",
    "5PC4-23",
    "5PC5-11",
    "5PC7-30",
    "FEC26",
]
DEFAULT_MIDTERM_MARKS = ["23", "16", "0", "22", "14", "47", "36", "30", "14", "35", "-"]
DEFAULT_ENDTERM_MARKS = ["41", "33", "48", "38", "40", "24", "30", "20", "46", "27", "68"]
DEFAULT_GRADES = ["A", "C", "D", "B+", "C+", "A+", "B", "D+", "A+", "B+", "B+"]
COURSE_ROW_LAYOUTS = [
    (663.097, 35.514, 333.850, 10.008, 433.110, 10.008, 534.370, 6.003),
    (646.097, 35.514, 333.850, 10.008, 433.110, 10.008, 534.120, 6.498),
    (629.097, 35.514, 336.360, 5.004, 433.110, 10.008, 534.120, 6.498),
    (612.097, 35.514, 333.850, 10.008, 433.110, 10.008, 531.740, 11.259),
    (595.097, 35.514, 333.850, 10.008, 433.110, 10.008, 531.490, 11.754),
    (578.097, 35.514, 333.850, 10.008, 433.110, 10.008, 531.740, 11.259),
    (561.097, 35.514, 333.850, 10.008, 433.110, 10.008, 534.370, 6.003),
    (544.097, 35.514, 333.850, 10.008, 433.110, 10.008, 531.490, 11.754),
    (527.097, 35.514, 333.850, 10.008, 433.110, 10.008, 531.740, 11.259),
    (510.097, 35.514, 333.850, 10.008, 433.110, 10.008, 531.740, 11.259),
    (493.097, 28.008, 333.850, 10.008, 433.110, 10.008, 531.740, 11.259),
]


def make_pdf(
    output_path: str,
    logo_path: str = DEFAULT_LOGO_PATH,
    roll_no: str = DEFAULT_ROLL_NO,
    enrollment_no: str = DEFAULT_ENROLLMENT_NO,
    student_name: str = DEFAULT_STUDENT_NAME,
    father_name: str = DEFAULT_FATHER_NAME,
    semester: str = DEFAULT_SEMESTER,
    course_titles=None,
    course_codes=None,
    midterm_marks=None,
    endterm_marks=None,
    grades=None,
) -> None:
    c = canvas.Canvas(output_path, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    pdf_title = str(roll_no or "").strip() or "gradesheet"
    c.setTitle(pdf_title)

    def resolve_row_value(values, defaults, idx):
        if isinstance(values, (list, tuple)) and idx < len(values):
            candidate = str(values[idx] or "").strip()
            if candidate:
                return candidate
        if idx < len(defaults):
            return defaults[idx]
        return "-"

    provided_lengths = [
        len(values)
        for values in (course_titles, course_codes, midterm_marks, endterm_marks, grades)
        if isinstance(values, (list, tuple)) and len(values) > 0
    ]
    row_count = max(provided_lengths) if provided_lengths else len(COURSE_ROW_LAYOUTS)
    row_count = min(row_count, len(COURSE_ROW_LAYOUTS))
    semester_value = str(semester or DEFAULT_SEMESTER).strip() or DEFAULT_SEMESTER
    has_fail_grade = False

    # ------------------------------------------------------------------ helpers
    def thin():
        c.setLineWidth(0.5)

    def thick():
        c.setLineWidth(0.8)

    def ln(x1, y1, x2, y2, width=0.5):
        c.setLineWidth(width)
        c.line(x1, y1, x2, y2)

    def word(x, y, bold: bool, size: float, width: float, text: str):
        """Draw text at (x, y) baseline-left. 
        'width' parameter added to match \PdfWord box width."""
        font = "Helvetica-Bold" if bold else "Helvetica"
        c.setFont(font, size)
        c.drawString(x, y, text)

    def draw_name_words(x, y, bold: bool, size: float, full_name: str):
        parts = [part for part in str(full_name or "").split() if part]
        if not parts:
            parts = ["-"]

        font = "Helvetica-Bold" if bold else "Helvetica"
        space_width = c.stringWidth(" ", font, size)
        current_x = x

        for part in parts:
            token_width = c.stringWidth(part, font, size)
            word(current_x, y, bold, size, token_width, part)
            current_x += token_width + space_width

    def draw_centered_cell_text(center_x: float, y: float, bold: bool, size: float, text: str):
        value = str(text or "-")
        font = "Helvetica-Bold" if bold else "Helvetica"
        text_width = c.stringWidth(value, font, size)
        start_x = center_x - (text_width / 2.0)
        word(start_x, y, bold, size, text_width, value)

    # ================================================================== LINES
    # ---- top frame --------------------------------------------------------
    thin()
    c.line(8.25,  834,    8.25,  766.71)
    c.line(586.75, 834,   586.75, 794)
    c.line(8,     833.75, 65.9,  833.75)
    c.line(65.9,  833.75, 587,   833.75)
    c.line(586.75, 794,   586.75, 766.71)

    # ---- row separators (thick left, thin right) --------------------------
    ROW_PAIRS = [
        (766.71, 758.71), (758.71, 750.71), (750.71, 733.71),
        (733.71, 716.71), (716.71, 699.71), (699.71, 675.71),
        (675.71, 658.71), (658.71, 641.71), (641.71, 624.71),
        (624.71, 607.71), (607.71, 590.71), (590.71, 573.71),
        (573.71, 556.71), (556.71, 539.71), (539.71, 522.71),
        (522.71, 505.71), (505.71, 488.71),
    ]
    for yA, yB in ROW_PAIRS:
        ln(8.4,    yA, 8.4,    yB, 0.8)  # thick left
        ln(586.75, yA, 586.75, yB, 0.5)  # thin right

    # ---- lower block borders ----------------------------------------------
    thin()
    LOWER_LINES = [
        (8.25, 488.71, 8.25, 448.71),
        (586.75, 488.71, 586.75, 448.71),
        (8, 448.96, 587, 448.96),
        (8.25, 448.71, 8.25, 431.71),
        (347.16, 448.71, 347.16, 431.71),
        (347.66, 448.71, 347.66, 431.71),
        (586.75, 448.71, 586.75, 431.71),
        (8, 431.96, 347.41, 431.96),
        (347.41, 431.96, 587, 431.96),
        (8.25, 431.71, 8.25, 415.71),
        (23.9, 431.71, 23.9, 415.71),
        (571.6, 431.71, 571.6, 415.71),
        (586.75, 431.71, 586.75, 415.71),
        (23.65, 415.96, 571.35, 415.96),
        (8.25, 415.71, 8.25, 399.71),
        (23.9, 415.71, 23.9, 399.71),
        (571.6, 415.71, 571.6, 399.71),
        (586.75, 415.71, 586.75, 399.71),
        (8.25, 399.71, 8.25, 383.71),
        (23.9, 399.71, 23.9, 383.71),
        (571.6, 399.71, 571.6, 383.71),
        (586.75, 399.71, 586.75, 383.71),
        (8.25, 383.71, 8.25, 367.71),
        (23.9, 383.71, 23.9, 367.71),
        (571.6, 383.71, 571.6, 367.71),
        (586.75, 383.71, 586.75, 367.71),
        (8.25, 367.71, 8.25, 351.71),
        (23.9, 367.71, 23.9, 351.71),
        (571.6, 367.71, 571.6, 351.71),
        (586.75, 367.71, 586.75, 351.71),
        (8.25, 351.71, 8.25, 335.71),
        (23.9, 351.71, 23.9, 335.71),
        (571.6, 351.71, 571.6, 335.71),
        (586.75, 351.71, 586.75, 335.71),
        (8.25, 335.71, 8.25, 311.71),
        (23.9, 335.71, 23.9, 311.71),
        (571.6, 335.71, 571.6, 311.71),
        (586.75, 335.71, 586.75, 311.71),
        (8.25, 311.71, 8.25, 303.71),
        (23.9, 311.71, 23.9, 303.71),
        (571.6, 311.71, 571.6, 303.71),
        (586.75, 311.71, 586.75, 303.71),
        (23.65, 303.96, 571.35, 303.96),
        (8.25, 303.71, 8.25, 295.71),
        (586.75, 303.71, 586.75, 295.71),
        (8, 295.96, 587, 295.96),
    ]
    for x1, y1, x2, y2 in LOWER_LINES:
        c.line(x1, y1, x2, y2)

    # ================================================================== LOGO
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 10, 770.71, width=70, height=59.29,
                    preserveAspectRatio=False, mask="auto")
    else:
        # Placeholder rectangle
        c.setLineWidth(0.5)
        c.rect(10, 770.71, 70, 59.29)
        c.setFont("Helvetica", 6)
        c.drawCentredString(45, 798, "LOGO")

    # ================================================================== HEADER
    word(135.890, 804.860, True, 20.000, 123.320, "RAJASTHAN")
    word(270.330, 804.860, True, 20.000, 115.540, "TECHNICAL")
    word(396.990, 804.860, True, 20.000, 120.020, "UNIVERSITY")
    word(309.450, 782.516, True, 12.000, 33.996, "KOTA")
    
    word(206.360, 759.054, False, 8.000, 7.560, "B.")
    word(216.144, 759.054, False, 8.000, 17.784, "Tech")
    word(238.376, 759.054, False, 8.000, 5.336, semester_value)
    word(248.160, 759.054, False, 8.000, 17.336, "SEM")
    word(269.944, 759.054, False, 8.000, 20.000, "MAIN")
    word(294.392, 759.054, False, 8.000, 22.672, "EXAM")
    word(323.736, 759.054, False, 8.000, 17.792, "2026")
    word(345.976, 759.054, False, 8.000, 42.664, "(GRADING)")
    
    word(248.600, 751.054, False, 8.000, 34.232, "(Powered")
    word(285.056, 751.054, False, 8.000, 8.448, "by")
    word(295.728, 751.054, False, 8.000, 50.672, "www.rtu.ac.in)")
    
    word(12.000, 738.097, True, 9.000, 32.508, "College")
    word(47.010, 738.097, True, 9.000, 27.504, "Name:")
    word(109.830, 738.097, False, 9.000, 54.009, "UNIVERSITY")
    word(166.341, 738.097, False, 9.000, 64.503, "DEPARTMENT,")
    word(233.346, 738.097, False, 9.000, 53.505, "RAJASTHAN")
    word(289.353, 738.097, False, 9.000, 51.003, "TECHNICAL")
    word(342.858, 738.097, False, 9.000, 56.511, "UNIVERSITY,")
    word(401.871, 738.097, False, 9.000, 24.507, "KOTA")

    # ================================================================== STUDENT INFO
    word(12.000, 721.097, True, 9.000, 17.001, "Roll")
    word(31.503, 721.097, True, 9.000, 11.997, "No")
    word(46.002, 721.097, True, 9.000, 2.997, ":")
    word(109.830, 721.097, False, 9.000, 56.520, str(roll_no))
    word(269.550, 721.097, True, 9.000, 47.007, "Enrollment")
    word(319.059, 721.097, True, 9.000, 11.997, "No")
    word(333.558, 721.097, True, 9.000, 2.997, ":")
    word(389.340, 721.097, False, 9.000, 85.032, str(enrollment_no))
    
    word(12.000, 704.097, True, 9.000, 24.507, "Name")
    word(39.009, 704.097, True, 9.000, 2.997, ":")
    draw_name_words(109.830, 704.097, False, 9.000, student_name)
    word(269.550, 704.097, True, 9.000, 34.650, "Father's")
    word(306.702, 704.097, True, 9.000, 24.507, "Name")
    word(333.711, 704.097, True, 9.000, 2.997, ":")
    draw_name_words(389.340, 704.097, False, 9.000, father_name)

    # ================================================================== COURSE TABLE HEADER
    word(12.000, 676.097, True, 9.000, 38.502, "COURSE")
    word(53.004, 676.097, True, 9.000, 25.002, "TITLE")
    word(208.510, 676.097, True, 9.000, 38.502, "COURSE")
    word(249.514, 676.097, True, 9.000, 26.001, "CODE")
    word(291.230, 676.097, True, 9.000, 85.986, "MARKS1(MIDTERM)")
    word(390.490, 676.097, True, 9.000, 88.488, "MARKS2(ENDTERM)")
    word(521.120, 676.097, True, 9.000, 32.499, "GRADE")

    # ================================================================== COURSE ROWS
    for row_idx in range(row_count):
        (
            y,
            code_width,
            midterm_x,
            midterm_width,
            endterm_x,
            endterm_width,
            grade_x,
            grade_width,
        ) = COURSE_ROW_LAYOUTS[row_idx]

        midterm_value = resolve_row_value(midterm_marks, DEFAULT_MIDTERM_MARKS, row_idx)
        endterm_value = resolve_row_value(endterm_marks, DEFAULT_ENDTERM_MARKS, row_idx)
        grade_value = resolve_row_value(grades, DEFAULT_GRADES, row_idx)
        normalized_grade = str(grade_value or "").strip().upper()
        if normalized_grade.startswith("F"):
            has_fail_grade = True

        midterm_center_x = midterm_x + (midterm_width / 2.0)
        endterm_center_x = endterm_x + (endterm_width / 2.0)
        grade_center_x = grade_x + (grade_width / 2.0)

        draw_name_words(
            12.000,
            y,
            False,
            9.000,
            resolve_row_value(course_titles, DEFAULT_COURSE_TITLES, row_idx),
        )
        word(
            208.510,
            y,
            False,
            9.000,
            code_width,
            resolve_row_value(course_codes, DEFAULT_COURSE_CODES, row_idx),
        )
        draw_centered_cell_text(midterm_center_x, y, False, 9.000, midterm_value)
        draw_centered_cell_text(endterm_center_x, y, False, 9.000, endterm_value)
        draw_centered_cell_text(grade_center_x, y, False, 9.000, grade_value)

    # ================================================================== REMARKS
    remarks_value = "FAIL" if has_fail_grade else "PASS"
    word(12.000, 436.097, False, 9.000, 44.505, "REMARKS")
    word(59.007, 436.097, False, 9.000, 2.502, ":")
    word(351.410, 436.097, False, 9.000, c.stringWidth(remarks_value, "Helvetica", 9.000), remarks_value)
    
    word(25.650, 420.054, True, 8.000, 41.336, "Instruction")
    word(69.210, 420.054, True, 8.000, 2.664, ":")
    
    word(25.650, 404.054, True, 8.000, 6.672, "1.")
    word(34.546, 404.054, True, 8.000, 16.448, "This")
    word(53.218, 404.054, True, 8.000, 6.672, "is")
    word(62.114, 404.054, True, 8.000, 15.560, "web")
    word(79.898, 404.054, True, 8.000, 23.120, "based")
    word(105.242, 404.054, True, 8.000, 24.008, "result.")
    word(131.474, 404.054, True, 8.000, 36.888, "Authentic")
    word(170.586, 404.054, True, 8.000, 21.784, "result")
    word(194.594, 404.054, True, 8.000, 18.232, "shall")
    word(215.050, 404.054, True, 8.000, 9.336, "be")
    word(226.610, 404.054, True, 8.000, 42.680, "considered")
    word(271.514, 404.054, True, 8.000, 7.112, "in")
    word(280.850, 404.054, True, 8.000, 42.680, "mark-sheet")
    word(325.754, 404.054, True, 8.000, 25.344, "issued")
    word(353.322, 404.054, True, 8.000, 9.336, "by")
    word(364.882, 404.054, True, 8.000, 18.664, "RTU.")
    
    word(25.650, 388.054, True, 8.000, 6.672, "2.")
    word(34.546, 388.054, True, 8.000, 14.224, "The")
    word(50.994, 388.054, True, 8.000, 14.224, "due")
    word(67.442, 388.054, True, 8.000, 16.448, "date")
    word(86.114, 388.054, True, 8.000, 7.552, "to")
    word(95.890, 388.054, True, 8.000, 26.224, "submit")
    word(124.338, 388.054, True, 8.000, 9.336, "an")
    word(135.898, 388.054, True, 8.000, 23.560, "online")
    word(161.682, 388.054, True, 8.000, 18.672, "copy")
    word(182.578, 388.054, True, 8.000, 17.344, "view")
    word(202.146, 388.054, True, 8.000, 14.224, "and")
    word(218.594, 388.054, True, 8.000, 42.680, "revaluation")
    word(263.498, 388.054, True, 8.000, 17.776, "form")
    word(283.498, 388.054, True, 8.000, 30.216, "through")
    word(315.938, 388.054, True, 8.000, 12.000, "the")
    word(330.162, 388.054, True, 8.000, 27.568, "college")
    word(359.954, 388.054, True, 8.000, 6.672, "is")
    word(368.850, 388.054, True, 8.000, 33.336, "FIFTEEN")
    word(404.410, 388.054, True, 8.000, 18.232, "days")
    word(424.866, 388.054, True, 8.000, 17.336, "after")
    word(444.426, 388.054, True, 8.000, 12.000, "the")
    word(458.650, 388.054, True, 8.000, 16.448, "date")
    word(477.322, 388.054, True, 8.000, 26.232, "results")
    word(505.778, 388.054, True, 8.000, 12.008, "are")
    word(520.010, 388.054, True, 8.000, 44.896, "announced.")
    
    word(25.650, 372.054, True, 8.000, 6.672, "3.")
    word(34.546, 372.054, True, 8.000, 34.224, "Students")
    word(70.994, 372.054, True, 8.000, 13.784, "can")
    word(87.002, 372.054, True, 8.000, 20.896, "apply")
    word(110.122, 372.054, True, 8.000, 18.672, "copy")
    word(131.018, 372.054, True, 8.000, 17.344, "view")
    word(150.586, 372.054, True, 8.000, 10.664, "for")
    word(163.474, 372.054, True, 8.000, 8.896, "all")
    word(174.594, 372.054, True, 8.000, 12.000, "the")
    word(188.818, 372.054, True, 8.000, 24.448, "theory")
    word(215.490, 372.054, True, 8.000, 34.680, "subjects.")
    word(252.394, 372.054, True, 8.000, 14.224, "The")
    word(268.842, 372.054, True, 8.000, 42.680, "revaluation")
    word(313.746, 372.054, True, 8.000, 6.672, "is")
    word(322.642, 372.054, True, 8.000, 36.448, "permitted")
    word(361.314, 372.054, True, 8.000, 7.112, "in")
    word(370.650, 372.054, True, 8.000, 37.344, "maximum")
    word(410.218, 372.054, True, 8.000, 22.664, "FOUR")
    word(435.106, 372.054, True, 8.000, 24.448, "theory")
    word(461.778, 372.054, True, 8.000, 28.456, "papers.")
    
    word(25.650, 356.054, True, 8.000, 6.672, "4.")
    word(34.546, 356.054, True, 8.000, 29.776, "Student")
    word(66.546, 356.054, True, 8.000, 13.784, "can")
    word(82.554, 356.054, True, 8.000, 20.896, "apply")
    word(105.674, 356.054, True, 8.000, 10.664, "for")
    word(118.562, 356.054, True, 8.000, 17.344, "view")
    word(138.130, 356.054, True, 8.000, 26.232, "his/her")
    word(166.586, 356.054, True, 8.000, 27.568, "answer")
    word(196.378, 356.054, True, 8.000, 41.776, "book(Copy")
    word(240.378, 356.054, True, 8.000, 20.896, "View)")
    word(263.498, 356.054, True, 8.000, 58.240, "simultaneously")
    word(323.962, 356.054, True, 8.000, 16.000, "with")
    word(342.186, 356.054, True, 8.000, 42.680, "revaluation")
    word(387.090, 356.054, True, 8.000, 7.552, "of")
    word(396.866, 356.054, True, 8.000, 27.568, "answer")
    word(426.658, 356.054, True, 8.000, 19.112, "book")
    word(447.994, 356.054, True, 8.000, 7.112, "in")
    word(457.330, 356.054, True, 8.000, 20.456, "same")
    word(480.010, 356.054, True, 8.000, 30.232, "subject.")
    
    word(25.650, 340.054, True, 8.000, 6.672, "5.")
    word(34.546, 340.054, True, 8.000, 18.664, "After")
    word(55.434, 340.054, True, 8.000, 40.008, "inspection")
    word(97.666, 340.054, True, 8.000, 7.552, "of")
    word(107.442, 340.054, True, 8.000, 27.568, "answer")
    word(137.234, 340.054, True, 8.000, 29.776, "book(S)")
    word(169.234, 340.054, True, 8.000, 2.224, ",")
    word(173.682, 340.054, True, 8.000, 24.000, "offline")
    word(199.906, 340.054, True, 8.000, 32.888, "(Manual)")
    word(235.018, 340.054, True, 8.000, 42.680, "revaluation")
    word(279.922, 340.054, True, 8.000, 42.232, "application")
    word(324.378, 340.054, True, 8.000, 17.776, "form")
    word(344.378, 340.054, True, 8.000, 12.896, "will")
    word(359.498, 340.054, True, 8.000, 12.440, "not")
    word(374.162, 340.054, True, 8.000, 9.336, "be")
    word(385.722, 340.054, True, 8.000, 36.904, "accepted.")
    
    word(25.650, 324.054, True, 8.000, 6.672, "6.")
    word(34.546, 324.054, True, 8.000, 43.120, "Candidates")
    word(79.890, 324.054, True, 8.000, 32.896, "applying")
    word(115.010, 324.054, True, 8.000, 10.664, "for")
    word(127.898, 324.054, True, 8.000, 40.008, "inspection")
    word(170.130, 324.054, True, 8.000, 7.552, "of")
    word(179.906, 324.054, True, 8.000, 53.792, "answer-books")
    word(235.922, 324.054, True, 8.000, 12.008, "are")
    word(250.154, 324.054, True, 8.000, 16.008, "also")
    word(268.386, 324.054, True, 8.000, 32.008, "required")
    word(302.618, 324.054, True, 8.000, 7.552, "to")
    word(312.394, 324.054, True, 8.000, 20.896, "apply")
    word(335.514, 324.054, True, 8.000, 58.240, "simultaneously")
    word(395.978, 324.054, True, 8.000, 10.664, "for")
    word(408.866, 324.054, True, 8.000, 45.344, "Revaluation")
    word(456.434, 324.054, True, 8.000, 24.448, "before")
    word(483.106, 324.054, True, 8.000, 13.784, "last")
    word(499.114, 324.054, True, 8.000, 16.448, "date")
    word(517.786, 324.054, True, 8.000, 8.896, "as")
    
    word(25.650, 316.054, True, 8.000, 42.672, "announced")
    word(70.546, 316.054, True, 8.000, 9.336, "by")
    word(82.106, 316.054, True, 8.000, 12.000, "the")
    word(96.330, 316.054, True, 8.000, 40.904, "University.")

    # ================================================================== FOOTER
    word(250.000, 3.430, False, 10.000, 23.350, "Page")
    word(276.130, 3.430, False, 10.000, 5.560, "1")

    c.save()
    print(f"PDF written to: {output_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate RTU marksheet PDF using the fixed ReportLab layout."
    )
    parser.add_argument(
        "-o",
        "--output",
        default=os.path.join(os.getcwd(), "rtu_marksheet.pdf"),
        help="Output PDF path (default: ./rtu_marksheet.pdf)",
    )
    parser.add_argument(
        "--logo",
        default=DEFAULT_LOGO_PATH,
        help="Path to logo image (default: pdfcode/image/extracted-000.jpg)",
    )
    parser.add_argument(
        "--roll-no",
        default=DEFAULT_ROLL_NO,
        help="Student roll number",
    )
    parser.add_argument(
        "--enrollment-no",
        default=DEFAULT_ENROLLMENT_NO,
        help="Student enrollment number",
    )
    parser.add_argument(
        "--student-name",
        default=DEFAULT_STUDENT_NAME,
        help="Student full name",
    )
    parser.add_argument(
        "--father-name",
        default=DEFAULT_FATHER_NAME,
        help="Father full name",
    )
    parser.add_argument(
        "--semester",
        default=DEFAULT_SEMESTER,
        help="Semester label shown in header (for example: V)",
    )
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()

    output_path = os.path.abspath(args.output)
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    make_pdf(
        output_path,
        logo_path=args.logo,
        roll_no=args.roll_no,
        enrollment_no=args.enrollment_no,
        student_name=args.student_name,
        father_name=args.father_name,
        semester=args.semester,
    )