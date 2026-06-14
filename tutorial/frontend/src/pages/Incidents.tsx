import { Plus } from "lucide-react";
import { useState } from "react";

import { IncidentList } from "@/components/IncidentList";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import * as incidentsApi from "@/api/incidents";
import { useSocShell } from "@/context/soc-shell";

export function Incidents() {
  const { incidents, loading, error, refresh } = useSocShell();
  const [selected, setSelected] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    title: "",
    description: "",
    severity: "medium",
    incident_type: "network_intrusion",
  });

  const startOne = async (id: string) => {
    await incidentsApi.startInvestigation(id);
    await refresh();
  };

  const bulkInvestigate = async () => {
    setBusy(true);
    try {
      for (const id of selected) {
        await incidentsApi.startInvestigation(id);
      }
      setSelected([]);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const exportReport = async () => {
    setBusy(true);
    try {
      const payloads = await Promise.all(selected.map((id) => incidentsApi.getIncident(id)));
      const blob = new Blob([JSON.stringify(payloads, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `soc-bulk-export-${Date.now()}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    setBusy(true);
    try {
      await incidentsApi.createIncident({
        title: form.title,
        description: form.description,
        severity: form.severity,
        incident_type: form.incident_type,
        status: "open",
      });
      setOpen(false);
      setForm({ title: "", description: "", severity: "medium", incident_type: "network_intrusion" });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not reach API</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>{error}</span>
            <Button size="sm" variant="secondary" onClick={() => void refresh()}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-50">Incident command</h1>
          <p className="text-sm text-slate-400">Queue investigations, export chain-of-custody ready bundles.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2">
                <Plus className="h-4 w-4" />
                New incident
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create incident</DialogTitle>
              </DialogHeader>
              <div className="space-y-3 py-2">
                <div className="space-y-1">
                  <label htmlFor="title" className="text-sm font-medium text-slate-200">
                    Title
                  </label>
                  <Input
                    id="title"
                    value={form.title}
                    onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                    placeholder="Suspicious lateral movement"
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="description" className="text-sm font-medium text-slate-200">
                    Description
                  </label>
                  <Input
                    id="description"
                    value={form.description}
                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                    placeholder="Narrative for analysts"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label htmlFor="severity" className="text-sm font-medium text-slate-200">
                      Severity
                    </label>
                    <select
                      id="severity"
                      className="h-10 w-full rounded-md border border-slate-800 bg-slate-900 px-2 text-sm"
                      value={form.severity}
                      onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value }))}
                    >
                      <option value="low">low</option>
                      <option value="medium">medium</option>
                      <option value="high">high</option>
                      <option value="critical">critical</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label htmlFor="type" className="text-sm font-medium text-slate-200">
                      Type
                    </label>
                    <Input
                      id="type"
                      value={form.incident_type}
                      onChange={(e) => setForm((f) => ({ ...f, incident_type: e.target.value }))}
                    />
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="secondary" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button disabled={busy || !form.title || !form.description} onClick={() => void create()}>
                  Create
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {selected.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3 text-sm text-slate-200">
          <span className="font-medium">{selected.length} selected</span>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => void bulkInvestigate()}>
            Start investigation
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void exportReport()}>
            Export report
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
            Clear
          </Button>
        </div>
      ) : null}

      <IncidentList
        incidents={incidents}
        loading={loading}
        onStartInvestigation={startOne}
        selectable
        selectedIds={selected}
        onSelectionChange={setSelected}
      />
    </div>
  );
}
