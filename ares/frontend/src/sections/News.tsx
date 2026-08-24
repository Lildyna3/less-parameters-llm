import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import type { CalendarEvent } from "../lib/types";
import { Empty, PanelTitle } from "../components/ui";

export default function News() {
  const status = useAres((s) => s.status);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [note, setNote] = useState("");
  const [form, setForm] = useState({ title: "", currency: "USD", impact: "high", scheduled_at: "" });

  const load = () =>
    void api.get<{ events: CalendarEvent[]; note: string }>("/api/calendar")
      .then((d) => { setEvents(d.events); setNote(d.note); })
      .catch(() => {});

  useEffect(() => { load(); }, []);

  const addEvent = async () => {
    if (!form.title || !form.scheduled_at) return;
    await api.post("/api/calendar/events", {
      ...form,
      scheduled_at: new Date(form.scheduled_at).toISOString(),
    });
    setForm({ title: "", currency: "USD", impact: "high", scheduled_at: "" });
    load();
  };

  const web = status?.web_intelligence;

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 overflow-y-auto p-3 lg:grid-cols-[1fr_320px]">
      <div className="panel">
        <PanelTitle>Economic Calendar</PanelTitle>
        {events.length === 0 ? (
          <Empty>{note || "No upcoming events."}</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-line text-left text-[10.5px] uppercase tracking-wider text-faint">
                  <th className="px-3.5 py-2">Time (UTC)</th><th className="px-2 py-2">Ccy</th>
                  <th className="px-2 py-2">Event</th><th className="px-2 py-2">Impact</th>
                  <th className="px-2 py-2 text-right">Prev</th><th className="px-2 py-2 text-right">Forecast</th>
                  <th className="px-2 py-2 text-right">Actual</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id} className="border-b border-line/50 last:border-0">
                    <td className="px-3.5 py-2 num text-dim">{e.scheduled_at.replace("T", " ").slice(5, 16)}</td>
                    <td className="px-2 py-2 font-bold num">{e.currency}</td>
                    <td className="px-2 py-2">{e.title}</td>
                    <td className="px-2 py-2">
                      <span className={`chip ${e.impact === "high" ? "!text-bear" : e.impact === "medium" ? "!text-warn" : ""}`}>
                        {e.impact}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right num text-faint">{e.previous ?? "—"}</td>
                    <td className="px-2 py-2 text-right num text-faint">{e.forecast ?? "—"}</td>
                    <td className="px-2 py-2 text-right num">{e.actual ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-3">
        <div className="panel">
          <PanelTitle>Web Intelligence</PanelTitle>
          <div className="p-3.5 text-[12px] text-dim">
            {web?.state === "ONLINE"
              ? "Web research layer is online."
              : <>Web intelligence is currently unavailable.<div className="mt-1 text-[11px] text-faint">{web?.reason}</div></>}
          </div>
        </div>

        <div className="panel">
          <PanelTitle>Add Calendar Event</PanelTitle>
          <div className="space-y-2 p-3.5">
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Event title (e.g. NFP)"
              className="w-full rounded-md border border-line bg-inset px-2 py-1.5 text-[12px] outline-none focus:border-accent/60" />
            <div className="grid grid-cols-2 gap-2">
              <input value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
                placeholder="USD" maxLength={3}
                className="rounded-md border border-line bg-inset px-2 py-1.5 text-[12px] outline-none focus:border-accent/60" />
              <select value={form.impact} onChange={(e) => setForm({ ...form, impact: e.target.value })}
                className="rounded-md border border-line bg-inset px-2 py-1.5 text-[12px] outline-none">
                <option value="high">high</option><option value="medium">medium</option><option value="low">low</option>
              </select>
            </div>
            <input type="datetime-local" value={form.scheduled_at}
              onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
              className="w-full rounded-md border border-line bg-inset px-2 py-1.5 text-[12px] outline-none focus:border-accent/60" />
            <button onClick={() => void addEvent()}
              className="w-full rounded-lg bg-accent/12 py-2 text-[11.5px] font-bold text-accent hover:bg-accent/20">
              Add event
            </button>
            <div className="text-[10.5px] text-faint">
              ARES never fabricates news — the calendar holds only events you add or a licensed feed provides.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
