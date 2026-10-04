import { useCallback, useEffect, useMemo, useState, type FormEvent, type ChangeEvent } from "react";
import {
  checkHealth,
  createGenericDraft,
  createPlaybook,
  decideDocument,
  listDocuments,
  listPlaybooks,
  publishPlaybook,
  updatePlaybook,
  uploadDocument,
  type GenericDraft,
  type IntakeQuestion,
  type Playbook,
  type SourceDocument,
} from "../lib/api";

type Tab = "documents" | "intake" | "playbooks";

const emptyQuestion = (): IntakeQuestion => ({
  key: "",
  label: "",
  type: "text",
  required: true,
});

const initialPlaybookForm = {
  key: "",
  version: "1",
  title: "",
  department: "Procurement",
  description: "",
  prompt_template: `You are an AI assistant for Acme Technologies LLC legal operations.

Produce a checklist and risk summary strictly grounded in the approved policy passages provided.

Rules:
1. Use only facts that appear in the retrieved source passages.
2. If the intake raises a risk but no source passage supports the required action, add the item to missing_information instead of inventing a requirement.
3. Keep the tone professional and concise.
4. The output is a draft for qualified human review, not a final legal determination.

Respond with valid JSON only with keys: summary, checklist, risk_indicators, missing_information, recommended_next_steps.`,
  intake_questions: [emptyQuestion()],
};

function App() {
  const [tab, setTab] = useState<Tab>("documents");
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [apiState, setApiState] = useState("checking");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [selectedFileName, setSelectedFileName] = useState("");

  // Intake state
  const [selectedPlaybook, setSelectedPlaybook] = useState<Playbook | null>(null);
  const [answers, setAnswers] = useState<Record<string, string | number | boolean>>({});
  const [draft, setDraft] = useState<GenericDraft | null>(null);

  // Playbook authoring state
  const [showPlaybookForm, setShowPlaybookForm] = useState(false);
  const [playbookForm, setPlaybookForm] = useState(initialPlaybookForm);

  const refreshDocuments = useCallback(async () => {
    const result = await listDocuments();
    setDocuments(result.items);
  }, []);

  const refreshPlaybooks = useCallback(async () => {
    const result = await listPlaybooks();
    setPlaybooks(result.items);
    if (result.items.length > 0 && !selectedPlaybook) {
      setSelectedPlaybook(result.items[0]);
    }
  }, [selectedPlaybook]);

  useEffect(() => {
    Promise.all([checkHealth(), refreshDocuments(), refreshPlaybooks()])
      .then(([health]) => setApiState(health.database === "connected" ? "connected" : "unavailable"))
      .catch(() => setApiState("unavailable"));
  }, [refreshDocuments, refreshPlaybooks]);

  useEffect(() => {
    // Reset answers when playbook changes
    if (selectedPlaybook) {
      const initial: Record<string, string | number | boolean> = {};
      selectedPlaybook.intake_questions.forEach((q) => {
        initial[q.key] = q.type === "boolean" ? false : q.type === "number" ? 0 : "";
      });
      setAnswers(initial);
      setDraft(null);
    }
  }, [selectedPlaybook]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const input = event.currentTarget.elements.namedItem("policy-file") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      setError("Choose the fictional Procurement Policy DOCX first.");
      return;
    }
    setBusy(true);
    try {
      const uploaded = await uploadDocument(file);
      await refreshDocuments();
      setSuccess(`Uploaded ${uploaded.original_filename}; status is ${uploaded.status}.`);
      input.value = "";
      setSelectedFileName("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDecision(document: SourceDocument, decision: "approved" | "rejected") {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const updated = await decideDocument(
        document.id,
        decision,
        decision === "approved" ? "Approved fictional source for demo indexing." : "Rejected in demo review.",
      );
      await refreshDocuments();
      setSuccess(
        decision === "approved"
          ? `Approved and indexed. Current status: ${updated.status}.`
          : `Document rejected. Current status: ${updated.status}.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Review action failed.");
      await refreshDocuments().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  async function handleDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPlaybook) return;
    setBusy(true);
    setError("");
    setDraft(null);
    try {
      const created = await createGenericDraft(selectedPlaybook.key, selectedPlaybook.version, answers);
      setDraft(created);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create draft.");
    } finally {
      setBusy(false);
    }
  }

  function updateAnswer(key: string, value: string | number | boolean) {
    setAnswers((current) => ({ ...current, [key]: value }));
  }

  function renderQuestionInput(question: IntakeQuestion) {
    const value = answers[question.key];
    if (question.type === "boolean") {
      return (
        <label key={question.key} className="check-row">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => updateAnswer(question.key, e.target.checked)}
          />
          <span>
            <b>{question.label}</b>
          </span>
        </label>
      );
    }
    if (question.type === "select") {
      return (
        <label key={question.key}>
          {question.label}
          <select
            value={String(value)}
            onChange={(e) => updateAnswer(question.key, e.target.value)}
          >
            {question.options?.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </label>
      );
    }
    if (question.type === "number") {
      return (
        <label key={question.key}>
          {question.label}
          <input
            type="number"
            required={question.required}
            value={value as number}
            onChange={(e) => updateAnswer(question.key, Number(e.target.value))}
          />
        </label>
      );
    }
    return (
      <label key={question.key}>
        {question.label}
        {question.validation && question.validation.max_length && question.validation.max_length > 100 ? (
          <textarea
            required={question.required}
            minLength={question.validation?.min_length}
            maxLength={question.validation?.max_length}
            rows={4}
            value={String(value)}
            onChange={(e) => updateAnswer(question.key, e.target.value)}
          />
        ) : (
          <input
            type="text"
            required={question.required}
            minLength={question.validation?.min_length}
            maxLength={question.validation?.max_length}
            value={String(value)}
            onChange={(e) => updateAnswer(question.key, e.target.value)}
          />
        )}
      </label>
    );
  }

  // Playbook authoring helpers
  function updatePlaybookField<K extends keyof typeof playbookForm>(key: K, value: (typeof playbookForm)[K]) {
    setPlaybookForm((current) => ({ ...current, [key]: value }));
  }

  function updateQuestion(index: number, field: keyof IntakeQuestion, value: unknown) {
    setPlaybookForm((current) => {
      const questions = [...current.intake_questions];
      questions[index] = { ...questions[index], [field]: value } as IntakeQuestion;
      return { ...current, intake_questions: questions };
    });
  }

  function updateQuestionValidation(index: number, field: string, value: string) {
    setPlaybookForm((current) => {
      const questions = [...current.intake_questions];
      const q = { ...questions[index] };
      const validation = { ...(q.validation || {}) } as Record<string, number | undefined>;
      if (value === "") {
        delete validation[field];
      } else {
        validation[field] = Number(value);
      }
      questions[index] = { ...q, validation };
      return { ...current, intake_questions: questions };
    });
  }

  function addQuestion() {
    setPlaybookForm((current) => ({
      ...current,
      intake_questions: [...current.intake_questions, emptyQuestion()],
    }));
  }

  function removeQuestion(index: number) {
    setPlaybookForm((current) => ({
      ...current,
      intake_questions: current.intake_questions.filter((_, i) => i !== index),
    }));
  }

  async function handleSavePlaybook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const cleanedQuestions = playbookForm.intake_questions.map((q) => ({
        ...q,
        options: q.type === "select" ? (q.options || []).filter((o) => o.trim() !== "") : undefined,
      }));
      await createPlaybook({
        key: playbookForm.key,
        version: playbookForm.version,
        title: playbookForm.title,
        department: playbookForm.department,
        description: playbookForm.description || null,
        intake_questions: cleanedQuestions,
        prompt_template: playbookForm.prompt_template,
        status: "draft",
      });
      setSuccess("Playbook created as draft.");
      setPlaybookForm(initialPlaybookForm);
      setShowPlaybookForm(false);
      await refreshPlaybooks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create playbook.");
    } finally {
      setBusy(false);
    }
  }

  async function handlePublishPlaybook(key: string) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await publishPlaybook(key);
      setSuccess(`Playbook '${key}' published.`);
      await refreshPlaybooks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not publish playbook.");
    } finally {
      setBusy(false);
    }
  }

  const publishedPlaybooks = useMemo(() => playbooks.filter((p) => p.status === "published"), [playbooks]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark">A</div>
        <div className="brand-copy">
          <strong>ACME</strong>
          <span>LEGAL OPS</span>
        </div>
        <div className="side-divider" />
        <span className="side-label">WORKSPACE</span>
        <button className={`nav-item ${tab === "documents" ? "active" : ""}`} onClick={() => setTab("documents")}>
          <span className="nav-icon">▤</span> Source library
        </button>
        <button className={`nav-item ${tab === "playbooks" ? "active" : ""}`} onClick={() => setTab("playbooks")}>
          <span className="nav-icon">⚙</span> Playbooks
        </button>
        <button className={`nav-item ${tab === "intake" ? "active" : ""}`} onClick={() => setTab("intake")}>
          <span className="nav-icon">✳</span> Run playbook
        </button>
        <div className="sidebar-bottom">
          <span className="fictional-chip">FICTIONAL DEMO</span>
          <span className="side-footnote">Acme Technologies LLC</span>
          <span className={`api-indicator ${apiState}`}>
            <i /> API {apiState}
          </span>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            Playbooks <span>/</span>{" "}
            {tab === "documents" ? "Source library" : tab === "playbooks" ? "Playbook authoring" : "Run playbook"}
          </div>
          <div className="topbar-right">
            <span className="avatar">D</span>
            <span>Demo approver</span>
          </div>
        </header>

        <section className="content">
          {error && (
            <div className="toast error" role="alert">
              {error}
            </div>
          )}
          {success && (
            <div className="toast success" role="status">
              {success}
            </div>
          )}

          {tab === "documents" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">KNOWLEDGE GOVERNANCE</div>
                  <h1>Source library</h1>
                  <p>Review fictional policies before they can ground playbook outputs.</p>
                </div>
                <span className="count-pill">{documents.length} DOCUMENT{documents.length === 1 ? "" : "S"}</span>
              </div>

              <div className="notice-card">
                <span className="notice-icon">i</span>
                <div>
                  <strong>Fictional demonstration workspace</strong>
                  <p>Only synthetic Acme documents belong here. Approved documents are embedded and become eligible for retrieval.</p>
                </div>
              </div>

              <div className="section-heading">
                <div>
                  <h2>Upload source</h2>
                  <p>DOCX only · 10 MB maximum · approval required before indexing</p>
                </div>
              </div>
              <form className="upload-card" onSubmit={handleUpload}>
                <label className="dropzone">
                  <input
                    id="policy-file"
                    name="policy-file"
                    type="file"
                    accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    onChange={(e) => setSelectedFileName(e.currentTarget.files?.[0]?.name ?? "")}
                  />
                  <span className="upload-symbol">↑</span>
                  <strong>{selectedFileName || "Select a fictional policy document"}</strong>
                  <span>
                    {selectedFileName ? "File selected — click Upload document to continue" : "Choose the Acme Procurement Policy DOCX from your computer"}
                  </span>
                </label>
                <div className="upload-actions">
                  <span>Metadata is pre-filled for the first Procurement Policy demo.</span>
                  <button className="button primary" type="submit" disabled={busy}>
                    {busy ? "Uploading…" : "Upload document"}
                  </button>
                </div>
              </form>

              <div className="section-heading list-heading">
                <div>
                  <h2>Documents</h2>
                  <p>
                    Only documents in <b>Ready</b> status are used for RAG retrieval.
                  </p>
                </div>
                <button
                  className="button secondary"
                  onClick={() => refreshDocuments().catch((e) => setError(String(e)))}
                >
                  Refresh
                </button>
              </div>
              <div className="table-card">
                <div className="table-head">
                  <span>DOCUMENT</span>
                  <span>DEPARTMENT</span>
                  <span>VERSION</span>
                  <span>STATUS</span>
                  <span>ACTION</span>
                </div>
                {documents.length === 0 ? (
                  <div className="empty-row">No source documents yet. Upload the fictional Procurement Policy to begin.</div>
                ) : (
                  documents.map((doc) => (
                    <div className="table-row" key={doc.id}>
                      <div className="document-cell">
                        <span className="file-icon">DOC</span>
                        <span>
                          <strong>{doc.title}</strong>
                          <small>{doc.document_code ?? doc.original_filename}</small>
                        </span>
                      </div>
                      <span>{doc.department}</span>
                      <span>{doc.version}</span>
                      <span>
                        <b className={`status-badge ${doc.status}`}>{doc.status.replaceAll("_", " ")}</b>
                      </span>
                      <span className="row-actions">
                        {doc.status === "uploaded" || doc.status === "pending_review" ? (
                          <>
                            <button className="text-action approve" disabled={busy} onClick={() => handleDecision(doc, "approved")}>
                              Approve & index
                            </button>
                            <button className="text-action reject" disabled={busy} onClick={() => handleDecision(doc, "rejected")}>
                              Reject
                            </button>
                          </>
                        ) : doc.status === "ready" ? (
                          <span className="ready-label">Available for RAG</span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </>
          )}

          {tab === "playbooks" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">PLAYBOOK AUTHORING</div>
                  <h1>Playbooks</h1>
                  <p>Create and publish reusable playbook definitions.</p>
                </div>
                <button className="button primary" onClick={() => setShowPlaybookForm((s) => !s)} disabled={busy}>
                  {showPlaybookForm ? "Cancel" : "New playbook"}
                </button>
              </div>

              {showPlaybookForm && (
                <form className="intake-card" onSubmit={handleSavePlaybook}>
                  <div className="form-title">
                    <span className="step-number">01</span>
                    <div>
                      <h2>Create playbook</h2>
                      <p>Define the intake questions and LLM prompt template.</p>
                    </div>
                  </div>
                  <label>
                    Key
                    <input
                      required
                      pattern="^[a-z0-9_]+$"
                      value={playbookForm.key}
                      onChange={(e) => updatePlaybookField("key", e.target.value)}
                      placeholder="invoice_review"
                    />
                  </label>
                  <label>
                    Version
                    <input required value={playbookForm.version} onChange={(e) => updatePlaybookField("version", e.target.value)} />
                  </label>
                  <label>
                    Title
                    <input required value={playbookForm.title} onChange={(e) => updatePlaybookField("title", e.target.value)} />
                  </label>
                  <label>
                    Department
                    <input required value={playbookForm.department} onChange={(e) => updatePlaybookField("department", e.target.value)} />
                  </label>
                  <label>
                    Description
                    <textarea
                      rows={2}
                      value={playbookForm.description}
                      onChange={(e) => updatePlaybookField("description", e.target.value)}
                    />
                  </label>
                  <label>
                    Prompt template
                    <textarea rows={8} required value={playbookForm.prompt_template} onChange={(e) => updatePlaybookField("prompt_template", e.target.value)} />
                  </label>

                  <div className="field-label">Intake questions</div>
                  {playbookForm.intake_questions.map((q, index) => (
                    <div key={index} className="question-card" style={{ border: "1px solid #d1d5db", padding: "1rem", borderRadius: "8px", marginBottom: "1rem" }}>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: "1rem", alignItems: "end" }}>
                        <label>
                          Key
                          <input required value={q.key} onChange={(e) => updateQuestion(index, "key", e.target.value)} />
                        </label>
                        <label>
                          Label
                          <input required value={q.label} onChange={(e) => updateQuestion(index, "label", e.target.value)} />
                        </label>
                        <button type="button" className="button secondary reject-review" onClick={() => removeQuestion(index)} disabled={playbookForm.intake_questions.length <= 1}>
                          Remove
                        </button>
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem", marginTop: "1rem" }}>
                        <label>
                          Type
                          <select value={q.type} onChange={(e) => updateQuestion(index, "type", e.target.value)}>
                            <option value="text">Text</option>
                            <option value="number">Number</option>
                            <option value="boolean">Boolean</option>
                            <option value="select">Select</option>
                          </select>
                        </label>
                        <label className="check-row" style={{ alignItems: "center" }}>
                          <input type="checkbox" checked={q.required} onChange={(e) => updateQuestion(index, "required", e.target.checked)} />
                          <span>Required</span>
                        </label>
                        {q.type === "select" && (
                          <label>
                            Options (comma separated)
                            <input
                              value={(q.options || []).join(", ")}
                              onChange={(e) => updateQuestion(index, "options", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                            />
                          </label>
                        )}
                      </div>
                      {q.type === "text" && (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginTop: "1rem" }}>
                          <label>
                            Min length
                            <input
                              type="number"
                              value={q.validation?.min_length ?? ""}
                              onChange={(e) => updateQuestionValidation(index, "min_length", e.target.value)}
                            />
                          </label>
                          <label>
                            Max length
                            <input
                              type="number"
                              value={q.validation?.max_length ?? ""}
                              onChange={(e) => updateQuestionValidation(index, "max_length", e.target.value)}
                            />
                          </label>
                        </div>
                      )}
                      {q.type === "number" && (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginTop: "1rem" }}>
                          <label>
                            Greater than
                            <input type="number" value={q.validation?.gt ?? ""} onChange={(e) => updateQuestionValidation(index, "gt", e.target.value)} />
                          </label>
                          <label>
                            Less than or equal
                            <input type="number" value={q.validation?.le ?? ""} onChange={(e) => updateQuestionValidation(index, "le", e.target.value)} />
                          </label>
                        </div>
                      )}
                    </div>
                  ))}
                  <button type="button" className="button secondary" onClick={addQuestion}>
                    Add question
                  </button>
                  <button className="button primary full-button" type="submit" disabled={busy}>
                    {busy ? "Saving…" : "Save draft playbook"}
                  </button>
                </form>
              )}

              <div className="section-heading list-heading">
                <div>
                  <h2>Existing playbooks</h2>
                  <p>Only published playbooks can be run.</p>
                </div>
                <button className="button secondary" onClick={() => refreshPlaybooks().catch((e) => setError(String(e)))}>
                  Refresh
                </button>
              </div>
              <div className="table-card">
                <div className="table-head">
                  <span>PLAYBOOK</span>
                  <span>DEPARTMENT</span>
                  <span>VERSION</span>
                  <span>STATUS</span>
                  <span>ACTION</span>
                </div>
                {playbooks.length === 0 ? (
                  <div className="empty-row">No playbooks yet.</div>
                ) : (
                  playbooks.map((p) => (
                    <div className="table-row" key={p.id}>
                      <div className="document-cell">
                        <span className="file-icon">PB</span>
                        <span>
                          <strong>{p.title}</strong>
                          <small>{p.key}</small>
                        </span>
                      </div>
                      <span>{p.department}</span>
                      <span>{p.version}</span>
                      <span>
                        <b className={`status-badge ${p.status}`}>{p.status}</b>
                      </span>
                      <span className="row-actions">
                        {p.status === "draft" ? (
                          <button className="text-action approve" disabled={busy} onClick={() => handlePublishPlaybook(p.key)}>
                            Publish
                          </button>
                        ) : (
                          <span className="ready-label">{p.status === "published" ? "Runnable" : "Archived"}</span>
                        )}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </>
          )}

          {tab === "intake" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">GUIDED WORKFLOW</div>
                  <h1>Run playbook</h1>
                  <p>Select a published playbook and complete the intake to generate a source-grounded draft.</p>
                </div>
                <span className="playbook-version">PLAYBOOK RUNNER</span>
              </div>

              <div className="notice-card">
                <span className="notice-icon">i</span>
                <div>
                  <strong>Human review required</strong>
                  <p>This fictional demo creates a checklist and risk summary. It does not provide legal advice or approve a vendor.</p>
                </div>
              </div>

              <div className="case-workspace">
                <div className="intake-layout">
                  <form className="intake-card" onSubmit={handleDraft}>
                    <div className="form-title">
                      <span className="step-number">01</span>
                      <div>
                        <h2>Select playbook</h2>
                        <p>Choose a published playbook to run.</p>
                      </div>
                    </div>
                    <label>
                      Playbook
                      <select
                        value={selectedPlaybook?.id ?? ""}
                        onChange={(e) => {
                          const p = publishedPlaybooks.find((pb) => pb.id === e.target.value);
                          setSelectedPlaybook(p || null);
                        }}
                      >
                        {publishedPlaybooks.length === 0 && <option value="">No published playbooks</option>}
                        {publishedPlaybooks.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.title} ({p.department})
                          </option>
                        ))}
                      </select>
                    </label>

                    {selectedPlaybook && (
                      <>
                        <div className="form-title" style={{ marginTop: "1.5rem" }}>
                          <span className="step-number">02</span>
                          <div>
                            <h2>{selectedPlaybook.title} intake</h2>
                            <p>Provide the information known at intake.</p>
                          </div>
                        </div>
                        {selectedPlaybook.intake_questions.map((q) => renderQuestionInput(q))}
                        <button className="button primary full-button" type="submit" disabled={busy}>
                          {busy ? "Preparing draft…" : "Generate draft"}
                          <span>→</span>
                        </button>
                      </>
                    )}
                  </form>

                  <div className="draft-column">
                    {!draft ? (
                      <div className="placeholder-card">
                        <div className="placeholder-art">✳</div>
                        <h2>Your draft will appear here</h2>
                        <p>Complete the intake. The result will include checklist items, risk indicators, and citations from ready sources.</p>
                        <div className="placeholder-rule" />
                        <span>Source-grounded · Human-reviewed · Version traceable</span>
                      </div>
                    ) : (
                      <div className="draft-card">
                        <div className="draft-header">
                          <div>
                            <div className="eyebrow">AI-ASSISTED DRAFT</div>
                            <h2>{selectedPlaybook?.title} summary</h2>
                          </div>
                          <span className="draft-state">{draft.draft_status.replaceAll("_", " ").toUpperCase()}</span>
                        </div>
                        <div className="disclaimer">{draft.disclaimer}</div>
                        <div className="draft-section">
                          <h3>Summary</h3>
                          <p>{draft.summary}</p>
                        </div>
                        <div className="draft-section">
                          <h3>Checklist</h3>
                          <ul>
                            {draft.checklist.map((item, i) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ul>
                        </div>
                        <div className="draft-section">
                          <h3>Risk indicators</h3>
                          <ul className="risk-list">
                            {draft.risk_indicators.map((item, i) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ul>
                        </div>
                        {draft.missing_information.length > 0 && (
                          <div className="draft-section">
                            <h3>Missing information</h3>
                            <ul>
                              {draft.missing_information.map((item, i) => (
                                <li key={i}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        <div className="draft-section">
                          <h3>Recommended next steps</h3>
                          <ul>
                            {draft.recommended_next_steps.map((item, i) => (
                              <li key={i}>{item}</li>
                            ))}
                          </ul>
                        </div>
                        <div className="draft-section sources-section">
                          <h3>
                            Retrieved sources <span>{draft.sources.length}</span>
                          </h3>
                          {draft.sources.map((source) => (
                            <div className="source-citation" key={source.chunk_id}>
                              <span className="citation-mark">§</span>
                              <div>
                                <strong>{source.title}</strong>
                                <small>
                                  {source.document_code ?? "Source"} · v{source.version}
                                  {source.section ? ` · ${source.section}` : ""}
                                </small>
                              </div>
                              <span className="similarity">{Math.round(source.similarity * 100)}%</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}

          <footer className="page-footer">
            <span>ACME LEGAL PLAYBOOK ASSISTANT</span>
            <span>Fictional portfolio demonstration · Not legal advice</span>
          </footer>
        </section>
      </main>
    </div>
  );
}

export default App;
