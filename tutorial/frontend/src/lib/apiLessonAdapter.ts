import type { LessonDetailResponse, LessonListItem } from "@/api/lessons";
import { readLessonProgress } from "@/lib/learnStorage";
import type {
  DifficultyLevel,
  LessonBlock,
  LessonCategory,
  LessonDefinition,
  LessonSummary,
} from "@/types/education";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const GRADIENTS = [
  "from-indigo-600 via-violet-600 to-fuchsia-600",
  "from-emerald-600 via-teal-600 to-cyan-600",
  "from-rose-600 via-amber-600 to-orange-600",
  "from-sky-600 via-indigo-600 to-blue-700",
  "from-purple-700 via-indigo-700 to-slate-900",
];

function normalizeDifficulty(raw: string): DifficultyLevel {
  const v = raw.toLowerCase();
  if (v === "advanced" || v === "expert") return "Advanced";
  if (v === "intermediate") return "Intermediate";
  return "Beginner";
}

function inferCategories(title: string, narrative: string): LessonCategory[] {
  const text = `${title} ${narrative}`.toLowerCase();
  const cats: LessonCategory[] = [];
  if (/dns|network|tcp|firewall|ddos/.test(text)) cats.push("Network");
  if (/memory|forensic|log|artifact|mft/.test(text)) cats.push("Forensics");
  if (/malware|ransom|wmi|virus/.test(text)) cats.push("Malware");
  if (/crypto|hash|encrypt|pki/.test(text)) cats.push("Crypto");
  return cats.length ? cats : ["Forensics"];
}

function gradientFor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) hash = (hash + id.charCodeAt(i)) % GRADIENTS.length;
  const pick = GRADIENTS[hash % GRADIENTS.length];
  return pick !== undefined ? pick : "from-indigo-600 via-violet-600 to-fuchsia-600";
}

export function isApiLessonId(id: string): boolean {
  return UUID_RE.test(id);
}

export function apiLessonToSummary(row: LessonListItem, opts?: { fromSoc?: boolean }): LessonSummary {
  const progress = readLessonProgress(row.id);
  const pct = progress
    ? Math.min(100, Math.round((progress.completedBlockIds.length / Math.max(1, progress.blockIndex + 1)) * 100))
    : undefined;
  return {
    id: row.id,
    title: row.title,
    subtitle: row.narrative.slice(0, 120) + (row.narrative.length > 120 ? "…" : ""),
    difficulty: normalizeDifficulty(row.difficulty),
    categories: inferCategories(row.title, row.narrative),
    concepts: (() => {
      const caps = row.narrative.match(/\b[A-Z]{2,}\b/g) ?? [];
      return caps.length ? [...new Set(caps)].slice(0, 3) : ["SOC", "investigation"];
    })(),
    durationMinutes: row.estimated_duration_minutes,
    rating: 4.9,
    enrollCount: 1,
    thumbnailGradient: gradientFor(row.id),
    cstaCodes: [],
    createdAt: row.created_at,
    progressPercent: pct,
    recommended: opts?.fromSoc ?? true,
    trending: opts?.fromSoc ?? false,
    fromSoc: opts?.fromSoc ?? true,
  };
}

function blocksFromDetail(detail: LessonDetailResponse): LessonBlock[] {
  const blocks: LessonBlock[] = [];
  const paragraphs = detail.narrative
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (paragraphs.length === 0 && detail.narrative.trim()) {
    paragraphs.push(detail.narrative.trim());
  }
  blocks.push({
    kind: "narrative",
    id: "api-narrative",
    title: detail.title,
    paragraphs: paragraphs.length ? paragraphs : ["This lesson was generated from a live SOC investigation."],
    dialogues: [
      { speaker: "SOC Lead", text: "Every clue below came from the investigation timeline." },
      { speaker: "You", text: "Walk me through the evidence chain." },
    ],
    glossary: {
      TTP: "Tactics, techniques, and procedures used by threat actors.",
      IOC: "Indicator of compromise — observable artifact of intrusion.",
    },
  });

  detail.interactive_elements.forEach((el, idx) => {
    const kind = String(el.kind ?? "reflection");
    if (kind === "reflection" || kind === "quiz") {
      blocks.push({
        kind: "reflection",
        id: `api-ref-${idx}`,
        prompt: String(el.prompt ?? "What was the most surprising finding in this case?"),
        guidance: "Reference a specific investigation step or artifact.",
        minChars: 24,
      });
      return;
    }
    if (kind === "choice") {
      const options = Array.isArray(el.options)
        ? (el.options as { id: string; label: string; correct?: boolean }[]).map((o) => ({
            id: String(o.id),
            label: String(o.label),
            correct: Boolean(o.correct),
          }))
        : [
            { id: "a", label: "Isolate the host", correct: true },
            { id: "b", label: "Ignore and wait", correct: false },
          ];
      blocks.push({
        kind: "choice",
        id: `api-choice-${idx}`,
        question: String(el.question ?? "What is the best next step?"),
        options,
        successMessage: "Solid analyst instinct.",
        failureMessage: "Re-read the narrative beat and try again.",
      });
      return;
    }
    if (kind === "sandbox" || kind === "narrative") {
      blocks.push({
        kind: "discovery",
        id: `api-discovery-${idx}`,
        headline: kind === "sandbox" ? "Sandbox ready" : "Investigation beat",
        teaser: "Reveal the operational context from the defense workflow.",
        reveal:
          kind === "sandbox"
            ? `Container sandbox configured: ${JSON.stringify(el.config ?? el, null, 0).slice(0, 200)}`
            : String(el.headline ?? detail.title),
      });
    }
  });

  if (blocks.length === 1) {
    blocks.push({
      kind: "reflection",
      id: "api-ref-default",
      prompt: "How would you explain this incident to a new analyst?",
      guidance: "Use plain language and mention one containment action.",
      minChars: 20,
    });
  }

  return blocks;
}

export function apiLessonToDefinition(detail: LessonDetailResponse): LessonDefinition {
  const summary = apiLessonToSummary(
    {
      id: detail.id,
      incident_id: detail.incident_id,
      title: detail.title,
      narrative: detail.narrative,
      difficulty: detail.difficulty,
      estimated_duration_minutes: detail.estimated_duration_minutes,
      created_at: detail.created_at,
    },
    { fromSoc: true },
  );
  summary.cstaCodes = detail.csta_standards.map(String);
  const blocks = blocksFromDetail(detail);
  const hintsByBlockId: Record<string, [string, string, string]> = {};
  blocks.forEach((b) => {
    hintsByBlockId[b.id] = [
      "This lesson was auto-generated from a defended incident.",
      "Cross-reference the investigation timeline in the SOC view.",
      "Complete the reflection to earn XP and credentials.",
    ];
  });
  return { id: detail.id, title: detail.title, summary, blocks, hintsByBlockId };
}

export function mergeLessonSummaries(apiRows: LessonSummary[], staticRows: LessonSummary[]): LessonSummary[] {
  const seen = new Set(apiRows.map((r) => r.id));
  const merged = [...apiRows];
  for (const row of staticRows) {
    if (!seen.has(row.id)) merged.push(row);
  }
  return merged;
}
