# Academic Helpdesk Agent: Report

**Team:** Aradhya Mahajan (B23CS1088), Pragay (B23ES1024), Vyom Shah (B23CM1058), Priyanshu Pandey (B24BB1029)

> STATUS: the system design and evaluation method below are final. The Results and Findings sections are
> filled in from `eval/results/summary.md` after the evaluation has been run on the collected documents.

## 1. Objective

Build a local, multi-agent academic helpdesk for IIT Jodhpur that (a) answers questions about academic
programmes, course contents, academic rules and regulations and the timetable, citing the source document,
(b) drafts emails to course instructors (sick leave, makeup exams) for the student to review, and
(c) says "I don't know" to anything outside that scope instead of guessing, logging the question for a
human to answer.

## 2. System design

| Component | Choice | Why |
|---|---|---|
| Agent framework | Google ADK 2.12 (`LlmAgent`, `sub_agents`, `transfer_to_agent`) | Required; native multi-agent delegation |
| LLM serving | Ollama, through ADK's LiteLLM connector (`ollama_chat/<model>`) | Local; `ollama_chat` supports native tool calling |
| Chat models | `qwen3:8b` (main), `llama3.1:8b` (comparison), Q4 quantised, ~5 GB each | Fit in 16 GB RAM |
| Embeddings | `nomic-embed-text` via Ollama, with `search_document:` / `search_query:` prefixes | Small (274 MB), strong retrieval |
| Vector store | ChromaDB (persistent, cosine) | Local, no server |
| Retrieval | Hybrid: dense top-10 + BM25 top-10, reciprocal rank fusion, top-5 returned | Dense alone misses exact tokens such as course codes and "75%" |
| Chunking | ~1200 characters, 200 overlap, split at line/sentence boundaries, per PDF page; file title prepended | Keeps page numbers for citations |
| Structured data | `courses.csv`, `slots.csv`, `faculty.csv`, read by deterministic tools | Counting and lookups are unreliable through RAG |

**Agents.**
- `helpdesk_orchestrator` routes each request to one specialist and never answers itself. It refuses and
  logs clearly non-academic requests.
- `policy_agent`: `search_documents`. Handles rules, regulations, curriculum, credits and syllabus.
- `schedule_agent`: `lookup_course`, `list_courses`, `search_documents`. Handles slots, timings and courses floated.
- `email_agent`: `get_instructor_email`, `lookup_course`, `save_email_draft`. Handles instructor emails and drafts.
- Every agent also has `log_unanswered_question`. Specialists cannot transfer back, so each turn ends
  with the specialist's answer and the next turn starts again at the orchestrator.
- Single-agent baseline: one agent with all six tools and a combined prompt.

**Grounding and refusal controls.**
- Prompts allow only tool output to be used, require a `Source:` line copied from the tool's `source`
  field, and specify one fixed refusal sentence.
- If an agent refuses without calling the log tool, the runner logs the question itself.
- Email drafts are written to `outputs/drafts/` and never sent.

**Design iterations made during development** (observed on synthetic fixtures before the real documents were added):
1. The orchestrator refused "Write an email to the course instructor of CSL7570 that I need leave for 2 days"
   as out of scope. Fix: added routing examples (deliberately worded differently from the evaluation
   prompts), a rule that any email-to-instructor request goes to `email_agent`, and "when unsure, transfer
   to `policy_agent`" (whose answers stay grounded, so the cost of that rule is a refusal, not a hallucination).
2. The model cited "page 0" or "page 1" for non-paginated files. Fix: the tool now returns
   `source = "file, page N"` as a single string to copy, and the prompt forbids adding page numbers.
3. The single agent appended "Source: None" to refusals. Fix: refusals are exempt from the citation rule.
4. `llama3.2:3b` (tried only as a plumbing check) emitted tool calls as JSON text instead of real calls,
   a known weakness of small Llama models with native tool calling.
5. LiteLLM 1.106.2 imports the `mcp` package without declaring it as a dependency, so it is pinned in
   `requirements.txt`.

## 3. Documents

**Unstructured corpus (`docs/raw/`): 29 documents.** All were fetched from the public IIT Jodhpur
website / academic intranet on 2026-10-26; `docs/manifest.csv` records the title, category, source URL,
fetch date, page count and SHA-256 of each. The four scanned circulars (attendance and examination
amendments, CGPA-conversion, holiday list) have no text layer, so they are stored as OCR'd Markdown
(`*.md`) instead of the scanned PDF; everything else keeps its original format.

| # | Document | Type | Pages | Covers |
|---|---|---|---|---|
| 1 | `reg_2019.pdf` | Regulation | 43 | UG (B.Tech.) academic regulations: credits, grading (Table 5.1), attendance, exams, make-up, registration limits (12–25 cr), CGPA, graduation |
| 2 | `reg_pg_2022.pdf` | Regulation | 36 | PG (M.Tech./M.Sc.) regulations |
| 3 | `reg_msr_2023.pdf` | Regulation | 6 | M.S. by Research regulations |
| 4 | `amend_attendance_2024.md` | Circular (OCR) | 2 | 08 Jul 2024 attendance-policy amendment (delinks exam eligibility from attendance; 4-week absence rule) |
| 5 | `amend_exam_2024.md` | Circular (OCR) | 2 | 08 Jul 2024 examination-policy amendment (Major exam 3 h, ≥40% weightage) |
| 6 | `amend_continuation_2020.pdf` | Circular | 1 | 26 Oct 2020 revised continuation / graduation norms |
| 7 | `circ_medtech_joint_2022.pdf` | Circular | 5 | Joint Medical-Technologies programme regulations |
| 8 | `calendar_2026_27.pdf` | Calendar | 10 | Academic calendar AY 2026-27 (add/drop, Minor/Major exam dates) |
| 9 | `calendar_summer_2026.pdf` | Calendar | 1 | Summer-term 2026 calendar |
| 10 | `holidays_2026.md` | Calendar (OCR) | 2 | Institute holiday list 2026 |
| 11 | `fee_2026_27.pdf` | Office order | 4 | Fee structure AY 2026-27 |
| 12 | `scholarships.pdf` | Office order | 3 | UG/PG scholarships, fellowships, fee reimbursement |
| 13 | `cgpa_conversion.md` | Office order (OCR) | 1 | CGPA-conversion and medium-of-instruction certificate |
| 14 | `form_medical_certificate.pdf` | Form | 2 | Medical-certificate form (for leave / make-up) |
| 15 | `btech_cse_structure.pdf` | Curriculum | 3 | B.Tech. CSE programme structure (credit buckets) |
| 16 | `btech_cse_curriculum.pdf` | Curriculum | 74 | B.Tech. CSE curriculum and **course contents** |
| 17 | `btech_ee_structure.pdf` | Curriculum | 2 | B.Tech. EE programme structure |
| 18 | `btech_me_structure.pdf` | Curriculum | 3 | B.Tech. ME programme structure |
| 19 | `btech_aids_structure.pdf` | Curriculum | 2 | B.Tech. AI & DS programme structure |
| 20 | `common_courses.pdf` | Curriculum | 35 | Institute-wide common courses and contents (2nd year onwards) |
| 21 | `hss_courses.pdf` | Curriculum | 138 | HSS course bouquet and course contents |
| 22 | `non_graded_courses.pdf` | Curriculum | 5 | Non-graded institute-level courses |
| 23 | `mtech_cse_curriculum.pdf` | Curriculum | 1 | M.Tech. CSE curriculum |
| 24 | `mtech_ai_curriculum.pdf` | Curriculum | 1 | M.Tech. AI curriculum |
| 25 | `web_ug_registration.md` | Web page | – | UG registration guidelines (HSS bouquets) |
| 26 | `web_specialization_minor.md` | Web page | – | Specialization / minor / dual degree |
| 27 | `web_engineering_science.md` | Web page | – | Engineering-science programmes |
| 28 | `web_academic_programs.md` | Web page | – | List of academic programmes |
| 29 | `web_academics_contact.md` | Web page | – | Office of Academic Affairs contact |

**Structured tables (`data/`).**

| File | Rows | Columns | Covers |
|---|---|---|---|
| `courses.csv` | 42 | `course_code, course_name, department, category, credits, slot, instructor, meetings, room` | Every course floated in Semester I, AY 2026-27 |
| `slots.csv` | 40 | `slot, day, start_time, end_time` | The official B.Tech. slot system (lecture slots A, C, F, G, I, K, N and lab slots) |
| `faculty.csv` | 38 | `name, department, email` | Instructor directory with official email IDs |

Courses with no slot letter (e.g. Autonomous Systems, `IDL4010`) carry their fixed lecture times in the
`meetings` column instead; `slot`/`meetings`/`room` are passed through to the agent by `lookup_course`.

**Dummy / illustrative data.** No real student record is used anywhere. Course titles, levels, credits and
faculty names/emails are taken from the public IITJ documents and department pages; course codes are real
where the HSS document publishes them and otherwise synthetic (following the `<dept><L/P><level><nnn>`
pattern), and **course-to-instructor assignments are illustrative**, not official teaching allocations.
The only "personal" artefacts the system produces — email drafts in `outputs/drafts/` — use placeholders
(`[Your Name]`, `[Roll Number]`) for the student's identity.

**Provenance of the structured data:** adapted from the companion data-collection repository
`Mohi1038/academic-helpdesk-agent` (same course/slot/faculty ground truth), re-shaped into the three-CSV
schema this project's tools expect.

## 4. Evaluation method

- **Question set:** `eval/questions.json` has 30 prompts.
  - Policy: 12
  - Schedule: 7
  - Email: 4
  - Out of scope: 6
  - Email for a non-existent course: 1 (correct behaviour is to refuse and not invent an address)
- **Accuracy:** every key fact in `expected` appears in the answer (whole-word, case-insensitive).
  Answerable questions only.
- **Groundedness:** the answer cites one of the expected source documents.
- **Correct refusals:** the share of `should_refuse` prompts answered with "I don't know". Also reported:
  false refusals (answerable questions refused), routing accuracy (multi-agent), and the share of email
  requests that produced a saved draft.
- **Stability:** each configuration runs 3 times at temperature 0.2. A question is "changed across runs"
  if its correct/grounded/refused outcome differs between runs; all raw answers are kept in
  `eval/results/*.json`.
- **Configurations:** qwen3:8b multi-agent, llama3.1:8b multi-agent, qwen3:8b single-agent.

Limitation of the metric: keyword matching can miss a correct paraphrase (e.g. "three-fourths" for 75%),
so every WRONG verdict was checked by hand and corrected where needed (noted below).

## 5. Results

The evaluation runs locally against Ollama (it is not checked in because it needs the models). To
reproduce, with Ollama serving and the index built (`python -m helpdesk.rag index`):

```bash
python eval/run_eval.py --model qwen3:8b   --mode multi  --runs 3
python eval/run_eval.py --model llama3.1:8b --mode multi  --runs 3
python eval/run_eval.py --model qwen3:8b   --mode single --runs 3
python eval/run_eval.py --summary-only        # rebuilds eval/results/summary.md
```

Then paste the metrics table from `eval/results/summary.md` here. Columns: accuracy (in-scope),
groundedness (correct citation), correct refusals, false refusals, routing accuracy (multi), email drafts
saved, average seconds/question, and the count of questions whose outcome changed across the 3 runs.

> Scoring note: 27 of the 30 questions are auto-scored. Three policy questions — **P05** does not apply
> (replaced by a registration-limit question that *is* keyed), **P09** (conditions for an Incomplete grade)
> and **P11** (first-year common curriculum) — have open-ended answers and are left with an empty answer
> key, so their accuracy is reported as *unscored* and should be graded by hand; their groundedness
> (citation of the expected document) is still scored automatically.

## 6. Findings

To be written from the results above. Points to address:
- **qwen3:8b vs llama3.1:8b** — accuracy, tool-call reliability, routing accuracy, refusals, latency.
- **single vs multi agent** — does routing help or hurt accuracy/grounding; latency cost of the extra hop.
- **Stability** — list the questions whose correct/grounded/refused verdict changed across the 3 runs
  (`unstable questions` in `summary.md`) and explain why (non-deterministic retrieval ties, routing flips,
  email recipient drift).
- **Typical failure modes** — retrieval miss, wrong CSV filter, missing/incorrect citation, over-refusal of
  in-scope questions, and (for weaker models) tool calls emitted as plain text instead of real calls.

## 7. Limitations and future work

- Answers are only as current as the indexed documents and CSVs; re-run `python -m helpdesk.rag index` after updates.
- Scanned PDFs need OCR before indexing.
- 8B models occasionally skip tool calls or mis-route; the runner's auto-logging guarantees refusals are
  still logged, but cannot recover a wrong answer.
- Keyword-based accuracy is a lower bound; an LLM-as-judge or human grading would be more lenient to paraphrases.
