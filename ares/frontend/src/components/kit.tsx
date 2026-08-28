import type { ReactNode } from "react";

/* ARES UI kit — the shared primitives of the executive design language.
   Everything here is deliberately quiet: hairlines, small caps labels, one
   brass accent, semantic colour used only to carry meaning. */

export function Dot({ state }: { state?: string }) {
  const tone =
    state === "ONLINE" || state === "CONNECTED" ? "bg-online" :
    state === "DEGRADED" || state === "CONNECTING" ? "bg-warn" : "bg-offline";
  const live = state === "DEGRADED" || state === "CONNECTING";
  return <span className={`h-[5px] w-[5px] shrink-0 rounded-full ${tone} ${live ? "breathe" : ""}`} />;
}

export function StatusPill({ label, state, detail }: { label: string; state?: string; detail?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5" title={detail ?? state}>
      <Dot state={state} />
      <span className="label !text-[9.5px] !tracking-[0.1em]">{label}</span>
    </span>
  );
}

export function Tag({ children, tone, title }: {
  children: ReactNode; tone?: "accent" | "bull" | "bear" | "warn" | "danger" | "muted"; title?: string;
}) {
  const cls =
    tone === "accent" ? "!text-accent !border-[var(--accent-line)] !bg-[var(--accent-dim)]" :
    tone === "bull" ? "!text-bull" :
    tone === "bear" ? "!text-bear" :
    tone === "warn" ? "!text-warn" :
    tone === "danger" ? "!text-danger" : "";
  return <span className={`tag ${cls}`} title={title}>{children}</span>;
}

export function Bias({ bias }: { bias: string }) {
  const tone = bias === "bullish" ? "bull" : bias === "bearish" ? "bear" : "muted";
  const glyph = bias === "bullish" ? "▲" : bias === "bearish" ? "▼" : "—";
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11.5px] font-semibold ${
      bias === "bullish" ? "text-bull" : bias === "bearish" ? "text-bear" : "text-dim"}`}>
      <span className="text-[9px]">{glyph}</span>{bias}
      <span className="hidden">{tone}</span>
    </span>
  );
}

/** Confidence as five hairline segments — legible at a glance, no gauge chrome. */
export function Confidence({ score, showLabel = true }: { score: number; showLabel?: boolean }) {
  const tone = score >= 4 ? "bg-bull" : score === 3 ? "bg-warn" : "bg-bear";
  return (
    <span className="inline-flex items-center gap-1.5" title={`Confidence ${score} of 5`}>
      <span className="flex gap-[3px]">
        {[1, 2, 3, 4, 5].map((i) => (
          <span key={i} className={`h-[3px] w-[9px] rounded-full ${i <= score ? tone : "bg-line-strong"}`} />
        ))}
      </span>
      {showLabel && <span className="num text-[11px] text-dim">{score}/5</span>}
    </span>
  );
}

export function Metric({ label, value, tone, sub, large }: {
  label: string; value: ReactNode; tone?: "bull" | "bear" | "accent" | "dim"; sub?: string; large?: boolean;
}) {
  const color =
    tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" :
    tone === "accent" ? "text-accent" : tone === "dim" ? "text-dim" : "text-ink";
  return (
    <div className="min-w-0">
      <div className="label">{label}</div>
      <div className={`num mt-1 ${large ? "text-[22px]" : "text-[15px]"} font-medium leading-none ${color}`}>
        {value}
      </div>
      {sub && <div className="mt-1 text-[10.5px] text-faint">{sub}</div>}
    </div>
  );
}

export function PanelHeader({ children, right, dense }: {
  children: ReactNode; right?: ReactNode; dense?: boolean;
}) {
  return (
    <header className={`flex items-center justify-between gap-3 border-b border-line px-4 ${dense ? "py-2" : "py-3"}`}>
      <h2 className="label">{children}</h2>
      {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
    </header>
  );
}

export function Empty({ children, tone }: { children: ReactNode; tone?: "warn" }) {
  return (
    <div className={`px-4 py-10 text-center text-[12px] leading-relaxed ${
      tone === "warn" ? "text-warn" : "text-faint"}`}>
      {children}
    </div>
  );
}

/** Explicit unavailability. ARES states the real reason rather than showing
    a placeholder value that could be mistaken for data. */
export function Unavailable({ what, reason }: { what: string; reason?: string }) {
  return (
    <div className="px-4 py-8 text-center">
      <div className="label !text-offline">{what} unavailable</div>
      {reason && <p className="mx-auto mt-2 max-w-sm text-[11.5px] leading-relaxed text-faint">{reason}</p>}
    </div>
  );
}

export function Impact({ level }: { level: string }) {
  const tone =
    level === "CRITICAL" ? "danger" : level === "HIGH" ? "warn" :
    level === "MODERATE" ? "accent" : "muted";
  return <Tag tone={tone as never}>{level}</Tag>;
}

/* ---- formatting helpers ---- */

export function signed(value: number | null | undefined, digits = 2): { text: string; tone: "bull" | "bear" | "dim" } {
  if (value == null || Number.isNaN(value)) return { text: "—", tone: "dim" };
  const text = `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
  return { text, tone: value > 0 ? "bull" : value < 0 ? "bear" : "dim" };
}

export function price(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1000) return value.toFixed(2);
  if (value >= 100) return value.toFixed(3);
  return value.toFixed(5);
}

export function ago(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function clock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toISOString().slice(11, 16);
}

export function duration(fromIso: string): string {
  const start = Date.parse(fromIso);
  if (Number.isNaN(start)) return "—";
  const minutes = Math.max(0, Math.floor((Date.now() - start) / 60000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours}h ${minutes % 60}m` : `${Math.floor(hours / 24)}d ${hours % 24}h`;
}
