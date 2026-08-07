// Typed client for the VAT Compliance API.

import { clearSession, getToken, setSession, type AuthUser } from "./auth";
import type {
  AiStatus,
  ChatResponse,
  DashboardSummary,
  ExtractedInvoice,
  KnowledgeDoc,
  ReviewDetail,
  ReviewStatus,
  ReviewSummary,
  SearchHit,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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

async function json<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    clearSession();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Session expired — please sign in again.");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// Fetch with the auth header attached.
function afetch(url: string, opts: RequestInit = {}): Promise<Response> {
  return fetch(url, { ...opts, headers: { ...authHeaders(), ...(opts.headers || {}) } });
}

export const api = {
  // ── Auth ───────────────────────────────────────────────────────────────────
  async login(email: string, password: string): Promise<{ token: string; user: AuthUser }> {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
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

  async upload(file: File, category = "invoice"): Promise<ReviewSummary[]> {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("category", category);
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

  async updateInvoice(reviewId: string, invoice: Partial<ExtractedInvoice>) {
    return json(
      await afetch(`${API_BASE}/api/reviews/${reviewId}/invoice`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invoice }),
      }),
    );
  },

  async chat(messages: { role: string; content: string }[]): Promise<ChatResponse> {
    return json(
      await afetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages }),
      }),
    );
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
