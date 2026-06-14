/** Education / student learning domain (no `any`). */

export type DifficultyLevel = "Beginner" | "Intermediate" | "Advanced";

export type LessonCategory = "Network" | "Forensics" | "Malware" | "Crypto";

export type LessonSort = "newest" | "popular" | "recommended";

export type SkillMastery = "locked" | "available" | "in_progress" | "mastered";

export interface LessonSummary {
  id: string;
  title: string;
  subtitle: string;
  difficulty: DifficultyLevel;
  categories: LessonCategory[];
  concepts: string[];
  durationMinutes: number;
  rating: number;
  enrollCount: number;
  thumbnailGradient: string;
  cstaCodes: string[];
  createdAt: string;
  /** 0–100 when in progress */
  progressPercent?: number;
  trending?: boolean;
  recommended?: boolean;
}

export type LessonBlockKind = "narrative" | "choice" | "puzzle" | "discovery" | "reflection";

export interface DialogueLine {
  speaker: string;
  text: string;
}

export interface NarrativeBlock {
  kind: "narrative";
  id: string;
  title: string;
  paragraphs: string[];
  dialogues: DialogueLine[];
  glossary: Record<string, string>;
}

export interface ChoiceBlock {
  kind: "choice";
  id: string;
  question: string;
  options: { id: string; label: string; correct: boolean }[];
  successMessage: string;
  failureMessage: string;
}

export interface PuzzleBlock {
  kind: "puzzle";
  id: string;
  prompt: string;
  answer: string;
  caseSensitive: boolean;
  successMessage: string;
}

export interface DiscoveryBlock {
  kind: "discovery";
  id: string;
  headline: string;
  teaser: string;
  reveal: string;
}

export interface ReflectionBlock {
  kind: "reflection";
  id: string;
  prompt: string;
  guidance: string;
  minChars: number;
}

export type LessonBlock = NarrativeBlock | ChoiceBlock | PuzzleBlock | DiscoveryBlock | ReflectionBlock;

export interface LessonDefinition {
  id: string;
  title: string;
  summary: LessonSummary;
  blocks: LessonBlock[];
  hintsByBlockId: Record<string, [string, string, string]>;
}

export interface SkillNodeDef {
  id: string;
  label: string;
  category: LessonCategory;
  mastery: SkillMastery;
  x: number;
  y: number;
}

export interface SkillEdgeDef {
  from: string;
  to: string;
}

export interface CredentialItem {
  id: string;
  conceptName: string;
  category: LessonCategory;
  completedAt: string;
  score: number;
  tokenId: string;
  chain: string;
  badges: string[];
}

export interface LeaderboardRow {
  rank: number;
  handle: string;
  xp: number;
  streak: number;
  lessonsCompleted: number;
  isYou?: boolean;
}

export interface StudentProfile {
  id: string;
  displayName: string;
  avatarGradient: string;
  level: number;
  levelTitle: string;
  xp: number;
  xpToNext: number;
  streakDays: number;
  lessonsCompleted: number;
  achievements: AchievementDef[];
}

export interface AchievementDef {
  id: string;
  title: string;
  description: string;
  icon: "star" | "flame" | "shield" | "terminal" | "trophy";
  unlocked: boolean;
  unlockedAt?: string;
}

export interface LearnProgressPayload {
  lessonId: string;
  blockIndex: number;
  completedBlockIds: string[];
  xpAwarded: number;
  updatedAt: string;
}

export interface SandboxWsMessage {
  type: "output" | "status" | "challenge_complete" | "error";
  data: string;
}

export interface LearnWsEnvelope {
  event: string;
  data: Record<string, unknown>;
}
