import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { buildSandboxTerminalWsUrl, mapRawToSandboxMessage } from "@/api/educationSockets";
import { Button } from "@/components/ui/button";

export interface SandboxTerminalProps {
  challengeId: string;
  timeLimitSeconds: number;
  onChallengeComplete?: () => void;
  onConnectionChange?: (connected: boolean) => void;
}

export function SandboxTerminal({
  challengeId,
  timeLimitSeconds,
  onChallengeComplete,
  onConnectionChange,
}: SandboxTerminalProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const demoRef = useRef(false);
  const lineBuf = useRef("");

  const [connected, setConnected] = useState(false);
  const [demo, setDemo] = useState(false);
  const [done, setDone] = useState(false);
  const [remaining, setRemaining] = useState(timeLimitSeconds);

  const applyConnected = useCallback(
    (v: boolean) => {
      setConnected(v);
      onConnectionChange?.(v);
    },
    [onConnectionChange],
  );

  useEffect(() => {
    demoRef.current = demo;
  }, [demo]);

  const append = useCallback((data: string) => {
    termRef.current?.write(data);
  }, []);

  const teardownWs = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const connectWs = useCallback(() => {
    teardownWs();
    const url = buildSandboxTerminalWsUrl();
    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      applyConnected(false);
      demoRef.current = true;
      setDemo(true);
      append("\r\n\x1b[33m[sandbox]\x1b[0m Socket error — demo shell. Type `help`.\r\n$ ");
      return;
    }
    wsRef.current = socket;
    socket.onopen = () => {
      applyConnected(true);
      append(`\r\n\x1b[32m[sandbox]\x1b[0m Connected — \x1b[1m${challengeId}\x1b[0m\r\n`);
      socket.send(JSON.stringify({ type: "hello", challengeId }));
    };
    socket.onmessage = (ev) => {
      const raw = typeof ev.data === "string" ? ev.data : "";
      const parsed = mapRawToSandboxMessage(raw);
      if (parsed?.type === "challenge_complete") {
        setDone(true);
        onChallengeComplete?.();
        append(`\r\n\x1b[32m${parsed.data}\x1b[0m\r\n`);
        return;
      }
      if (parsed?.type === "error") {
        append(`\r\n\x1b[31m${parsed.data}\x1b[0m\r\n`);
        return;
      }
      append(parsed?.data ?? raw);
    };
    socket.onclose = () => {
      applyConnected(false);
      append("\r\n\x1b[33m[sandbox]\x1b[0m Disconnected.\r\n");
    };
    socket.onerror = () => {
      applyConnected(false);
    };
  }, [append, applyConnected, challengeId, onChallengeComplete, teardownWs]);

  useEffect(() => {
    const el = hostRef.current;
    if (!el) return undefined;
    const term = new Terminal({
      cursorBlink: true,
      fontFamily: "JetBrains Mono, monospace",
      theme: { background: "#0f172a", foreground: "#e2e8f0", cursor: "#a855f7" },
      scrollback: 2000,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(el);
    termRef.current = term;
    fitRef.current = fit;
    fit.fit();
    term.writeln("\x1b[36m╔══════════════════════════════════════╗\x1b[0m");
    term.writeln("\x1b[36m║  Tutorial SOC — learner sandbox tty  ║\x1b[0m");
    term.writeln("\x1b[36m╚══════════════════════════════════════╝\x1b[0m");

    const disposable = term.onData((data) => {
      const ws = wsRef.current;
      const useDemo = demoRef.current || !ws || ws.readyState !== WebSocket.OPEN;
      if (useDemo) {
        if (data === "\r") {
          const cmd = lineBuf.current.trim();
          lineBuf.current = "";
          term.write("\r\n");
          if (cmd === "help") {
            term.writeln("ls  pwd  echo <msg>  win (complete)  strings file (stub)");
          } else if (cmd === "ls") {
            term.writeln("artifacts/  logs/  quarantine/");
          } else if (cmd === "pwd") {
            term.writeln("/home/student/lab");
          } else if (cmd.startsWith("echo ")) {
            term.writeln(cmd.slice(5));
          } else if (cmd === "win") {
            setDone(true);
            onChallengeComplete?.();
            term.writeln("\x1b[32mLocal challenge marked complete.\x1b[0m");
          } else if (cmd) {
            term.writeln(`\x1b[90m(stub)\x1b[0m ${cmd}`);
          }
          term.write("$ ");
        } else if (data === "\u007f") {
          if (lineBuf.current.length) {
            lineBuf.current = lineBuf.current.slice(0, -1);
            term.write("\b \b");
          }
        } else {
          lineBuf.current += data;
          term.write(data);
        }
        return;
      }
      ws.send(data);
    });

    const ro = new ResizeObserver(() => fit.fit());
    ro.observe(el);

    return () => {
      ro.disconnect();
      disposable.dispose();
      teardownWs();
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
    };
  }, [onChallengeComplete, teardownWs]);

  useEffect(() => {
    connectWs();
    return () => teardownWs();
  }, [challengeId, connectWs, teardownWs]);

  useEffect(() => {
    setRemaining(timeLimitSeconds);
    setDone(false);
  }, [timeLimitSeconds, challengeId]);

  useEffect(() => {
    if (done) return undefined;
    const id = window.setInterval(() => {
      setRemaining((s) => (s <= 1 ? 0 : s - 1));
    }, 1000);
    return () => window.clearInterval(id);
  }, [done]);

  const reset = () => {
    setDone(false);
    lineBuf.current = "";
    termRef.current?.reset();
    termRef.current?.writeln("\x1b[33m[sandbox]\x1b[0m Reset…\r\n");
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "reset", challengeId }));
    }
    demoRef.current = false;
    setDemo(false);
    connectWs();
    termRef.current?.write("$ ");
  };

  const enableDemo = () => {
    teardownWs();
    applyConnected(false);
    demoRef.current = true;
    setDemo(true);
    append("\r\n\x1b[33m[sandbox]\x1b[0m Demo shell — offline practice.\r\n$ ");
  };

  return (
    <div className="space-y-2">
      {done ? (
        <div className="rounded-lg border border-emerald-500/50 bg-emerald-500/15 px-3 py-2 text-center text-sm font-medium text-emerald-100">
          Challenge completed — nice work!
        </div>
      ) : null}
      {!connected && !demo ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-950/40 px-3 py-2 text-xs text-amber-100">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>Disconnected from sandbox host.</span>
          <Button type="button" size="sm" variant="secondary" className="ml-auto h-7" onClick={enableDemo}>
            Demo shell
          </Button>
          <Button type="button" size="sm" className="h-7 bg-indigo-600" onClick={connectWs}>
            Reconnect
          </Button>
        </div>
      ) : null}
      <div className="overflow-hidden rounded-xl border border-indigo-700/50 bg-slate-950 shadow-inner">
        <div ref={hostRef} className="h-[min(420px,55vh)] w-full" />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-indigo-200/80">
        <span>
          Timer: <strong className="text-indigo-50">{remaining}s</strong>
        </span>
        <Button type="button" size="sm" variant="outline" className="h-7 gap-1 border-indigo-700 text-indigo-50" onClick={reset}>
          <RotateCcw className="h-3.5 w-3.5" />
          Reset
        </Button>
      </div>
    </div>
  );
}
