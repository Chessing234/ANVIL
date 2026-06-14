import { Check, Copy, FileWarning } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { EvidenceRow } from "@/types";

export interface EvidencePanelProps {
  items: EvidenceRow[];
}

export function EvidencePanel({ items }: EvidencePanelProps) {
  const [copied, setCopied] = useState<string | null>(null);

  const copyHash = async (hash: string) => {
    await navigator.clipboard.writeText(hash);
    setCopied(hash);
    setTimeout(() => setCopied(null), 1500);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Evidence locker</CardTitle>
        <p className="text-sm text-slate-400">Chain-ready artifacts with SHA-256 fingerprints.</p>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[320px] pr-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Path</TableHead>
                <TableHead>Hash</TableHead>
                <TableHead>Verified</TableHead>
                <TableHead>Size</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-slate-500">
                    No evidence ingested yet.
                  </TableCell>
                </TableRow>
              ) : (
                items.map((ev) => (
                  <TableRow key={ev.id}>
                    <TableCell>
                      <Badge variant="info">{ev.evidence_type}</Badge>
                    </TableCell>
                    <TableCell className="max-w-[220px] truncate font-mono text-xs text-slate-300">{ev.file_path}</TableCell>
                    <TableCell className="font-mono text-[11px] text-emerald-300/90">{ev.hash_sha256.slice(0, 18)}…</TableCell>
                    <TableCell>
                      {ev.verified_at ? (
                        <Badge variant="success">verified</Badge>
                      ) : (
                        <Badge variant="warning">pending</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-slate-400">{ev.file_size_bytes} B</TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant="ghost" className="gap-1" onClick={() => void copyHash(ev.hash_sha256)}>
                        {copied === ev.hash_sha256 ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </ScrollArea>
        <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
          <FileWarning className="h-4 w-4 text-amber-400" />
          Verification against disk is performed server-side via <code className="text-slate-400">verify_integrity</code>.
        </div>
      </CardContent>
    </Card>
  );
}
