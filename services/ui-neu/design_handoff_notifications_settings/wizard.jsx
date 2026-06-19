// ARM Notifications — Add Channel wizard + inline Channel Editor
// Both share the same form sections (Configure / Events / Templates).

const { useState: useStateW, useMemo: useMemoW, useEffect: useEffectW } = React;
const W = window.ARM_PRIMS;
const { EVENTS: WEVENTS, TEMPLATE_VARS: WVARS, SERVICES: WSERVICES } = window.ARM_DATA;

// ── Shared form sections ─────────────────────────────────────────────────

function ConfigureSection({ type, serviceId, name, setName, enabled, setEnabled, config, setConfig }) {
  const service = WSERVICES.find((s) => s.id === serviceId);
  const fields =
    type === "apprise"
      ? service?.fields ?? []
      : type === "webhook"
      ? [
          { key: "url", label: "Webhook URL", required: true, placeholder: "https://example.com/hook" },
          { key: "method", label: "HTTP Method", placeholder: "POST" },
          { key: "secret", label: "Shared Secret", secret: true, placeholder: "(optional) HMAC signing key" },
        ]
      : [
          { key: "path", label: "Script Path", required: true, placeholder: "/opt/arm/scripts/notify.sh" },
          { key: "args", label: "Arguments", placeholder: "(optional) --color --notify" },
        ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-[1fr_auto] gap-5 items-end">
        <W.Field label="Channel Label" required>
          <W.TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Discord — #arm-rips"
          />
        </W.Field>
        <div className="flex items-center gap-2 pb-2">
          <W.Toggle checked={enabled} onChange={setEnabled} />
          <span className="text-[13px] text-slate-300">Enabled</span>
        </div>
      </div>

      {fields.length ? (
        <div className="rounded-lg bg-[#13162a] border border-[#252b48] p-4">
          <div className="text-[11px] font-semibold text-violet-400 tracking-[0.12em] uppercase mb-3 flex items-center gap-2">
            {type === "apprise" ? (
              <>
                <W.ServiceGlyph id={service.id} name={service.name} size={18} />
                {service.name} configuration
                <span className="text-slate-500 font-mono normal-case tracking-normal text-[11px] ml-1">
                  {service.scheme}://…
                </span>
              </>
            ) : type === "webhook" ? (
              "Webhook configuration"
            ) : (
              "Bash script configuration"
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            {fields.map((f) => (
              <div key={f.key} className={f.key === "url" || f.key === "path" ? "col-span-2" : ""}>
                <W.Field label={f.label} required={f.required} hint={f.help}>
                  <W.TextInput
                    type={f.secret ? "password" : "text"}
                    value={config[f.key] ?? ""}
                    onChange={(e) => setConfig({ ...config, [f.key]: e.target.value })}
                    placeholder={f.placeholder ?? ""}
                  />
                </W.Field>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function EventsSection({ events, setEvents }) {
  const toggle = (key) =>
    setEvents(events.includes(key) ? events.filter((e) => e !== key) : [...events, key]);
  return (
    <div className="rounded-lg bg-[#13162a] border border-[#252b48] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] font-semibold text-violet-400 tracking-[0.12em] uppercase">
          Events
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setEvents(WEVENTS.map((e) => e.key))}
            className="text-[11px] text-slate-400 hover:text-violet-300"
          >
            Select all
          </button>
          <span className="text-slate-700">·</span>
          <button
            type="button"
            onClick={() => setEvents([])}
            className="text-[11px] text-slate-400 hover:text-violet-300"
          >
            Clear
          </button>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-y-3 gap-x-6">
        {WEVENTS.map((ev) => (
          <W.Checkbox
            key={ev.key}
            checked={events.includes(ev.key)}
            onChange={() => toggle(ev.key)}
            label={ev.label}
            description={ev.description}
          />
        ))}
      </div>
    </div>
  );
}

function TemplatesSection({ events, templates, setTemplates }) {
  const [openKey, setOpenKey] = useStateW(null);
  if (!events.length) {
    return (
      <div className="rounded-lg bg-[#13162a] border border-[#252b48] p-6 text-center">
        <div className="text-[12px] text-slate-500">
          No events subscribed. Pick at least one event above to customize templates.
        </div>
      </div>
    );
  }

  const subbedEvents = WEVENTS.filter((e) => events.includes(e.key));

  return (
    <div className="rounded-lg bg-[#13162a] border border-[#252b48]">
      <div className="px-4 pt-4 pb-3 border-b border-[#252b48]">
        <div className="text-[11px] font-semibold text-violet-400 tracking-[0.12em] uppercase">
          Message templates
          <span className="ml-2 text-slate-500 normal-case tracking-normal font-normal">
            optional — leave blank to use defaults
          </span>
        </div>
      </div>
      <div className="divide-y divide-[#252b48]">
        {subbedEvents.map((ev) => {
          const open = openKey === ev.key;
          const tpl = templates[ev.key] ?? {};
          const customized = !!(tpl.title || tpl.body);
          return (
            <div key={ev.key}>
              <button
                type="button"
                onClick={() => setOpenKey(open ? null : ev.key)}
                className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[#181b34] transition-colors"
              >
                <span className="flex items-center gap-3 min-w-0">
                  <svg
                    viewBox="0 0 16 16"
                    className={"w-[11px] h-[11px] text-slate-500 transition-transform flex-shrink-0 " + (open ? "rotate-90" : "")}
                    fill="none"
                  >
                    <path
                      d="M6 4l4 4-4 4"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    ></path>
                  </svg>
                  <span className="text-[13px] font-medium text-slate-200">{ev.label}</span>
                  {customized ? <W.Pill tone="violet">customized</W.Pill> : <W.Pill>default</W.Pill>}
                </span>
                <span className="text-[11px] text-slate-500 font-mono truncate max-w-[280px]">
                  {(tpl.title || ev.defaults.title)}
                </span>
              </button>
              {open ? (
                <div className="px-4 pb-4 pt-1 space-y-3">
                  <W.Field label="Title">
                    <W.TextInput
                      value={tpl.title ?? ""}
                      onChange={(e) =>
                        setTemplates({ ...templates, [ev.key]: { ...tpl, title: e.target.value } })
                      }
                      placeholder={ev.defaults.title}
                    />
                  </W.Field>
                  <W.Field label="Body">
                    <W.TextArea
                      value={tpl.body ?? ""}
                      onChange={(e) =>
                        setTemplates({ ...templates, [ev.key]: { ...tpl, body: e.target.value } })
                      }
                      placeholder={ev.defaults.body}
                    />
                  </W.Field>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] text-slate-500">Click to insert:</span>
                    {WVARS.map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => {
                          const cur = tpl.body ?? "";
                          setTemplates({
                            ...templates,
                            [ev.key]: { ...tpl, body: cur + (cur ? " " : "") + v },
                          });
                        }}
                        className="px-2 py-[3px] rounded text-[11px] font-mono bg-violet-500/10 border border-violet-500/30 text-violet-300 hover:bg-violet-500/20"
                      >
                        {v}
                      </button>
                    ))}
                    {customized ? (
                      <button
                        type="button"
                        onClick={() => {
                          const next = { ...templates };
                          delete next[ev.key];
                          setTemplates(next);
                        }}
                        className="ml-auto text-[11px] text-slate-500 hover:text-red-400"
                      >
                        Reset to default
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Add Channel form (unified, single screen) ────────────────────────────

function AddChannelWizard({ onCancel, onSave, onTest }) {
  const [type, setType] = useStateW("apprise");
  const [serviceId, setServiceId] = useStateW("discord");
  const [name, setName] = useStateW("");
  const [enabled, setEnabled] = useStateW(true);
  const [config, setConfig] = useStateW({});
  const [events, setEvents] = useStateW(["job.started"]);
  const [templates, setTemplates] = useStateW({});

  const service = WSERVICES.find((s) => s.id === serviceId);

  // Reset configure-section state when type changes — different fields apply.
  useEffectW(() => {
    setConfig({});
  }, [type, serviceId]);

  const requiredFields =
    type === "apprise"
      ? (service?.fields ?? []).filter((f) => f.required)
      : type === "webhook"
      ? [{ key: "url" }]
      : [{ key: "path" }];

  const missing = {
    name: !name.trim(),
    config: !requiredFields.every((f) => (config[f.key] ?? "").trim().length > 0),
    events: events.length === 0,
  };
  const canSave = !missing.name && !missing.config && !missing.events;

  function save() {
    const channel = {
      id: Date.now(),
      name: name.trim(),
      type,
      serviceId: type === "apprise" ? serviceId : null,
      enabled,
      config,
      events,
      templates,
      lastSentAt: null,
      lastStatus: "off",
      lastError: null,
      sent24h: 0,
      failed24h: 0,
    };
    onSave(channel);
  }

  return (
    <section className="rounded-xl border border-[#252b48] bg-[#161b2d] overflow-hidden shadow-[0_8px_40px_-12px_rgba(0,0,0,0.5)]">
      <header className="px-5 py-4 border-b border-[#252b48] flex items-center justify-between gap-4 bg-gradient-to-r from-violet-500/5 to-transparent">
        <div className="flex items-center gap-3 min-w-0">
          <span className="inline-flex items-center justify-center w-[28px] h-[28px] rounded-md bg-violet-500/15 text-violet-300">
            <svg viewBox="0 0 16 16" className="w-[14px] h-[14px]" fill="none">
              <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"></path>
            </svg>
          </span>
          <div className="min-w-0">
            <div className="text-[14px] font-semibold text-violet-300">Add notification channel</div>
            <div className="text-[11.5px] text-slate-500">
              Configure delivery, pick events, and customize templates — all in one place.
            </div>
          </div>
        </div>
        <button
          onClick={onCancel}
          className="text-slate-500 hover:text-slate-200 text-[12px] flex items-center gap-1"
        >
          <svg viewBox="0 0 16 16" className="w-[12px] h-[12px]" fill="none">
            <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"></path>
          </svg>
          Cancel
        </button>
      </header>

      <div className="p-5 space-y-5">
        {/* 1. Delivery */}
        <FormBlock
          step="1"
          title="Delivery"
          subtitle="How this channel sends messages."
        >
          <StepType
            type={type}
            setType={setType}
            serviceId={serviceId}
            setServiceId={setServiceId}
          />
        </FormBlock>

        {/* 2. Configure */}
        <FormBlock
          step="2"
          title="Configuration"
          subtitle="Channel label and credentials."
        >
          <ConfigureSection
            type={type}
            serviceId={serviceId}
            name={name}
            setName={setName}
            enabled={enabled}
            setEnabled={setEnabled}
            config={config}
            setConfig={setConfig}
          />
        </FormBlock>

        {/* 3. Events */}
        <FormBlock
          step="3"
          title="Events"
          subtitle={`${events.length} of ${WEVENTS.length} subscribed.`}
        >
          <EventsSection events={events} setEvents={setEvents} />
        </FormBlock>

        {/* 4. Templates */}
        <FormBlock
          step="4"
          title="Message templates"
          subtitle="Optional — override the built-in defaults per event."
        >
          <TemplatesSection events={events} templates={templates} setTemplates={setTemplates} />
        </FormBlock>
      </div>

      <footer className="px-5 py-3.5 border-t border-[#252b48] bg-[#131727] flex items-center justify-between gap-3">
        <div className="text-[11.5px] text-slate-500 flex items-center gap-3 min-w-0 flex-wrap">
          {canSave ? (
            <span className="flex items-center gap-1.5 text-emerald-400">
              <svg viewBox="0 0 16 16" className="w-[12px] h-[12px]" fill="none">
                <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"></circle>
                <path d="M5 8.5l2 2 4-5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"></path>
              </svg>
              Ready to save
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-amber-400/90">
              <svg viewBox="0 0 16 16" className="w-[12px] h-[12px]" fill="none">
                <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"></circle>
                <path d="M8 5v4m0 2v.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"></path>
              </svg>
              Needs:&nbsp;
              <span className="text-slate-400">
                {[
                  missing.name && "channel label",
                  missing.config && "required fields",
                  missing.events && "at least one event",
                ]
                  .filter(Boolean)
                  .join(", ")}
              </span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <W.Button variant="ghost" onClick={onCancel}>Cancel</W.Button>
          <W.Button
            variant="secondary"
            onClick={() => onTest({ name, type, serviceId, config, events, templates })}
          >
            <svg viewBox="0 0 16 16" className="w-[11px] h-[11px]" fill="none">
              <path
                d="M3 8h7m0 0L7 5m3 3l-3 3"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              ></path>
              <circle cx="12.5" cy="8" r="1.5" fill="currentColor"></circle>
            </svg>
            Send test
          </W.Button>
          <W.Button onClick={save} disabled={!canSave} className={!canSave ? "opacity-40 pointer-events-none" : ""}>
            Save channel
          </W.Button>
        </div>
      </footer>
    </section>
  );
}

// Numbered section header used to lightly structure the unified form.
function FormBlock({ step, title, subtitle, children }) {
  return (
    <section>
      <header className="flex items-center gap-2.5 mb-3">
        <span className="inline-flex items-center justify-center w-[20px] h-[20px] rounded-full text-[10.5px] font-semibold bg-violet-500/15 text-violet-300 border border-violet-500/30">
          {step}
        </span>
        <span className="text-[13px] font-semibold text-slate-100">{title}</span>
        {subtitle ? <span className="text-[11.5px] text-slate-500">· {subtitle}</span> : null}
      </header>
      {children}
    </section>
  );
}

function StepType({ type, setType, serviceId, setServiceId }) {
  const cards = [
    {
      id: "apprise",
      title: "Service (Apprise)",
      desc: "Discord, Slack, Telegram, Pushover, ntfy, Email, and 70+ more.",
      badge: "Recommended",
      icon: (
        <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
          <path
            d="M5 8a3 3 0 116 0v3H5V8zm8 0a3 3 0 116 0v3h-6V8zM4 13h16v6a2 2 0 01-2 2H6a2 2 0 01-2-2v-6z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          ></path>
        </svg>
      ),
    },
    {
      id: "webhook",
      title: "Webhook",
      desc: "Send a JSON POST to any HTTP endpoint with optional HMAC signing.",
      icon: (
        <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
          <path
            d="M8 13a4 4 0 117 2.6M16 11a4 4 0 11-7-2.6M12 19l-2-3.5M10 9l-2-3.5M19 12l-1-3"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          ></path>
        </svg>
      ),
    },
    {
      id: "bash",
      title: "Bash script",
      desc: "Run a local script with event data as environment variables.",
      icon: (
        <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
          <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"></rect>
          <path
            d="M7 10l2.5 2L7 14M11 14h4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          ></path>
        </svg>
      ),
    },
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-3">
        {cards.map((c) => {
          const active = type === c.id;
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => setType(c.id)}
              className={
                "relative text-left p-4 rounded-lg border transition-all " +
                (active
                  ? "bg-violet-500/10 border-violet-500 shadow-[0_0_0_3px_rgba(139,92,246,0.12)]"
                  : "bg-[#13162a] border-[#252b48] hover:border-[#3a4170]")
              }
            >
              {c.badge ? (
                <span className="absolute top-3 right-3 text-[9.5px] font-semibold tracking-wider uppercase text-violet-300 bg-violet-500/15 px-1.5 py-[2px] rounded">
                  {c.badge}
                </span>
              ) : null}
              <span
                className={
                  "inline-flex items-center justify-center w-9 h-9 rounded-md mb-3 " +
                  (active ? "bg-violet-500/20 text-violet-300" : "bg-[#1c1f37] text-slate-400")
                }
              >
                {c.icon}
              </span>
              <div className="text-[13.5px] font-semibold text-slate-100 mb-1">{c.title}</div>
              <div className="text-[11.5px] text-slate-500 leading-snug">{c.desc}</div>
            </button>
          );
        })}
      </div>

      {type === "apprise" ? (
        <div className="rounded-lg bg-[#13162a] border border-[#252b48] p-4">
          <W.Field label="Service" required hint="Featured services are pinned. Search to find more.">
            <W.ServiceDropdown services={WSERVICES} value={serviceId} onChange={setServiceId} />
          </W.Field>
        </div>
      ) : null}
    </div>
  );
}

function ReviewSummary({ name, type, serviceId, events, enabled }) {
  const service = WSERVICES.find((s) => s.id === serviceId);
  return (
    <div className="rounded-lg bg-[#13162a] border border-[#252b48] p-4">
      <div className="text-[11px] font-semibold text-violet-400 tracking-[0.12em] uppercase mb-3">
        Summary
      </div>
      <dl className="grid grid-cols-[120px_1fr] gap-y-2 text-[12.5px]">
        <dt className="text-slate-500">Label</dt>
        <dd className="text-slate-200">{name || <span className="text-slate-600 italic">unnamed</span>}</dd>
        <dt className="text-slate-500">Type</dt>
        <dd className="text-slate-200 capitalize flex items-center gap-2">
          {type === "apprise" ? (
            <>
              <W.ServiceGlyph id={service.id} name={service.name} size={18} /> Apprise · {service.name}
            </>
          ) : type === "webhook" ? (
            "Webhook"
          ) : (
            "Bash script"
          )}
        </dd>
        <dt className="text-slate-500">Status</dt>
        <dd>{enabled ? <W.Pill tone="green">Enabled</W.Pill> : <W.Pill>Disabled</W.Pill>}</dd>
        <dt className="text-slate-500">Events</dt>
        <dd className="flex items-center gap-1.5 flex-wrap">
          {events.length ? (
            events.map((e) => {
              const ev = WEVENTS.find((x) => x.key === e);
              return <W.Pill key={e} tone="blue">{ev.label}</W.Pill>;
            })
          ) : (
            <span className="text-slate-600 italic">none</span>
          )}
        </dd>
      </dl>
    </div>
  );
}

// ── Inline channel editor (expanded row body) ───────────────────────────

function ChannelEditor({ channel, onSave, onTest, onDelete, onClose }) {
  const [name, setName] = useStateW(channel.name);
  const [enabled, setEnabled] = useStateW(channel.enabled);
  const [config, setConfig] = useStateW(channel.config);
  const [events, setEvents] = useStateW(channel.events);
  const [templates, setTemplates] = useStateW(channel.templates);
  const [open, setOpen] = useStateW({ config: true, events: true, templates: false });
  const [dirty, setDirty] = useStateW(false);

  useEffectW(() => {
    setDirty(true);
  }, [name, enabled, config, events, templates]);

  function save() {
    onSave({ ...channel, name: name.trim(), enabled, config, events, templates });
    setDirty(false);
  }

  return (
    <div className="bg-[#131727] border-t border-[#252b48] p-5 space-y-3">
      <CollapseSection
        title="Configuration"
        open={open.config}
        onToggle={() => setOpen({ ...open, config: !open.config })}
      >
        <ConfigureSection
          type={channel.type}
          serviceId={channel.serviceId}
          name={name}
          setName={setName}
          enabled={enabled}
          setEnabled={setEnabled}
          config={config}
          setConfig={setConfig}
        />
      </CollapseSection>

      <CollapseSection
        title={`Events · ${events.length} subscribed`}
        open={open.events}
        onToggle={() => setOpen({ ...open, events: !open.events })}
      >
        <EventsSection events={events} setEvents={setEvents} />
      </CollapseSection>

      <CollapseSection
        title="Message templates"
        open={open.templates}
        onToggle={() => setOpen({ ...open, templates: !open.templates })}
      >
        <TemplatesSection events={events} templates={templates} setTemplates={setTemplates} />
      </CollapseSection>

      <div className="flex items-center gap-2 pt-2">
        <W.Button onClick={save} disabled={!dirty} className={!dirty ? "opacity-40 pointer-events-none" : ""}>
          Save changes
        </W.Button>
        <W.Button variant="secondary" onClick={() => onTest(channel)}>
          <svg viewBox="0 0 16 16" className="w-[11px] h-[11px]" fill="none">
            <path d="M3 8h7m0 0L7 5m3 3l-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"></path>
          </svg>
          Send test
        </W.Button>
        <W.Button variant="ghost" onClick={onClose}>
          Close
        </W.Button>
        <span className="flex-1"></span>
        <W.Button variant="danger" onClick={() => onDelete(channel)}>
          <svg viewBox="0 0 16 16" className="w-[11px] h-[11px]" fill="none">
            <path
              d="M5 6v6m3-6v6m3-6v6M3 4h10M6 4V3a1 1 0 011-1h2a1 1 0 011 1v1M4 4l.5 9a1 1 0 001 1h5a1 1 0 001-1L12 4"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            ></path>
          </svg>
          Delete
        </W.Button>
      </div>
    </div>
  );
}

function CollapseSection({ title, open, onToggle, children }) {
  return (
    <div className="rounded-lg border border-[#252b48] bg-[#161b2d] overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-[#1a1f36] transition-colors"
      >
        <span className="flex items-center gap-2.5 text-[12px] font-semibold text-slate-200 tracking-wide">
          <svg
            viewBox="0 0 16 16"
            className={"w-[11px] h-[11px] text-slate-500 transition-transform " + (open ? "rotate-90" : "")}
            fill="none"
          >
            <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"></path>
          </svg>
          {title}
        </span>
      </button>
      {open ? <div className="px-4 pb-4 pt-1">{children}</div> : null}
    </div>
  );
}

window.ARM_WIZARD = { AddChannelWizard, ChannelEditor };
