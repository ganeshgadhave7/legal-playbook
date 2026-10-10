import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { RichTextEditor } from "../components/RichTextEditor";
import {
  checkHealth,
  createGenericDraft,
  createPlaybook,
  decideDocument,
  getMe,
  getPlaybookCase,
  listDocuments,
  listPlaybookCases,
  listPlaybooks,
  login,
  publishPlaybook,
  revisePlaybookCase,
  setAuthToken,
  updateDraft,
  createDraftVersion,
  listDraftVersions,
  getDraftVersion,
  exportDraft,
  type DraftVersion,
  updatePlaybook,
  uploadDocument,
  type GenericDraft,
  type IntakeQuestion,
  type Playbook,
  type PlaybookCase,
  type PlaybookCaseList,
  type SourceDocument,
  type SourceDocumentUploadMetadata,
  type UserResponse,
} from "../lib/api";

type Tab = "documents" | "intake" | "playbooks" | "drafts";

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
  department: "Third-Party Risk",
  description: "",
  prompt_template: `You are an AI assistant for the Acme Demo Bank third-party technology risk program.

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
  const [token, setToken] = useState<string | null>(() => {
    const saved = typeof window !== "undefined" ? window.localStorage.getItem("authToken") : null;
    if (saved) setAuthToken(saved);
    return saved;
  });
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [selectedFileName, setSelectedFileName] = useState("");
  const [uploadMetadata, setUploadMetadata] = useState<SourceDocumentUploadMetadata>({
    title: "",
    department: "Third-Party Risk",
    document_type: "Vendor due diligence",
    document_code: "",
    version: "1.0",
    fictional: true,
  });

  // Intake state
  const [selectedPlaybook, setSelectedPlaybook] = useState<Playbook | null>(null);
  const [answers, setAnswers] = useState<Record<string, string | number | boolean>>({});
  const [draft, setDraft] = useState<GenericDraft | null>(null);
  const [lastSubmittedAnswers, setLastSubmittedAnswers] = useState<Record<string, string | number | boolean> | null>(null);

  // Playbook authoring state
  const [showPlaybookForm, setShowPlaybookForm] = useState(false);
  const [playbookForm, setPlaybookForm] = useState(initialPlaybookForm);
  const [editingPlaybookId, setEditingPlaybookId] = useState<string | null>(null);
  const [editingPlaybookKey, setEditingPlaybookKey] = useState<string | null>(null);
  const [viewingPlaybook, setViewingPlaybook] = useState<Playbook | null>(null);

  // Draft cases state
  const [cases, setCases] = useState<PlaybookCaseList["items"]>([]);
  const [selectedCase, setSelectedCase] = useState<PlaybookCase | null>(null);
  const [editingCaseId, setEditingCaseId] = useState<string | null>(null);
  const [isEditingDraft, setIsEditingDraft] = useState(false);
  const [draftHtml, setDraftHtml] = useState<string>("");
  const [savingDraft, setSavingDraft] = useState(false);
  const [generationStatus, setGenerationStatus] = useState<string | null>(null);
  const [draftVersions, setDraftVersions] = useState<DraftVersion[]>([]);
  const [viewingVersion, setViewingVersion] = useState<PlaybookCase | null>(null);
  const [exportFormat, setExportFormat] = useState<"html" | "docx" | "pdf">("html");

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

  const refreshCases = useCallback(async () => {
    const result = await listPlaybookCases();
    setCases(result.items);
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      if (token) window.localStorage.setItem("authToken", token);
      else window.localStorage.removeItem("authToken");
    }
    setAuthToken(token);
  }, [token]);

  useEffect(() => {
    if (!token) return;
    getMe().then(setUser).catch(() => {
      setToken(null);
      setUser(null);
    });
  }, [token]);

  useEffect(() => {
    if (!selectedCase) {
      setDraftVersions([]);
      setViewingVersion(null);
      return;
    }
    listDraftVersions(selectedCase.case_id)
      .then((result) => setDraftVersions(result.items))
      .catch((e) => {
        console.error("Failed to load draft versions:", e);
        setDraftVersions([]);
      });
  }, [selectedCase?.case_id]);

  useEffect(() => {
    if (tab === "drafts" && cases.length > 0 && !selectedCase) {
      getPlaybookCase(cases[0].case_id)
        .then((full) => setSelectedCase(full))
        .catch((e) => {
          console.error("Auto-load first draft failed:", e);
          setError(e instanceof Error ? e.message : "Could not load draft.");
        });
    }
  }, [tab, cases.length, selectedCase?.case_id]);

  useEffect(() => {
    if (!token) return;
    Promise.all([checkHealth(), refreshDocuments(), refreshPlaybooks(), refreshCases()])
      .then(([health]) => setApiState(health.database === "connected" ? "connected" : "unavailable"))
      .catch(() => setApiState("unavailable"));
  }, [token, refreshDocuments, refreshPlaybooks, refreshCases]);

  useEffect(() => {
    // Reset answers when playbook changes
    if (selectedPlaybook) {
      const initial: Record<string, string | number | boolean> = {};
      selectedPlaybook.intake_questions.forEach((q) => {
        initial[q.key] = q.type === "boolean" ? false : q.type === "number" ? 0 : "";
      });
      setAnswers(initial);
      setDraft(null);
      setLastSubmittedAnswers(null);
      setSuccess("");
    }
  }, [selectedPlaybook]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const response = await login(loginEmail, loginPassword);
      setToken(response.access_token);
      setLoginEmail("");
      setLoginPassword("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  function handleLogout() {
    setToken(null);
    setUser(null);
    setDraft(null);
    setDocuments([]);
    setPlaybooks([]);
    setSelectedPlaybook(null);
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const input = event.currentTarget.elements.namedItem("policy-file") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      setError("Choose a fictional vendor-onboarding DOCX to upload.");
      return;
    }
    setBusy(true);
    try {
      const uploaded = await uploadDocument(file, uploadMetadata);
      await refreshDocuments();
      setSuccess(`Uploaded ${uploaded.original_filename}; status is ${uploaded.status}.`);
      input.value = "";
      setSelectedFileName("");
      setUploadMetadata((current) => ({ ...current, title: "", document_code: "" }));
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
    setGenerationStatus("Reading intake answers…");
    const statusInterval = window.setInterval(() => {
      setGenerationStatus((current) => {
        const messages = [
          "Reading intake answers…",
          "Retrieving relevant policy passages…",
          "Analyzing gaps against bank standards…",
          "Building checklist and risk summary…",
          "Finalizing draft…",
        ];
        const idx = messages.indexOf(current ?? "");
        return messages[Math.min(idx + 1, messages.length - 1)];
      });
    }, 1200);
    try {
      let caseId: string;
      if (editingCaseId) {
        const revised = await revisePlaybookCase(editingCaseId, answers, "Intake answers updated by user");
        caseId = revised.case_id;
        setEditingCaseId(null);
      } else {
        const created = await createGenericDraft(selectedPlaybook.key, selectedPlaybook.version, answers);
        caseId = created.case_id;
      }
      await refreshCases();
      setLastSubmittedAnswers({ ...answers });
      setSuccess("Draft generated successfully.");
      setGenerationStatus(null);
      window.clearInterval(statusInterval);
      // Redirect to drafts tab and select the new case
      setTab("drafts");
      const fullCase = await getPlaybookCase(caseId);
      setSelectedCase(fullCase);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create draft.");
      window.clearInterval(statusInterval);
      setGenerationStatus(null);
    } finally {
      setBusy(false);
    }
  }

  function updateAnswer(key: string, value: string | number | boolean) {
    setAnswers((current) => ({ ...current, [key]: value }));
  }

  async function loadCaseForEdit(caseItem: PlaybookCase) {
    const playbook = playbooks.find((p) => p.key === caseItem.playbook_key && p.version === caseItem.playbook_version);
    if (!playbook) {
      setError("Playbook for this case is not available.");
      return;
    }
    const fullCase = await getPlaybookCase(caseItem.case_id);
    setSelectedPlaybook(playbook);
    setAnswers(fullCase.intake_answers as Record<string, string | number | boolean>);
    setLastSubmittedAnswers(null);
    setEditingCaseId(fullCase.case_id);
    setDraft(null);
    setTab("intake");
    setSuccess("Answers loaded. Edit them and click Generate draft to create a revision.");
  }

  function viewPlaybook(playbook: Playbook) {
    setViewingPlaybook(playbook);
  }

  async function exportDraftFile(draft: PlaybookCase, format: "html" | "docx" | "pdf") {
    try {
      const blob = await exportDraft(draft.case_id, draft.draft_id, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${draft.playbook_title.replace(/\s+/g, "_")}_v${draft.draft_version}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setSuccess(`Exported as ${format.toUpperCase()}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not export as ${format.toUpperCase()}.`);
    }
  }

  function startEditingDraft() {
    if (!selectedCase) return;
    setDraftHtml(selectedCase.full_html);
    setIsEditingDraft(true);
  }

  function cancelEditingDraft() {
    setIsEditingDraft(false);
    setDraftHtml("");
  }

  async function saveDraftChanges(mode: "overwrite" | "new_version") {
    if (!selectedCase) return;
    setSavingDraft(true);
    setError("");
    setSuccess("");
    try {
      const updated =
        mode === "overwrite"
          ? await updateDraft(selectedCase.case_id, selectedCase.draft_id, draftHtml)
          : await createDraftVersion(selectedCase.case_id, draftHtml);
      setSelectedCase(updated);
      setViewingVersion(null);
      setIsEditingDraft(false);
      setDraftHtml("");
      setSuccess(mode === "overwrite" ? "Draft updated successfully." : "New draft version saved successfully.");
      await refreshCases();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save draft.");
    } finally {
      setSavingDraft(false);
    }
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
      if (field === "key" && typeof value === "string") {
        value = value.trim().replace(/[^a-z0-9_]/g, "");
      }
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

  function handleEditPlaybook(playbook: Playbook) {
    setPlaybookForm({
      key: playbook.key,
      version: playbook.version,
      title: playbook.title,
      department: playbook.department,
      description: playbook.description ?? "",
      prompt_template: playbook.prompt_template,
      intake_questions: playbook.intake_questions.length > 0 ? playbook.intake_questions : [emptyQuestion()],
    });
    setEditingPlaybookId(playbook.id);
    setEditingPlaybookKey(playbook.key);
    setShowPlaybookForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function handleNewPlaybook() {
    setPlaybookForm(initialPlaybookForm);
    setEditingPlaybookId(null);
    setEditingPlaybookKey(null);
    setShowPlaybookForm((s) => !s);
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
      if (editingPlaybookKey) {
        await updatePlaybook(editingPlaybookKey, {
          title: playbookForm.title,
          department: playbookForm.department,
          description: playbookForm.description || null,
          intake_questions: cleanedQuestions,
          prompt_template: playbookForm.prompt_template,
        });
        setSuccess("Playbook updated.");
      } else {
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
      }
      setPlaybookForm(initialPlaybookForm);
      setEditingPlaybookId(null);
      setEditingPlaybookKey(null);
      setShowPlaybookForm(false);
      await refreshPlaybooks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save playbook.");
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

  if (!token) {
    return (
      <div className="login-shell">
        <div className="login-card">
          <div className="brand-mark" style={{ margin: "0 auto 16px", float: "none", width: 48, height: 48, borderRadius: 14, fontSize: 24 }}>
            A
          </div>
          <h1>Acme Legal Playbook</h1>
          <p>Sign in to access the fictional bank vendor onboarding demo.</p>
          <form onSubmit={handleLogin}>
            <label>
              Email
              <input
                type="email"
                required
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
                placeholder="admin@acme.demo"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                required
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="••••••••"
              />
            </label>
            {error && <div className="toast error">{error}</div>}
            <button className="button primary full-button" type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <div className="login-hint">
            Default demo account: <b>admin@acme.demo</b> / <b>AcmeDemo2025!</b>
          </div>
        </div>
      </div>
    );
  }

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
        <button className={`nav-item ${tab === "drafts" ? "active" : ""}`} onClick={() => setTab("drafts")}>
          <span className="nav-icon">🗀</span> Drafts
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
            {user ? (
              <>
                <span className="avatar">{user.email.slice(0, 1).toUpperCase()}</span>
                <span>{user.email}</span>
                <button className="button secondary" onClick={handleLogout} disabled={busy}>
                  Log out
                </button>
              </>
            ) : (
              <span className="muted">Not signed in</span>
            )}
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
                  <p>Review fictional bank policies and vendor evidence before they can ground playbook outputs.</p>
                </div>
                <span className="count-pill">{documents.length} DOCUMENT{documents.length === 1 ? "" : "S"}</span>
              </div>

              <div className="notice-card">
                <span className="notice-icon">i</span>
                <div>
                  <strong>Fictional bank vendor-onboarding workspace</strong>
                  <p>Only synthetic bank policies and vendor evidence belong here. Approved documents are embedded and become eligible for retrieval.</p>
                </div>
              </div>

              <div className="section-heading">
                <div>
                  <h2>Upload source</h2>
                  <p>DOCX only · 10 MB maximum · approval required before indexing</p>
                </div>
              </div>
              <form className="upload-card" onSubmit={handleUpload}>
                <div className="upload-metadata-grid">
                  <label className="upload-title-field">
                    Document title
                    <input
                      required
                      maxLength={300}
                      value={uploadMetadata.title}
                      onChange={(e) => setUploadMetadata((current) => ({ ...current, title: e.target.value }))}
                      placeholder="Third-Party IT Risk Assessment Standard"
                    />
                  </label>
                  <label>
                    Department
                    <input
                      required
                      maxLength={120}
                      value={uploadMetadata.department}
                      onChange={(e) => setUploadMetadata((current) => ({ ...current, department: e.target.value }))}
                      placeholder="Third-Party Risk"
                    />
                  </label>
                  <label>
                    Document type
                    <input
                      required
                      maxLength={120}
                      value={uploadMetadata.document_type}
                      onChange={(e) => setUploadMetadata((current) => ({ ...current, document_type: e.target.value }))}
                      placeholder="Policy, questionnaire, evidence summary"
                    />
                  </label>
                  <label>
                    Document code (optional)
                    <input
                      maxLength={120}
                      value={uploadMetadata.document_code}
                      onChange={(e) => setUploadMetadata((current) => ({ ...current, document_code: e.target.value }))}
                      placeholder="TPRM-STD-001"
                    />
                  </label>
                  <label>
                    Version
                    <input
                      required
                      maxLength={50}
                      value={uploadMetadata.version}
                      onChange={(e) => setUploadMetadata((current) => ({ ...current, version: e.target.value }))}
                      placeholder="1.0"
                    />
                  </label>
                  <label className="check-row upload-fictional-field">
                    <input
                      type="checkbox"
                      checked={uploadMetadata.fictional}
                      onChange={(e) => setUploadMetadata((current) => ({ ...current, fictional: e.target.checked }))}
                    />
                    <span>
                      <b>Fictional demo document</b>
                      <small>Keep enabled for the included sample vendor packet.</small>
                    </span>
                  </label>
                </div>
                <label className="dropzone">
                  <input
                    id="policy-file"
                    name="policy-file"
                    type="file"
                    accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    onChange={(e) => setSelectedFileName(e.currentTarget.files?.[0]?.name ?? "")}
                  />
                  <span className="upload-symbol">↑</span>
                  <strong>{selectedFileName || "Select a fictional vendor-onboarding DOCX"}</strong>
                  <span>
                    {selectedFileName ? "File selected — click Upload document to continue" : "Choose a synthetic bank policy or vendor-evidence DOCX"}
                  </span>
                </label>
                <div className="upload-actions">
                  <span>Enter the document's title, type, code, and version before uploading.</span>
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
                  <div className="empty-row">No source documents yet. Upload a fictional bank policy or vendor evidence file to begin.</div>
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
                <button className="button primary" onClick={handleNewPlaybook} disabled={busy}>
                  {showPlaybookForm ? "Cancel" : "New playbook"}
                </button>
              </div>

              {showPlaybookForm && (
                <form className="intake-card" onSubmit={handleSavePlaybook}>
                  <div className="form-title">
                    <span className="step-number">01</span>
                    <div>
                      <h2>{editingPlaybookId ? "Edit playbook" : "Create playbook"}</h2>
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
                      disabled={!!editingPlaybookId}
                    />
                  </label>
                  <label>
                    Version
                    <input
                      required
                      value={playbookForm.version}
                      onChange={(e) => updatePlaybookField("version", e.target.value)}
                      disabled={!!editingPlaybookId}
                    />
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
                    <div key={index} className="question-card">
                      <div className="question-card-top">
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
                      <div className="question-card-meta">
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
                        <div className="question-card-validation">
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
                        <div className="question-card-validation">
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
                    {busy ? "Saving…" : editingPlaybookId ? "Update draft playbook" : "Save draft playbook"}
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
                        <button className="text-action" disabled={busy} onClick={() => viewPlaybook(p)}>
                          View
                        </button>
                        {p.status === "draft" && (
                          <>
                            <button className="text-action approve" disabled={busy} onClick={() => handlePublishPlaybook(p.key)}>
                              Publish
                            </button>
                            <button className="text-action" disabled={busy} onClick={() => handleEditPlaybook(p)}>
                              Edit
                            </button>
                          </>
                        )}
                        {p.status === "archived" && (
                          <button className="text-action approve" disabled={busy} onClick={() => handlePublishPlaybook(p.key)}>
                            Republish
                          </button>
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
                        {generationStatus && (
                          <div className="generation-status">
                            <span className="spinner" />
                            <span>{generationStatus}</span>
                          </div>
                        )}
                        <button
                          className="button primary full-button"
                          type="submit"
                          disabled={busy}
                        >
                          {busy ? "Preparing draft…" : "Generate draft"}
                          {!busy && <span>→</span>}
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

          {tab === "drafts" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">DRAFT HISTORY</div>
                  <h1>Drafts</h1>
                  <p>View and revise previously generated drafts.</p>
                </div>
              </div>
              <div className="case-workspace">
                <div className="saved-cases-card">
                  <div className="saved-cases-heading">
                    <div>
                      <h2>Saved drafts</h2>
                      <p>{cases.length} total</p>
                    </div>
                  </div>
                  {cases.length === 0 ? (
                    <div className="cases-empty">No drafts yet. Run a playbook to create one.</div>
                  ) : (
                    cases.map((c) => (
                      <button
                        key={c.case_id}
                        className={`saved-case ${selectedCase?.case_id === c.case_id ? "selected" : ""}`}
                        onClick={async () => {
                          try {
                            const full = await getPlaybookCase(c.case_id);
                            setViewingVersion(null);
                            setSelectedCase(full);
                          } catch (e) {
                            console.error("Load draft failed:", e);
                            setError(e instanceof Error ? e.message : "Could not load draft.");
                          }
                        }}
                      >
                        <strong>{c.playbook_title}</strong>
                        <span>V{c.draft_version} · {c.case_status.replaceAll("_", " ")}</span>
                        <small>{new Date(c.created_at).toLocaleString()}</small>
                      </button>
                    ))
                  )}
                </div>
                <div className="draft-column">
                  {!selectedCase ? (
                    <div className="placeholder-card">
                      <div className="placeholder-art">✳</div>
                      <h2>Select a draft to view</h2>
                      <p>Choose a saved draft from the list to review or edit its intake answers.</p>
                    </div>
                  ) : (
                    (() => {
                      const display = viewingVersion || selectedCase;
                      const isLatest = !viewingVersion || viewingVersion.draft_id === selectedCase.draft_id;
                      return (
                        <div className="draft-card">
                          <div className="draft-header">
                            <div>
                              <div className="eyebrow">SAVED DRAFT</div>
                              <h2>{display.playbook_title}</h2>
                            </div>
                            <span className="draft-state">
                              V{display.draft_version} · {display.draft_status.replaceAll("_", " ").toUpperCase()}
                              {!isLatest && " · OLD VERSION"}
                            </span>
                          </div>
                          <div className="review-actions">
                            {!isEditingDraft && (
                              <>
                                <div className="export-dropdown">
                                  <select
                                    value={exportFormat}
                                    onChange={(e) => setExportFormat(e.target.value as "html" | "docx" | "pdf")}
                                  >
                                    <option value="html">Export as HTML</option>
                                    <option value="docx">Export as Word</option>
                                    <option value="pdf">Export as PDF</option>
                                  </select>
                                  <button className="button secondary" onClick={() => exportDraftFile(display, exportFormat)}>
                                    Export
                                  </button>
                                </div>
                                {isLatest && (
                                  <button className="button primary" onClick={startEditingDraft}>
                                    Edit draft
                                  </button>
                                )}
                              </>
                            )}
                            {isEditingDraft && (
                              <>
                                <button className="button secondary" onClick={cancelEditingDraft} disabled={savingDraft}>
                                  Cancel
                                </button>
                                <button className="button primary" onClick={() => saveDraftChanges("overwrite")} disabled={savingDraft}>
                                  {savingDraft ? "Saving…" : "Overwrite current draft"}
                                </button>
                                <button className="button primary" onClick={() => saveDraftChanges("new_version")} disabled={savingDraft}>
                                  {savingDraft ? "Saving…" : "Save as new version"}
                                </button>
                              </>
                            )}
                          </div>
                          <div className="draft-section">
                            <h3>Versions</h3>
                            {draftVersions.length === 0 ? (
                              <p className="muted">No version history available. Save a new version to create one.</p>
                            ) : (
                              <div className="version-table">
                                <div className="table-head">
                                  <span>VERSION</span>
                                  <span>STATUS</span>
                                  <span>CREATED</span>
                                  <span>ACTION</span>
                                </div>
                                {draftVersions.map((v) => (
                                  <div className={`table-row ${display.draft_id === v.draft_id ? "current" : ""}`} key={v.draft_id}>
                                    <span>V{v.version}</span>
                                    <span>{v.status.replaceAll("_", " ")}</span>
                                    <span>{new Date(v.created_at).toLocaleString()}</span>
                                    <span className="row-actions">
                                      {display.draft_id === v.draft_id ? (
                                        <span className="current-label">Viewing</span>
                                      ) : (
                                        <button
                                          className="text-action"
                                          onClick={async () => {
                                            try {
                                              const full = await getDraftVersion(selectedCase.case_id, v.draft_id);
                                              setViewingVersion(full);
                                            } catch (e) {
                                              setError(e instanceof Error ? e.message : "Could not load version.");
                                            }
                                          }}
                                        >
                                          View
                                        </button>
                                      )}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="disclaimer">{display.disclaimer}</div>
                          {isEditingDraft ? (
                            <div className="draft-section">
                              <RichTextEditor value={draftHtml} onChange={setDraftHtml} height={500} />
                            </div>
                          ) : (
                            <div
                              className="draft-section rich-document"
                              dangerouslySetInnerHTML={{ __html: display.full_html }}
                            />
                          )}
                          <div className="draft-section sources-section">
                            <h3>
                              Retrieved sources <span>{display.sources.length}</span>
                            </h3>
                            {display.sources.map((source) => (
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
                      );
                    })()
                  )}
                </div>
              </div>
            </>
          )}

          <footer className="page-footer">
            <span>ACME LEGAL PLAYBOOK ASSISTANT</span>
            <span>Fictional portfolio demonstration · Not legal advice</span>
          </footer>
        </section>

        {viewingPlaybook && (
          <div className="modal-overlay" onClick={() => setViewingPlaybook(null)}>
            <div className="modal-card" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <div>
                  <div className="eyebrow">PLAYBOOK DETAILS</div>
                  <h2>{viewingPlaybook.title}</h2>
                </div>
                <button className="button secondary" onClick={() => setViewingPlaybook(null)}>
                  Close
                </button>
              </div>
              <div className="modal-body">
                <p className="modal-meta">
                  <b>{viewingPlaybook.key}</b> · v{viewingPlaybook.version} · {viewingPlaybook.department} ·{" "}
                  <span className={`status-badge ${viewingPlaybook.status}`}>{viewingPlaybook.status}</span>
                </p>
                {viewingPlaybook.description && <p>{viewingPlaybook.description}</p>}
                <h3>Intake questions</h3>
                <ul className="modal-list">
                  {viewingPlaybook.intake_questions.map((q) => (
                    <li key={q.key}>
                      <strong>{q.label}</strong> <small>({q.key})</small>
                      <br />
                      <small>Type: {q.type} · {q.required ? "Required" : "Optional"}</small>
                    </li>
                  ))}
                </ul>
                <h3>Prompt template</h3>
                <pre className="modal-pre">{viewingPlaybook.prompt_template}</pre>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
