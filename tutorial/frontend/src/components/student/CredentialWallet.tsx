import { format, isAfter, isBefore, parseISO } from "date-fns";
import { Check, Filter, Share2, Shield } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import * as studentsApi from "@/api/students";
import { ConceptTag } from "@/components/common/ConceptTag";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { CREDENTIAL_CATALOG } from "@/data/credentialCatalog";
import type { CredentialItem, LessonCategory } from "@/types/education";

const CATS: (LessonCategory | "All")[] = ["All", "Network", "Forensics", "Malware", "Crypto"];

function mapCategory(raw: string | null | undefined): LessonCategory {
  const v = (raw ?? "").toLowerCase();
  if (v.includes("network") || v.includes("dns")) return "Network";
  if (v.includes("malware") || v.includes("ransom")) return "Malware";
  if (v.includes("crypto")) return "Crypto";
  return "Forensics";
}

function entryToItem(entry: studentsApi.CredentialEntry): CredentialItem {
  const score = entry.score ?? 100;
  return {
    id: entry.credential_id,
    conceptName: entry.concept_name ?? "Verified skill",
    category: mapCategory(entry.category),
    completedAt: entry.issued_at,
    score,
    tokenId: entry.verification_hash.slice(0, 18) + "…",
    chain: entry.chain,
    badges: entry.lesson_id ? ["lesson-complete", "soc-generated"] : ["foundation"],
  };
}

export function CredentialWallet() {
  const [items, setItems] = useState<CredentialItem[]>(CREDENTIAL_CATALOG);
  const [loading, setLoading] = useState(true);
  const [apiNote, setApiNote] = useState<string | null>(null);
  const [cat, setCat] = useState<LessonCategory | "All">("All");
  const [minScore, setMinScore] = useState(0);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [selected, setSelected] = useState<CredentialItem | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const demo = await studentsApi.getDemoStudent();
        const creds = await studentsApi.getCredentials(demo.id);
        if (cancelled) return;
        const mapped = creds.map(entryToItem);
        const seen = new Set(mapped.map((c) => c.id));
        const merged = [...mapped, ...CREDENTIAL_CATALOG.filter((c) => !seen.has(c.id))];
        setItems(merged);
        setApiNote(mapped.length ? "Live credentials from completed lessons" : "Demo credential issued");
      } catch {
        if (!cancelled) {
          setItems(CREDENTIAL_CATALOG);
          setApiNote("Using static catalog — API unavailable");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    return items.filter((c) => {
      if (cat !== "All" && c.category !== cat) return false;
      if (c.score < minScore) return false;
      const d = parseISO(c.completedAt);
      if (from && isBefore(d, parseISO(from))) return false;
      if (to && isAfter(d, parseISO(to))) return false;
      return true;
    });
  }, [cat, from, items, minScore, to]);

  const share = async (c: CredentialItem) => {
    const url = `${window.location.origin}/credentials?highlight=${encodeURIComponent(c.id)}`;
    if (navigator.share) {
      try {
        await navigator.share({ title: `${c.conceptName} credential`, text: "Verified learner credential", url });
        return;
      } catch {
        /* fall through */
      }
    }
    await navigator.clipboard.writeText(url);
  };

  return (
    <div className="space-y-4">
      {apiNote ? <p className="text-xs text-indigo-300/80">{apiNote}</p> : null}
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-indigo-800/60 bg-indigo-950/50 p-4">
        <div className="flex items-center gap-2 text-indigo-200">
          <Filter className="h-4 w-4" />
          <span className="text-sm font-medium text-indigo-100">Filters</span>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-indigo-300">Category</label>
          <select
            className="h-9 rounded-md border border-indigo-800 bg-slate-950 px-2 text-sm text-indigo-50"
            value={cat}
            onChange={(e) => setCat(e.target.value as LessonCategory | "All")}
          >
            {CATS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-indigo-300">Min score</label>
          <Input
            type="number"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value) || 0)}
            className="h-9 w-24 border-indigo-800 bg-slate-950 text-indigo-50"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-indigo-300">From</label>
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-9 border-indigo-800 bg-slate-950 text-indigo-50" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-indigo-300">To</label>
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-9 border-indigo-800 bg-slate-950 text-indigo-50" />
        </div>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((c) => (
            <button
              key={c.id}
              type="button"
              className="rounded-2xl bg-gradient-to-br from-indigo-600/40 via-fuchsia-600/30 to-cyan-500/25 p-[1px] text-left shadow-lg transition hover:brightness-110"
              onClick={() => setSelected(c)}
            >
              <Card className="h-full border-0 bg-slate-950/95">
                <CardContent className="space-y-3 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-lg font-semibold text-indigo-50">{c.conceptName}</h3>
                      <p className="text-xs text-indigo-300/80">{format(parseISO(c.completedAt), "PPP")}</p>
                    </div>
                    <Badge className="bg-emerald-600/30 text-emerald-100">{c.score}%</Badge>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    <ConceptTag label={c.category} />
                    {c.badges.map((b) => (
                      <Badge key={b} className="border-indigo-700/60 bg-indigo-900/60 text-indigo-100">
                        {b}
                      </Badge>
                    ))}
                  </div>
                  <p className="font-mono text-[11px] text-indigo-200/80">{c.tokenId}</p>
                </CardContent>
              </Card>
            </button>
          ))}
        </div>
      )}

      {!loading && filtered.length === 0 ? (
        <p className="text-center text-sm text-indigo-300/80">No credentials match these filters.</p>
      ) : null}

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent>
          {selected ? (
            <>
              <DialogHeader>
                <DialogTitle>{selected.conceptName}</DialogTitle>
              </DialogHeader>
              <div className="space-y-3 text-sm text-indigo-100/90">
                <p>
                  On-chain proof on <strong>{selected.chain}</strong> with learner score <strong>{selected.score}%</strong>.
                </p>
                <p className="font-mono text-xs text-indigo-300/90">Token: {selected.tokenId}</p>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" className="gap-2 bg-indigo-600" onClick={() => void share(selected)}>
                    <Share2 className="h-4 w-4" />
                    Share link
                  </Button>
                  <Button type="button" variant="secondary" className="gap-2" onClick={() => setSelected(null)}>
                    <Check className="h-4 w-4" />
                    Close
                  </Button>
                </div>
                <div className="rounded-lg border border-indigo-800/60 bg-indigo-950/60 p-3 text-xs text-indigo-200/90">
                  <div className="flex items-center gap-2 font-semibold text-indigo-50">
                    <Shield className="h-4 w-4 text-emerald-400" />
                    Blockchain verify
                  </div>
                  <p className="mt-2">
                    Verification hash is derived deterministically from student + lesson progress. Set{" "}
                    <code className="text-emerald-200">BLOCKCHAIN_MOCK=0</code> to mint on testnet in production
                    deployments.
                  </p>
                </div>
              </div>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
