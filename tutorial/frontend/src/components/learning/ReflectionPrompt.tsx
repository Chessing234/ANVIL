import { useMemo, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface ReflectionPromptProps {
  prompt: string;
  guidance: string;
  minChars: number;
  onChangeValid: (ok: boolean, text: string) => void;
}

export function ReflectionPrompt({ prompt, guidance, minChars, onChangeValid }: ReflectionPromptProps) {
  const [text, setText] = useState("");

  const ok = useMemo(() => text.trim().length >= minChars, [minChars, text]);

  const update = (v: string) => {
    setText(v);
    onChangeValid(v.trim().length >= minChars, v);
  };

  return (
    <Card className="border-indigo-800/60 bg-indigo-950/60">
      <CardHeader>
        <CardTitle className="text-lg text-indigo-50">Reflection</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-base text-indigo-100/90">{prompt}</p>
        <p className="text-sm text-indigo-200/80">{guidance}</p>
        <div className="min-h-[9rem] rounded-md border border-indigo-800/70 bg-indigo-950/80">
          <textarea
            className="h-full min-h-[9rem] w-full resize-y bg-transparent p-3 text-sm text-indigo-50 outline-none"
            value={text}
            onChange={(e) => update(e.target.value)}
            placeholder="Type your response…"
            spellCheck
          />
        </div>
        <div className="flex items-center justify-between text-xs text-indigo-200/80">
          <span>{text.trim().length} / {minChars} characters minimum</span>
          <span className={ok ? "text-emerald-300" : "text-amber-300"}>{ok ? "Ready to continue" : "Keep writing"}</span>
        </div>
      </CardContent>
    </Card>
  );
}
