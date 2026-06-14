import { useState } from "react";

import { ChallengePanel } from "@/components/sandbox/ChallengePanel";
import { FileExplorer } from "@/components/sandbox/FileExplorer";
import { SandboxTerminal } from "@/components/sandbox/SandboxTerminal";
import type { VerificationState } from "@/components/sandbox/VerificationPanel";
import { VerificationPanel } from "@/components/sandbox/VerificationPanel";

export function Sandbox() {
  const [verify, setVerify] = useState<{ state: VerificationState; message: string }>({
    state: "idle",
    message: "Awaiting challenge completion signal from the terminal stream.",
  });
  const [wsOk, setWsOk] = useState(false);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-indigo-50">Hands-on sandbox</h1>
        <p className="mt-1 max-w-3xl text-indigo-200/85">
          xterm.js shell with backend WebSocket when available, graceful demo echo offline, and reset to pristine lab
          snapshots.
        </p>
      </div>

      <ChallengePanel
        title="Artifact triage sprint"
        difficultyLabel="Intermediate"
        description="Hunt a staged exfil marker inside DNS logs, then prove integrity with strings and grep."
        objectives={[
          "Navigate `/home/student/lab` and inspect `artifacts/dns_sample.pcap` metadata.",
          "Use `strings` / `grep` patterns from the lesson narrative.",
          "Type `win` in demo mode or satisfy the remote checker to fire verification.",
        ]}
      />

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <SandboxTerminal
            challengeId="dns-lab-v3"
            timeLimitSeconds={900}
            onChallengeComplete={() => {
              setVerify({
                state: "passed",
                message: "Challenge objective satisfied — hash chain matches instructor baseline.",
              });
            }}
            onConnectionChange={setWsOk}
          />
          <p className="text-xs text-indigo-300/80">
            Connection: {wsOk ? "WebSocket live" : "Offline / demo"} — tools like tcpdump/hexedit appear when the backend
            exposes them; local stub lists common analyst utilities.
          </p>
        </div>
        <div className="space-y-4">
          <FileExplorer />
          <VerificationPanel
            state={verify.state}
            message={verify.message}
            hashHint={verify.state === "passed" ? "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" : undefined}
          />
        </div>
      </div>
    </div>
  );
}
