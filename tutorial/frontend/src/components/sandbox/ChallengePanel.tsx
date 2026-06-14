import { Target } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface ChallengePanelProps {
  title: string;
  description: string;
  objectives: string[];
  difficultyLabel: string;
}

export function ChallengePanel({ title, description, objectives, difficultyLabel }: ChallengePanelProps) {
  return (
    <Card className="border-indigo-700/50 bg-gradient-to-br from-indigo-950/90 to-violet-950/60">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-xl text-indigo-50">
          <Target className="h-6 w-6 text-fuchsia-300" />
          {title}
          <Badge className="bg-indigo-600/40 text-indigo-50">{difficultyLabel}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-indigo-100/90">
        <p>{description}</p>
        <ul className="list-inside list-disc space-y-1 text-indigo-200/90">
          {objectives.map((o) => (
            <li key={o}>{o}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
