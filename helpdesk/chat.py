"""Command-line chat with the helpdesk.

    python -m helpdesk.chat                          # multi-agent, default model
    python -m helpdesk.chat --mode single --model llama3.1:8b
    python -m helpdesk.chat -q "What is the slot for Autonomous Systems?"
"""
import argparse
import asyncio
import logging
import re
import time
import uuid
import warnings

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from . import agent as agents
from .tools import log_unanswered_question

logging.getLogger("google_adk").setLevel(logging.ERROR)  # hides Gemini-specific context-cache advice
warnings.filterwarnings("ignore", message=r"\[EXPERIMENTAL\]")

REFUSAL_RE = re.compile(r"\bI (?:do not|don't|dont) know\b", re.I)


class Helpdesk:
    def __init__(self, mode="multi", model=None):
        root = agents.build_multi(model) if mode == "multi" else agents.build_single(model)
        self.runner = Runner(app_name="helpdesk", agent=root, session_service=InMemorySessionService())

    async def ask(self, question: str, session_id: str | None = None) -> dict:
        """Run one turn. Pass the same session_id to keep conversation context across turns."""
        session_id = session_id or uuid.uuid4().hex
        svc = self.runner.session_service
        if not await svc.get_session(app_name="helpdesk", user_id="student", session_id=session_id):
            await svc.create_session(app_name="helpdesk", user_id="student", session_id=session_id)
        calls, authors, answer, t0 = [], [], "", time.time()
        msg = types.Content(role="user", parts=[types.Part(text=question)])
        async for ev in self.runner.run_async(user_id="student", session_id=session_id, new_message=msg):
            authors.append(ev.author)
            calls += [{"agent": ev.author, "name": c.name, "args": dict(c.args or {})} for c in ev.get_function_calls()]
            if ev.content and ev.content.parts:
                text = "".join(p.text or "" for p in ev.content.parts if not getattr(p, "thought", False))
                if text.strip():
                    answer = text
        answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip()
        refused = bool(REFUSAL_RE.search(answer)) or not answer
        if not answer:
            answer = agents.REFUSAL
        # The model is told to log refusals itself; this guarantees nothing is lost if it forgets.
        if refused and not any(c["name"] == "log_unanswered_question" for c in calls):
            log_unanswered_question(question, "agent could not answer (auto-logged)")
        return {"question": question, "answer": answer, "refused": refused,
                "answered_by": next((a for a in reversed(authors) if a != "user"), None),
                "tool_calls": calls, "seconds": round(time.time() - t0, 1), "session_id": session_id}


def main():
    ap = argparse.ArgumentParser(description="Academic Helpdesk chat")
    ap.add_argument("--mode", choices=["multi", "single"], default="multi")
    ap.add_argument("--model", default=None, help="Ollama model, e.g. qwen3:8b or llama3.1:8b")
    ap.add_argument("-q", "--question", help="ask one question and exit")
    ap.add_argument("-v", "--verbose", action="store_true", help="show tool calls")
    a = ap.parse_args()
    hd = Helpdesk(a.mode, a.model)

    def show(r):
        if a.verbose:
            for c in r["tool_calls"]:
                print(f"  [{c['agent']}] {c['name']}({c['args']})")
        print(f"\n[{r['answered_by']}, {r['seconds']}s]\n{r['answer']}\n")

    if a.question:
        show(asyncio.run(hd.ask(a.question)))
        return

    async def repl():
        sid = uuid.uuid4().hex
        print("Academic Helpdesk - type your question, or 'exit' to quit.")
        while (q := input("> ").strip()).lower() not in ("exit", "quit"):
            if q:
                show(await hd.ask(q, sid))

    try:
        asyncio.run(repl())
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
