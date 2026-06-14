import { Lightbulb } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface HintSystemProps {
  hints: [string, string, string] | undefined;
  blockLabel?: string;
}

export function HintSystem({ hints, blockLabel }: HintSystemProps) {
  const [level, setLevel] = useState(0);

  const visible = useMemo(() => {
    if (!hints) return [] as string[];
    return hints.slice(0, level);
  }, [hints, level]);

  const revealNext = useCallback(() => {
    if (!hints) return;
    setLevel((l) => Math.min(3, l + 1));
  }, [hints]);

  const reset = useCallback(() => setLevel(0), []);

  if (!hints) {
    return (
      <Card className="border-indigo-800/60 bg-indigo-950/40">
        <CardHeader className="py-3">
          <CardTitle className="flex items-center gap-2 text-sm text-indigo-100">
            <Lightbulb className="h-4 w-4 text-amber-300" />
            Hints
          </CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-indigo-200/70">No hints for this beat—trust your instincts.</CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-indigo-800/60 bg-indigo-950/40">
      <CardHeader className="flex flex-row items-center justify-between py-3">
        <CardTitle className="flex items-center gap-2 text-sm text-indigo-100">
          <Lightbulb className="h-4 w-4 text-amber-300" />
          Hints {blockLabel ? `· ${blockLabel}` : ""}
        </CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={reset} disabled={level === 0}>
            Reset
          </Button>
          <Button size="sm" variant="default" className="bg-indigo-600 hover:bg-indigo-500" onClick={revealNext} disabled={level >= 3}>
            {level >= 3 ? "Max hints" : `Level ${level + 1}`}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-indigo-50/90">
        {visible.length === 0 ? <p className="text-indigo-200/70">Tap “Level 1” for a nudge—three progressive reveals.</p> : null}
        {visible.map((h, i) => (
          <p key={i} className="rounded-md border border-indigo-800/50 bg-indigo-900/40 p-2">
            <span className="font-semibold text-amber-200">L{i + 1}: </span>
            {h}
          </p>
        ))}
      </CardContent>
    </Card>
  );
}
