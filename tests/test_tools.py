"""Deterministic checks for the CSV/email/log tools against synthetic fixtures (no LLM needed).

    python tests/test_tools.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
tmp = Path(tempfile.mkdtemp())
os.environ.update(HELPDESK_DATA_DIR=str(HERE / "fixtures" / "data"), HELPDESK_DRAFTS_DIR=str(tmp / "drafts"),
                  HELPDESK_UNANSWERED_LOG=str(tmp / "unanswered.jsonl"))
sys.path.insert(0, str(HERE.parent))

from helpdesk.tools import (get_instructor_email, list_courses, log_unanswered_question, lookup_course,  # noqa: E402
                            save_email_draft)

r = lookup_course("csl 7570")
assert r["found"] and r["courses"][0]["slot"] == "B" and r["courses"][0]["level"] == 700, r
assert len(r["courses"][0]["slot_timings"]) == 2, r
assert lookup_course("Autonomous Systems")["courses"][0]["course_code"] == "CSL7570"
assert lookup_course("autonomus systm")["found"]  # fuzzy name match
assert not lookup_course("Underwater Basket Weaving")["found"]
assert not lookup_course("")["found"]

assert list_courses(department="Humanities", level=400, category="elective")["count"] == 2
assert list_courses(department="Humanities")["count"] == 3
assert list_courses(level="700")["count"] == 1  # LLMs sometimes pass numbers as strings

e = get_instructor_email("CSL7570")
assert e["found"] and e["instructors"][0]["email"] == "test.instructor@example.edu", e
assert get_instructor_email("Prof. Alpha Beta")["instructors"][0]["email"] == "alpha.beta@example.edu"
assert not get_instructor_email("XYZ9999")["found"]

d = save_email_draft("a@b.c", "Leave", "Dear Prof.")
assert Path(d["path"]).read_text().startswith("To: a@b.c\nSubject: Leave")

log_unanswered_question("Where is the canteen?", "out of scope")
assert json.loads((tmp / "unanswered.jsonl").read_text())["question"] == "Where is the canteen?"
print("all tool checks passed")
