"use client";

import { EyeOff, ShieldAlert } from "lucide-react";
import type { RedactionSummary } from "@/lib/types";

interface PiiDiffViewerProps {
  originalMessage?: string | null;
  redactedMessage: string;
  summary: RedactionSummary;
}

const TOKEN_REGEX = /(\[[A-Z_]+_\d+\])/g;

function renderHighlightedRedacted(text: string) {
  const parts = text.split(TOKEN_REGEX);
  return parts.map((part, idx) => {
    if (/^\[[A-Z_]+_\d+\]$/.test(part)) {
      return (
        <span
          key={`${part}-${idx}`}
          className="mx-0.5 inline-block rounded border border-cyan-400/50 bg-cyan-500/20 px-1.5 py-0.5 font-mono text-xs font-semibold text-cyan-200"
        >
          {part}
        </span>
      );
    }
    return <span key={idx}>{part}</span>;
  });
}

export function PiiDiffViewer({
  originalMessage,
  redactedMessage,
  summary,
}: PiiDiffViewerProps) {
  const entries = Object.entries(summary.entity_counts ?? {});

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <EyeOff className="h-4 w-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-slate-100">
            PDPA PII Redaction Diff (Pre-LLM &amp; Pre-DB Boundary)
          </h3>
        </div>
        <span className="rounded-full border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-0.5 font-mono text-xs text-cyan-300">
          {summary.total_redacted} {summary.total_redacted === 1 ? "entity" : "entities"} masked
        </span>
      </div>

      {entries.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {entries.map(([entityType, count]) => (
            <span
              key={entityType}
              className="rounded-md border border-slate-700 bg-slate-950 px-2 py-0.5 font-mono text-[11px] text-slate-300"
            >
              {entityType}: <strong className="text-cyan-300">{count}</strong>
            </span>
          ))}
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3">
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            <span>Inbound Input (Client Memory Only)</span>
            <span className="inline-flex items-center gap-1 text-amber-300">
              <ShieldAlert className="h-3 w-3" />
              Never Persisted
            </span>
          </div>
          <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-slate-300">
            {originalMessage ??
              "Original unredacted input is never stored in PostgreSQL. Only client-initiated runs keep a transient preview in browser memory."}
          </p>
        </div>

        <div className="rounded-lg border border-cyan-500/30 bg-slate-950/90 p-3">
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-cyan-300">
            <span>Redacted Payload (PostgreSQL + Gemini)</span>
            <span className="font-mono text-[10px] text-emerald-300">PDPA SAFE</span>
          </div>
          <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-slate-100">
            {renderHighlightedRedacted(redactedMessage)}
          </p>
        </div>
      </div>
    </div>
  );
}
