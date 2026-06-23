// ARM Notifications — wizard + channel-editor shared form
// These are the building blocks the main App composes.

const { useState, useMemo, useEffect, useRef } = React;

// ── Small primitives ─────────────────────────────────────────────────────

function Field({ label, required, hint, children }) {
  return (
    <label className="block">
      <div className="text-[12px] font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
        {label}
        {required ? <span className="text-violet-400">*</span> : null}
      </div>
      {children}
      {hint ? <div className="mt-1 text-[11px] text-slate-500">{hint}</div> : null}
    </label>
  );
}

function TextInput(props) {
  const { className = "", ...rest } = props;
  return (
    <input
      type="text"
      {...rest}
      className={
        "w-full bg-[#1c1f37] border border-[#2d3458] rounded-md px-3 py-2 text-[13px] text-slate-100 " +
        "placeholder:text-slate-500 outline-none focus:border-violet-500 focus:bg-[#221f47] " +
        "transition-colors " + className
      }
    />
  );
}

function TextArea(props) {
  const { className = "", ...rest } = props;
  return (
    <textarea
      {...rest}
      className={
        "w-full bg-[#1c1f37] border border-[#2d3458] rounded-md px-3 py-2 text-[13px] text-slate-100 " +
        "placeholder:text-slate-500 outline-none focus:border-violet-500 focus:bg-[#221f47] " +
        "transition-colors resize-y min-h-[72px] font-mono " + className
      }
    />
  );
}

function Checkbox({ checked, onChange, label, description }) {
  return (
    <label className="flex items-start gap-2.5 cursor-pointer group">
      <span
        onClick={() => onChange(!checked)}
        className={
          "mt-0.5 inline-flex items-center justify-center w-[16px] h-[16px] rounded border transition-colors flex-shrink-0 " +
          (checked
            ? "bg-violet-500 border-violet-500"
            : "bg-[#1c1f37] border-[#3a4170] group-hover:border-violet-500")
        }
      >
        {checked ? (
          <svg viewBox="0 0 16 16" className="w-[12px] h-[12px] text-white">
            <path
              d="M3.5 8.5l3 3 6-7"
              stroke="currentColor"
              strokeWidth="2"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            ></path>
          </svg>
        ) : null}
      </span>
      <span className="min-w-0">
        <span className="block text-[13px] text-slate-200 leading-snug">{label}</span>
        {description ? (
          <span className="block text-[11px] text-slate-500 leading-snug mt-0.5">
            {description}
          </span>
        ) : null}
      </span>
    </label>
  );
}

function Radio({ checked, onChange, label }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <span
        onClick={onChange}
        className={
          "inline-flex items-center justify-center w-[16px] h-[16px] rounded-full border transition-colors " +
          (checked ? "border-violet-400" : "border-[#3a4170]")
        }
      >
        {checked ? <span className="w-[8px] h-[8px] rounded-full bg-violet-500"></span> : null}
      </span>
      <span className="text-[13px] text-slate-200">{label}</span>
    </label>
  );
}

function Toggle({ checked, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={
        "relative inline-flex h-[20px] w-[36px] items-center rounded-full transition-colors " +
        (checked ? "bg-violet-500" : "bg-[#2d3458]")
      }
    >
      <span
        className={
          "inline-block h-[14px] w-[14px] transform rounded-full bg-white shadow transition-transform " +
          (checked ? "translate-x-[19px]" : "translate-x-[3px]")
        }
      ></span>
    </button>
  );
}

function Button({ variant = "primary", className = "", children, ...rest }) {
  const variants = {
    primary:
      "bg-violet-500 hover:bg-violet-600 text-white shadow-[0_4px_14px_-4px_rgba(139,92,246,0.6)]",
    secondary:
      "bg-[#222845] hover:bg-[#2a3258] text-slate-200 border border-[#2d3458]",
    ghost: "bg-transparent hover:bg-[#222845] text-slate-300",
    danger: "bg-transparent hover:bg-red-500/10 text-red-400 border border-transparent hover:border-red-500/40",
    chip:
      "bg-violet-500/10 hover:bg-violet-500/20 text-violet-300 border border-violet-500/30 font-mono text-[11px]",
  };
  return (
    <button
      {...rest}
      className={
        "inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-[12.5px] font-medium transition-all whitespace-nowrap " +
        variants[variant] +
        " " +
        className
      }
    >
      {children}
    </button>
  );
}

function StatusDot({ status }) {
  // ok | warn | error | off
  const map = {
    ok: "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]",
    warn: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]",
    error: "bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.6)]",
    off: "bg-slate-600",
  };
  return <span className={"inline-block w-[8px] h-[8px] rounded-full " + map[status]}></span>;
}

function Pill({ children, tone = "default" }) {
  const tones = {
    default: "bg-[#222845] text-slate-300 border-[#2d3458]",
    violet: "bg-violet-500/10 text-violet-300 border-violet-500/30",
    blue: "bg-blue-500/10 text-blue-300 border-blue-500/30",
    amber: "bg-amber-500/10 text-amber-300 border-amber-500/30",
    green: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  };
  return (
    <span
      className={
        "inline-flex items-center gap-1 px-2 py-[2px] rounded text-[10.5px] font-medium border " +
        tones[tone]
      }
    >
      {children}
    </span>
  );
}

// Service-icon "logo" placeholder — a colored monogram square. Each service id
// gets a stable hue from a hash; deliberately monogram-only (we don't have
// the real brand marks, which would be copyright).
function ServiceGlyph({ id, name, size = 32 }) {
  const hash = useMemo(() => {
    let h = 0;
    for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
    return h;
  }, [id]);
  const hue = hash % 360;
  const bg = `oklch(0.45 0.13 ${hue})`;
  const accent = `oklch(0.78 0.16 ${hue})`;
  return (
    <span
      style={{ width: size, height: size, background: bg, color: accent }}
      className="inline-flex items-center justify-center rounded-md font-bold text-[13px] tracking-tight flex-shrink-0 border border-white/5"
    >
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}

// ── Wizard ──────────────────────────────────────────────────────────────

function Stepper({ steps, current }) {
  return (
    <ol className="flex items-center gap-0 w-full">
      {steps.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={s} className="flex items-center flex-1 last:flex-none">
            <div className="flex items-center gap-2.5 min-w-0">
              <span
                className={
                  "inline-flex items-center justify-center w-[24px] h-[24px] rounded-full text-[11px] font-semibold transition-colors flex-shrink-0 " +
                  (active
                    ? "bg-violet-500 text-white"
                    : done
                    ? "bg-violet-500/20 text-violet-300 border border-violet-500/40"
                    : "bg-[#1c1f37] text-slate-500 border border-[#2d3458]")
                }
              >
                {done ? (
                  <svg viewBox="0 0 16 16" className="w-[11px] h-[11px]" fill="none">
                    <path
                      d="M3.5 8.5l3 3 6-7"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    ></path>
                  </svg>
                ) : (
                  i + 1
                )}
              </span>
              <span
                className={
                  "text-[12.5px] font-medium tracking-wide whitespace-nowrap transition-colors " +
                  (active ? "text-slate-100" : done ? "text-violet-300" : "text-slate-500")
                }
              >
                {s}
              </span>
            </div>
            {i < steps.length - 1 ? (
              <div
                className={
                  "flex-1 h-[1px] mx-3 transition-colors " +
                  (done ? "bg-violet-500/40" : "bg-[#2d3458]")
                }
              ></div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function ServiceDropdown({ services, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef(null);
  useEffect(() => {
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const featured = services.filter((s) => s.featured);
  const rest = services.filter((s) => !s.featured);
  const byCat = rest.reduce((acc, s) => {
    (acc[s.category] = acc[s.category] || []).push(s);
    return acc;
  }, {});

  const filterFn = (s) =>
    !query ||
    s.name.toLowerCase().includes(query.toLowerCase()) ||
    s.category.toLowerCase().includes(query.toLowerCase());

  const selected = services.find((s) => s.id === value);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={
          "w-full flex items-center justify-between gap-3 bg-[#1c1f37] border border-[#2d3458] " +
          "rounded-md px-3 py-2.5 text-left text-[13px] hover:border-violet-500/60 transition-colors " +
          (open ? "border-violet-500" : "")
        }
      >
        {selected ? (
          <span className="flex items-center gap-2.5 min-w-0">
            <ServiceGlyph id={selected.id} name={selected.name} size={22} />
            <span className="min-w-0">
              <span className="block text-slate-100 truncate">{selected.name}</span>
              <span className="block text-[11px] text-slate-500">{selected.category}</span>
            </span>
          </span>
        ) : (
          <span className="text-slate-500">Select a service…</span>
        )}
        <svg
          viewBox="0 0 16 16"
          className={"w-[14px] h-[14px] text-slate-400 transition-transform " + (open ? "rotate-180" : "")}
          fill="none"
        >
          <path
            d="M3.5 6l4.5 4.5L12.5 6"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          ></path>
        </svg>
      </button>

      {open ? (
        <div className="absolute z-20 mt-1 left-0 right-0 bg-[#161b2d] border border-[#2d3458] rounded-md shadow-2xl shadow-black/60 overflow-hidden">
          <div className="p-2 border-b border-[#2d3458] sticky top-0 bg-[#161b2d]">
            <div className="relative">
              <svg
                viewBox="0 0 16 16"
                className="w-[13px] h-[13px] absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500"
                fill="none"
              >
                <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5"></circle>
                <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"></path>
              </svg>
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search services…"
                className="w-full bg-[#1c1f37] border border-[#2d3458] rounded pl-7 pr-2 py-1.5 text-[12px] text-slate-100 outline-none focus:border-violet-500"
              />
            </div>
          </div>
          <div className="max-h-[280px] overflow-y-auto">
            {featured.filter(filterFn).length ? (
              <div>
                <div className="px-3 pt-2 pb-1 text-[10px] font-semibold text-violet-400 tracking-[0.12em] uppercase flex items-center gap-1.5">
                  <svg viewBox="0 0 16 16" className="w-[10px] h-[10px]" fill="currentColor">
                    <path d="M8 1l2.2 4.5L15 6.3l-3.5 3.4.8 4.8L8 12.3 3.7 14.5l.8-4.8L1 6.3l4.8-.8L8 1z"></path>
                  </svg>
                  Featured
                </div>
                {featured.filter(filterFn).map((s) => (
                  <ServiceOption
                    key={s.id}
                    service={s}
                    active={s.id === value}
                    onClick={() => {
                      onChange(s.id);
                      setOpen(false);
                    }}
                  />
                ))}
              </div>
            ) : null}
            {Object.entries(byCat).map(([cat, list]) => {
              const filtered = list.filter(filterFn);
              if (!filtered.length) return null;
              return (
                <div key={cat}>
                  <div className="px-3 pt-2 pb-1 text-[10px] font-semibold text-slate-500 tracking-[0.12em] uppercase">
                    {cat}
                  </div>
                  {filtered.map((s) => (
                    <ServiceOption
                      key={s.id}
                      service={s}
                      active={s.id === value}
                      onClick={() => {
                        onChange(s.id);
                        setOpen(false);
                      }}
                    />
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ServiceOption({ service, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors " +
        (active ? "bg-violet-500/15" : "hover:bg-[#1c1f37]")
      }
    >
      <ServiceGlyph id={service.id} name={service.name} size={22} />
      <span className="flex-1 min-w-0">
        <span className="block text-[13px] text-slate-100">{service.name}</span>
        <span className="block text-[10.5px] text-slate-500 font-mono">{service.scheme}://</span>
      </span>
      {active ? (
        <svg viewBox="0 0 16 16" className="w-[12px] h-[12px] text-violet-400" fill="none">
          <path
            d="M3.5 8.5l3 3 6-7"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          ></path>
        </svg>
      ) : null}
    </button>
  );
}

window.ARM_PRIMS = {
  Field, TextInput, TextArea, Checkbox, Radio, Toggle, Button,
  StatusDot, Pill, ServiceGlyph, Stepper, ServiceDropdown,
};
