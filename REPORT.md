# Academic Helpdesk Agent: Report

**Team:** Aradhya Mahajan (B23CS1088), Pragay (B23ES1024), Vyom Shah (B23CM1058), Priyanshu Pandey (B24BB1029)

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

**Iterations made once the real documents and timetable were added:**

6. `reg_2019.pdf`, the most important document, extracts with one word per line, which hurt both the
   embeddings and the model's reading. Fix: the PDF loader re-joins pages whose lines average under two
   words. Before the fix, the make-up-exam chunk retrieved for P08 lacked "ten days"; after it, the key
   facts of 10 of the 12 policy questions appear in the top-5 retrieved chunks.
7. The real timetable has no core/elective column. The model passed `course_type="Elective"` and `"all"`
   to `list_courses` and confidently answered "0 courses". Fix (in the tool, so every caller benefits):
   `all`/`any` mean no filter, and an unrecorded type is ignored with a `note` that explains why.
8. The model quoted the superseded rule ("Existing policy: ... allowed to appear ... need a C grade") from
   the 2024 attendance circular as if it were current. Fix: the policy prompt now says the most recent
   circular wins and superseded policy must not be presented as the current rule.
9. Fees were first listed as out of scope, but the Office of Academic Affairs fee order is in the corpus.
   Fee and scholarship questions now go to `policy_agent`, and the out-of-scope test "hostel fee"
   (answerable from `fee_2026_27.pdf`) was replaced by "campus gym timings".
10. **Fabricated citation copied from the prompt.** The first full evaluation (v1, kept in
    `eval/results/v1_example_citation/`) showed the single agent citing "UG_Academic_Regulations.pdf,
    page 12" 12 times. That file does not exist: it was the *example* in the citation rule. Twice (P04,
    P06) it answered with no tool call at all; for P04 it invented "4 years". Fix: the example became a
    placeholder ("Source: <source field>"), and the single agent must call a tool before answering. The
    multi-agent specialists never copied it (0 occurrences). All three configurations were then
    re-run (v2), and v2 is the result reported below.

## 3. Documents

**Unstructured corpus (`docs/raw/`): 30 documents.** Twenty-nine were fetched from the public IIT
Jodhpur website / academic intranet on 2026-10-26; `docs/manifest.csv` records the title, category,
source URL, fetch date, page count and SHA-256 of each. The four scanned circulars (attendance and
examination amendments, CGPA-conversion, holiday list) have no text layer, so they are stored as OCR'd
Markdown (`*.md`) instead of the scanned PDF; everything else keeps its original format. The 30th,
`timetable_slot_system_2026_27.md`, is generated from the official slot-system workbook (below).

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
| 30 | `timetable_slot_system_2026_27.md` | Timetable (generated) | – | Slot timings, slot-allocation rules, Minor exam timetable (15–20 Sep 2026), common-course slots, Time Table Committee, minor/specialization coordinators |

**Structured tables (`data/`).** These are generated by `python data/build_tables.py` from the official
workbook *AY 2026-27 Semester I Slot System (2nd Year onwards)* (`data/source/slot_system_2026_27_sem1.xlsx`).

| File | Rows | Columns | Built from |
|---|---|---|---|
| `courses.csv` | 613 | `course_code, course_name, department, course_type, ltp, credits, slot, instructor, co_instructors, room, students_registered, note` | "Classroom Allocation" sheet (740 rows, merged to one row per course code; tutorial / non-English sections kept in `slot`) |
| `slots.csv` | 81 | `slot, day, start_time, end_time` | "Slot System" grid: lecture slots A–K, N, U, V, the 2-hour lab slots L1–L10 / M1–M10 (from merged cells), and the M.Tech. Executive slots O–S, YO–YS |
| `faculty.csv` | 297 | `name, department, email, email_source` | Every instructor and co-instructor in the timetable |

Decisions in the conversion:

- **Course type, not core/elective.** The timetable does not say whether a course is core or elective,
  because that depends on the student's programme. `course_type` is instead decoded from the course code
  using Table 4.3 of the UG regulations (L = Lecture, P = Practical, D = Project, N = Non-graded,
  T = Thesis, ...). Asked about "electives", the agent reports the matching courses and says the
  timetable does not classify them.
- **Department names.** "School of Liberal Arts (SoLA)" is labelled
  "... / Humanities and Social Sciences (HSS)", following the workbook's own committee sheet, so that
  "Humanities" questions find it.
- **CSL7570.** The assignment's example prompts use CSL7570, but the official timetable lists Autonomous
  Systems as **CSL7650** (slot E, Gaurav Harit). At the team's request, CSL7570 was added as an alias row
  of CSL7650. Its `note` says so (the agent repeats it), and it is excluded from all counts.
- **Emails.**
  - 67 faculty have a real address: 37 from the collected department-page directory
    (`data/source/faculty_emails_collected.csv`) and 30 from the workbook's Time Table Committee sheet.
  - The remaining 230 have dummy placeholders (`first.last@dummy.iitj.ac.in`), as the assignment allows.
    `get_instructor_email` flags these, and the email agent tells the student to verify them.
  - Names are matched across spellings ("Nitin Awathare" ~ "Awathare Nitin Niranjan"). The build script
    prints every fuzzy match, and wrong ones were ruled out with a department check: timetable
    "Atul Kumar" (Chemistry) is not directory "Atul Kumar Sharma" (Mechanical).
- **No student data** is used anywhere. Drafts use placeholders such as `[Your Name]` and `[Roll Number]`.

These tables replace an earlier hand-made set of 42 courses. That set used synthetic course codes and
illustrative instructor assignments, and its `slots.csv` was missing slots B, D, E, H, J, U and V.

## 4. Evaluation method

- **Question set:** `eval/questions.json` has 30 prompts, including every example prompt in the assignment.
  - Policy (rules, credits, curriculum, calendar, circulars): 12
  - Schedule (slots, timings, course counts, instructors): 7
  - Email (instructor email ID or drafting): 4, three of which ask for a draft (`expects_draft`)
  - Out of scope (dining, travel, gym, Wi-Fi, weather, placements): 6
  - Email for a non-existent course: 1 (XYZ9999). The correct behaviour is to refuse, not invent an address.
- **Answer key.** Every key fact was checked by hand against the source. Several keys from the earlier
  synthetic data were wrong for the real timetable and were replaced: CSL7140 and ECL4010 do not exist,
  and the 400-level Humanities count is 2, not 7.

  | Q | Key | Where it is stated |
  |---|---|---|
  | P01 | 75% | `amend_attendance_2024.md`: exam eligibility delinked from attendance, but attendance "should not fall below 75%" |
  | P02 | 10 OE credits | `reg_2019.pdf` p.17 credit table; `btech_cse_curriculum.pdf` p.8 Table 2 |
  | P03 | 165 (150 graded + 15 non-graded) | `reg_2019.pdf` p.17; `btech_cse_curriculum.pdf` p.8; programme structures |
  | P04 | 14 registered semesters | `reg_2019.pdf` p.17, §11.4 |
  | P05 / P07 | min 12, max 25 credits | `reg_2019.pdf` p.29, §12.2 |
  | P06 | B = 8 | `reg_2019.pdf` p.8, Table 5.1 |
  | P08 | apply to Dean (Academics) through the instructor within ten days | `reg_2019.pdf` p.11, §8 |
  | P09 | on instructor approval; missed evaluation on medical/special grounds | `reg_2019.pdf` p.9 |
  | P10 | 7 August 2026 | `calendar_2026_27.pdf` p.1 |
  | P11 | Maths, Physics, Chemistry, Engineering Mechanics, ... | semester I/II of `btech_*_structure.pdf` |
  | P12 | Major ≥ 40% | `amend_exam_2024.md`, item 3 |
  | S/E | slot, times, counts, instructor, email | `courses.csv`, `slots.csv`, `faculty.csv` (generated from the official workbook) |
- **Accuracy (answerable questions only):** every entry of `expected` appears in the answer (whole word,
  case-insensitive; `a|b` means either). Short all-caps keys such as slot names are matched
  case-sensitively, so the word "a" is not slot A.
- **Groundedness:** the answer's `Source:` line names one of `expected_source`.
- **Correct refusals:** the share of `should_refuse` prompts answered with "I don't know".
- **Log tool called by agent:** the share of correct refusals where the agent called
  `log_unanswered_question` itself (the runner logs the rest).
- **False refusals:** the share of answerable questions that got "I don't know".
- **Routing** (multi-agent only): the answering specialist is in `expected_agent`.
- **Email drafts saved:** `save_email_draft` was really called, not just claimed in the reply.
- **Stability:** each configuration ran 3 times (temperature 0.2, fresh session per question).
  "Verdict changed" means the correct/grounded/refused outcome differed between runs. "Wording changed"
  means the answer text differed at all.
- **Configurations:** qwen3:8b multi-agent, llama3.1:8b multi-agent (LLM swapped), and qwen3:8b single-agent.
- **Hand review:** every WRONG verdict (§6.4) was read. Two scorer/key problems were found and fixed for
  all configurations by re-scoring the stored answers:
  - P10 "7th August" was not accepted.
  - S01 ("what is the slot") also demanded the time, which only S02 asks for.

  One remaining case is reported as a hand-adjusted figure (see §5).

Reproduce (Ollama running, index built):

```bash
python eval/run_eval.py --model qwen3:8b    --mode multi  --runs 3
python eval/run_eval.py --model llama3.1:8b --mode multi  --runs 3
python eval/run_eval.py --model qwen3:8b    --mode single --runs 3
python eval/run_eval.py --summary-only      # re-scores stored answers, writes eval/results/summary.md
```

## 5. Results

The final run (v2) produced 270 answers in about 40 minutes of model time, on an RTX 4050 6 GB laptop with 16 GB RAM.
Full per-question, per-run tables are in [eval/results/summary.md](eval/results/summary.md); every
answer and tool call is in `eval/results/<model>__<mode>.json`.

| Configuration | Accuracy | Groundedness | Correct refusals | Log tool called by agent | False refusals | Routing | Email drafts saved | Avg s / question |
|---|---|---|---|---|---|---|---|---|
| **qwen3:8b, multi-agent** | **82.6%** (57/69) | 82.6% (57/69) | **100%** (21/21) | 0% (0/21) | 4.3% (3/69) | 96.7% (87/90) | **100%** (9/9) | 10.1 |
| llama3.1:8b, multi-agent | 65.2% (45/69) | 69.6% (48/69) | **100%** (21/21) | 85.7% (18/21) | 14.5% (10/69) | 96.7% (87/90) | 0% (0/9) | **6.3** |
| qwen3:8b, single agent | 72.5% (50/69), hand-adjusted 85.5% (59/69) | **92.8%** (64/69) | **100%** (21/21) | 57.1% (12/21) | **0%** (0/69) | n/a | **100%** (9/9) | 9.8 |

Accuracy by category (3 runs, counts are answers):

| Configuration | Policy (36) | Schedule (21) | Email (12) | Refusals (21) |
|---|---|---|---|---|
| qwen3:8b multi | 24 | **21** | **12** | 21 |
| llama3.1:8b multi | 23 | 18 | 4 | 21 |
| qwen3:8b single | **27** | **21** | 2 (11 hand-adjusted) | 21 |

*Hand adjustment:* in E01, E02 and E04 the single agent saved a correct draft every time; all 9 saved
drafts in `eval/results/qwen3-8b__single_drafts/` are addressed to the right instructor. Its chat reply,
however, showed only the body without the "To:" line, so the automatic check (which looks for the
address in the reply) fails. Counting the saved draft gives 85.5%.

**Effect of the citation-prompt fix** (v1 → v2, same scorer):

| Configuration | Accuracy v1 → v2 | Groundedness v1 → v2 | False refusals v1 → v2 |
|---|---|---|---|
| qwen3:8b single | 49.3% → 72.5% | 71.0% → 92.8% | 13.0% → 0% |
| qwen3:8b multi | 87.0% → 82.6% | 87.0% → 82.6% | 0% → 4.3% |
| llama3.1:8b multi | 62.3% → 65.2% | 68.1% → 69.6% | 17.4% → 14.5% |

The qwen3 multi-agent drop is a single question: P08 was routed to `email_agent` in all three v2 runs and
to `policy_agent` in all three v1 runs. The orchestrator's prompt was identical in v1 and v2, so this is
sampling variation on a borderline routing decision, not an effect of the fix (§6.3).

**Answers that changed across runs:**

| Configuration | Verdict changed | Wording changed (verdict same unless listed left) |
|---|---|---|
| qwen3:8b multi | none | 10: P01, P02, P03, P10, S03, S04, S06, E01, E02, E04 |
| llama3.1:8b multi | P01, P02, E01, E02, E03 | 17: P01, P02, P03, P08, P09, P10, P11, P12, S01, S02, S04, S06, S07, E01, E02, E03, E04 |
| qwen3:8b single | P09, E03 | 13: P01, P03, P08, P09, P11, P12, S03, S04, E01, E02, E03, E04, R04 |

## 6. Findings

### 6.1 Refusals are solid. Logging needs the safeguard.
- All three configurations refused all 21 out-of-scope answers (6 questions × 3 runs + XYZ9999 × 3),
  and none invented an answer or an address for them.
- Every refusal reached `logs/unanswered.jsonl` (24, 31 and 21 entries, one per refused answer).
- But qwen3's orchestrator **never** called `log_unanswered_question` itself (0/21): it just wrote the
  refusal sentence. All its log entries come from the runner's safeguard. Without that safeguard the
  human hand-off requirement would have failed silently, so it should stay.
- llama3.1 did call the tool (85.7%). It also logged its 10 false refusals, which puts answerable
  questions into the human queue.

### 6.2 qwen3:8b is the better model; llama3.1:8b is faster but unreliable with tools
qwen3 was more accurate (82.6% vs 65.2%), had fewer false refusals (4.3% vs 14.5%), and was perfect on
schedule and email questions. llama3.1 was about 40% faster (6.3 s vs 10.1 s per question; qwen3's
email turns average 23 s because they make 3 tool calls). Its failures are the dangerous kind:

- **Ignoring tool results.** In 4 of 6 E01/E02 answers, `get_instructor_email` returned
  `found: true, email: gharit@iitj.ac.in`, yet llama replied "the course or instructor is not in the
  faculty directory".
- **Corrupting data it was given.** In E01 run 1 and in all three E03 runs, it wrote the address as
  "ghari@iitj.ac.in" (one letter lost) and added a false "this is a placeholder address" warning.
- **Claiming actions it did not take.** It never called `save_email_draft` (0/9), yet in 2 of the 3 E04
  runs it told the student "This email has been saved for review".
- **Misreading a tool note as failure.** In S03, `list_courses` ignored the unknown "elective" filter,
  said why in a note, and returned the 2 correct courses. llama answered "I don't know" all three times.

### 6.3 Multi-agent vs single agent
- **Routing is good but brittle at the edges.** Routing was 96.7% for both models, and the only
  misroute was P08 ("If I miss the Major exam because I was sick, how can I apply for a makeup exam?").
  The orchestrator's rule sends "email ... for illness, makeup exam" requests to `email_agent`, and
  "sick" + "makeup exam" pulls this procedural question there. `email_agent` has no document search,
  so it refused: a routing error became a false refusal. qwen3 routed it correctly in all of v1 and
  wrongly in all of v2 with an identical prompt, so the decision sits near a boundary.
- **Specialists follow their procedures better.** On email requests the single agent's replies dropped
  the recipient line, and in E03 run 3 it never called `get_instructor_email` (it told the student to
  "use the get_instructor_email function"). The focused email specialist did neither.
- **The single agent was more susceptible to prompt artefacts.** v1's copied example citation and its
  tool-less answers appeared only in the single agent.
- **With those fixed, the single agent is competitive.** Its groundedness was the highest (92.8%),
  it had no false refusals, and it scored 85.5% after hand adjustment. The single agent also has no
  routing step that can fail. The multi-agent system's advantages are modularity (a smaller tool set
  and prompt per agent) and more consistent email behaviour, at the cost of one more LLM call per turn.

### 6.4 Failures common to all configurations (hand-reviewed)
| Question | What happened | Root cause |
|---|---|---|
| P02 Open-elective credits (key: 10, `btech_cse_curriculum.pdf` p.8, `reg_2019.pdf` p.17) | **20** in 8 of 9 answers (llama run 3 was correct) | Every model cited `reg_2019.pdf` p.16, clause 11.2.2: "a total of 20 Credits in the Major/Department Specialization or Minor ... 10 Credits out of 20 can be taken up as a part of Open electives". That is the specialization requirement; the models took its first number instead of the OE row of the p.17 credit table. |
| P03 Total B.Tech. credits (key: 165) | 160, 170, 180 or 200; never 165 | The total sits in the last row of a multi-column table ("Total Graded+Non Graded 165 175 211") that PDF extraction flattens. The right column is lost, and the 165 chunk often isn't retrieved (§2, item 6). |
| P11 First-year courses | Every run lists credit **categories** (IE 34, IS 16, ...) instead of courses | Retrieval returns the credit-distribution table, not the semester I/II rows of the programme structures. |
| P06, P09 | Correct facts, but cited `reg_pg_2022.pdf` (PG) for a B.Tech. question | The PG regulations repeat the grade table and the I-grade rule, so both rank high. For P09, the PG version sets a different completion deadline ("on or before the last date of add and drop") than the UG rule ("before the end of the first week of the next semester"). The PG deadline appears in 7 of the 9 P09 answers (every multi-agent run, 1 single-agent run). The keyword check cannot see this, so P09 is only partly correct. |
| P01 (llama only) | "the minimum attendance requirement ... is 0%" / "not applicable" | The 2024 circular delinks *exam eligibility* from attendance but keeps a 75% floor (below it, de-registration). llama kept only the first half. |

Questions answered correctly (by the key) in every run of every configuration: P04, P05, P06, P07, P09,
P10, P12, S01, S02, S04, S05, S06, S07, and all seven refusal prompts (P06 and P09 with the PG citation
noted above).

### 6.5 Retrieval and data lessons
- **Exact facts belong in tools.** Schedule questions, served by deterministic CSV tools, scored 21/21
  for qwen3. Every policy failure traces back to how PDF tables and long passages reach the model.
- **Extraction quality comes first.** Fixing one-word-per-line extraction in `reg_2019.pdf` raised the
  retrieval of key facts from 9/12 to 10/12 of the policy questions.
- **Tools should reject impossible filters loudly.** When `list_courses` matched nothing for "Elective",
  qwen confidently reported "0 courses". Making the tool explain that it ignored the filter fixed qwen;
  llama still failed (§6.2).

## 7. Limitations and future work

- **Table-heavy PDFs** (credit structures) are the main source of wrong answers. Table-aware extraction
  (e.g. pdfplumber, or converting the structure PDFs to Markdown tables, as was done for the circulars)
  and a reranker would target P02, P03 and P11 directly.
- **Programme filtering:** tagging chunks with the programme (UG/PG) and filtering on it would stop
  B.Tech. answers citing PG rules (P06, P09).
- **Routing:** give `email_agent` access to `search_documents`, or tell the orchestrator that "how do I
  apply for X" is a policy question even when it mentions illness. This would remove the P08 false refusal.
- **Data:**
  - 230 of the 297 instructor emails are dummy placeholders. They are flagged to the student, but a
    real directory would remove them.
  - The timetable has no core/elective classification.
  - CSL7570 is an alias row added only for the assignment's example prompts.
- **Keyword scoring** is strict. It was hand-reviewed here, but an LLM judge or a second human grader
  would scale better.
- **Re-index after changes:** answers are only as current as `docs/raw/` and the CSVs, so after any
  change run `python data/build_tables.py` and `python -m helpdesk.rag index`.
