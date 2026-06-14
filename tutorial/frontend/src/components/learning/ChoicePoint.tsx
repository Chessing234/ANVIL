import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface ChoicePointProps {
  question: string;
  options: { id: string; label: string; correct: boolean }[];
  successMessage: string;
  failureMessage: string;
  onResolved: (correct: boolean) => void;
}

export function ChoicePoint({ question, options, successMessage, failureMessage, onResolved }: ChoicePointProps) {
  const [picked, setPicked] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "correct" | "wrong">("idle");

  const pick = (id: string) => {
    if (status === "correct") return;
    setPicked(id);
    const opt = options.find((o) => o.id === id);
    if (!opt) return;
    if (opt.correct) {
      setStatus("correct");
      onResolved(true);
    } else {
      setStatus("wrong");
    }
  };

  const selected = picked ? options.find((o) => o.id === picked) : null;

  return (
    <Card className="border-indigo-800/60 bg-indigo-950/60">
      <CardHeader>
        <CardTitle className="text-lg text-indigo-50">Decision point</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-base text-indigo-100/90">{question}</p>
        <div className="grid gap-2 sm:grid-cols-1">
          {options.map((o) => {
            const active = picked === o.id;
            const show = active && status !== "idle";
            const tone =
              show && o.correct
                ? "border-emerald-500/60 bg-emerald-500/10"
                : show && !o.correct
                  ? "border-rose-500/60 bg-rose-500/10"
                  : "border-indigo-800/60 bg-indigo-900/40";
            return (
              <Button
                key={o.id}
                type="button"
                variant="outline"
                disabled={status === "correct"}
                className={`h-auto justify-start whitespace-normal py-3 text-left text-indigo-50 ${tone}`}
                onClick={() => pick(o.id)}
              >
                {o.label}
              </Button>
            );
          })}
        </div>
        {status === "correct" ? <p className="text-sm text-emerald-300">{successMessage}</p> : null}
        {status === "wrong" && selected ? (
          <div className="space-y-2">
            <p className="text-sm text-rose-300">{failureMessage}</p>
            <Button type="button" size="sm" variant="secondary" onClick={() => { setPicked(null); setStatus("idle"); }}>
              Try again
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
