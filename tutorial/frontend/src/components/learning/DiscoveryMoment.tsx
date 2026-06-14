import confetti from "canvas-confetti";
import { Sparkles } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface DiscoveryMomentProps {
  headline: string;
  teaser: string;
  reveal: string;
  onReveal?: () => void;
}

function burst(): void {
  void confetti({
    particleCount: 120,
    spread: 70,
    origin: { y: 0.35 },
    colors: ["#6366f1", "#a855f7", "#22c55e", "#fbbf24"],
    disableForReducedMotion: true,
  });
}

export function DiscoveryMoment({ headline, teaser, reveal, onReveal }: DiscoveryMomentProps) {
  const [open, setOpen] = useState(false);
  const fired = useRef(false);

  const handleReveal = useCallback(() => {
    setOpen(true);
    onReveal?.();
    if (!fired.current) {
      fired.current = true;
      requestAnimationFrame(() => burst());
    }
  }, [onReveal]);

  return (
    <Card className="relative overflow-hidden border-fuchsia-500/40 bg-gradient-to-br from-indigo-950 via-violet-950 to-slate-950 shadow-[0_0_40px_rgba(99,102,241,0.15)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(168,85,247,0.18),transparent_45%)]" />
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl text-indigo-50">
          <Sparkles className="h-6 w-6 text-amber-300" />
          {headline}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-lg text-indigo-100/90">{teaser}</p>
        {!open ? (
          <Button
            type="button"
            className="bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-6 text-white shadow-lg transition hover:brightness-110"
            onClick={handleReveal}
          >
            Reveal insight
          </Button>
        ) : (
          <div className="transition-opacity duration-500 opacity-100">
            <p className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-base text-emerald-50">{reveal}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
