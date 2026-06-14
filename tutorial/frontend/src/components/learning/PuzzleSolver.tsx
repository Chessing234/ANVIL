import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export interface PuzzleSolverProps {
  prompt: string;
  answer: string;
  caseSensitive: boolean;
  successMessage: string;
  onSolved: () => void;
}

export function PuzzleSolver({ prompt, answer, caseSensitive, successMessage, onSolved }: PuzzleSolverProps) {
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<"idle" | "ok" | "bad">("idle");

  const submit = () => {
    const a = caseSensitive ? answer.trim() : answer.trim().toLowerCase();
    const b = caseSensitive ? value.trim() : value.trim().toLowerCase();
    if (a === b) {
      setStatus("ok");
      onSolved();
    } else {
      setStatus("bad");
    }
  };

  return (
    <Card className="border-indigo-800/60 bg-indigo-950/60">
      <CardHeader>
        <CardTitle className="text-lg text-indigo-50">Hands-on puzzle</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-base text-indigo-100/90">{prompt}</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              setStatus("idle");
            }}
            placeholder="Your answer"
            className="border-indigo-800 bg-indigo-950 text-indigo-50"
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
          <Button type="button" className="bg-indigo-600 hover:bg-indigo-500" onClick={submit} disabled={status === "ok"}>
            Submit
          </Button>
        </div>
        {status === "ok" ? <p className="text-sm text-emerald-300">{successMessage}</p> : null}
        {status === "bad" ? <p className="text-sm text-rose-300">Not quite—re-read the narrative hints.</p> : null}
      </CardContent>
    </Card>
  );
}
