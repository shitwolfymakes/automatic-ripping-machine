// ARM Notifications Settings — main App
// Composes sidebar + settings tabs + channel list + add-channel wizard.

const { useState: useStateA, useMemo: useMemoA, useEffect: useEffectA } = React;
const P = window.ARM_PRIMS;
const { AddChannelWizard, ChannelEditor } = window.ARM_WIZARD;
const { EVENTS: AEVENTS, SERVICES: ASERVICES, INITIAL_CHANNELS } = window.ARM_DATA;

// ── Helpers ──────────────────────────────────────────────────────────────

function formatAgo(ts) {
  if (!ts) return "never";
  const diff = Date.now() - ts;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

function channelStatus(ch) {
  if (!ch.enabled) return "off";
  if (ch.lastError) return "warn";
  if (ch.lastStatus === "error") return "error";
  return "ok";
}

function channelDescription(ch) {
  if (ch.type === "apprise") {
    const s = ASERVICES.find((x) => x.id === ch.serviceId);
    return s ? `Apprise · ${s.name}` : "Apprise";
  }
  if (ch.type === "webhook") return "Webhook";
  return "Bash script";
}

// ── Sidebar (slim, for context) ──────────────────────────────────────────

function Sidebar() {
  const items = [
    { label: "Dashboard", icon: "M3 12l9-8 9 8M5 10v9h4v-6h6v6h4v-9", active: false },
    { label: "Jobs", icon: "M4 6h16M4 12h16M4 18h10", active: false },
    { label: "Files", icon: "M4 5a2 2 0 012-2h4l2 2h6a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V5z", active: false },
    { label: "Logs", icon: "M5 4h14v16H5zM8 8h8M8 12h8M8 16h5", active: false },
    { label: "Transcoder", icon: "M4 7l8-4 8 4-8 4-8-4zm0 5l8 4 8-4M4 17l8 4 8-4", active: false },
    { label: "Settings", icon: "M12 9a3 3 0 100 6 3 3 0 000-6zm9 3l-2-1-1-2 1-3-2-2-3 1-2-1-1-2h-4l-1 2-2 1-3-1-2 2 1 3-1 2-2 1v4l2 1 1 2-1 3 2 2 3-1 2 1 1 2h4l1-2 2-1 3 1 2-2-1-3 1-2 2-1z", active: true },
  ];
  return (
    <aside className="w-[208px] flex-shrink-0 bg-[#0c0f1c] border-r border-[#1c2138] flex flex-col">
      <div className="px-4 py-4 border-b border-[#1c2138] flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-md bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center font-bold text-white text-[13px] shadow-[0_0_16px_-4px_rgba(139,92,246,0.6)]">
          ARM
        </div>
        <div className="min-w-0">
          <div className="text-[12.5px] font-semibold text-slate-100 leading-tight">
            Auto Ripping
          </div>
          <div className="text-[10.5px] text-slate-500 leading-tight font-mono">v2.7.0</div>
        </div>
      </div>
      <nav className="flex-1 py-3">
        {items.map((it) => (
          <a
            key={it.label}
            href="#"
            className={
              "flex items-center gap-3 px-4 py-2 text-[12.5px] transition-colors " +
              (it.active
                ? "text-violet-300 bg-violet-500/10 border-l-2 border-violet-500"
                : "text-slate-400 hover:text-slate-100 hover:bg-[#13182b] border-l-2 border-transparent")
            }
          >
            <svg viewBox="0 0 24 24" fill="none" className="w-[15px] h-[15px]">
              <path d={it.icon} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"></path>
            </svg>
            <span>{it.label}</span>
          </a>
        ))}
      </nav>
      <div className="px-4 py-3 border-t border-[#1c2138]">
        <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500 mb-2">Drives</div>
        <div className="space-y-1.5">
          {[
            { name: "/dev/sr0", state: "Ripping", color: "bg-blue-400" },
            { name: "/dev/sr1", state: "Idle", color: "bg-slate-600" },
          ].map((d) => (
            <div key={d.name} className="flex items-center gap-2 text-[11px]">
              <span className={"w-1.5 h-1.5 rounded-full " + d.color}></span>
              <span className="text-slate-300 font-mono">{d.name}</span>
              <span className="text-slate-500 ml-auto">{d.state}</span>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}

// ── Header ───────────────────────────────────────────────────────────────

function Header() {
  return (
    <header className="h-[52px] flex-shrink-0 border-b border-[#1c2138] bg-[#0c0f1c]/80 backdrop-blur flex items-center px-6 gap-4">
      <nav className="flex items-center gap-1.5 text-[12.5px] text-slate-400">
        <a href="#" className="hover:text-slate-100">Settings</a>
        <span className="text-slate-700">/</span>
        <span className="text-slate-100">Notifications</span>
      </nav>
      <span className="flex-1"></span>
      <button className="text-slate-400 hover:text-slate-100 p-1.5 rounded hover:bg-[#13182b]">
        <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none">
          <path d="M12 3a6 6 0 016 6c0 3 1 5 2 6H4c1-1 2-3 2-6a6 6 0 016-6zm-2 16a2 2 0 004 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"></path>
        </svg>
      </button>
      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-violet-500 text-white text-[11px] font-bold flex items-center justify-center">
        J
      </div>
    </header>
  );
}

// ── Settings tabs ────────────────────────────────────────────────────────

function SettingsTabs() {
  const tabs = ["Ripping", "Music", "Transcoding", "Notifications", "Drives", "Appearance", "System"];
  return (
    <div className="border-b border-[#1c2138]">
      <nav className="flex items-center gap-1 px-6">
        {tabs.map((t) => {
          const active = t === "Notifications";
          return (
            <a
              key={t}
              href="#"
              className={
                "px-3 py-3 text-[13px] font-medium transition-colors border-b-2 -mb-px " +
                (active
                  ? "text-blue-400 border-blue-400"
                  : "text-slate-400 hover:text-slate-100 border-transparent")
              }
            >
              {t}
            </a>
          );
        })}
      </nav>
    </div>
  );
}

// ── Channel row ──────────────────────────────────────────────────────────

function ChannelRow({ channel, expanded, onToggle, onTest, onSave, onDelete, onClose, onSetEnabled }) {
  const status = channelStatus(channel);
  const svc = channel.serviceId ? ASERVICES.find((x) => x.id === channel.serviceId) : null;
  const desc = channelDescription(channel);
  return (
    <div className={"transition-colors " + (expanded ? "bg-[#13172a]" : "hover:bg-[#13172a]/60")}>
      <div
        className="px-4 py-3 grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-4 cursor-pointer"
        onClick={onToggle}
      >
        <div className="flex items-center gap-3 min-w-0">
          <P.StatusDot status={status} />
          {svc ? (
            <P.ServiceGlyph id={svc.id} name={svc.name} size={28} />
          ) : (
            <span
              className={
                "inline-flex items-center justify-center w-[28px] h-[28px] rounded-md font-bold text-[11px] border " +
                (channel.type === "webhook"
                  ? "bg-blue-500/10 border-blue-500/30 text-blue-300"
                  : "bg-amber-500/10 border-amber-500/30 text-amber-300")
              }
            >
              {channel.type === "webhook" ? "{}" : "$_"}
            </span>
          )}
        </div>

        <div className="min-w-0">
          <div className="text-[13.5px] font-medium text-slate-100 truncate">{channel.name}</div>
          <div className="text-[11.5px] text-slate-500 truncate">
            {desc}
            <span className="text-slate-700 mx-1.5">·</span>
            <span className="text-slate-500">
              {channel.events.length} event{channel.events.length === 1 ? "" : "s"}
            </span>
            {channel.lastError ? (
              <>
                <span className="text-slate-700 mx-1.5">·</span>
                <span className="text-amber-400 truncate">{channel.lastError}</span>
              </>
            ) : null}
          </div>
        </div>

        <div className="hidden md:flex flex-col items-end text-right">
          <div className="text-[11.5px] text-slate-300 font-mono">{formatAgo(channel.lastSentAt)}</div>
          <div className="text-[10.5px] text-slate-500">
            {channel.sent24h} sent · {channel.failed24h} failed (24h)
          </div>
        </div>

        <div onClick={(e) => e.stopPropagation()}>
          <P.Toggle checked={channel.enabled} onChange={(v) => onSetEnabled(channel, v)} />
        </div>

        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => onTest(channel)}
            title="Send test"
            className="p-1.5 rounded text-slate-400 hover:text-violet-300 hover:bg-violet-500/10"
          >
            <svg viewBox="0 0 16 16" className="w-[14px] h-[14px]" fill="none">
              <path d="M3 8h8m0 0L8 5m3 3l-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"></path>
              <circle cx="13" cy="8" r="1.3" fill="currentColor"></circle>
            </svg>
          </button>
          <button
            onClick={onToggle}
            title={expanded ? "Collapse" : "Edit"}
            className="p-1.5 rounded text-slate-400 hover:text-slate-100 hover:bg-[#1c2138]"
          >
            <svg
              viewBox="0 0 16 16"
              className={"w-[14px] h-[14px] transition-transform " + (expanded ? "rotate-180" : "")}
              fill="none"
            >
              <path d="M3.5 6l4.5 4.5L12.5 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"></path>
            </svg>
          </button>
        </div>
      </div>

      {expanded ? (
        <ChannelEditor channel={channel} onSave={onSave} onTest={onTest} onDelete={onDelete} onClose={onClose} />
      ) : null}
    </div>
  );
}

// ── Channels list ────────────────────────────────────────────────────────

function ChannelsList({ channels, ...handlers }) {
  const [expandedId, setExpandedId] = useStateA(null);

  if (!channels.length) {
    return (
      <div className="rounded-xl border border-dashed border-[#2d3458] bg-[#13162a]/40 px-6 py-12 text-center">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-violet-500/10 text-violet-400 mb-3">
          <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6">
            <path
              d="M5 9a7 7 0 0114 0v4l2 3H3l2-3V9zm5 11a2 2 0 004 0"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            ></path>
          </svg>
        </div>
        <div className="text-[14px] font-medium text-slate-200 mb-1">No notification channels yet</div>
        <div className="text-[12px] text-slate-500 mb-4 max-w-md mx-auto">
          Wire up Discord, Slack, your phone, or a custom webhook so ARM can tell you when discs are
          done — or when something goes sideways.
        </div>
        <P.Button onClick={handlers.onAdd}>
          <svg viewBox="0 0 16 16" className="w-[12px] h-[12px]" fill="none">
            <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"></path>
          </svg>
          Add your first channel
        </P.Button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[#252b48] bg-[#161b2d] overflow-hidden divide-y divide-[#252b48]">
      <div className="px-4 py-2 grid grid-cols-[auto_1fr_auto_auto_auto] gap-4 text-[10.5px] uppercase tracking-[0.12em] text-slate-500 font-semibold bg-[#131727]">
        <div className="w-[44px]"></div>
        <div>Channel</div>
        <div className="hidden md:block text-right">Last delivery</div>
        <div>Enabled</div>
        <div className="w-[60px] text-right">Actions</div>
      </div>
      {channels.map((ch) => (
        <ChannelRow
          key={ch.id}
          channel={ch}
          expanded={expandedId === ch.id}
          onToggle={() => setExpandedId(expandedId === ch.id ? null : ch.id)}
          onClose={() => setExpandedId(null)}
          {...handlers}
        />
      ))}
    </div>
  );
}

// ── Toast ────────────────────────────────────────────────────────────────

function Toast({ toast, onDismiss }) {
  useEffectA(() => {
    if (!toast) return;
    const t = setTimeout(onDismiss, 4200);
    return () => clearTimeout(t);
  }, [toast, onDismiss]);

  if (!toast) return null;
  const tones = {
    success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
    error: "border-red-500/40 bg-red-500/10 text-red-200",
    info: "border-violet-500/40 bg-violet-500/10 text-violet-200",
  };
  const icons = {
    success: (
      <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none">
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"></circle>
        <path d="M5 8.5l2 2 4-5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"></path>
      </svg>
    ),
    error: (
      <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none">
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"></circle>
        <path d="M8 5v4m0 2v.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"></path>
      </svg>
    ),
    info: (
      <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none">
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"></circle>
        <path d="M8 7v4M8 5v.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"></path>
      </svg>
    ),
  };

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <div
        className={
          "flex items-start gap-3 px-4 py-3 rounded-lg border shadow-2xl shadow-black/60 backdrop-blur min-w-[280px] max-w-[420px] " +
          tones[toast.tone]
        }
      >
        <span className="mt-0.5">{icons[toast.tone]}</span>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-semibold">{toast.title}</div>
          {toast.body ? <div className="text-[11.5px] opacity-80 mt-0.5">{toast.body}</div> : null}
        </div>
        <button onClick={onDismiss} className="text-current opacity-60 hover:opacity-100">
          <svg viewBox="0 0 16 16" className="w-3 h-3" fill="none">
            <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"></path>
          </svg>
        </button>
      </div>
    </div>
  );
}

// ── Confirm delete dialog ────────────────────────────────────────────────

function ConfirmDialog({ open, channel, onConfirm, onCancel }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="rounded-xl border border-[#2d3458] bg-[#161b2d] max-w-[420px] w-full overflow-hidden">
        <div className="p-5">
          <div className="flex items-start gap-3">
            <span className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-red-500/15 text-red-400 flex-shrink-0">
              <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none">
                <path d="M12 8v5m0 3v.5M3 19h18L12 4 3 19z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"></path>
              </svg>
            </span>
            <div>
              <div className="text-[14px] font-semibold text-slate-100 mb-1">
                Delete channel?
              </div>
              <div className="text-[12px] text-slate-400">
                <span className="text-slate-200 font-medium">{channel?.name}</span> will be removed and stop
                receiving events. This cannot be undone.
              </div>
            </div>
          </div>
        </div>
        <div className="px-5 py-3 bg-[#131727] border-t border-[#252b48] flex items-center justify-end gap-2">
          <P.Button variant="ghost" onClick={onCancel}>Cancel</P.Button>
          <button
            onClick={onConfirm}
            className="px-3 py-1.5 rounded-md text-[12.5px] font-medium bg-red-500 hover:bg-red-600 text-white shadow-[0_4px_14px_-4px_rgba(239,68,68,0.6)]"
          >
            Delete channel
          </button>
        </div>
      </div>
    </div>
  );
}

// ── App ─────────────────────────────────────────────────────────────────

function App() {
  const [channels, setChannels] = useStateA(INITIAL_CHANNELS);
  const [wizardOpen, setWizardOpen] = useStateA(false);
  const [toast, setToast] = useStateA(null);
  const [deleteTarget, setDeleteTarget] = useStateA(null);
  const [filter, setFilter] = useStateA("all");

  function showToast(t) { setToast(t); }

  function onSetEnabled(channel, enabled) {
    setChannels((cs) => cs.map((c) => (c.id === channel.id ? { ...c, enabled } : c)));
    showToast({
      tone: "info",
      title: enabled ? `Enabled ${channel.name}` : `Paused ${channel.name}`,
    });
  }

  function onSaveChannel(updated) {
    setChannels((cs) => cs.map((c) => (c.id === updated.id ? updated : c)));
    showToast({ tone: "success", title: "Channel saved", body: updated.name });
  }

  function onAddChannel(channel) {
    setChannels((cs) => [channel, ...cs]);
    setWizardOpen(false);
    showToast({
      tone: "success",
      title: "Channel added",
      body: `${channel.name} is now listening for events.`,
    });
  }

  function onTest(channel) {
    showToast({
      tone: "info",
      title: `Sending test to ${channel.name ?? "new channel"}…`,
    });
    setTimeout(() => {
      showToast({
        tone: "success",
        title: "Test delivered",
        body: `Sample “job.started” event sent at ${new Date().toLocaleTimeString()}.`,
      });
      // also bump lastSentAt
      if (channel?.id) {
        setChannels((cs) =>
          cs.map((c) =>
            c.id === channel.id
              ? { ...c, lastSentAt: Date.now(), lastStatus: "ok", lastError: null, sent24h: c.sent24h + 1 }
              : c
          )
        );
      }
    }, 900);
  }

  function onDeleteRequest(channel) {
    setDeleteTarget(channel);
  }

  function onConfirmDelete() {
    setChannels((cs) => cs.filter((c) => c.id !== deleteTarget.id));
    showToast({ tone: "info", title: `Deleted ${deleteTarget.name}` });
    setDeleteTarget(null);
  }

  const filtered = useMemoA(() => {
    if (filter === "all") return channels;
    if (filter === "enabled") return channels.filter((c) => c.enabled);
    if (filter === "disabled") return channels.filter((c) => !c.enabled);
    if (filter === "issues") return channels.filter((c) => c.lastError);
    return channels;
  }, [channels, filter]);

  const counts = useMemoA(() => {
    const enabled = channels.filter((c) => c.enabled).length;
    const issues = channels.filter((c) => c.lastError).length;
    const sent24h = channels.reduce((s, c) => s + c.sent24h, 0);
    return { total: channels.length, enabled, issues, sent24h };
  }, [channels]);

  return (
    <div className="flex h-screen w-screen bg-[#0a0d18] text-slate-200" data-screen-label="Notifications">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-[1080px] mx-auto px-6 py-6">
            <div className="mb-5">
              <h1 className="text-[22px] font-semibold text-white tracking-tight">Settings</h1>
            </div>
            <SettingsTabs />

            <div className="py-5">
              {/* Section header */}
              <div className="flex items-end justify-between gap-4 mb-4">
                <div>
                  <h2 className="text-[18px] font-semibold text-white tracking-tight mb-1">
                    Notifications
                  </h2>
                  <p className="text-[12.5px] text-slate-400 max-w-2xl">
                    Manage notification channels — Discord, Slack, webhooks, scripts, and more. ARM
                    sends events as they happen.
                  </p>
                </div>
                {!wizardOpen ? (
                  <P.Button onClick={() => setWizardOpen(true)}>
                    <svg viewBox="0 0 16 16" className="w-[12px] h-[12px]" fill="none">
                      <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"></path>
                    </svg>
                    Add channel
                  </P.Button>
                ) : null}
              </div>

              {/* Stat strip */}
              <div className="grid grid-cols-4 gap-3 mb-5">
                <StatCard
                  label="Channels"
                  value={counts.total}
                  hint={`${counts.enabled} enabled`}
                  accent="violet"
                />
                <StatCard
                  label="Events delivered"
                  value={counts.sent24h}
                  hint="last 24 hours"
                  accent="blue"
                />
                <StatCard
                  label="Issues"
                  value={counts.issues}
                  hint={counts.issues ? "needs attention" : "all clear"}
                  accent={counts.issues ? "amber" : "green"}
                />
                <StatCard
                  label="Subscribed events"
                  value={AEVENTS.length}
                  hint="across all channels"
                  accent="slate"
                />
              </div>

              {wizardOpen ? (
                <div className="mb-5">
                  <AddChannelWizard
                    onCancel={() => setWizardOpen(false)}
                    onSave={onAddChannel}
                    onTest={onTest}
                  />
                </div>
              ) : null}

              {/* Filter bar */}
              {channels.length > 0 ? (
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-1 bg-[#13162a] border border-[#252b48] rounded-md p-0.5">
                    {[
                      { id: "all", label: `All · ${counts.total}` },
                      { id: "enabled", label: `Enabled · ${counts.enabled}` },
                      { id: "disabled", label: `Paused · ${counts.total - counts.enabled}` },
                      { id: "issues", label: `Issues · ${counts.issues}` },
                    ].map((f) => (
                      <button
                        key={f.id}
                        onClick={() => setFilter(f.id)}
                        className={
                          "px-2.5 py-1 rounded text-[11.5px] font-medium transition-colors " +
                          (filter === f.id
                            ? "bg-violet-500/15 text-violet-300"
                            : "text-slate-400 hover:text-slate-200")
                        }
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                  <div className="text-[11.5px] text-slate-500">
                    Click a row to edit · drag to reorder (coming soon)
                  </div>
                </div>
              ) : null}

              <ChannelsList
                channels={filtered}
                onAdd={() => setWizardOpen(true)}
                onTest={onTest}
                onSave={onSaveChannel}
                onDelete={onDeleteRequest}
                onSetEnabled={onSetEnabled}
              />

              {/* Subtle footnote */}
              <div className="mt-6 text-[11.5px] text-slate-600 text-center">
                Notification dispatch is queued and retried up to 3 times with exponential backoff.
                See <a href="#" className="text-blue-400 hover:underline">delivery logs</a> for the
                full audit trail.
              </div>
            </div>
          </div>
        </main>
      </div>

      <Toast toast={toast} onDismiss={() => setToast(null)} />
      <ConfirmDialog
        open={!!deleteTarget}
        channel={deleteTarget}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={onConfirmDelete}
      />
    </div>
  );
}

function StatCard({ label, value, hint, accent = "violet" }) {
  const tints = {
    violet: "text-violet-300",
    blue: "text-blue-300",
    amber: "text-amber-300",
    green: "text-emerald-300",
    slate: "text-slate-300",
  };
  return (
    <div className="rounded-lg bg-[#13162a] border border-[#252b48] px-4 py-3">
      <div className="text-[10.5px] uppercase tracking-[0.12em] text-slate-500 font-semibold mb-1">
        {label}
      </div>
      <div className="flex items-baseline gap-2">
        <span className={"text-[24px] font-semibold tracking-tight " + tints[accent]}>{value}</span>
        <span className="text-[11px] text-slate-500">{hint}</span>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
