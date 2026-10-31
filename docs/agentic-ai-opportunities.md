# Agentic AI Opportunities — Acme Legal Playbook Assistant

> This doc captures what is already "agentic" in the current codebase and what can be added next to make the product behave more like an autonomous legal-ops teammate.

## 1. Current state: how agentic is it already?

The repo is farther along than the top-level `README.md` suggests. The backend already implements:

| Agentic ingredient | What exists now | Where |
|---|---|---|
| **State-machine workflow** | LangGraph graph with `load → validate → retrieve → generate → assemble` nodes | `backend/app/workflows/playbook_draft.py` |
| **Tool-like retrieval** | pgvector semantic search + department filter + citation persistence | `backend/app/services/retrieval_utils.py`, `backend/app/api/v1/retrieval.py` |
| **Structured generation** | LLM returns JSON with `summary/checklist/risks/missing/next_steps` | `backend/app/services/llm_client.py` |
| **Deterministic guardrails** | Mandatory safety items appended when LLM misses them; deterministic rules in `playbook_rules.py` | `backend/app/workflows/vendor_onboarding.py`, `backend/app/workflows/playbook_rules.py` |
| **Human-in-the-loop** | Drafts stop at `pending_review`; approvers can approve/request changes/reject; revisions are versioned | `backend/app/api/v1/playbooks.py` |
| **Memory / audit** | `audit_logs`, `draft_reviews`, `approval_decisions`, versioned `drafts` | `backend/app/models/audit_log.py`, migrations |
| **Authentication & authorization** | JWT + role-based access (`admin/editor/user/viewer`) | `backend/app/services/auth.py`, `backend/app/models/user.py` |
| **Budget guardrails** | Voyage token ledger with reservation/reconcile pattern | `backend/app/services/usage_budget.py` |
| **Generic playbook engine** | No-code playbook authoring UI + dynamic intake forms | `backend/app/api/v1/playbooks.py`, `frontend/src/app/App.tsx` |

In other words, the system is already a **single-agent RAG workflow with guardrails, memory, and human approval**. The next phase is to evolve it from a "one-shot draft generator" into a **multi-step, self-improving legal-ops agent**.

## 2. What "more agentic" looks like for this product

Legal ops is a good agentic-AI domain because the work is:

- **Rule-heavy** — policies, thresholds, approvals.
- **Evidence-driven** — every claim needs a citation.
- **Human-gated** — final determinations must be reviewed by qualified people.
- **Iterative** — intake is rarely complete on the first try.

The agentic upgrades below are grouped by capability, with the simplest wins first.

---

### A. Planning & multi-step reasoning

Current behavior: one retrieval call, one LLM call, done.

Opportunities:

1. **Decompose the intake into sub-tasks.**
   - If a vendor provides a contract, the agent should plan: extract key terms → map to playbook questions → identify missing evidence → retrieve relevant policies → generate draft.
   - Implementation: add a `planning` node in LangGraph that emits a list of required evidence items before retrieval.
2. **Adaptive retrieval loops.**
   - After the first retrieval, the agent can judge whether the evidence is sufficient and issue follow-up queries (e.g., "find data-retention clauses").
   - Add a `needs_more_evidence` conditional edge back to `retrieve_sources`.
3. **Question-clarification planning.**
   - When answers are ambiguous, the agent should ask targeted clarification questions instead of guessing.
   - Add an `ask_clarification` interrupt node that returns questions to the frontend and resumes on answer.

Files to touch:

- `backend/app/workflows/playbook_draft.py`
- `backend/app/schemas/playbook.py` (add `ClarificationRequest`, `PlanStep`)
- `frontend/src/app/App.tsx` (clarification UI)

---

### B. Memory beyond the current case

Current behavior: each case is isolated; the agent has no memory of prior similar vendors or reviewer preferences.

Opportunities:

1. **Case similarity memory.**
   - When a new intake arrives, retrieve the *most similar closed cases* and use their reviewer feedback as a prior.
   - Add a `case_memory` table with embeddings over intake answers.
2. **Reviewer preference memory.**
   - Track per-reviewer patterns: does reviewer X always ask for an extra privacy clause for high-criticality vendors?
   - Store lightweight preference embeddings and surface them as "reviewer likely to ask for..." hints.
3. **Source-version memory.**
   - When a source is superseded, proactively flag drafts that cited the old version so they can be re-evaluated.

Files to touch:

- New model: `backend/app/models/case_memory.py`
- Workflow node: `recall_similar_cases`
- Service: `backend/app/services/case_memory.py`

---

### C. Reflection & self-correction

Current behavior: the LLM output is accepted (with deterministic safety padding) and persisted.

Opportunities:

1. **Citation verifier node.**
   - After generation, verify that every checklist item is actually supported by one of the retrieved passages.
   - Flag unsupported items and either remove them or move them to `missing_information`.
2. **Consistency checker.**
   - Compare the draft against deterministic playbook rules in `playbook_rules.py` and surface contradictions.
   - Example: if a rule says invoice > $10k needs human review and the intake says $50k, the draft must contain that action.
3. **Self-critique loop.**
   - Run a second LLM pass that critiques the draft for completeness, tone, and legal caution; feed critique back for a revision.
   - Keep the loop bounded (max 2 iterations) and log each iteration.
4. **Hallucination / drift detector.**
   - Compute semantic similarity between each generated claim and the nearest retrieved passage; reject low-similarity claims.

Files to touch:

- `backend/app/workflows/playbook_draft.py` (add `verify`, `critique`, `revise` nodes)
- `backend/app/services/citation_verifier.py`
- `backend/app/services/consistency_checker.py`

---

### D. Tool use & external action

Current behavior: the agent only reads from the internal vector store.

Opportunities:

1. **Document parsers as tools.**
   - DOCX only today. Add PDF, scanned PDF (OCR), and email parsers as LangGraph tools the planner can call.
   - Tool: `extract_document(file_bytes) -> structured_text`
2. **Web / registry lookup tools.**
   - Company registration lookup, sanctions-screening lists, or open supplier databases (where allowed in demo).
   - Tool: `screen_vendor(name: str) -> risk_flags`
3. **Notification / action tools.**
   - Email the requester when clarification is needed; notify the approver when a draft is pending.
   - In a real deployment: Slack, Teams, e-signature APIs.
4. **Calendar / SLA tracker.**
   - Estimate review SLA from case metadata and schedule reminders.

Files to touch:

- `backend/app/tools/` (new package)
- `backend/app/workflows/playbook_draft.py` (tool-calling node)
- `backend/app/services/notifications.py`

---

### E. Multi-agent orchestration

Current behavior: one monolithic graph does everything.

Opportunities:

1. **Specialist sub-agents.**
   - `IntakeAgent`: parses and validates intake.
   - `ResearchAgent`: retrieves and ranks evidence.
   - `DraftingAgent`: writes the checklist/risk summary.
   - `ComplianceAgent`: checks against hard rules and flags issues.
   - `ReviewCoordinator`: manages hand-off to human approvers.
2. **Supervisor pattern.**
   - A supervisor agent receives the request, delegates to specialists, and assembles the final output.
   - Each specialist can be a separate LangGraph graph with its own state and tools.
3. **Adversarial review agent.**
   - One agent drafts; another agent tries to find flaws; a third resolves.

Files to touch:

- `backend/app/agents/` (new package)
- `backend/app/workflows/supervisor.py`
- Refactor `playbook_draft.py` into agent-specific graphs.

---

### F. Human-in-the-loop at the right moments

Current behavior: workflow runs to completion, then waits for external review.

Opportunities:

1. **Clarification interrupts.**
   - Pause the graph when the agent detects missing or ambiguous information; resume via API when the user answers.
   - Use LangGraph `interrupt`/`checkpoint` functionality.
2. **Escalation interrupts.**
   - Pause when risk score crosses a threshold and require a senior approver before continuing.
3. **Approval-to-act.**
   - After human approval, the agent can auto-trigger export, notify stakeholders, or schedule follow-up tasks.
4. **Active learning from reviewer edits.**
   - When a reviewer edits a draft, capture the diff and use it to fine-tune future prompts (or at least surface it as a pattern).

Files to touch:

- `backend/app/workflows/playbook_draft.py` (interrupt nodes)
- `backend/app/api/v1/playbooks.py` (resume endpoints)
- `frontend/src/app/App.tsx` (interrupt UI)

---

### G. Autonomous background operations

Current behavior: indexing is triggered only by a human approval click.

Opportunities:

1. **Retry scheduler.**
   - Failed indexing jobs should auto-retry with exponential backoff and notify admins on persistent failure.
2. **Source freshness monitor.**
   - Periodically check whether source documents are approaching expiration and suggest re-review.
3. **Embedding model drift monitor.**
   - Alert if retrieval quality drops (measured by eval benchmarks) so the team can re-embed or tune prompts.
4. **Case auto-progression.**
   - If a case is stuck in `draft_pending_review` for N days, auto-escalate to the next approver.

Files to touch:

- `backend/app/jobs/` (new Celery/ARQ background worker package)
- `backend/app/services/scheduler.py`
- `infra/local/docker-compose.yml` (worker service)

---

### H. Evaluation & observability

Current behavior: minimal tests; no systematic eval of retrieval or generation quality.

Opportunities:

1. **Retrieval eval harness.**
   - Build a small golden dataset of questions + expected chunk IDs.
   - Metrics: recall@k, MRR, NDCG.
2. **Generation eval harness.**
   - Evaluate drafts against reference outputs using LLM-as-judge + deterministic rubrics (citation recall, rule coverage).
3. **Tracing.**
   - Integrate LangSmith / OpenTelemetry so every graph step, LLM call, and retrieval is traceable.
4. **A/B prompt registry.**
   - Store prompt templates with versions; run shadow tests on a fraction of cases.

Files to touch:

- `backend/tests/eval/` (new)
- `backend/app/services/eval.py`
- `backend/app/core/tracing.py`

---

## 3. Suggested roadmap (priority order)

| Phase | Focus | Deliverable | Why first? |
|---|---|---|---|
| **0. Polish** | Fix doc drift; top-level README says features are missing that already exist. | Update `README.md`, `PROJECT_HANDOVER.md`, `backend/README.md` | Makes the project credible and avoids duplicate work. |
| **1. Reflection** | Add citation verifier + consistency checker. | `backend/app/services/citation_verifier.py`, updated `playbook_draft.py` | Highest trust impact; cheap to add; directly reduces hallucination risk. |
| **2. Clarification HITL** | LangGraph interrupt when intake is incomplete. | Resume endpoint + frontend modal | Reduces garbage-in-garbage-out; legal intake is rarely complete. |
| **3. Case memory** | Retrieve similar closed cases as examples. | `case_memory` model + `recall_similar_cases` node | Makes the agent feel context-aware and improves draft quality. |
| **4. Eval harness** | Golden dataset + LLM-as-judge + LangSmith tracing. | `backend/tests/eval/` | Needed before iterating on prompts or models. |
| **5. Multi-agent refactor** | Split graph into Intake/Research/Draft/Compliance agents under a supervisor. | `backend/app/agents/` | Enables scaling to new playbooks and more complex workflows. |
| **6. Background autonomy** | Retry scheduler, source-freshness monitor, SLA escalation. | `backend/app/jobs/` | Moves from "tool you operate" to "system that runs itself". |
| **7. External tools** | PDF/OCR parser, demo screening lookup, notifications. | `backend/app/tools/` | Unlocks real-world integrations. |

## 4. Non-functional guardrails to keep

As the system becomes more autonomous, these existing controls become *more* important, not less:

- **Mandatory disclaimer** on every draft (already present).
- **No final determination without human approval** — keep the `approved` status as a human-only transition.
- **Citation provenance** — every generated claim must remain traceable to a `document_chunk`.
- **Budget caps** — extend the reservation pattern to LLM tokens and tool calls, not just embeddings.
- **Audit immutability** — never mutate `audit_logs` or `approval_decisions`; append only.
- **Role-based tool access** — only admins/editors can publish sources or playbooks; viewers cannot trigger generation.

## 5. One-line takeaway

The project already has the skeleton of a trustworthy agentic legal-ops assistant. The biggest near-term wins are **reflection (citation/rule verification)**, **clarification interrupts**, and **case memory** — together they move the product from "RAG chatbot" to "collaborative agent that knows when it doesn't know."
