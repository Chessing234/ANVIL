import { BookOpen } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";

export interface NarrativeReaderProps {
  title: string;
  paragraphs: string[];
  dialogues: { speaker: string; text: string }[];
  glossary: Record<string, string>;
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function renderParagraph(text: string, glossary: Record<string, string>, onTerm: (term: string) => void): ReactNode {
  const keys = Object.keys(glossary).sort((a, b) => b.length - a.length);
  if (keys.length === 0) return text;
  const pattern = new RegExp(`(${keys.map(escapeRegExp).join("|")})`, "gi");
  const parts = text.split(pattern);
  return parts.map((part, i) => {
    const key = keys.find((k) => k.toLowerCase() === part.toLowerCase());
    if (key) {
      return (
        <button
          key={i}
          type="button"
          className="mx-0.5 rounded bg-indigo-500/25 px-1 font-semibold text-fuchsia-200 underline decoration-dotted underline-offset-2 transition hover:bg-indigo-500/40"
          onClick={() => onTerm(key)}
        >
          {part}
        </button>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export function NarrativeReader({ title, paragraphs, dialogues, glossary }: NarrativeReaderProps) {
  const [term, setTerm] = useState<string | null>(null);

  const definition = useMemo(() => (term ? glossary[term] : null), [glossary, term]);

  return (
    <Card className="h-full border-indigo-800/60 bg-gradient-to-b from-indigo-950/80 to-slate-950/90">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg text-indigo-50">
          <BookOpen className="h-5 w-5 text-fuchsia-300" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ScrollArea className="h-[min(52vh,520px)] pr-3">
          <div className="space-y-4 text-base leading-relaxed text-indigo-50/95">
            {paragraphs.map((p, idx) => (
              <p key={idx}>{renderParagraph(p, glossary, setTerm)}</p>
            ))}
          </div>
          <div className="mt-6 space-y-3">
            {dialogues.map((d, idx) => (
              <div
                key={idx}
                className={cn(
                  "max-w-[95%] rounded-2xl border px-4 py-3 text-sm shadow-sm",
                  idx % 2 === 0
                    ? "ml-0 border-indigo-700/50 bg-indigo-900/50 text-indigo-50"
                    : "ml-auto border-fuchsia-700/40 bg-fuchsia-950/40 text-fuchsia-50",
                )}
              >
                <div className="text-[11px] font-semibold uppercase tracking-wide text-indigo-200/80">{d.speaker}</div>
                <div className="mt-1">{renderParagraph(d.text, glossary, setTerm)}</div>
              </div>
            ))}
          </div>
        </ScrollArea>
        {term && definition ? (
          <div className="rounded-xl border border-fuchsia-500/40 bg-fuchsia-950/50 p-3 text-sm text-fuchsia-50 shadow-[0_0_0_1px_rgba(217,70,239,0.15)] animate-in fade-in zoom-in-95 duration-200">
            <div className="text-xs font-semibold uppercase text-fuchsia-200/80">{term}</div>
            <p className="mt-1 text-fuchsia-50/95">{definition}</p>
            <button type="button" className="mt-2 text-xs text-indigo-200 underline" onClick={() => setTerm(null)}>
              Dismiss
            </button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
