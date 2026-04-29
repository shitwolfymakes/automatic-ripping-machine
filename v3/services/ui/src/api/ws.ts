// Minimal UI WS client used by the transcodes store for live progress.
//
// Single shared connection per page; subscribes to topics on demand. Auth
// uses the JWT stored in localStorage by the auth store. Reconnects with
// exponential backoff (capped at 30s); replays subscriptions on every
// reconnect.

import { getToken } from "./client";

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 30000];

export interface WSEnvelope {
  op: "event";
  event_id: string;
  event_type: string;
  emitted_at: string;
  topic: string;
  job_id: string | null;
  track_id: string | null;
  payload: Record<string, unknown>;
}

type Handler = (env: WSEnvelope) => void;

class WSConnection {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Set<Handler>> = new Map();
  private connected = false;
  private retryIdx = 0;
  private reconnectTimer: number | null = null;
  private stopping = false;

  start(): void {
    if (this.ws !== null) return;
    this.stopping = false;
    this.connect();
  }

  stop(): void {
    this.stopping = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws !== null) {
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
  }

  subscribe(topic: string, handler: Handler): () => void {
    let set = this.handlers.get(topic);
    if (set === undefined) {
      set = new Set();
      this.handlers.set(topic, set);
      if (this.connected) this.send({ op: "subscribe", topic });
    }
    set.add(handler);
    return () => {
      const s = this.handlers.get(topic);
      if (s === undefined) return;
      s.delete(handler);
      if (s.size === 0) {
        this.handlers.delete(topic);
        if (this.connected) this.send({ op: "unsubscribe", topic });
      }
    };
  }

  private connect(): void {
    if (this.stopping) return;
    const token = getToken();
    if (!token) {
      // No auth — wait for login. Auth store calls .start() post-login.
      return;
    }
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const base = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
    let url: string;
    if (base) {
      url = base.replace(/^http/, "ws") + "/ws";
    } else {
      url = `${proto}//${window.location.host}/ws`;
    }
    const ws = new WebSocket(url);
    this.ws = ws;
    ws.addEventListener("open", () => {
      ws.send(JSON.stringify({ op: "auth", token }));
    });
    ws.addEventListener("message", (ev) => {
      this.onMessage(ev.data);
    });
    ws.addEventListener("close", () => {
      this.connected = false;
      this.ws = null;
      if (!this.stopping) {
        const delay = RECONNECT_DELAYS[Math.min(this.retryIdx, RECONNECT_DELAYS.length - 1)];
        this.retryIdx += 1;
        this.reconnectTimer = window.setTimeout(() => {
          this.reconnectTimer = null;
          this.connect();
        }, delay);
      }
    });
    ws.addEventListener("error", () => {
      // Close handler runs the reconnect.
    });
  }

  private onMessage(raw: unknown): void {
    if (typeof raw !== "string") return;
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }
    if (msg.op === "ack" && msg.topic === "") {
      // Initial auth ack — replay subscriptions.
      this.connected = true;
      this.retryIdx = 0;
      for (const topic of this.handlers.keys()) {
        this.send({ op: "subscribe", topic });
      }
      return;
    }
    if (msg.op !== "event") return;
    const env = msg as unknown as WSEnvelope;
    const set = this.handlers.get(env.topic);
    if (set === undefined) return;
    for (const handler of set) {
      try {
        handler(env);
      } catch (e) {
        // never let one bad handler poison the demux loop
        console.error("WS handler raised", env.topic, e);
      }
    }
  }

  private send(msg: Record<string, unknown>): void {
    if (this.ws === null || !this.connected) return;
    try {
      this.ws.send(JSON.stringify(msg));
    } catch {
      // best-effort; reconnect will replay
    }
  }
}

export const wsClient = new WSConnection();
