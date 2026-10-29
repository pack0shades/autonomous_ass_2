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

r = lookup_course("csl 7650")
assert r["found"] and r["courses"][0]["slot"] == "B" and r["courses"][0]["level"] == 700, r
assert len(r["courses"][0]["slot_timings"]) == 2, r
assert {c["course_code"] for c in lookup_course("Autonomous Systems")["courses"]} == {"CSL7650", "CSL7570"}
assert lookup_course("autonomus systm")["found"]  # fuzzy name match
assert not lookup_course("Underwater Basket Weaving")["found"]
assert not lookup_course("")["found"]
assert "CSL7650" in lookup_course("CSL7651")["similar_course_codes"]
d_wed = lookup_course("HSL4020")["courses"][0]["slot_timings"]  # "D (Wed)" -> only the Wednesday meeting
assert [t["day"] for t in d_wed] == ["Wednesday"], d_wed

assert list_courses(department="Humanities", level=400)["count"] == 3
assert list_courses(department="Humanities", level=400, course_type="lecture")["count"] == 2
assert list_courses(department="Humanities")["count"] == 4
assert list_courses(department="Humanities", level=400, course_type="Elective")["count"] == 3  # unknown type ignored
assert "note" in list_courses(course_type="elective") and list_courses(course_type="all")["count"] == 6
assert list_courses(level="700")["count"] == 1  # alias row excluded; LLMs sometimes pass numbers as strings

e = get_instructor_email("CSL7570")
assert e["found"] and e["instructors"][0]["email"] == "test.instructor@example.edu", e
e = get_instructor_email("HSL4010")
assert [(i["role"], i["email"]) for i in e["instructors"]] == [("instructor", "alpha.beta@example.edu"),
                                                                ("co-instructor", "gamma.delta@example.edu")], e
assert "email_warning" in get_instructor_email("CSL1010")["instructors"][0]  # dummy address is flagged
assert get_instructor_email("Prof. Alpha Beta")["instructors"][0]["email"] == "alpha.beta@example.edu"
assert not get_instructor_email("XYZ9999")["found"]

d = save_email_draft("a@b.c", "Leave", "Dear Prof.")
assert Path(d["path"]).read_text().startswith("To: a@b.c\nSubject: Leave")

log_unanswered_question("Where is the canteen?", "out of scope")
assert json.loads((tmp / "unanswered.jsonl").read_text())["question"] == "Where is the canteen?"
print("all tool checks passed")
