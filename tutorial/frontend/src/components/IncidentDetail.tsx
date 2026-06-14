import { format } from "date-fns";
import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { IncidentRow } from "@/types";

export interface IncidentDetailProps {
  incident: IncidentRow;
}

export function IncidentDetail({ incident }: IncidentDetailProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="text-xl">{incident.title}</CardTitle>
          <p className="mt-2 text-sm text-slate-400">{incident.description}</p>
        </div>
        <div className="flex flex-col items-end gap-2 text-xs text-slate-500">
          <span>ID {incident.id}</span>
          <Link
            className="inline-flex items-center gap-1 text-emerald-400 hover:text-emerald-300"
            to={`/investigations/${incident.id}`}
          >
            Open investigation <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Badge variant="info">{incident.severity}</Badge>
          <Badge variant="default">{incident.status}</Badge>
          <Badge variant="default">{incident.incident_type}</Badge>
        </div>
        <Separator />
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <div className="text-xs uppercase text-slate-500">Source IP</div>
            <div className="font-mono text-sm">{incident.source_ip ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-slate-500">Target asset</div>
            <div className="text-sm">{incident.target_asset ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-slate-500">Created</div>
            <div className="text-sm">{format(new Date(incident.created_at), "PPpp")}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-slate-500">Updated</div>
            <div className="text-sm">{format(new Date(incident.updated_at), "PPpp")}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
