"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { KnowledgeDoc, SearchHit } from "@/lib/types";
import { Card } from "@/components/ui";

export default function KnowledgePage() {
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  const refresh = () =>
    api.listKnowledge().then(setDocs).catch((e) => setError(String(e.message ?? e)));

  useEffect(() => {
    refresh();
  }, []);

  const seed = async () => {
    setSeeding(true);
    try {
      await api.seedKnowledge();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSeeding(false);
    }
  };

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    if (q.trim().length < 2) return;
    setSearching(true);
    try {
      setHits(await api.searchKnowledge(q));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="space-y-6 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Knowledge Base</h1>
          <p className="text-sm text-muted">
            Official FTA source material powering the assistant&apos;s citations (RAG).
          </p>
        </div>
        <button
          onClick={seed}
          disabled={seeding}
          className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg disabled:opacity-50"
        >
          {seeding ? "Seeding…" : "Load seed corpus"}
        </button>
      </div>

      {error && (
        <Card className="border-danger/40 bg-danger/5 p-4 text-sm text-danger">{error}</Card>
      )}

      <Card className="p-5">
        <form onSubmit={search} className="flex gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Semantic search across VAT provisions…"
            className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
          />
          <button
            type="submit"
            disabled={searching}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-elevated"
          >
            Search
          </button>
        </form>
        {hits && (
          <div className="mt-4 space-y-3">
            {hits.length === 0 && <p className="text-sm text-muted">No matches.</p>}
            {hits.map((h, i) => (
              <div key={i} className="rounded-lg border border-border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{h.title}</span>
                  <span className="text-xs text-muted">score {h.score.toFixed(3)}</span>
                </div>
                {h.source_ref && <div className="text-xs text-brand">{h.source_ref}</div>}
                <p className="mt-1 text-sm text-muted">{h.text}</p>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="font-semibold">Indexed documents ({docs.length})</h2>
        </div>
        {docs.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-muted">
            No documents indexed yet. Click <b>Load seed corpus</b> to index the key VAT provisions.
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {docs.map((d) => (
              <li key={d.id} className="flex items-center justify-between px-5 py-3">
                <div className="min-w-0">
                  <div className="truncate font-medium">{d.title}</div>
                  {d.source_ref && <div className="truncate text-xs text-brand">{d.source_ref}</div>}
                </div>
                <span className="shrink-0 rounded-full border border-border px-2 py-0.5 text-xs text-muted">
                  {d.chunk_count} chunk{d.chunk_count === 1 ? "" : "s"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <p className="text-xs text-muted">
        The seed corpus is concise, cited summaries authored for grounding — not verbatim law.
        Ingest official FTA PDFs via <code>POST /api/knowledge/ingest</code> for authoritative
        text. Retrieval uses an offline lexical embedder by default; add an OpenAI key for
        semantic embeddings.
      </p>
    </div>
  );
}
