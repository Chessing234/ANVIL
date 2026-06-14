import { memo, useCallback, useMemo, useState, type WheelEvent } from "react";

import { buildSkillGraph } from "@/lib/skillGraph";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LessonCategory, SkillMastery, SkillNodeDef } from "@/types/education";

const CATEGORY_COLOR: Record<LessonCategory, string> = {
  Network: "#38bdf8",
  Forensics: "#a78bfa",
  Malware: "#fb7185",
  Crypto: "#34d399",
};

const MASTERY_RING: Record<SkillMastery, string> = {
  locked: "#475569",
  available: "#6366f1",
  in_progress: "#fbbf24",
  mastered: "#34d399",
};

const NodeShape = memo(function NodeShape({
  n,
  onPick,
}: {
  n: SkillNodeDef;
  onPick: (id: string) => void;
}) {
  const stroke = MASTERY_RING[n.mastery];
  const fill = CATEGORY_COLOR[n.category];
  return (
    <g className="cursor-pointer" onClick={() => onPick(n.id)} style={{ transition: "opacity 150ms ease" }}>
      <circle cx={n.x} cy={n.y} r={14} fill="#0f172a" stroke={stroke} strokeWidth={2} className="hover:opacity-90" />
      <circle cx={n.x} cy={n.y} r={6} fill={fill} opacity={n.mastery === "locked" ? 0.35 : 1} />
    </g>
  );
});

export function SkillTree() {
  const { nodes, edges } = useMemo(() => buildSkillGraph(), []);
  const gridPatternId = useMemo(() => `skill-grid-${Math.random().toString(36).slice(2, 9)}`, []);
  const [selected, setSelected] = useState<string | null>(null);
  const [tx, setTx] = useState(40);
  const [ty, setTy] = useState(20);
  const [scale, setScale] = useState(0.72);

  const sel = useMemo(() => nodes.find((n) => n.id === selected) ?? null, [nodes, selected]);

  const onWheel = useCallback((e: WheelEvent<SVGSVGElement>) => {
    if (e.ctrlKey) {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.04 : 0.04;
      setScale((s) => Math.min(1.35, Math.max(0.45, s + delta)));
    } else {
      e.preventDefault();
      setTx((x) => x - e.deltaX * 0.45);
      setTy((y) => y - e.deltaY * 0.45);
    }
  }, []);

  return (
    <Card className="border-indigo-800/60 bg-indigo-950/40">
      <CardHeader>
        <CardTitle className="text-lg text-indigo-50">Knowledge graph</CardTitle>
        <p className="text-xs text-indigo-200/80">
          {nodes.length} concepts · scroll wheel pans · ctrl+wheel zooms · nodes memoized for 100+ graph performance.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="relative overflow-hidden rounded-xl border border-indigo-800/60 bg-slate-950">
          <svg
            className="h-[420px] w-full touch-none select-none"
            role="img"
            aria-label="Skill tree"
            onWheel={onWheel}
          >
            <defs>
              <pattern id={gridPatternId} width="24" height="24" patternUnits="userSpaceOnUse">
                <path d="M 24 0 L 0 0 0 24" fill="none" stroke="#1e293b" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill={`url(#${gridPatternId})`} opacity={0.35} />
            <g transform={`translate(${tx},${ty}) scale(${scale})`} style={{ willChange: "transform" }}>
              {edges.map((e) => {
                const a = nodes.find((n) => n.id === e.from);
                const b = nodes.find((n) => n.id === e.to);
                if (!a || !b) return null;
                return (
                  <line
                    key={`${e.from}-${e.to}`}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke="#334155"
                    strokeWidth={1.2}
                    opacity={0.55}
                  />
                );
              })}
              {nodes.map((n) => (
                <NodeShape key={n.id} n={n} onPick={setSelected} />
              ))}
            </g>
          </svg>
        </div>
        <div
          className={cn(
            "rounded-lg border border-indigo-800/60 bg-slate-950/80 p-3 text-sm text-indigo-100/90",
            !sel && "text-indigo-300/70",
          )}
        >
          {sel ? (
            <>
              <div className="font-semibold text-indigo-50">{sel.label}</div>
              <div className="mt-1 text-xs text-indigo-200/80">
                Category <span className="text-fuchsia-200">{sel.category}</span> · mastery{" "}
                <span className="text-emerald-200">{sel.mastery}</span>
              </div>
              <p className="mt-2 text-xs text-indigo-200/80">
                Prerequisite edges visualize unlock order—stack lessons to climb from Script Kiddie toward CISO badges.
              </p>
            </>
          ) : (
            <span>Tap a node to inspect relationships.</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
