import { ChevronRight, File, Folder } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";

interface FsNode {
  name: string;
  type: "dir" | "file";
  children?: FsNode[];
}

const TREE: FsNode = {
  name: "/home/student/lab",
  type: "dir",
  children: [
    {
      name: "artifacts",
      type: "dir",
      children: [
        { name: "dns_sample.pcap", type: "file" },
        { name: "memdump.lime", type: "file" },
      ],
    },
    { name: "logs", type: "dir", children: [{ name: "auth.jsonl", type: "file" }] },
    { name: "quarantine", type: "dir", children: [{ name: "suspect.exe", type: "file" }] },
    { name: "README.txt", type: "file" },
  ],
};

function flattenPaths(node: FsNode, prefix = ""): string[] {
  const p = prefix ? `${prefix}/${node.name}` : node.name;
  const self = node.type === "file" ? [p] : [];
  if (!node.children) return self;
  return [p, ...node.children.flatMap((c) => flattenPaths(c, p))];
}

export interface FileExplorerProps {
  onOpenPath?: (path: string) => void;
}

export function FileExplorer({ onOpenPath }: FileExplorerProps) {
  const [open, setOpen] = useState<Record<string, boolean>>({ "/home/student/lab": true });
  const paths = useMemo(() => flattenPaths(TREE), []);

  const toggle = (path: string) => {
    setOpen((o) => ({ ...o, [path]: !o[path] }));
  };

  const renderNode = (node: FsNode, prefix: string, depth: number): ReactNode => {
    const path = prefix ? `${prefix}/${node.name}` : node.name;
    const expanded = open[path] ?? false;
    return (
      <div key={path} className="select-none">
        <button
          type="button"
          className={cn(
            "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm text-indigo-100 hover:bg-indigo-900/50",
            depth === 0 && "font-semibold text-indigo-50",
          )}
          style={{ paddingLeft: 8 + depth * 12 }}
          onClick={() => {
            if (node.type === "dir") toggle(path);
            else onOpenPath?.(path);
          }}
        >
          {node.type === "dir" ? (
            <>
              <ChevronRight className={cn("h-4 w-4 transition", expanded && "rotate-90")} />
              <Folder className="h-4 w-4 text-amber-300" />
            </>
          ) : (
            <>
              <span className="w-4" />
              <File className="h-4 w-4 text-indigo-300" />
            </>
          )}
          <span className="truncate">{node.name}</span>
        </button>
        {node.type === "dir" && expanded && node.children
          ? node.children.map((c) => renderNode(c, path, depth + 1))
          : null}
      </div>
    );
  };

  return (
    <div className="rounded-xl border border-indigo-800/60 bg-indigo-950/50">
      <div className="border-b border-indigo-800/60 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-indigo-200/80">
        Sandbox files
      </div>
      <ScrollArea className="h-64 p-2">
        {renderNode(TREE, "", 0)}
        <p className="mt-3 px-2 text-[11px] text-indigo-300/70">{paths.length} paths indexed (read-only demo tree).</p>
      </ScrollArea>
    </div>
  );
}
