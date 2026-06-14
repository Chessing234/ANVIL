import { ChevronLeft, ChevronRight, Save } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { readLessonProgress, writeLessonProgress } from "@/lib/learnStorage";
import { Button } from "@/components/ui/button";
import type { LearnProgressPayload, LessonBlock, LessonDefinition, NarrativeBlock } from "@/types/education";

import { ChoicePoint } from "./ChoicePoint";
import { DiscoveryMoment } from "./DiscoveryMoment";
import { HintSystem } from "./HintSystem";
import { NarrativeReader } from "./NarrativeReader";
import { ProgressBar } from "./ProgressBar";
import { PuzzleSolver } from "./PuzzleSolver";
import { ReflectionPrompt } from "./ReflectionPrompt";

export interface LessonPlayerProps {
  lesson: LessonDefinition;
  onXpEarned?: (amount: number) => void;
}

function firstNarrative(blocks: LessonBlock[]): NarrativeBlock | null {
  const b = blocks.find((x): x is NarrativeBlock => x.kind === "narrative");
  return b ?? null;
}

function canProceed(
  block: LessonBlock | undefined,
  flags: { choiceResolved: boolean; puzzleSolved: boolean; discoveryDone: boolean; reflectionOk: boolean },
): boolean {
  if (!block) return false;
  switch (block.kind) {
    case "narrative":
      return true;
    case "choice":
      return flags.choiceResolved;
    case "puzzle":
      return flags.puzzleSolved;
    case "discovery":
      return flags.discoveryDone;
    case "reflection":
      return flags.reflectionOk;
    default:
      return false;
  }
}

export function LessonPlayer({ lesson, onXpEarned }: LessonPlayerProps) {
  const blocks = lesson.blocks;
  const [idx, setIdx] = useState(0);
  const [completedIds, setCompletedIds] = useState<string[]>([]);
  const [xp, setXp] = useState(0);
  const [finished, setFinished] = useState(false);
  const [choiceResolved, setChoiceResolved] = useState(false);
  const [puzzleSolved, setPuzzleSolved] = useState(false);
  const [discoveryDone, setDiscoveryDone] = useState(false);
  const [reflectionOk, setReflectionOk] = useState(false);

  const current = blocks[idx];
  const primary = useMemo(() => firstNarrative(blocks), [blocks]);

  const flags = useMemo(
    () => ({ choiceResolved, puzzleSolved, discoveryDone, reflectionOk }),
    [choiceResolved, discoveryDone, puzzleSolved, reflectionOk],
  );

  const snapRef = useRef<LearnProgressPayload>({
    lessonId: lesson.id,
    blockIndex: 0,
    completedBlockIds: [],
    xpAwarded: 0,
    updatedAt: new Date().toISOString(),
  });

  useEffect(() => {
    snapRef.current = {
      lessonId: lesson.id,
      blockIndex: idx,
      completedBlockIds: completedIds,
      xpAwarded: xp,
      updatedAt: new Date().toISOString(),
    };
  }, [completedIds, idx, lesson.id, xp]);

  useEffect(() => {
    const id = window.setInterval(() => {
      writeLessonProgress(snapRef.current);
    }, 30000);
    return () => window.clearInterval(id);
  }, [lesson.id]);

  useEffect(() => {
    const saved = readLessonProgress(lesson.id);
    if (!saved) return;
    setIdx(Math.min(saved.blockIndex, blocks.length - 1));
    setCompletedIds(saved.completedBlockIds);
    setXp(saved.xpAwarded);
  }, [blocks.length, lesson.id]);

  useEffect(() => {
    setChoiceResolved(false);
    setPuzzleSolved(false);
    setDiscoveryDone(false);
    setReflectionOk(false);
  }, [idx]);

  const persistNow = useCallback(() => {
    writeLessonProgress(snapRef.current);
  }, []);

  const next = useCallback(() => {
    if (!current || !canProceed(current, flags)) return;
    const already = completedIds.includes(current.id);
    const gained = already ? 0 : 50;
    const nextCompleted = already ? completedIds : [...completedIds, current.id];
    const nextXp = xp + gained;
    if (gained) onXpEarned?.(gained);
    setCompletedIds(nextCompleted);
    setXp(nextXp);
    if (idx < blocks.length - 1) {
      setIdx((i) => i + 1);
    } else {
      setFinished(true);
    }
    writeLessonProgress({
      lessonId: lesson.id,
      blockIndex: idx,
      completedBlockIds: nextCompleted,
      xpAwarded: nextXp,
      updatedAt: new Date().toISOString(),
    });
  }, [blocks.length, completedIds, current, flags, idx, lesson.id, onXpEarned, xp]);

  const prev = useCallback(() => {
    setFinished(false);
    setIdx((i) => Math.max(0, i - 1));
  }, []);

  const pct = useMemo(() => {
    const done = blocks.filter((b) => completedIds.includes(b.id)).length;
    return (done / Math.max(1, blocks.length)) * 100;
  }, [blocks, completedIds]);

  const proceed = canProceed(current, flags);

  const leftPanel = useMemo(() => {
    if (!primary) {
      return (
        <div className="flex h-full min-h-[320px] items-center justify-center rounded-xl border border-indigo-800/60 bg-indigo-950/40 p-6 text-center text-indigo-200">
          No narrative anchor configured for this lesson.
        </div>
      );
    }
    const beat =
      current && current.kind !== "narrative"
        ? `Current beat: **${current.kind}** — collaborate before advancing.`
        : "Read carefully — glossary terms are tappable.";
    return (
      <NarrativeReader
        title={primary.title}
        paragraphs={[...primary.paragraphs, beat]}
        dialogues={primary.dialogues}
        glossary={primary.glossary}
      />
    );
  }, [current, primary]);

  const rightPanel = useMemo(() => {
    if (!current) return null;
    if (current.kind === "narrative") {
      return (
        <div className="rounded-xl border border-indigo-800/50 bg-indigo-950/40 p-4 text-sm text-indigo-100/90">
          <p>
            This chapter sets the scene. When your team agrees the story beats are internalized, press{" "}
            <strong className="text-indigo-50">Next</strong> to continue.
          </p>
        </div>
      );
    }
    if (current.kind === "choice") {
      return (
        <ChoicePoint
          question={current.question}
          options={current.options}
          successMessage={current.successMessage}
          failureMessage={current.failureMessage}
          onResolved={() => setChoiceResolved(true)}
        />
      );
    }
    if (current.kind === "puzzle") {
      return (
        <PuzzleSolver
          prompt={current.prompt}
          answer={current.answer}
          caseSensitive={current.caseSensitive}
          successMessage={current.successMessage}
          onSolved={() => setPuzzleSolved(true)}
        />
      );
    }
    if (current.kind === "discovery") {
      return (
        <DiscoveryMoment
          headline={current.headline}
          teaser={current.teaser}
          reveal={current.reveal}
          onReveal={() => setDiscoveryDone(true)}
        />
      );
    }
    if (current.kind === "reflection") {
      return (
        <ReflectionPrompt
          prompt={current.prompt}
          guidance={current.guidance}
          minChars={current.minChars}
          onChangeValid={(ok) => setReflectionOk(ok)}
        />
      );
    }
    return null;
  }, [current]);

  if (finished) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-emerald-500/40 bg-emerald-950/30 p-12 text-center">
        <h2 className="text-2xl font-semibold text-emerald-100">Lesson complete</h2>
        <p className="max-w-lg text-indigo-100/90">
          Progress saved locally and synced when the learn WebSocket is available. Total XP this run:{" "}
          <strong>{xp}</strong>.
        </p>
        <Button type="button" variant="secondary" onClick={() => setFinished(false)}>
          Review lesson
        </Button>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-8rem)] flex-col gap-4">
      <div className="grid flex-1 gap-4 lg:grid-cols-5">
        <div className="lg:col-span-2">{leftPanel}</div>
        <div className="space-y-4 lg:col-span-3">
          {rightPanel}
          <HintSystem hints={lesson.hintsByBlockId[current?.id ?? ""]} blockLabel={current?.id} />
        </div>
      </div>
      <div className="sticky bottom-0 z-20 rounded-xl border border-indigo-800/60 bg-slate-950/95 p-4 shadow-xl backdrop-blur">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <ProgressBar value={pct} label="Lesson completion" className="md:flex-1" />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={prev} disabled={idx === 0}>
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <Button type="button" size="sm" className="bg-indigo-600 hover:bg-indigo-500" onClick={next} disabled={!proceed}>
              {idx >= blocks.length - 1 ? "Finish" : "Next"}
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-1 border-indigo-700 text-indigo-100"
              onClick={persistNow}
            >
              <Save className="h-4 w-4" />
              Save
            </Button>
            <span className="text-xs text-indigo-200/80">XP {xp}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
