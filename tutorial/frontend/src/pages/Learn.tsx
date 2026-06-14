import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { learnProgressClient } from "@/api/educationSockets";
import { LessonCard } from "@/components/learning/LessonCard";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { getLessonSummaries } from "@/data/educationCatalog";
import type { DifficultyLevel, LessonCategory, LessonSort, LessonSummary } from "@/types/education";

const DIFFS: (DifficultyLevel | "All")[] = ["All", "Beginner", "Intermediate", "Advanced"];
const CATS: (LessonCategory | "All")[] = ["All", "Network", "Forensics", "Malware", "Crypto"];

export function Learn() {
  const [lessons] = useState<LessonSummary[]>(() => getLessonSummaries());
  const [difficulty, setDifficulty] = useState<DifficultyLevel | "All">("All");
  const [category, setCategory] = useState<LessonCategory | "All">("All");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<LessonSort>("recommended");
  const [live, setLive] = useState<string | null>(null);

  useEffect(() => {
    return learnProgressClient.subscribe((msg) => {
      if (msg.event === "xp_update" || msg.event === "lesson_progress") {
        setLive(`${msg.event} @ ${new Date().toLocaleTimeString()}`);
        window.setTimeout(() => setLive(null), 4000);
      }
    });
  }, []);

  const filtered = useMemo(() => {
    let rows = lessons.filter((l) => {
      if (difficulty !== "All" && l.difficulty !== difficulty) return false;
      if (category !== "All" && !l.categories.includes(category)) return false;
      if (search && !l.title.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
    if (sort === "newest") {
      rows = [...rows].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
    } else if (sort === "popular") {
      rows = [...rows].sort((a, b) => b.enrollCount - a.enrollCount);
    } else {
      rows = [...rows].sort((a, b) => Number(b.recommended) - Number(a.recommended) || b.rating - a.rating);
    }
    return rows;
  }, [category, difficulty, lessons, search, sort]);

  const inProgress = useMemo(() => lessons.filter((l) => (l.progressPercent ?? 0) > 0 && (l.progressPercent ?? 0) < 100), [lessons]);
  const recommended = useMemo(() => lessons.filter((l) => l.recommended), [lessons]);
  const trending = useMemo(() => lessons.filter((l) => l.trending), [lessons]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-indigo-50">Learn</h1>
        <p className="mt-1 max-w-2xl text-indigo-200/85">
          Gamified cyber curriculum tuned for DSH Hacks, USAII Global AI, and ML Empowerment scoreboards—pick a track and
          ship evidence-backed wins.
        </p>
      </div>

      {live ? (
        <Alert className="border-indigo-600/40 bg-indigo-950/60">
          <AlertTitle>Live sync</AlertTitle>
          <AlertDescription>{live}</AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-indigo-800/60 bg-indigo-950/50 p-4">
        <Input
          placeholder="Search lessons…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs border-indigo-800 bg-slate-950 text-indigo-50"
        />
        <div className="flex flex-col gap-1">
          <label className="text-xs text-indigo-300">Difficulty</label>
          <select
            className="h-9 rounded-md border border-indigo-800 bg-slate-950 px-2 text-sm text-indigo-50"
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value as DifficultyLevel | "All")}
          >
            {DIFFS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-indigo-300">Category</label>
          <select
            className="h-9 rounded-md border border-indigo-800 bg-slate-950 px-2 text-sm text-indigo-50"
            value={category}
            onChange={(e) => setCategory(e.target.value as LessonCategory | "All")}
          >
            {CATS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-indigo-300">Sort</label>
          <select
            className="h-9 rounded-md border border-indigo-800 bg-slate-950 px-2 text-sm text-indigo-50"
            value={sort}
            onChange={(e) => setSort(e.target.value as LessonSort)}
          >
            <option value="recommended">Recommended for you</option>
            <option value="newest">Newest</option>
            <option value="popular">Most popular</option>
          </select>
        </div>
      </div>

      {inProgress.length ? (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-indigo-50">Continue learning</h2>
            <Link to="/profile" className="text-sm text-fuchsia-300 hover:text-fuchsia-200">
              View profile →
            </Link>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {inProgress.map((l) => (
              <LessonCard key={l.id} lesson={l} />
            ))}
          </div>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-indigo-50">Recommended</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {recommended.map((l) => (
            <LessonCard key={l.id} lesson={l} />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-indigo-50">Trending from real incidents</h2>
        <p className="text-sm text-indigo-200/80">Labs tagged with live SOC telemetry remixes—perfect for judge walkthroughs.</p>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {trending.map((l) => (
            <LessonCard key={l.id} lesson={l} />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-indigo-50">All lessons</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((l) => (
            <LessonCard key={l.id} lesson={l} />
          ))}
        </div>
      </section>
    </div>
  );
}
