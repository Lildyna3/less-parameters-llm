import { useEffect, useState } from "react";
import { api, getToken, setToken } from "../lib/api";
import { useAres } from "../store";
import { requestNotificationPermission } from "../lib/ws";
import type { BridgeStatus, RiskSnapshot, StatusMap } from "../lib/types";
import { Dot, Empty, PanelHeader, Tag, ago } from "../components/kit";

/* Settings: a configuration centre organised into named sections, navigated
   by a quiet index on the left (a segmented scroller on a phone). */

type SectionId =
  | "general" | "connections" | "trading" | "risk" | "ai"
  | "notifications" | "interface" | "security" | "system";

const SECTIONS: { id: SectionId; label: string }[] = [
  { id: "general", label: "General" },
  { id: "connections", label: "Connections" },
  { id: "trading", label: "Trading" },
  { id: "risk", label: "Risk" },
  { id: "ai", label: "AI" },
  { id: "notifications", label: "Notifications" },
  { id: "interface", label: "Interface" },
  { id: "security", label: "Security" },
  { id: "system", label: "System" },
];

const LIMIT_FIELDS: { key: string; label: string; hint?: string }[] = [
  { key: "max_daily_loss", label: "Maximum daily loss", hint: "account currency" },
  { key: "max_drawdown_percent", label: "Maximum drawdown", hint: "percent of balance" },
  { key: "max_open_positions", label: "Maximum open positions" },
  { key: "max_exposure_lots", label: "Maximum exposure", hint: "lots" },
  { key: "max_trades_per_session", label: "Maximum trades per session" },
  { key: "max_position_size_lots", label: "Maximum position size", hint: "lots" },
  { key: "max_spread_points", label: "Maximum spread", hint: "points" },
  { key: "cooldown_seconds_after_loss", label: "Cooldown after a loss", hint: "seconds" },
];

function Row({ label, hint, children }: { label: string; hint?: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3 last:border-b-0">
      <div className="min-w-0 flex-1">
        <div className="text-[12.5px] text-ink">{label}</div>
        {hint && <div className="mt-0.5 text-[10.5px] leading-relaxed text-faint">{hint}</div>}
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </div>
  );
}

function Connections() {
  const [bridge, setBridge] = useState<BridgeStatus | null>(null);

  const load = () => {
    void api.get<BridgeStatus>("/api/bridge").then(setBridge).catch(() => setBridge(null));
  };
  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  if (!bridge) return <Empty>Connection status unavailable.</Empty>;

  const connected = bridge.state === "CONNECTED";
  const tone = connected ? "bull" : bridge.state === "CONNECTING" ? "warn" : "muted";

  return (
    <div>
      <Row label="MetaTrader 5" hint={`Access mode: ${bridge.access_mode}`}>
        <span className="inline-flex items-center gap-2">
          <Dot state={connected ? "CONNECTED" : bridge.state === "CONNECTING" ? "CONNECTING" : "OFFLINE"} />
          <Tag tone={tone as never}>{bridge.state}</Tag>
        </span>
      </Row>

      {bridge.attached && (
        <>
          <Row label="Bridge host" hint={`bridge v${bridge.bridge.bridge_version}`}>
            <span className="num text-[11.5px] text-dim">{bridge.bridge.host}</span>
          </Row>
          <Row label="Terminal state">
            <span className="num text-[11.5px] text-dim">{bridge.bridge.mt5_state}</span>
          </Row>
          {bridge.bridge.detail && (
            <Row label="Terminal detail">
              <span className="text-[11.5px] text-warn">{bridge.bridge.detail}</span>
            </Row>
          )}
        </>
      )}

      {bridge.account ? (
        <>
          <Row label="Broker">
            <span className="text-[11.5px] text-dim">{bridge.account.broker}</span>
          </Row>
          <Row label="Server">
            <span className="text-[11.5px] text-dim">{bridge.account.server}</span>
          </Row>
          <Row label="Account" hint="shown masked; ARES never displays the full login or password">
            <span className="num text-[11.5px] text-dim">{bridge.account.login_masked}</span>
          </Row>
          <Row label="Account type">
            <Tag tone={bridge.account.is_demo ? "bull" : "warn"}>
              {bridge.account.is_demo ? "DEMO" : "NOT VERIFIED AS DEMO"}
            </Tag>
          </Row>
        </>
      ) : (
        <Row
          label="No MT5 account attached"
          hint={bridge.last_error ?? bridge.instructions}
        >
          <Tag>{bridge.token_configured ? "AWAITING BRIDGE" : "TOKEN REQUIRED"}</Tag>
        </Row>
      )}

      {bridge.connected_since && (
        <Row label="Attached since">
          <span className="text-[11.5px] text-dim">{ago(bridge.connected_since)}</span>
        </Row>
      )}

      <div className="border-t border-line px-4 py-3">
        <div className="label">How the bridge works</div>
        <p className="mt-2 text-[11.5px] leading-relaxed text-faint">
          The official MetaTrader5 Python package only exists for Windows, so a Linux or
          cloud host can never drive the terminal directly. ARES instead runs a small
          bridge process on a Windows machine beside MetaTrader 5; it dials out to this
          backend over an authenticated WebSocket, so the Windows machine needs no open
          ports. Until that bridge attaches and its terminal reports a live broker
          connection, ARES shows MT5 as offline — it never displays a connection it does
          not have. Setup instructions are in <span className="num">docs/MT5_BRIDGE.md</span>.
        </p>
      </div>
    </div>
  );
}

function RiskLimits() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [state, setState] = useState<"idle" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void api.get<RiskSnapshot>("/api/risk").then((data) => {
      const next: Record<string, string> = {};
      for (const field of LIMIT_FIELDS) next[field.key] = String(data.limits[field.key] ?? "");
      setValues(next);
    }).catch(() => {});
  }, []);

  const save = async () => {
    const payload: Record<string, number> = {};
    for (const [key, value] of Object.entries(values)) {
      const parsed = parseFloat(value);
      if (!Number.isNaN(parsed)) payload[key] = parsed;
    }
    try {
      await api.post("/api/risk/limits", payload);
      setState("saved");
      setMessage(null);
      setTimeout(() => setState("idle"), 2200);
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Rejected");
    }
  };

  return (
    <div>
      {LIMIT_FIELDS.map((field) => (
        <Row key={field.key} label={field.label} hint={field.hint}>
          <input
            value={values[field.key] ?? ""}
            onChange={(event) => setValues({ ...values, [field.key]: event.target.value })}
            className="field num !w-[110px] text-right"
          />
        </Row>
      ))}
      <div className="flex items-center gap-3 px-4 py-3">
        <button onClick={() => void save()} className="btn btn-accent">
          {state === "saved" ? "Saved" : "Save limits"}
        </button>
        {state === "error" && (
          <span className="text-[11.5px] text-danger">
            {message ?? "Rejected"} — limits must be positive values.
          </span>
        )}
        <span className="ml-auto text-[10.5px] text-faint">
          Limits apply to every order, including authorized takeover sessions.
        </span>
      </div>
    </div>
  );
}

function Security() {
  const [hasToken, setHasToken] = useState(Boolean(getToken()));
  const [value, setValue] = useState("");
  const [protectedApi, setProtectedApi] = useState<boolean | null>(null);

  useEffect(() => {
    // Probe without a token to learn whether the server enforces one.
    void fetch("/api/status")
      .then((response) => setProtectedApi(response.status === 401))
      .catch(() => setProtectedApi(null));
  }, []);

  return (
    <div>
      <Row
        label="Access control"
        hint={
          protectedApi === null
            ? "Could not determine whether this deployment requires a token."
            : protectedApi
              ? "This deployment requires an access token. Requests without it are rejected."
              : "This deployment is open — anyone who can reach the URL can use ARES. Set ARES_ACCESS_TOKEN on the server before exposing it to the internet."
        }
      >
        <Tag tone={protectedApi ? "bull" : "warn"}>
          {protectedApi === null ? "UNKNOWN" : protectedApi ? "TOKEN REQUIRED" : "OPEN"}
        </Tag>
      </Row>
      <Row label="Token stored in this browser" hint="Stored locally only; never part of the app bundle.">
        <div className="flex items-center gap-2">
          {hasToken ? (
            <>
              <Tag tone="accent">SET</Tag>
              <button
                onClick={() => { setToken(null); setHasToken(false); }}
                className="btn h-7"
              >
                Forget
              </button>
            </>
          ) : (
            <>
              <input
                type="password"
                value={value}
                onChange={(event) => setValue(event.target.value)}
                placeholder="Access token"
                className="field !w-[160px]"
              />
              <button
                onClick={() => { setToken(value.trim()); setHasToken(Boolean(value.trim())); setValue(""); }}
                className="btn h-7"
              >
                Save
              </button>
            </>
          )}
        </div>
      </Row>
      <Row
        label="Credential handling"
        hint="MT5 credentials live only in the bridge machine's local .env. ARES never receives, displays, logs, or sends your password to any AI provider. Account logins are shown masked."
      />
    </div>
  );
}

function System({ status }: { status: StatusMap | null }) {
  if (!status) return <Empty>System status unavailable.</Empty>;
  return (
    <div>
      {Object.entries(status).map(([name, component]) => (
        <Row
          key={name}
          label={name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
          hint={component.reason}
        >
          <span className="inline-flex items-center gap-2">
            <Dot state={component.state} />
            <span className="label !text-[9.5px]">{component.state}</span>
          </span>
        </Row>
      ))}
    </div>
  );
}

export default function Settings() {
  const { theme, setTheme, status, refreshStatus } = useAres();
  const [active, setActive] = useState<SectionId>("connections");
  const [aiStatus, setAiStatus] = useState<string | null>(null);
  const [newsEnabled, setNewsEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    void refreshStatus();
    void api.get<{ status: { enabled: boolean } }>("/api/news")
      .then((data) => setNewsEnabled(data.status.enabled)).catch(() => {});
  }, [refreshStatus]);

  useEffect(() => {
    setAiStatus(status?.ai?.reason ?? null);
  }, [status]);

  const body = () => {
    switch (active) {
      case "general":
        return (
          <div>
            <Row label="Application" hint="ARES — private executive trading command center">
              <Tag tone="accent">v1.0</Tag>
            </Row>
            <Row label="Default instrument" hint="Restored on every device from this browser's storage">
              <span className="num text-[11.5px] text-dim">{useAres.getState().symbol}</span>
            </Row>
            <Row label="Default timeframe">
              <span className="num text-[11.5px] text-dim">{useAres.getState().timeframe}</span>
            </Row>
            <Row
              label="Data integrity"
              hint="ARES never fabricates prices, news, account data, or execution results. When something is unavailable it says so."
            />
          </div>
        );
      case "connections":
        return <Connections />;
      case "trading":
        return (
          <div>
            <Row label="Execution mode" hint="Live-money execution does not exist in this build. Orders are simulated against real quotes from the configured data source.">
              <Tag tone="accent">DEMO / PAPER</Tag>
            </Row>
            <Row label="Takeover Mode" hint="ARES may request autonomous execution at 4/5 evidence or better. You must authorize each session explicitly; hard caps on trades, total loss, and duration apply, and you can stop it instantly.">
              <Tag>AUTHORIZATION REQUIRED</Tag>
            </Row>
            <Row label="Order verification" hint="Every fill is priced from a fresh quote. A stale quote refuses the order rather than filling at an old price." />
          </div>
        );
      case "risk":
        return <RiskLimits />;
      case "ai":
        return (
          <div>
            <Row label="Provider" hint={aiStatus ?? "Configured with ARES_AI__PROVIDER and an API key on the server."}>
              <span className="inline-flex items-center gap-2">
                <Dot state={status?.ai?.state} />
                <span className="label !text-[9.5px]">{status?.ai?.state ?? "UNKNOWN"}</span>
              </span>
            </Row>
            <Row
              label="Role of the language model"
              hint="The provider only narrates analysis that ARES has already computed. Bias, confidence, and levels always come from the deterministic engine, so the model cannot invent a signal or trigger execution."
            />
            <Row label="Key handling" hint="API keys are read from the server environment, redacted from logs, and never sent to the browser." />
          </div>
        );
      case "notifications":
        return (
          <div>
            <Row label="Browser notifications" hint="Used for triggered alerts, risk events, and connection changes.">
              <button onClick={requestNotificationPermission} className="btn h-7">Enable</button>
            </Row>
            <Row label="News feed" hint={newsEnabled === false ? "Disabled in configuration." : status?.news?.reason ?? ""}>
              <span className="inline-flex items-center gap-2">
                <Dot state={status?.news?.state} />
                <span className="label !text-[9.5px]">{status?.news?.state ?? "UNKNOWN"}</span>
              </span>
            </Row>
          </div>
        );
      case "interface":
        return (
          <div>
            <Row label="Theme" hint="Persisted in this browser; switching never reloads the app.">
              <div className="flex gap-1.5">
                {(["dark", "light"] as const).map((option) => (
                  <button
                    key={option}
                    onClick={() => setTheme(option)}
                    className={`btn h-7 ${theme === option ? "btn-accent" : ""}`}
                  >
                    {option === "dark" ? "Dark" : "Light"}
                  </button>
                ))}
              </div>
            </Row>
            <Row label="Install as an app" hint="On iOS: Share → Add to Home Screen. On Android/desktop Chrome: the install icon in the address bar. ARES then launches standalone, full screen." />
            <Row label="State preservation" hint="Sections keep their state while you navigate: the chart is never re-initialised, and selected instrument, timeframe and filters persist." />
          </div>
        );
      case "security":
        return <Security />;
      case "system":
        return <System status={status} />;
    }
  };

  return (
    <div className="scroll-y h-full">
      <div className="mx-auto max-w-[1000px] p-4 pb-6">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[168px_1fr]">
          <nav className="lg:pt-1">
            <div className="scroll-x flex gap-1.5 lg:flex-col lg:gap-px">
              {SECTIONS.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActive(section.id)}
                  className={`shrink-0 rounded-md px-3 py-1.5 text-left text-[12.5px] transition-colors ${
                    active === section.id
                      ? "bg-s2 text-ink"
                      : "text-dim hover:bg-s2/60 hover:text-ink"
                  }`}
                >
                  {section.label}
                </button>
              ))}
            </div>
          </nav>

          <section className="panel">
            <PanelHeader>{SECTIONS.find((s) => s.id === active)?.label}</PanelHeader>
            {body()}
          </section>
        </div>
      </div>
    </div>
  );
}
