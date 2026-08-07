"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui";

interface Msg {
  role: "user" | "assistant";
  content: string;
  citations?: string[];
}

const SUGGESTIONS = [
  "Does reverse charge apply to imported SaaS subscriptions?",
  "Which VAT rate applies to exported goods, and what evidence do I need?",
  "Can I recover input VAT on staff entertainment?",
  "What are the mandatory fields of a full tax invoice?",
];

export default function AssistantPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    const next: Msg[] = [...messages, { role: "user", content: q }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const res = await api.chat(next);
      setMessages([...next, { role: "assistant", content: res.reply, citations: res.citations }]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages([...next, { role: "assistant", content: `⚠️ ${msg}` }]);
    } finally {
      setBusy(false);
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-semibold">VAT Assistant</h1>
        <p className="text-sm text-muted">
          Ask UAE VAT questions. Answers cite the applicable legislation.
        </p>
      </div>

      <Card className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-muted">Try one of these:</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-elevated"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] ${m.role === "user" ? "" : "w-full"}`}>
                <div
                  className={`whitespace-pre-line rounded-xl px-4 py-2.5 text-sm ${
                    m.role === "user" ? "bg-brand text-brand-fg" : "bg-elevated"
                  }`}
                >
                  {m.content}
                </div>
                {m.citations && m.citations.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {m.citations.map((c, j) => (
                      <span
                        key={j}
                        className="rounded-md border border-border bg-surface px-2 py-0.5 text-xs text-brand"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {busy && <div className="text-sm text-muted">Thinking…</div>}
          <div ref={endRef} />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex gap-2 border-t border-border p-3"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a UAE VAT question…"
            className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-fg disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </Card>
      <p className="mt-2 text-xs text-muted">
        Requires an AI provider key. Without one, the assistant explains how to enable it. RAG
        grounding over FTA sources is the next backend slice.
      </p>
    </div>
  );
}
