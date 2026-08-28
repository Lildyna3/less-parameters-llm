import { api } from "./api";
import { useAres } from "../store";
import type { AccountSnapshot, AlertEvent, Tick } from "./types";

let socket: WebSocket | null = null;
let retryDelay = 1000;
let started = false;

/** Single managed WebSocket connection for the whole app (no duplicates). */
export function startWebSocket(): void {
  if (started) return;
  started = true;
  connect();
}

function connect(): void {
  const { setWsConnected, applyTicks, pushAlert, setAccount, refreshStatus } = useAres.getState();
  try {
    socket = new WebSocket(api.wsUrl());
  } catch {
    scheduleReconnect();
    return;
  }

  socket.onopen = () => {
    retryDelay = 1000;
    setWsConnected(true);
    void refreshStatus();
  };

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data as string) as { type: string; data: unknown };
      if (msg.type === "ticks") applyTicks(msg.data as Tick[]);
      else if (msg.type === "alert") {
        const alert = msg.data as AlertEvent;
        pushAlert(alert);
        notifyBrowser(alert);
      } else if (msg.type === "account") setAccount(msg.data as AccountSnapshot);
    } catch { /* malformed frame — ignore */ }
  };

  socket.onclose = () => {
    setWsConnected(false);
    scheduleReconnect();
  };
  socket.onerror = () => socket?.close();
}

function scheduleReconnect(): void {
  setTimeout(connect, retryDelay);
  retryDelay = Math.min(retryDelay * 2, 15000);
}

function notifyBrowser(alert: AlertEvent): void {
  if (alert.severity === "info") return;
  if (typeof Notification === "undefined") return;
  if (Notification.permission === "granted") {
    new Notification("ARES", { body: alert.message });
  }
}

export function requestNotificationPermission(): void {
  if (typeof Notification !== "undefined" && Notification.permission === "default") {
    void Notification.requestPermission();
  }
}
