const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type SourceDocument = { id: string; title: string; department: string; document_type: string; document_code: string | null; version: string; status: string; original_filename: string; mime_type: string; file_size_bytes: number; sha256: string; fictional: boolean; created_at: string };
export type SourceDocumentList = { items: SourceDocument[]; limit: number; offset: number; total: number };

export type IntakeQuestion = {
  key: string;
  label: string;
  type: "text" | "number" | "boolean" | "select";
  required: boolean;
  options?: string[];
  validation?: {
    min_length?: number;
    max_length?: number;
    gt?: number;
    ge?: number;
    lt?: number;
    le?: number;
  };
};

export type Playbook = {
  id: string;
  key: string;
  version: string;
  title: string;
  department: string;
  description: string | null;
  status: "draft" | "published" | "archived";
  intake_questions: IntakeQuestion[];
  prompt_template: string;
  created_at: string;
  updated_at: string;
};

export type PlaybookList = { items: Playbook[]; total: number };

export type PlaybookSource = {
  document_id: string;
  title: string;
  document_code: string | null;
  version: string;
  section: string | null;
  page_number: number | null;
  chunk_id: string;
  similarity: number;
};

export type GenericDraft = {
  case_id: string;
  draft_id: string;
  case_status: string;
  draft_status: string;
  playbook_key: string;
  playbook_version: string;
  created_at: string | null;
  disclaimer: string;
  summary: string;
  checklist: string[];
  risk_indicators: string[];
  missing_information: string[];
  recommended_next_steps: string[];
  sources: PlaybookSource[];
  review_feedback?: string | null;
};

export type VendorOnboardingRequest = { vendor_name: string; service_description: string; annual_spend_usd: number; handles_personal_data: boolean; requires_system_access: boolean; uses_subcontractors: boolean; business_criticality: "low" | "medium" | "high" | "critical" };
export type VendorOnboardingDraft = { case_id: string; draft_id: string; case_status: string; draft_status: string; created_at: string | null; review_feedback: string | null; disclaimer: string; vendor_summary: string; checklist: string[]; risk_indicators: string[]; missing_information: string[]; recommended_next_steps: string[]; sources: PlaybookSource[] };
export type VendorCaseList = { items: Array<{ case_id: string; draft_id: string; vendor_name: string; playbook_key: string; playbook_version: string; case_status: string; draft_status: string; created_at: string }>; total: number };

async function parseResponse<T>(response: Response): Promise<T> {
  let body: Record<string, unknown> = {};
  try { body = await response.json(); } catch { /* retain HTTP status fallback */ }
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}

async function fetchApi(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try { return await fetch(input, init); }
  catch (error) {
    if (error instanceof TypeError) throw new Error(`Cannot reach API at ${API_BASE}. Check that the backend is running.`);
    throw error;
  }
}

export async function checkHealth(): Promise<{ status: string; database: string }> { return parseResponse(await fetchApi(`${API_BASE}/health`)); }
export async function listDocuments(): Promise<SourceDocumentList> { return parseResponse(await fetchApi(`${API_BASE}/api/v1/source-documents?limit=100`)); }

export async function uploadDocument(file: File): Promise<SourceDocument> {
  const form = new FormData();
  form.append("file", file);
  form.append("title", "Acme Technologies LLC Procurement Policy");
  form.append("department", "Procurement");
  form.append("document_type", "Policy");
  form.append("document_code", "PROC-POL-001");
  form.append("version", `upload-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`);
  form.append("fictional", "true");
  return parseResponse(await fetchApi(`${API_BASE}/api/v1/source-documents`, { method: "POST", body: form }));
}

export async function decideDocument(id: string, decision: "approved" | "rejected", reason = ""): Promise<SourceDocument> {
  return parseResponse(await fetchApi(`${API_BASE}/api/v1/source-documents/${id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, reviewer: "local-demo-approver", reason }) }));
}

// Playbook definition APIs
export async function listPlaybooks(status?: string): Promise<PlaybookList> {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  return parseResponse(await fetchApi(`${API_BASE}/api/v1/playbooks?${params.toString()}`));
}

export async function createPlaybook(playbook: Omit<Playbook, "id" | "created_at" | "updated_at">): Promise<Playbook> {
  return parseResponse(await fetchApi(`${API_BASE}/api/v1/playbooks`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(playbook) }));
}

export async function updatePlaybook(key: string, updates: Partial<Omit<Playbook, "id" | "key" | "version" | "created_at" | "updated_at">>): Promise<Playbook> {
  return parseResponse(await fetchApi(`${API_BASE}/api/v1/playbooks/${key}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updates) }));
}

export async function publishPlaybook(key: string): Promise<Playbook> {
  return parseResponse(await fetchApi(`${API_BASE}/api/v1/playbooks/${key}/publish`, { method: "POST" }));
}

// Generic draft API
export async function createGenericDraft(playbookKey: string, playbookVersion: string, answers: Record<string, string | number | boolean>): Promise<GenericDraft> {
  return parseResponse(await fetchApi(`${API_BASE}/api/v1/playbooks/draft`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ playbook_key: playbookKey, playbook_version: playbookVersion, answers }) }));
}

// Legacy vendor-onboarding APIs (kept for compatibility)
export async function listVendorCases(): Promise<VendorCaseList> { return parseResponse(await fetchApi(`${API_BASE}/api/v1/playbooks/vendor-onboarding/cases?limit=50`)); }
export async function getVendorCase(caseId: string): Promise<VendorOnboardingDraft> { return parseResponse(await fetchApi(`${API_BASE}/api/v1/playbooks/vendor-onboarding/cases/${caseId}`)); }
export async function createVendorDraft(intake: VendorOnboardingRequest): Promise<VendorOnboardingDraft> {
  return parseResponse(await fetchApi(`${API_BASE}/api/v1/playbooks/vendor-onboarding/draft`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(intake) }));
}
export async function reviewVendorDraft(caseId: string, decision: "approved" | "changes_requested" | "rejected", reason = ""): Promise<{ case_id: string; draft_id: string; case_status: string; draft_status: string; decision: string; reviewer: string; reason: string | null }> {
  return parseResponse(await fetchApi(`${API_BASE}/api/v1/playbooks/vendor-onboarding/cases/${caseId}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, reviewer: "local-demo-approver", reason }) }));
}
export async function resubmitVendorDraft(caseId: string, intake: VendorOnboardingRequest, revisionNote: string): Promise<VendorOnboardingDraft> {
  return parseResponse(await fetchApi(`${API_BASE}/api/v1/playbooks/vendor-onboarding/cases/${caseId}/revisions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ intake, revision_note: revisionNote }) }));
}
