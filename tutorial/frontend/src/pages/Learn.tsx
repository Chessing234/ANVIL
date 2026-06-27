import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import * as lessonsApi from "@/api/lessons";
import { learnProgressClient } from "@/api/educationSockets";
import { LessonCard } from "@/components/learning/LessonCard";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { getLessonSummaries } from "@/data/educationCatalog";
import { apiLessonToSummary, mergeLessonSummaries } from "@/lib/apiLessonAdapter";
import type { DifficultyLevel, LessonCategory, LessonSort, LessonSummary } from "@/types/education";

const DIFFS: (DifficultyLevel | "All")[] = ["All", "Beginner", "Intermediate", "Advanced"];
const CATS: (LessonCategory | "All")[] = ["All", "Network", "Forensics", "Malware", "Crypto"];

export function Learn() {
  const [lessons, setLessons] = useState<LessonSummary[]>(() => getLessonSummaries());
  const [apiError, setApiError] = useState<string | null>(null);
  const [loadingApi, setLoadingApi] = useState(true);
  const [difficulty, setDifficulty] = useState<DifficultyLevel | "All">("All");
  const [category, setCategory] = useState<LessonCategory | "All">("All");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<LessonSort>("recommended");
  const [live, setLive] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingApi(true);
      setApiError(null);
      try {
        const rows = await lessonsApi.listLessons();
        if (cancelled) return;
        const apiSummaries = rows.map((r) => apiLessonToSummary(r, { fromSoc: true }));
        setLessons(mergeLessonSummaries(apiSummaries, getLessonSummaries()));
      } catch (e) {
        if (!cancelled) {
          setApiError(e instanceof Error ? e.message : "Could not load API lessons");
          setLessons(getLessonSummaries());
        }
      } finally {
        if (!cancelled) setLoadingApi(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return learnProgressClient.subscribe((msg) => {
      if (msg.event === "xp_update" || msg.event === "lesson_progress" || msg.event === "lesson_complete") {
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
      rows = [...rows].sort(
        (a, b) =>
          Number(b.fromSoc) - Number(a.fromSoc) ||
          Number(b.recommended) - Number(a.recommended) ||
          b.rating - a.rating,
      );
    }
    return rows;
  }, [category, difficulty, lessons, search, sort]);

  const inProgress = useMemo(() => lessons.filter((l) => (l.progressPercent ?? 0) > 0 && (l.progressPercent ?? 0) < 100), [lessons]);
  const recommended = useMemo(() => lessons.filter((l) => l.recommended), [lessons]);
  const trending = useMemo(() => lessons.filter((l) => l.trending || l.fromSoc), [lessons]);
  const fromSoc = useMemo(() => lessons.filter((l) => l.fromSoc), [lessons]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-indigo-50">Learn</h1>
        <p className="mt-1 max-w-2xl text-indigo-200/85">
          Gamified cyber curriculum that turns real SOC workflows into hands-on lessons—pick a track and
          ship evidence-backed wins.
        </p>
      </div>

      {apiError ? (
        <Alert variant="warning">
          <AlertTitle>API catalog offline</AlertTitle>
          <AlertDescription>Showing static curriculum only. {apiError}</AlertDescription>
        </Alert>
      ) : null}

      {live ? (
        <Alert className="border-indigo-600/40 bg-indigo-950/60">
          <AlertTitle>Live sync</AlertTitle>
          <AlertDescription>{live}</AlertDescription>
        </Alert>
      ) : null}

      {!loadingApi && fromSoc.length > 0 ? (
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-xl font-semibold text-emerald-100">Generated from investigations</h2>
            <span className="text-xs text-emerald-300/80">{fromSoc.length} live lesson(s)</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {fromSoc.slice(0, 3).map((l) => (
              <LessonCard key={l.id} lesson={l} />
            ))}
          </div>
        </section>
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
            <option value="recommended">Recommended</option>
            <option value="newest">Newest</option>
            <option value="popular">Popular</option>
          </select>
        </div>
      </div>

      {inProgress.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-indigo-50">Continue learning</h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {inProgress.map((l) => (
              <LessonCard key={l.id} lesson={l} />
            ))}
          </div>
        </section>
      ) : null}

      {recommended.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-indigo-50">Recommended</h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {recommended.slice(0, 3).map((l) => (
              <LessonCard key={l.id} lesson={l} />
            ))}
          </div>
        </section>
      ) : null}

      {trending.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-indigo-50">Trending</h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {trending.slice(0, 3).map((l) => (
              <LessonCard key={l.id} lesson={l} />
            ))}
          </div>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-indigo-50">All lessons</h2>
        {loadingApi ? (
          <p className="text-sm text-indigo-300/80">Loading live lessons from API…</p>
        ) : null}
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((l) => (
            <LessonCard key={l.id} lesson={l} />
          ))}
        </div>
        {filtered.length === 0 ? (
          <p className="text-center text-sm text-indigo-300/80">
            No lessons match.{" "}
            <Link to="/incidents" className="text-indigo-200 underline">
              Investigate an incident
            </Link>{" "}
            to auto-generate one.
          </p>
        ) : null}
      </section>
    </div>
  );
}
