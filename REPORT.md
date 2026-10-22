# Academic Helpdesk Agent: Report

**Team:** TODO: names and roll numbers

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

TODO: table of the documents in `docs/raw/` (name, type, pages, what it covers) and of the CSV tables,
plus how personal data was replaced with dummy values.

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

TODO: paste the table from `eval/results/summary.md`.

## 6. Findings

TODO, to be written from the results:
- qwen3 vs llama3.1: accuracy, tool-call reliability, routing, refusals, latency
- single vs multi agent
- questions whose answers changed across runs, and why
- typical failure modes (retrieval miss, wrong filter, citation missing, over-refusal)

## 7. Limitations and future work

- Answers are only as current as the indexed documents and CSVs; re-run `python -m helpdesk.rag index` after updates.
- Scanned PDFs need OCR before indexing.
- 8B models occasionally skip tool calls or mis-route; the runner's auto-logging guarantees refusals are
  still logged, but cannot recover a wrong answer.
- Keyword-based accuracy is a lower bound; an LLM-as-judge or human grading would be more lenient to paraphrases.
