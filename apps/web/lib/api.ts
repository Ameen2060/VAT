// Typed client for the VAT Compliance API.

import { clearSession, getToken, setSession, type AuthUser } from "./auth";
import type {
  AiStatus,
  ArchiveEntry,
  ChatResponse,
  DashboardSummary,
  ExtractedInvoice,
  FtaDashboard,
  FtaRule,
  FtaSource,
  FtaUpdate,
  FtaUpdateInput,
  KnowledgeDoc,
  ReviewDetail,
  ReviewStatus,
  ReviewSummary,
  SearchHit,
  VatCode,
} from "./types";

// Default to same-origin relative URLs ("") — Next proxies /api to the backend
// (see next.config.mjs rewrites → BACKEND_ORIGIN). A non-empty value overrides it.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Append the session token to URLs used in <iframe>/<a> where headers can't be set.
function withToken(url: string): string {
  const token = getToken();
  if (!token) return url;
  return url + (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(token);
}

// The server is unreachable when the gateway can't reach the backend (502/503/504).
const SERVER_DOWN_MSG =
  "The server is temporarily unavailable — it may be starting up or reconnecting. Please retry in a moment.";

export function isServerDown(status: number): boolean {
  return status === 502 || status === 503 || status === 504;
}

async function json<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    clearSession();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Session expired — please sign in again.");
  }
  if (isServerDown(res.status)) {
    throw new Error(SERVER_DOWN_MSG);
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// Fetch with the auth header attached. Network failures become a friendly message.
async function afetch(url: string, opts: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(url, { ...opts, headers: { ...authHeaders(), ...(opts.headers || {}) } });
  } catch {
    throw new Error(SERVER_DOWN_MSG);
  }
}

export const api = {
  // ── Auth ───────────────────────────────────────────────────────────────────
  async login(email: string, password: string): Promise<{ token: string; user: AuthUser }> {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
    } catch {
      throw new Error(SERVER_DOWN_MSG);
    }
    if (isServerDown(res.status)) throw new Error(SERVER_DOWN_MSG);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Incorrect email or password");
    }
    const data = await res.json();
    setSession(data.access_token, data.user);
    return { token: data.access_token, user: data.user };
  },

  async me(): Promise<AuthUser> {
    return json(await afetch(`${API_BASE}/api/auth/me`, { cache: "no-store" }));
  },

  // ── Password reset / recovery ──────────────────────────────────────────────
  async forgotPassword(email: string): Promise<{ message: string; reset_url: string | null }> {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
    } catch {
      throw new Error(SERVER_DOWN_MSG);
    }
    if (isServerDown(res.status)) throw new Error(SERVER_DOWN_MSG);
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new Error(b.detail || "Request failed. Please try again.");
    }
    return res.json();
  },

  async resetPassword(token: string, newPassword: string): Promise<AuthUser> {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/api/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
    } catch {
      throw new Error(SERVER_DOWN_MSG);
    }
    if (isServerDown(res.status)) throw new Error(SERVER_DOWN_MSG);
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new Error(b.detail || "Reset failed.");
    }
    const data = await res.json();
    setSession(data.access_token, data.user); // sign in with the new password
    return data.user;
  },

  async listUsers(): Promise<AuthUser[]> {
    return json(await afetch(`${API_BASE}/api/auth/users`, { cache: "no-store" }));
  },

  // ── VAT tax-code master (configurable) ───────────────────────────────────
  async listVatCodes(): Promise<VatCode[]> {
    return json(await afetch(`${API_BASE}/api/vat-codes`, { cache: "no-store" }));
  },

  async updateVatCode(code: string, patch: Partial<VatCode>): Promise<VatCode> {
    return json(
      await afetch(`${API_BASE}/api/vat-codes/${encodeURIComponent(code)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }),
    );
  },

  async adminResetPassword(userId: string): Promise<{ user_email: string; reset_url: string; expires_minutes: number }> {
    return json(await afetch(`${API_BASE}/api/auth/users/${userId}/reset-password`, { method: "POST" }));
  },

  async authAudit(): Promise<
    { id: string; event: string; user_email: string | null; actor_email: string | null; detail: string | null; created_at: string | null }[]
  > {
    return json(await afetch(`${API_BASE}/api/auth/audit`, { cache: "no-store" }));
  },

  // Change the signed-in user's own login details. Requires the current password.
  async updateAccount(body: {
    current_password: string;
    new_email?: string;
    new_password?: string;
    full_name?: string;
  }): Promise<AuthUser> {
    const data = await json<{ access_token: string; user: AuthUser }>(
      await afetch(`${API_BASE}/api/auth/account`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
    setSession(data.access_token, data.user); // refresh token + stored identity
    return data.user;
  },

  // ── Reviews / documents ────────────────────────────────────────────────────
  async dashboard(): Promise<DashboardSummary> {
    return json(await afetch(`${API_BASE}/api/dashboard`, { cache: "no-store" }));
  },

  async listReviews(params: { risk?: string; status?: string } = {}): Promise<ReviewSummary[]> {
    const q = new URLSearchParams();
    if (params.risk) q.set("risk", params.risk);
    if (params.status) q.set("status", params.status);
    const qs = q.toString() ? `?${q}` : "";
    return json(await afetch(`${API_BASE}/api/reviews${qs}`, { cache: "no-store" }));
  },

  async getReview(id: string): Promise<ReviewDetail> {
    return json(await afetch(`${API_BASE}/api/reviews/${id}`, { cache: "no-store" }));
  },

  async upload(file: File, category = "invoice", folderPath?: string): Promise<ReviewSummary[]> {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("category", category);
    if (folderPath) fd.append("folder_path", folderPath);
    return json(await afetch(`${API_BASE}/api/documents/upload`, { method: "POST", body: fd }));
  },

  async setStatus(id: string, status: ReviewStatus, notes?: string) {
    return json(
      await afetch(`${API_BASE}/api/reviews/${id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, reviewer_notes: notes }),
      }),
    );
  },

  async deleteReview(id: string) {
    return json(await afetch(`${API_BASE}/api/reviews/${id}`, { method: "DELETE" }));
  },

  // Tokenized download URL for the repository export (respects the active filters).
  reviewsExportUrl(
    format: "csv" | "xlsx",
    filters: { risk?: string; status?: string; compliance?: string; q?: string } = {},
  ) {
    const p = new URLSearchParams({ format });
    if (filters.risk) p.set("risk", filters.risk);
    if (filters.status) p.set("status", filters.status);
    if (filters.compliance) p.set("compliance", filters.compliance);
    if (filters.q) p.set("q", filters.q);
    return withToken(`${API_BASE}/api/reviews/export?${p}`);
  },

  async markRead(id: string, read = true) {
    return json(
      await afetch(`${API_BASE}/api/reviews/${id}/read`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ read }),
      }),
    );
  },

  reportUrl(id: string, format: "pdf" | "html" = "pdf") {
    return withToken(`${API_BASE}/api/reviews/${id}/report?format=${format}`);
  },

  // Combined, stored, per-document review report.
  reviewReportUrl(id: string, download = true) {
    return withToken(`${API_BASE}/api/reviews/${id}/report/file?download=${download ? 1 : 0}`);
  },

  async generateReport(id: string): Promise<{
    id: string;
    has_report: boolean;
    report_url: string;
    report_generated_at: string | null;
  }> {
    return json(await afetch(`${API_BASE}/api/reviews/${id}/report/generate`, { method: "POST" }));
  },

  fileUrl(documentId: string) {
    return withToken(`${API_BASE}/api/documents/${documentId}/file`);
  },

  // Rendered PNG of one page, for source-evidence bbox overlays.
  pageUrl(documentId: string, page: number) {
    return withToken(`${API_BASE}/api/documents/${documentId}/page/${page}`);
  },

  async updateInvoice(reviewId: string, invoice: Partial<ExtractedInvoice>) {
    return json(
      await afetch(`${API_BASE}/api/reviews/${reviewId}/invoice`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invoice }),
      }),
    );
  },

  async chat(
    messages: { role: string; content: string }[],
    doc?: { name: string; text: string } | null,
    asOfDate?: string | null,
  ): Promise<ChatResponse> {
    return json(
      await afetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages,
          document_name: doc?.name ?? null,
          document_text: doc?.text ?? null,
          as_of_date: asOfDate || null,
        }),
      }),
    );
  },

  // Attach a document to the assistant (PDF / Word / image) → extracted text.
  async uploadAssistantDoc(file: File): Promise<{
    filename: string;
    text: string;
    chars: number;
    ocr_used: boolean;
    truncated: boolean;
    warnings: string[];
  }> {
    const fd = new FormData();
    fd.append("file", file);
    return json(await afetch(`${API_BASE}/api/assistant/upload`, { method: "POST", body: fd }));
  },

  async seedKnowledge(): Promise<{ added: number; total_documents: number }> {
    return json(await afetch(`${API_BASE}/api/knowledge/seed`, { method: "POST" }));
  },

  async listKnowledge(): Promise<KnowledgeDoc[]> {
    return json(await afetch(`${API_BASE}/api/knowledge/documents`, { cache: "no-store" }));
  },

  async searchKnowledge(q: string): Promise<SearchHit[]> {
    return json(
      await afetch(`${API_BASE}/api/knowledge/search?q=${encodeURIComponent(q)}`, {
        cache: "no-store",
      }),
    );
  },

  async aiStatus(): Promise<AiStatus> {
    return json(await afetch(`${API_BASE}/api/ai/status`, { cache: "no-store" }));
  },

  // ── Archive ────────────────────────────────────────────────────────────────
  async listArchive(params: { q?: string; source?: string; deleted?: boolean } = {}): Promise<ArchiveEntry[]> {
    const p = new URLSearchParams();
    if (params.q) p.set("q", params.q);
    if (params.source) p.set("source", params.source);
    if (params.deleted) p.set("deleted", "true");
    const qs = p.toString() ? `?${p}` : "";
    return json(await afetch(`${API_BASE}/api/archive${qs}`, { cache: "no-store" }));
  },

  archiveFileUrl(id: string, download = false) {
    return withToken(`${API_BASE}/api/archive/${id}/file?download=${download ? 1 : 0}`);
  },

  // Soft delete by default; pass permanent to hard-delete immediately (admin only).
  async deleteArchive(id: string, permanent = false): Promise<{ deleted: string }> {
    const qs = permanent ? "?permanent=true" : "";
    return json(await afetch(`${API_BASE}/api/archive/${id}${qs}`, { method: "DELETE" }));
  },

  async restoreArchive(id: string): Promise<ArchiveEntry> {
    return json(await afetch(`${API_BASE}/api/archive/${id}/restore`, { method: "POST" }));
  },

  // ── FTA VAT Regulatory Updates ─────────────────────────────────────────────
  async ftaDashboard(): Promise<FtaDashboard> {
    return json(await afetch(`${API_BASE}/api/fta/dashboard`, { cache: "no-store" }));
  },
  async seedFta(): Promise<{ sources_added: number; rules_added: number }> {
    return json(await afetch(`${API_BASE}/api/fta/seed`, { method: "POST" }));
  },
  async listFtaUpdates(params: { status?: string; critical?: boolean } = {}): Promise<FtaUpdate[]> {
    const p = new URLSearchParams();
    if (params.status) p.set("status", params.status);
    if (params.critical) p.set("critical", "true");
    const qs = p.toString() ? `?${p}` : "";
    return json(await afetch(`${API_BASE}/api/fta/updates${qs}`, { cache: "no-store" }));
  },
  async createFtaUpdate(body: FtaUpdateInput): Promise<FtaUpdate> {
    return json(
      await afetch(`${API_BASE}/api/fta/updates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
  },
  async transitionFtaUpdate(id: string, status: string): Promise<FtaUpdate> {
    return json(
      await afetch(`${API_BASE}/api/fta/updates/${id}/transition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      }),
    );
  },
  async deleteFtaUpdate(id: string): Promise<{ deleted: string }> {
    return json(await afetch(`${API_BASE}/api/fta/updates/${id}`, { method: "DELETE" }));
  },
  async listFtaSources(): Promise<FtaSource[]> {
    return json(await afetch(`${API_BASE}/api/fta/sources`, { cache: "no-store" }));
  },
  async checkFtaSources(): Promise<{ checked: number; changed: number; errors: number }> {
    return json(await afetch(`${API_BASE}/api/fta/sources/check`, { method: "POST" }));
  },
  async listFtaRules(): Promise<FtaRule[]> {
    return json(await afetch(`${API_BASE}/api/fta/rules`, { cache: "no-store" }));
  },

  // Bulk archive action (admin): delete (soft) | restore | permanent.
  async bulkArchive(
    ids: string[],
    action: "delete" | "restore" | "permanent",
  ): Promise<{ processed: number; action: string }> {
    return json(
      await afetch(`${API_BASE}/api/archive/bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids, action }),
      }),
    );
  },

  // Build a tokenized, absolute URL from an API path returned by the backend
  // (e.g. a related report_url), for use in <a>/<iframe>.
  apiUrl(path: string) {
    return withToken(`${API_BASE}${path}`);
  },

  async verifyAi(): Promise<{ ok: boolean; provider: string; error: string | null }> {
    return json(await afetch(`${API_BASE}/api/ai/verify`, { method: "POST" }));
  },

  async reanalyze(reviewId: string): Promise<{ id: string; advisory: unknown }> {
    return json(
      await afetch(`${API_BASE}/api/ai/reviews/${reviewId}/reanalyze`, { method: "POST" }),
    );
  },

  // ── VAT201 return ──────────────────────────────────────────────────────────
  async generateVat201(
    file: File,
    opts: {
      company_name?: string;
      company_trn?: string;
      period_type: string;
      year: number;
      index: number;
      filter_by_date?: boolean;
      default_emirate?: string;
    },
  ): Promise<{ id: string; return: import("./types").Vat201Return }> {
    const fd = new FormData();
    fd.append("file", file);
    if (opts.company_name) fd.append("company_name", opts.company_name);
    if (opts.company_trn) fd.append("company_trn", opts.company_trn);
    fd.append("period_type", opts.period_type);
    fd.append("year", String(opts.year));
    fd.append("index", String(opts.index));
    fd.append("filter_by_date", String(opts.filter_by_date ?? true));
    if (opts.default_emirate) fd.append("default_emirate", opts.default_emirate);
    return json(await afetch(`${API_BASE}/api/vat201/generate`, { method: "POST", body: fd }));
  },

  async listVat201Returns(): Promise<import("./types").Vat201ReturnSummary[]> {
    return json(await afetch(`${API_BASE}/api/vat201/returns`, { cache: "no-store" }));
  },

  async getVat201Return(id: string): Promise<{ id: string; status: string; return: import("./types").Vat201Return }> {
    return json(await afetch(`${API_BASE}/api/vat201/returns/${id}`, { cache: "no-store" }));
  },

  async vat201DrillDown(id: string, box: string): Promise<import("./types").Vat201Txn[]> {
    return json(
      await afetch(`${API_BASE}/api/vat201/returns/${id}/transactions?box=${encodeURIComponent(box)}`, {
        cache: "no-store",
      }),
    );
  },

  vat201ExportUrl(id: string, format: "csv" | "xlsx" | "pdf") {
    return withToken(`${API_BASE}/api/vat201/returns/${id}/export?format=${format}`);
  },

  // FTA Audit File (FAF) — official VAT-audit workbook derived from the return.
  vat201FafUrl(id: string) {
    return withToken(`${API_BASE}/api/vat201/returns/${id}/faf`);
  },

  async prepareRefund311(
    id: string,
    body: {
      amount_requested?: number;
      late_registration_penalty?: number;
      legal_name?: string;
      authorized_signatory?: string;
    },
  ): Promise<import("./types").Vat311Application> {
    return json(
      await afetch(`${API_BASE}/api/vat201/returns/${id}/refund311`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
  },

  refund311ExportUrl(id: string) {
    return withToken(`${API_BASE}/api/vat201/returns/${id}/refund311/export`);
  },
};
