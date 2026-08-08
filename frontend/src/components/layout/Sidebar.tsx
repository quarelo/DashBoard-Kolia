import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Lightbulb,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  LogOut,
} from "lucide-react";
import { cn } from "../../lib/utils";
import { KoliaLogo } from "../ui/KoliaLogo";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  { to: "/app/dashboard", icon: LayoutDashboard, label: "Dashboard Executivo", exact: true },
  { to: "/app/meetings",  icon: CalendarDays,    label: "Reuniões",             exact: false },
  { to: "/app/insights",  icon: Lightbulb,       label: "Insights",             exact: true },
  { to: "/app/chat",      icon: MessageSquare,   label: "Chat IA",              exact: true },
];

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  return (
    <aside
      className={cn(
        "flex flex-col h-screen flex-shrink-0 transition-all duration-300 ease-in-out",
        collapsed ? "w-[60px]" : "w-[220px]"
      )}
      style={{ backgroundColor: "#111827" }}
    >
      {/* ── Logo ─────────────────────────────────────────────── */}
      <div
        className={cn(
          "flex items-center flex-shrink-0 border-b",
          collapsed ? "justify-center px-3 py-4" : "px-5 py-4 gap-3"
        )}
        style={{ borderColor: "rgba(255,255,255,0.08)" }}
      >
        {collapsed ? (
          <KoliaLogo variant="icon" height={28} />
        ) : (
          <KoliaLogo variant="horizontal-light" height={28} />
        )}
      </div>

      {/* ── Navigation ───────────────────────────────────────── */}
      <nav className="flex-1 px-2 py-4 space-y-0.5 overflow-y-auto scrollbar-thin">
        {navItems.map(({ to, icon: Icon, label, exact }) => (
          <NavLink
            key={to}
            to={to}
            end={exact}
            title={collapsed ? label : undefined}
          >
            {({ isActive }) => (
              <span
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150",
                  collapsed && "justify-center",
                  isActive
                    ? "text-white"
                    : "text-gray-400 hover:text-gray-100"
                )}
                style={
                  isActive
                    ? { backgroundColor: "#E76B38", boxShadow: "0 2px 8px rgba(231,107,56,0.35)" }
                    : undefined
                }
                onMouseEnter={(e) => {
                  if (!isActive)
                    (e.currentTarget as HTMLElement).style.backgroundColor = "rgba(255,255,255,0.08)";
                }}
                onMouseLeave={(e) => {
                  if (!isActive)
                    (e.currentTarget as HTMLElement).style.backgroundColor = "transparent";
                }}
              >
                <Icon size={17} className="flex-shrink-0" />
                {!collapsed && <span className="truncate">{label}</span>}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* ── User section ─────────────────────────────────────── */}
      <div className="px-2 py-3 space-y-1">
        {!collapsed && (
          <div
            className="px-3 py-3 rounded-lg mb-1"
            style={{
              backgroundColor: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.08)",
            }}
          >
            <div className="flex items-center gap-2.5 mb-2">
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
                style={{ background: "linear-gradient(135deg, #E76B38, #D85D2B)" }}
              >
                C
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-white truncate">Carlos Andrade</p>
                <p className="text-[10px] text-gray-500 truncate">Diretor Comercial</p>
              </div>
            </div>
            <button className="w-full flex items-center gap-2 text-[11px] text-gray-500 hover:text-gray-300 transition-colors">
              <LogOut size={11} />
              Sair da conta
            </button>
          </div>
        )}

        {collapsed && (
          <div className="flex justify-center mb-1">
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold"
              style={{ background: "linear-gradient(135deg, #E76B38, #D85D2B)" }}
            >
              C
            </div>
          </div>
        )}

        {/* Collapse toggle */}
        <button
          onClick={onToggle}
          title={collapsed ? "Expandir menu" : undefined}
          className={cn(
            "w-full flex items-center px-3 py-2 rounded-lg text-xs font-medium transition-all duration-150 text-gray-500 hover:text-gray-200",
            collapsed ? "justify-center" : "gap-2"
          )}
          style={{ backgroundColor: "transparent" }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.backgroundColor = "rgba(255,255,255,0.08)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.backgroundColor = "transparent";
          }}
        >
          {collapsed
            ? <ChevronRight size={14} />
            : <><ChevronLeft size={14} /><span>Recolher menu</span></>
          }
        </button>
      </div>
    </aside>
  );
}
