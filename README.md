# Academic Helpdesk Agent (multi-agent, RAG, fully local)

An academic helpdesk for IIT Jodhpur students that answers questions about academic programmes, course
contents, academic rules and regulations, and the semester timetable, and drafts emails to course
instructors (sick leave, makeup exams). It answers only from the institute's documents, cites the document
each answer came from, and replies "I don't know" (and logs the question for a human) to anything else.

Built with **Google ADK**, with local LLMs served by **Ollama** through ADK's **LiteLLM** connector,
**ChromaDB** + `nomic-embed-text` embeddings for RAG, and CSV tables for the timetable and faculty directory.
Runs on a 16 GB RAM laptop.

**Team:**

| Name | Roll number |
| --- | --- |
| Aradhya Mahajan | B23CS1088 |
| Pragay | B23ES1024 |
| Vyom Shah | B23CM1058 |
| Priyanshu Pandey | B24BB1029 |

## Architecture

```
                         ┌──────────────────────────┐
  student question ───►  │  helpdesk_orchestrator   │── out of scope ──► log_unanswered_question
                         │  (routes, never answers) │                    + "I don't know ..."
                         └────────────┬─────────────┘
                transfer_to_agent     │
        ┌─────────────────────────────┼──────────────────────────────┐
        ▼                             ▼                              ▼
┌───────────────┐            ┌─────────────────┐             ┌────────────────┐
│ policy_agent  │            │ schedule_agent  │             │  email_agent   │
│ rules, credits│            │ slots, timings, │             │ instructor     │
│ curriculum,   │            │ courses floated │             │ email + draft  │
│ syllabus      │            │                 │             │                │
└──────┬────────┘            └───────┬─────────┘             └──────┬─────────┘
  search_documents        lookup_course, list_courses,     get_instructor_email,
  log_unanswered_question search_documents, log_...        lookup_course, save_email_draft, log_...
       │                             │                              │
       ▼                             ▼                              ▼
 ChromaDB (docs/raw, hybrid    data/courses.csv              data/faculty.csv
 dense + BM25 retrieval)       data/slots.csv                outputs/drafts/*.txt
```

There is also a **single-agent** baseline (`--mode single`) with the same six tools on one agent.

| Tool | What it does | Data |
|---|---|---|
| `search_documents(query)` | Hybrid retrieval (Chroma dense vectors + BM25, fused with reciprocal rank fusion); returns top-5 chunks with file name and page | `docs/raw/*` |
| `lookup_course(query)` | Course by code or (fuzzy) name, with slot, slot day/times, room, instructor and co-instructors; suggests similar codes when not found | `data/courses.csv`, `data/slots.csv` |
| `list_courses(department, level, course_type)` | Count and list the courses floated, e.g. 400-level Humanities courses (alias rows excluded) | `data/courses.csv` |
| `get_instructor_email(course_or_name)` | Instructor and co-instructors of a course and their email IDs (flags dummy addresses) | `data/courses.csv`, `data/faculty.csv` |
| `save_email_draft(to, subject, body)` | Saves the draft for the student to review; **never sends** it | `outputs/drafts/` |
| `log_unanswered_question(question, reason)` | Appends to the human hand-off log | `logs/unanswered.jsonl` |

Safeguard: if an agent replies "I don't know" without calling `log_unanswered_question`, the runner logs
the question anyway ([helpdesk/chat.py](helpdesk/chat.py)).

## Setup

```bash
# Python 3.12 venv (uv)
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
source .venv/bin/activate

# Ollama models (~5 GB each for the chat models)
ollama serve &                 # if it is not already running as a service
ollama pull nomic-embed-text   # embeddings
ollama pull qwen3:8b           # main model
ollama pull llama3.1:8b        # comparison model
```

## 1. Documents and data

**Unstructured documents are in `docs/raw/`** (30 files: PDF and Markdown; `docs/manifest.csv` records
the source URL and fetch date of each). The file name is what gets cited. To add documents, drop PDF,
DOCX, TXT, MD, HTML or CSV files there and re-index. Scanned PDFs have no text layer: the indexer flags
them (`WARNING: ... scanned PDF?`), so OCR them first (e.g. `ocrmypdf in.pdf out.pdf`).

**Structured tables in `data/` are generated** from the official AY 2026-27 Semester I slot-system
workbook by one script:

```bash
python data/build_tables.py   # data/source/*.xlsx -> data/courses.csv, slots.csv, faculty.csv
                              #                    + docs/raw/timetable_slot_system_2026_27.md
```

| Output | Rows | Built from |
|---|---|---|
| `data/courses.csv` | 613 | "Classroom Allocation" sheet, one row per course code (sections, tutorials and rooms merged) |
| `data/slots.csv` | 81 | "Slot System" grid (merged cells give the 2-hour lab slots L1–L10, M1–M10) and the M.Tech. Executive evening/weekend slots |
| `data/faculty.csv` | 297 | every instructor and co-instructor in the timetable, with emails from `data/source/faculty_emails_collected.csv` and the "Time Table Committee Members" sheet |
| `docs/raw/timetable_slot_system_2026_27.md` | – | the other sheets (slot rules, Minor exam timetable, common-course slots, committee, minor/specialization coordinators) as text, so RAG can cite them |

Columns:

- `courses.csv`: `course_code, course_name, department, course_type, ltp, credits, slot, instructor, co_instructors, room, students_registered, note`
- `slots.csv`: `slot, day, start_time, end_time`
- `faculty.csv`: `name, department, email, email_source`

Notes on the data:

- **`course_type`** comes from the third letter of the course code, as defined in Table 4.3 of the UG
  regulations (L = Lecture, P = Practical/Lab, D = Project, N = Non-graded, T = Thesis, ...). The
  timetable has **no core/elective classification** (it depends on the student's programme), so the
  agent says so when asked about "electives".
- The **course level** is the first digit of the code's number (`LAL4070` is 400-level, `CSL7650` is 700-level).
- A `slot` such as `D (Wed)` means only the Wednesday meeting of slot D. `lookup_course` filters the
  timings accordingly and always returns the raw slot text too.
- The School of Liberal Arts is labelled "School of Liberal Arts (SoLA) / Humanities and Social Sciences
  (HSS)", the name the workbook's committee sheet uses, so questions about "Humanities" find it.
- **`CSL7570` is an alias row** for `CSL7650` Autonomous Systems. The assignment's example prompts use
  CSL7570, but the official timetable lists the course as CSL7650. The row carries a `note` saying so,
  and it is excluded from all course counts.
- **Emails:** 67 faculty have an address from a real source (37 from the collected directory, 30 from the
  committee sheet; `email_source` says which). The other 230 have **dummy placeholders** (`firstname.lastname@dummy.iitj.ac.in`,
  `email_source = dummy placeholder`), as the assignment allows. The email agent warns the student
  whenever it uses one.
- No student data is used. Drafts use placeholders such as `[Your Name]` and `[Roll Number]`.

## 2. Index the documents

```bash
python -m helpdesk.rag index                      # rebuilds .chroma/ from docs/raw (run again after changes)
python -m helpdesk.rag search "attendance for major exam"   # see what retrieval returns
```

The index command prints the pages and chunks for every file and warns about files with no extractable text.

## 3. Use the helpdesk

```bash
python -m helpdesk.chat                                   # interactive, multi-agent, qwen3:8b
python -m helpdesk.chat -v                                # also print every tool call / agent
python -m helpdesk.chat --mode single                     # single-agent baseline
python -m helpdesk.chat --model llama3.1:8b -q "What is the slot for the course Autonomous Systems?"
```

Web UI and REST API (ADK built-ins; run from the repo root, where `helpdesk` is the app name):

```bash
adk web          # http://localhost:8000, select "helpdesk", shows agent transfers and tool calls
adk api_server   # REST API on http://localhost:8000

curl -X POST localhost:8000/apps/helpdesk/users/u1/sessions/s1 -H 'Content-Type: application/json' -d '{}'
curl -X POST localhost:8000/run -H 'Content-Type: application/json' -d '{
  "app_name": "helpdesk", "user_id": "u1", "session_id": "s1",
  "new_message": {"role": "user", "parts": [{"text": "How many Open Elective credits do I need for a B.Tech.?"}]}}'
```

Outputs: email drafts go to `outputs/drafts/`, unanswered questions to `logs/unanswered.jsonl`.

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `HELPDESK_MODEL` | `qwen3:8b` | Ollama chat model (also `--model`) |
| `HELPDESK_EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model (re-index after changing) |
| `HELPDESK_NUM_CTX` | `8192` | Context window passed to Ollama (Ollama's own default is too small for RAG + tools) |
| `HELPDESK_TEMPERATURE` | `0.2` | Sampling temperature |
| `HELPDESK_INSTITUTE` | `IIT Jodhpur` | Institute name used in the prompts |
| `OLLAMA_API_BASE` | `http://localhost:11434` | Ollama server |

Qwen3's "thinking" mode is switched off (`think=False`) to keep latency acceptable on a laptop.

## 4. Evaluate

The question set is in [eval/questions.json](eval/questions.json): 30 prompts covering policy, schedule
and email requests, out-of-scope questions, and an email for a non-existent course. Each entry has:

- `expected`: strings that must all appear in a correct answer (`"a|b"` means a or b; matched as whole words, case-insensitive)
- `expected_source`: file name(s), at least one of which must be cited (groundedness)
- `expected_agent`: the specialist(s) that should handle it (routing)
- `should_refuse`: the correct behaviour is "I don't know" plus logging the question
- `expects_draft`: the request asks for a draft, so `save_email_draft` must actually be called

```bash
python eval/run_eval.py --model qwen3:8b    --mode multi  --runs 3
python eval/run_eval.py --model llama3.1:8b --mode multi  --runs 3
python eval/run_eval.py --model qwen3:8b    --mode single --runs 3   # single vs multi agent
python eval/run_eval.py --only P01 S03 --runs 1                      # quick check
python eval/run_eval.py --summary-only                               # re-score stored answers, rebuild summary
```

Each configuration writes `eval/results/<model>__<mode>.json` (every answer, tool call, latency and
score) plus its own refusal log and drafts. `eval/results/summary.md` compares all configurations and
gives a per-question, per-run table that flags **questions whose verdict or wording changed across runs**.
`eval/results/v1_example_citation/` keeps the first full run, before the citation-prompt fix described in
the report. Results: see [REPORT.md](REPORT.md) §5–6. In short, qwen3:8b multi-agent scored 82.6%
accuracy and refused 100% of out-of-scope prompts correctly; llama3.1:8b scored 65.2%.

Deterministic tool checks (no LLM): `python tests/test_tools.py`.

## Project layout

```
helpdesk/config.py   paths, models, settings (env-overridable)
helpdesk/rag.py      loaders, chunking, Ollama embeddings, ChromaDB, hybrid search, index CLI
helpdesk/tools.py    the six agent tools
helpdesk/agent.py    prompts, single agent, multi-agent orchestrator + specialists (root_agent for adk web)
helpdesk/chat.py     runner (Helpdesk.ask), refusal detection/auto-logging, CLI
eval/                questions.json, run_eval.py, results/
docs/raw/            the 30 indexed documents; docs/manifest.csv = provenance
data/build_tables.py builds data/*.csv (+ the timetable .md) from data/source/ (official xlsx, collected emails)
tests/               tool self-check with synthetic fixtures
REPORT.md            findings
```

## Hardware notes

Tested with 16 GB RAM and a 6 GB laptop GPU. An 8B Q4 model (~5 GB) plus an 8k context does not fit
entirely in 6 GB of VRAM, so Ollama offloads part of it to the CPU, which is slower but works. Without
a GPU everything still runs on the CPU, just more slowly. Only one chat model is loaded at a time.
