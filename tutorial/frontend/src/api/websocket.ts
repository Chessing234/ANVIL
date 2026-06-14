import { readApiBaseUrl, resolvePublicApiUrl } from "@/api/client";
import type { WsEnvelope } from "@/types";

type WsListener = (payload: WsEnvelope) => void;

function buildWsUrl(): string {
  const explicit = import.meta.env.VITE_WS_URL;
  if (explicit) return explicit;
  const apiBase = readApiBaseUrl();
  const u = resolvePublicApiUrl(apiBase);
  const path = `${u.pathname.replace(/\/$/, "")}/ws/events`;
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = path;
  const key =
    import.meta.env.VITE_API_KEY ||
    (typeof localStorage !== "undefined" ? localStorage.getItem("tutorial_api_key") : null) ||
    "tutorial-demo-key";
  u.searchParams.set("api_key", key);
  return u.toString();
}

export class WebSocketClient {
  private readonly url = buildWsUrl();

  private ws: WebSocket | null = null;

  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  private readonly reconnectIntervalMs = 3000;

  private readonly maxReconnectAttempts = 10;

  private reconnectAttempts = 0;

  private readonly listeners = new Map<string, Set<WsListener>>();

  private shouldReconnect = true;

  connect(): void {
    this.shouldReconnect = true;
    this.openSocket();
  }

  private openSocket(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }
    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(event.data) as WsEnvelope;
        this.notifyListeners(msg.event, msg);
        this.notifyListeners("*", msg);
      } catch {
        /* ignore malformed */
      }
    };

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
    };

    this.ws.onerror = () => {
      /* onclose will handle reconnect */
    };

    this.ws.onclose = () => {
      this.ws = null;
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect) return;
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      return;
    }
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts += 1;
      this.openSocket();
    }, this.reconnectIntervalMs);
  }

  subscribe(eventType: string, callback: WsListener): () => void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(callback);
    return () => this.unsubscribe(eventType, callback);
  }

  unsubscribe(eventType: string, callback: WsListener): void {
    const set = this.listeners.get(eventType);
    if (!set) return;
    set.delete(callback);
    if (set.size === 0) this.listeners.delete(eventType);
  }

  private notifyListeners(eventType: string, msg: WsEnvelope): void {
    const set = this.listeners.get(eventType);
    if (!set) return;
    for (const cb of set) {
      try {
        cb(msg);
      } catch {
        /* listener errors are isolated */
      }
    }
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const wsClient = new WebSocketClient();
