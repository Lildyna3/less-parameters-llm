import { useAres } from "../store";
import type { Section } from "../lib/types";

const ITEMS: { id: Section; label: string; icon: string }[] = [
  { id: "command", label: "Command", icon: "⌘" },
  { id: "markets", label: "Markets", icon: "≋" },
  { id: "chart", label: "Chart", icon: "◫" },
  { id: "scanner", label: "Scanner", icon: "◎" },
  { id: "positions", label: "Positions", icon: "▤" },
  { id: "journal", label: "Journal", icon: "✎" },
  { id: "analytics", label: "Analytics", icon: "∿" },
  { id: "news", label: "News", icon: "◍" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

export default function SideNav() {
  const { section, setSection } = useAres();
  return (
    <>
      {/* Desktop rail */}
      <nav className="hidden w-[76px] shrink-0 flex-col items-stretch gap-0.5 border-r border-line bg-elev py-2 md:flex">
        {ITEMS.map((item) => (
          <button
            key={item.id}
            onClick={() => setSection(item.id)}
            className={`mx-1.5 flex flex-col items-center gap-0.5 rounded-lg px-1 py-2 transition-colors ${
              section === item.id
                ? "bg-accent/12 text-accent"
                : "text-faint hover:bg-inset hover:text-dim"
            }`}
          >
            <span className="text-[16px] leading-none">{item.icon}</span>
            <span className="text-[9.5px] font-semibold tracking-wide">{item.label}</span>
          </button>
        ))}
      </nav>

      {/* Mobile bottom bar (priority items) */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex justify-around border-t border-line bg-elev py-1.5 md:hidden">
        {ITEMS.filter((i) => ["command", "chart", "markets", "positions", "settings"].includes(i.id)).map((item) => (
          <button
            key={item.id}
            onClick={() => setSection(item.id)}
            className={`flex flex-col items-center gap-0.5 rounded-md px-3 py-1 ${
              section === item.id ? "text-accent" : "text-faint"
            }`}
          >
            <span className="text-[16px] leading-none">{item.icon}</span>
            <span className="text-[9px] font-semibold">{item.label}</span>
          </button>
        ))}
      </nav>
    </>
  );
}
