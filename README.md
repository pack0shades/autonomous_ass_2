# Academic Helpdesk Agent (multi-agent, RAG, fully local)

An academic helpdesk for IIT Jodhpur students that answers questions about academic programmes, course
contents, academic rules and regulations, and the semester timetable, and drafts emails to course
instructors (sick leave, makeup exams). It answers only from the institute's documents, cites the document
each answer came from, and replies "I don't know" (and logs the question for a human) to anything else.

Built with **Google ADK**, with local LLMs served by **Ollama** through ADK's **LiteLLM** connector,
**ChromaDB** + `nomic-embed-text` embeddings for RAG, and CSV tables for the timetable and faculty directory.
Runs on a 16 GB RAM laptop.

**Team:** TODO: names and roll numbers

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
| `lookup_course(query)` | Course by code or (fuzzy) name, with slot, slot day/times and instructor | `data/courses.csv`, `data/slots.csv` |
| `list_courses(department, level, category)` | Count and list the courses floated, e.g. 400-level Humanities electives | `data/courses.csv` |
| `get_instructor_email(course_or_name)` | Instructor(s) of a course and their email IDs | `data/courses.csv`, `data/faculty.csv` |
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

## 1. Put the documents in place

**Unstructured documents go in `docs/raw/`**: PDF, DOCX, TXT, MD, HTML or CSV, and subfolders are fine.
The file name is what gets cited, so use descriptive names (e.g. `UG_Academic_Regulations_2024.pdf`, not
`doc1.pdf`). Suggested set (20–30 files):

- UG (B.Tech.) academic regulations / rule book, and PG regulations if available
- B.Tech. curriculum / programme structure (credits per category: core, programme electives, open electives, HSS)
- Course contents / syllabi (at least the courses used in the questions, e.g. CSL7570 Autonomous Systems)
- Academic calendar for the current semester
- Semester timetable (PDF) and slot chart
- Course registration guidelines / add-drop notices
- Recent office orders and circulars (attendance, makeup exams, leave, grading, etc.)
- Faculty directory (with email IDs replaced by dummy values if you prefer)

Scanned PDFs have no text layer. The indexer flags them (`WARNING: ... scanned PDF?`), so run OCR first,
e.g. `ocrmypdf in.pdf out.pdf`. Excel files: export to CSV.

**Structured tables go in `data/`**, with exactly these columns (the header-only templates are already
there; extra columns are allowed and are passed through to the agent):

| File | Required columns | Example row |
|---|---|---|
| `data/courses.csv` | `course_code,course_name,department,category,credits,slot,instructor` | `CSL7570,Autonomous Systems,Computer Science and Engineering,Program Elective,3,B,Dr. A. Kumar` |
| `data/slots.csv` | `slot,day,start_time,end_time` (one row per class meeting) | `B,Monday,09:00,09:55` |
| `data/faculty.csv` | `name,department,email` | `Dr. A. Kumar,Computer Science and Engineering,akumar@iitj.ac.in` |

- `courses.csv` covers the **current semester's** courses (the timetable), one row per course.
- The course level comes from the first digit of the course number: `HSL4010` is 400-level, `CSL7570` is 700-level.
- `category` is free text that is matched by substring: "Program Elective", "Open Elective" and "HSS Elective" all match "elective".
- `slot` may list several slots (`B, B1`). `instructor` may list several people separated by `;`.
- Names in `instructor` should match `faculty.csv` names (titles such as Dr./Prof. and small typos are tolerated).
- Personal data (student names, phone numbers) should be replaced with dummy values.

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

```bash
python eval/run_eval.py --model qwen3:8b    --mode multi  --runs 3
python eval/run_eval.py --model llama3.1:8b --mode multi  --runs 3
python eval/run_eval.py --model qwen3:8b    --mode single --runs 3   # single vs multi agent
python eval/run_eval.py --only P01 S03 --runs 1                      # quick check
```

Each configuration writes `eval/results/<model>__<mode>.json` (every answer, tool call, latency and
score) plus its own refusal log and drafts. `eval/results/summary.md` compares all configurations and
gives a per-question, per-run table that flags **questions whose outcome changed across runs**.

Deterministic tool checks (no LLM): `python tests/test_tools.py`.

## Project layout

```
helpdesk/config.py   paths, models, settings (env-overridable)
helpdesk/rag.py      loaders, chunking, Ollama embeddings, ChromaDB, hybrid search, index CLI
helpdesk/tools.py    the six agent tools
helpdesk/agent.py    prompts, single agent, multi-agent orchestrator + specialists (root_agent for adk web)
helpdesk/chat.py     runner (Helpdesk.ask), refusal detection/auto-logging, CLI
eval/                questions.json, run_eval.py, results/
docs/raw/            your documents        data/  timetable + faculty CSVs
tests/               tool self-check with synthetic fixtures
REPORT.md            findings
```

## Hardware notes

Tested with 16 GB RAM and a 6 GB laptop GPU. An 8B Q4 model (~5 GB) plus an 8k context does not fit
entirely in 6 GB of VRAM, so Ollama offloads part of it to the CPU, which is slower but works. Without
a GPU everything still runs on the CPU, just more slowly. Only one chat model is loaded at a time.
