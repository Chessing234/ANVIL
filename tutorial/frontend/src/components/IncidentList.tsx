import { formatDistanceToNow } from "date-fns";
import { Eye, Play } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { IncidentRow } from "@/types";

export interface IncidentListProps {
  incidents: IncidentRow[];
  loading: boolean;
  onStartInvestigation: (id: string) => Promise<void>;
  selectable?: boolean;
  selectedIds?: string[];
  onSelectionChange?: (ids: string[]) => void;
}

function severityVariant(sev: string): "critical" | "warning" | "info" | "success" | "default" {
  const s = sev.toLowerCase();
  if (s === "critical") return "critical";
  if (s === "high") return "warning";
  if (s === "medium") return "info";
  if (s === "low") return "success";
  return "default";
}

export function IncidentList({
  incidents,
  loading,
  onStartInvestigation,
  selectable,
  selectedIds,
  onSelectionChange,
}: IncidentListProps) {
  const navigate = useNavigate();
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [rangeFrom, setRangeFrom] = useState("");
  const [rangeTo, setRangeTo] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const selection = selectedIds ?? [];

  const filtered = useMemo(() => {
    const fromTs = rangeFrom
      ? (() => {
          const d = new Date(rangeFrom);
          d.setHours(0, 0, 0, 0);
          return d.getTime();
        })()
      : null;
    const toTs = rangeTo
      ? (() => {
          const d = new Date(rangeTo);
          d.setHours(23, 59, 59, 999);
          return d.getTime();
        })()
      : null;

    return incidents.filter((row) => {
      if (severity && row.severity.toLowerCase() !== severity.toLowerCase()) return false;
      if (status && row.status.toLowerCase() !== status.toLowerCase()) return false;
      if (query && !row.title.toLowerCase().includes(query.toLowerCase())) return false;
      const updated = new Date(row.updated_at).getTime();
      if (fromTs !== null && updated < fromTs) return false;
      if (toTs !== null && updated > toTs) return false;
      return true;
    });
  }, [incidents, query, rangeFrom, rangeTo, severity, status]);

  const allFilteredSelected = filtered.length > 0 && filtered.every((r) => selection.includes(r.id));

  const toggleRow = (id: string) => {
    if (!onSelectionChange) return;
    if (selection.includes(id)) {
      onSelectionChange(selection.filter((x) => x !== id));
    } else {
      onSelectionChange([...selection, id]);
    }
  };

  const toggleAllFiltered = () => {
    if (!onSelectionChange) return;
    if (allFilteredSelected) {
      const filteredIds = new Set(filtered.map((r) => r.id));
      onSelectionChange(selection.filter((id) => !filteredIds.has(id)));
    } else {
      const merged = new Set([...selection, ...filtered.map((r) => r.id)]);
      onSelectionChange([...merged]);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <CardTitle>Incidents</CardTitle>
          <p className="text-sm text-slate-400">Filter, triage, and launch autonomous investigations.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Input placeholder="Search title…" value={query} onChange={(e) => setQuery(e.target.value)} className="w-48" />
          <Input type="date" value={rangeFrom} onChange={(e) => setRangeFrom(e.target.value)} className="w-40" />
          <Input type="date" value={rangeTo} onChange={(e) => setRangeTo(e.target.value)} className="w-40" />
          <select
            className="h-10 rounded-md border border-slate-800 bg-slate-900 px-2 text-sm text-slate-200"
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          >
            <option value="">All severities</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
          <select
            className="h-10 rounded-md border border-slate-800 bg-slate-900 px-2 text-sm text-slate-200"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="triaging">Triaging</option>
            <option value="investigating">Investigating</option>
            <option value="contained">Contained</option>
            <option value="resolved">Resolved</option>
            <option value="closed">Closed</option>
          </select>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-slate-800/80" />
            ))}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                {selectable ? (
                  <TableHead className="w-10">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-600 bg-slate-900"
                      checked={allFilteredSelected}
                      onChange={toggleAllFiltered}
                      aria-label="Select all visible incidents"
                    />
                  </TableHead>
                ) : null}
                <TableHead>Title</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((row, idx) => (
                <TableRow key={row.id} className={idx % 2 === 0 ? "bg-slate-900/30 hover:bg-slate-900/50" : "hover:bg-slate-900/40"}>
                  {selectable ? (
                    <TableCell className="w-10">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-slate-600 bg-slate-900"
                        checked={selection.includes(row.id)}
                        onChange={() => toggleRow(row.id)}
                        aria-label={`Select ${row.title}`}
                      />
                    </TableCell>
                  ) : null}
                  <TableCell className="font-medium text-slate-100">{row.title}</TableCell>
                  <TableCell>
                    <Badge variant={severityVariant(row.severity)}>{row.severity}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="default">{row.status}</Badge>
                  </TableCell>
                  <TableCell className="text-slate-400 text-xs">
                    {formatDistanceToNow(new Date(row.updated_at), { addSuffix: true })}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => navigate(`/investigations/${row.id}`)}
                        className="gap-1"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        View
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busyId === row.id}
                        onClick={async () => {
                          setBusyId(row.id);
                          try {
                            await onStartInvestigation(row.id);
                          } finally {
                            setBusyId(null);
                          }
                        }}
                        className="gap-1"
                      >
                        <Play className="h-3.5 w-3.5" />
                        Investigate
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
