import { Copy } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";

export interface TerminalProps {
  lines: string[];
}

function highlight(line: string): ReactNode {
  const cmd = /(\[[^\]]+\]\s*)(\[soc\]|event=|topic=)(.*)/.exec(line);
  if (!cmd) return <span className="text-emerald-300/90">{line}</span>;
  return (
    <span>
      <span className="text-slate-500">{cmd[1]}</span>
      <span className="text-amber-300">{cmd[2]}</span>
      <span className="text-emerald-200">{cmd[3]}</span>
    </span>
  );
}

export function Terminal({ lines }: TerminalProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  const copyAll = async () => {
    await navigator.clipboard.writeText(lines.join("\n"));
  };

  return (
    <Card className="border-emerald-500/20 bg-black/60">
      <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-emerald-500/20 pb-3">
        <CardTitle className="font-mono text-sm text-emerald-300">livebus // ttySOC</CardTitle>
        <Button size="sm" variant="secondary" className="gap-2 font-mono text-xs" onClick={() => void copyAll()}>
          <Copy className="h-3.5 w-3.5" />
          copy
        </Button>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-64 rounded-b-lg">
          <div className="space-y-1 px-4 py-3 font-mono text-xs leading-relaxed text-emerald-200">
            {lines.map((line, idx) => (
              <div key={`${idx}-${line.slice(0, 24)}`}>{highlight(line)}</div>
            ))}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
