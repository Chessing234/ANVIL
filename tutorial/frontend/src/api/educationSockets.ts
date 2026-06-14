import type { LearnWsEnvelope, SandboxWsMessage } from "@/types/education";

import { readApiBaseUrl, resolvePublicApiUrl } from "@/api/client";

function readApiKey(): string {
  return (
    import.meta.env.VITE_API_KEY ||
    (typeof localStorage !== "undefined" ? localStorage.getItem("tutorial_api_key") : null) ||
    "tutorial-demo-key"
  );
}

export function buildSandboxTerminalWsUrl(): string {
  const explicit = import.meta.env.VITE_SANDBOX_WS_URL as string | undefined;
  if (explicit) return explicit;
  const u = resolvePublicApiUrl(readApiBaseUrl());
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = `${u.pathname.replace(/\/$/, "")}/sandbox/terminal`;
  u.searchParams.set("api_key", readApiKey());
  return u.toString();
}

export function buildLearnProgressWsUrl(): string {
  const explicit = import.meta.env.VITE_LEARN_WS_URL as string | undefined;
  if (explicit) return explicit;
  const u = resolvePublicApiUrl(readApiBaseUrl());
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = `${u.pathname.replace(/\/$/, "")}/ws/learn`;
  u.searchParams.set("api_key", readApiKey());
  return u.toString();
}

export class LearnProgressClient {
  private ws: WebSocket | null = null;

  private listeners = new Set<(msg: LearnWsEnvelope) => void>();

  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  private readonly maxAttempts = 8;

  private attempts = 0;

  private allowReconnect = true;

  connect(): void {
    this.allowReconnect = true;
    this.attempts = 0;
    this.scheduleOpen(0);
  }

  private scheduleOpen(delayMs: number): void {
    if (!this.allowReconnect) return;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this.open(), delayMs);
  }

  private open(): void {
    if (!this.allowReconnect) return;
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }
    try {
      this.ws = new WebSocket(buildLearnProgressWsUrl());
    } catch {
      this.bumpReconnect();
      return;
    }
    this.ws.onmessage = (ev: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(ev.data) as LearnWsEnvelope;
        for (const cb of this.listeners) cb(msg);
      } catch {
        /* ignore */
      }
    };
    this.ws.onopen = () => {
      this.attempts = 0;
    };
    this.ws.onclose = () => {
      this.ws = null;
      if (this.allowReconnect) this.bumpReconnect();
    };
    this.ws.onerror = () => {
      /* onclose handles */
    };
  }

  private bumpReconnect(): void {
    if (!this.allowReconnect) return;
    if (this.attempts >= this.maxAttempts) return;
    this.attempts += 1;
    this.scheduleOpen(2500);
  }

  subscribe(cb: (msg: LearnWsEnvelope) => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  disconnect(): void {
    this.allowReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }
}

export const learnProgressClient = new LearnProgressClient();

export function mapRawToSandboxMessage(raw: string): SandboxWsMessage | null {
  try {
    return JSON.parse(raw) as SandboxWsMessage;
  } catch {
    return { type: "output", data: raw };
  }
}
