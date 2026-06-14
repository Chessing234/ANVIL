import type { LessonCategory, SkillEdgeDef, SkillMastery, SkillNodeDef } from "@/types/education";

const CATEGORIES: LessonCategory[] = ["Network", "Forensics", "Malware", "Crypto"];

const LAYER_COUNTS = [1, 3, 5, 8, 12, 16, 18, 15, 12, 10, 10, 10];

function masteryForIndex(i: number): SkillMastery {
  if (i === 0) return "mastered";
  if (i < 8) return "mastered";
  if (i < 25) return "in_progress";
  if (i < 45) return "available";
  return "locked";
}

/** Deterministic ~120-node graph for performant SVG rendering. */
export function buildSkillGraph(): { nodes: SkillNodeDef[]; edges: SkillEdgeDef[] } {
  const nodes: SkillNodeDef[] = [];
  const edges: SkillEdgeDef[] = [];
  let globalIndex = 0;
  const layerStartIndex: number[] = [];

  for (let layer = 0; layer < LAYER_COUNTS.length; layer++) {
    layerStartIndex[layer] = globalIndex;
    const count = LAYER_COUNTS[layer] ?? 0;
    const spread = Math.max(520, count * 72);
    for (let j = 0; j < count; j++) {
      const id = `sk-${globalIndex}`;
      const x = 80 + (j + 0.5) * (spread / Math.max(1, count));
      const y = 40 + layer * 88;
      const cat = CATEGORIES[globalIndex % CATEGORIES.length] ?? "Network";
      const label =
        layer === 0
          ? "Security mindset"
          : `${cat.slice(0, 3)} · Node ${globalIndex}`;
      nodes.push({
        id,
        label,
        category: cat,
        mastery: masteryForIndex(globalIndex),
        x,
        y,
      });
      if (layer > 0) {
        const prevCount = LAYER_COUNTS[layer - 1] ?? 1;
        const prevStart = layerStartIndex[layer - 1] ?? 0;
        const ratio = j / Math.max(1, count);
        const parentOffset = Math.min(prevCount - 1, Math.floor(ratio * prevCount));
        const parentIndex = prevStart + parentOffset;
        edges.push({ from: `sk-${parentIndex}`, to: id });
        if (j % 4 === 0 && parentOffset + 1 < prevCount) {
          edges.push({ from: `sk-${parentIndex + 1}`, to: id });
        }
      }
      globalIndex += 1;
    }
  }

  return { nodes, edges };
}
