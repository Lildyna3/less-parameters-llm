import type { ReactNode } from "react";

export function StatusDot({ state, label }: { state?: string; label?: string }) {
  const color =
    state === "ONLINE" ? "bg-online" :
    state === "DEGRADED" ? "bg-warn" : "bg-offline";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${color} ${state === "ONLINE" ? "" : state === "DEGRADED" ? "pulse" : ""}`} />
      {label && <span className="text-[11px] font-medium text-dim">{label}</span>}
    </span>
  );
}

export function BiasTag({ bias }: { bias: string }) {
  const cls =
    bias === "bullish" ? "text-bull border-bull/30 bg-bull/10" :
    bias === "bearish" ? "text-bear border-bear/30 bg-bear/10" :
    "text-dim border-line bg-inset";
  return (
    <span className={`chip !border ${cls}`} style={{ background: undefined }}>
      {bias.toUpperCase()}
    </span>
  );
}

export function Confidence({ score, size = "md" }: { score: number; size?: "sm" | "md" }) {
  const h = size === "sm" ? "h-1" : "h-1.5";
  return (
    <span className="inline-flex items-center gap-1" title={`Confidence ${score}/5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          className={`${h} w-3 rounded-sm ${i <= score
            ? score >= 4 ? "bg-bull" : score === 3 ? "bg-warn" : "bg-bear"
            : "bg-line-strong/40"}`}
        />
      ))}
      <span className="ml-1 text-[11px] font-semibold text-dim num">{score}/5</span>
    </span>
  );
}

export function Stat({ label, value, tone, sub }: {
  label: string; value: ReactNode; tone?: "bull" | "bear" | "dim"; sub?: string;
}) {
  const color = tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-ink";
  return (
    <div className="min-w-0">
      <div className="text-[10.5px] font-semibold uppercase tracking-wider text-faint">{label}</div>
      <div className={`text-[15px] font-semibold num ${color}`}>{value}</div>
      {sub && <div className="text-[11px] text-faint">{sub}</div>}
    </div>
  );
}

export function PanelTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-line px-3.5 py-2.5">
      <h3 className="text-[11px] font-bold uppercase tracking-[0.12em] text-dim">{children}</h3>
      {right}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-8 text-center text-[12.5px] text-faint">{children}</div>;
}

export function pl(value: number | null | undefined): { text: string; tone: "bull" | "bear" | "dim" } {
  if (value == null) return { text: "—", tone: "dim" };
  return { text: `${value >= 0 ? "+" : ""}${value.toFixed(2)}`, tone: value >= 0 ? "bull" : "bear" };
}

export function fmtPrice(value: number | null | undefined, digits = 5): string {
  if (value == null) return "—";
  return value.toFixed(value > 500 ? 2 : digits);
}
