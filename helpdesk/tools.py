"""Tools exposed to the agents. ADK builds each tool's schema from the signature and docstring."""
import csv
import difflib
import json
import re
from datetime import datetime

from . import config, rag


def search_documents(query: str) -> dict:
    """Search the institute's academic documents (rules and regulations, curriculum, programme
    structure, academic calendar, office orders, timetable notices) for passages relevant to the query.

    Args:
        query: A focused search query, e.g. "minimum attendance required to appear in major exam".

    Returns:
        The most relevant passages, each with its source (document name and page number).
    """
    return {"results": [{"source": r["source"] + (f", page {r['page']}" if r["page"] else ""), "text": r["text"]}
                        for r in rag.search(query)]}


def _read(name):
    path = config.DATA_DIR / name
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]


def _code(s):
    return re.sub(r"[\s\-_]", "", s).upper()


def _level(code):
    m = re.search(r"\d", code)
    return int(m.group()) * 100 if m else 0


def _with_slot_times(course, slots):
    names = [s for s in re.split(r"[^A-Za-z0-9]+", course.get("slot", "")) if s]
    return {**course, "level": _level(course["course_code"]),
            "slot_timings": [s for s in slots if s.get("slot", "").upper() in {n.upper() for n in names}]}


def lookup_course(query: str) -> dict:
    """Look up a course offered this semester by course code (e.g. "CSL7570") or by course name
    (e.g. "Autonomous Systems"). Returns its name, department, category, credits, slot, slot timings
    (days and times) and instructor, from the semester timetable.

    Args:
        query: Course code or (part of) the course name.
    """
    courses, slots = _read("courses.csv"), _read("slots.csv")
    q = query.strip()
    if not q:
        return {"found": False, "message": "Empty query."}
    hits = [c for c in courses if _code(c["course_code"]) == _code(q)]
    if not hits:
        hits = [c for c in courses if q.lower() in c["course_name"].lower()]
    if not hits:
        close = difflib.get_close_matches(q.lower(), [c["course_name"].lower() for c in courses], n=3, cutoff=0.6)
        hits = [c for c in courses if c["course_name"].lower() in close]
    if not hits:
        return {"found": False, "message": f"No course matching '{query}' in the timetable.", "source": "courses.csv"}
    return {"found": True, "courses": [_with_slot_times(c, slots) for c in hits[:5]],
            "source": "courses.csv (semester timetable), slots.csv (slot timings)"}


def list_courses(department: str = "", level: int = 0, category: str = "") -> dict:
    """List and count the courses floated this semester, filtered by department, course level and/or
    category. Use this for questions like "how many 400 level electives are offered by Humanities".

    Args:
        department: Department name or part of it, e.g. "Humanities", "Computer Science". Empty = all.
        level: Course level such as 100, 200, 300, 400, 500, 600, 700 (taken from the first digit of the
            course code number, so CSL7570 is a 700 level course). 0 = all levels.
        category: Course category or part of it, e.g. "elective", "core", "open elective". Empty = all.
    """
    rows = _read("courses.csv")
    if department:
        d = department.lower()
        rows = [r for r in rows if d in r.get("department", "").lower()]
    if level:
        rows = [r for r in rows if _level(r["course_code"]) == int(level)]
    if category:
        cat = category.lower()
        rows = [r for r in rows if cat in r.get("category", "").lower()]
    return {"count": len(rows),
            "courses": [{k: r.get(k, "") for k in ("course_code", "course_name", "department", "category", "credits")}
                        for r in rows],
            "filters": {"department": department, "level": level, "category": category},
            "source": "courses.csv (semester timetable)"}


def _norm_name(name):
    name = re.sub(r"\b(dr|prof|professor|mr|mrs|ms)\b\.?", " ", name.lower())
    return " ".join(re.findall(r"[a-z]+", name))


def get_instructor_email(course_or_name: str) -> dict:
    """Find the instructor(s) of a course and their official email IDs from the faculty directory.

    Args:
        course_or_name: A course code (e.g. "CSL7570"), a course name, or a faculty member's name.
    """
    faculty = _read("faculty.csv")
    by_name = {_norm_name(f["name"]): f for f in faculty}

    def find(person):
        n = _norm_name(person)
        if n in by_name:
            return by_name[n]
        close = difflib.get_close_matches(n, list(by_name), n=1, cutoff=0.8)
        return by_name[close[0]] if close else None

    f = find(course_or_name)
    if f:
        return {"found": True, "instructors": [{"instructor": f["name"], "email": f["email"],
                                                "department": f.get("department", "")}], "source": "faculty.csv"}
    course = lookup_course(course_or_name)
    if course["found"]:
        out = []
        for c in course["courses"]:
            for person in [p for p in re.split(r";|,|/|\band\b", c.get("instructor", "")) if p.strip()]:
                f = find(person)
                out.append({"course_code": c["course_code"], "course_name": c["course_name"],
                            "instructor": person.strip(), "email": f["email"] if f else None,
                            "department": f.get("department", "") if f else ""})
        return {"found": any(o["email"] for o in out), "instructors": out,
                "source": "courses.csv (instructor), faculty.csv (email)"}
    return {"found": False, "message": f"No course or faculty member matching '{course_or_name}'."}


def save_email_draft(to: str, subject: str, body: str) -> dict:
    """Save an email draft for the student to review. The email is NOT sent.

    Args:
        to: Recipient email address (the instructor's email from get_instructor_email).
        subject: Email subject line.
        body: Full email body, including greeting and sign-off with placeholders for the student's
            name and roll number.
    """
    config.DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.DRAFTS_DIR / f"draft_{datetime.now():%Y%m%d_%H%M%S_%f}.txt"
    path.write_text(f"To: {to}\nSubject: {subject}\n\n{body}\n")
    return {"saved": True, "path": str(path), "note": "Draft saved for review; it has not been sent."}


def log_unanswered_question(question: str, reason: str) -> dict:
    """Record a question that cannot be answered from the available documents, so that a human at the
    academic office can answer it. Call this whenever you reply that you don't know.

    Args:
        question: The user's question, verbatim.
        reason: Why it could not be answered, e.g. "out of scope: dining" or "not found in documents".
    """
    config.UNANSWERED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(config.UNANSWERED_LOG, "a") as f:
        f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"),
                            "question": question, "reason": reason}) + "\n")
    return {"logged": True}
