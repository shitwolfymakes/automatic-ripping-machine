// ARM Notifications — services catalog, events catalog, seeded channels
// Modeled after the Apprise notification library's service list.
(function () {
const EVENTS = [
  { key: "job.started", label: "Job started", description: "A new disc has been inserted and ripping has begun.", defaults: { title: "ARM started: {job_title}", body: "Job {job_id} started ripping {job_title} ({job_disc_type})." } },
  { key: "rip.complete", label: "Rip complete", description: "Disc ripping finished. Files are ready for transcode.", defaults: { title: "Rip complete: {job_title}", body: "Finished ripping {job_title} from {drive_mount}." } },
  { key: "transcode.complete", label: "Transcode complete", description: "Final media file ready in the library.", defaults: { title: "Transcode complete: {job_title}", body: "Job {job_id} ({job_title}) finished transcoding." } },
  { key: "job.failed", label: "Job failed", description: "A job hit an error and could not complete.", defaults: { title: "ARM FAILED: {job_title}", body: "Job {job_id} ({job_title}) failed at {occurred_at}." } },
  { key: "manual.wait", label: "Manual wait required", description: "A disc needs review before ARM can continue.", defaults: { title: "ARM needs review: {job_title}", body: "Job {job_id} is waiting on manual disc identification." } },
  { key: "duplicate", label: "Duplicate detected", description: "ARM detected this disc has already been ripped.", defaults: { title: "Duplicate disc: {job_title}", body: "{job_title} ({job_imdb_id}) was previously ripped on this server." } },
];

const TEMPLATE_VARS = [
  "{job_id}", "{job_title}", "{job_disc_type}",
  "{job_imdb_id}", "{occurred_at}", "{drive_mount}",
];

// Apprise-style service catalog. Each service declares its required fields so
// the wizard can render them. The `featured` flag pins it to the top group.
const SERVICES = [
  // ── Featured (pinned) ─────────────────────────────────────────────────
  { id: "discord", name: "Discord", category: "Chat", featured: true, scheme: "discord", fields: [
    { key: "webhook_id", label: "Webhook ID", required: true, placeholder: "1098765432109876543" },
    { key: "webhook_token", label: "Webhook Token", required: true, secret: true, placeholder: "abc123…" },
    { key: "thread_id", label: "Thread ID", placeholder: "(optional)" },
  ] },
  { id: "slack", name: "Slack", category: "Chat", featured: true, scheme: "slack", fields: [
    { key: "token_a", label: "Token A", required: true, secret: true },
    { key: "token_b", label: "Token B", required: true, secret: true },
    { key: "token_c", label: "Token C", required: true, secret: true },
    { key: "channel", label: "Channel", required: true, placeholder: "#arm-rips" },
  ] },
  { id: "telegram", name: "Telegram", category: "Chat", featured: true, scheme: "tgram", fields: [
    { key: "bot_token", label: "Bot Token", required: true, secret: true },
    { key: "chat_id", label: "Chat ID(s)", required: true, placeholder: "@username or 12345" },
  ] },
  { id: "pushover", name: "Pushover", category: "Push", featured: true, scheme: "pover", fields: [
    { key: "user_key", label: "User Key", required: true, secret: true },
    { key: "app_token", label: "App Token", required: true, secret: true },
    { key: "priority", label: "Priority", placeholder: "0", help: "-2 lowest, 2 emergency" },
  ] },
  { id: "ntfy", name: "ntfy", category: "Push", featured: true, scheme: "ntfy", fields: [
    { key: "host", label: "Host", required: true, placeholder: "ntfy.sh" },
    { key: "topic", label: "Topic", required: true, placeholder: "arm-alerts" },
    { key: "token", label: "Auth Token", secret: true, placeholder: "(optional)" },
  ] },
  { id: "gotify", name: "Gotify", category: "Push", featured: true, scheme: "gotify", fields: [
    { key: "host", label: "Server", required: true, placeholder: "https://gotify.example.com" },
    { key: "token", label: "App Token", required: true, secret: true },
  ] },

  // ── All services, by category ─────────────────────────────────────────
  { id: "mattermost", name: "Mattermost", category: "Chat", scheme: "mmost", fields: [
    { key: "host", label: "Host", required: true, placeholder: "https://chat.example.com" },
    { key: "token", label: "Token", required: true, secret: true },
    { key: "channel", label: "Channel", placeholder: "(optional)" },
  ] },
  { id: "msteams", name: "Microsoft Teams", category: "Chat", scheme: "msteams", fields: [
    { key: "token_a", label: "Token A", required: true, secret: true },
    { key: "token_b", label: "Token B", required: true, secret: true },
    { key: "token_c", label: "Token C", required: true, secret: true },
  ] },
  { id: "rocketchat", name: "Rocket.Chat", category: "Chat", scheme: "rocket", fields: [
    { key: "host", label: "Host", required: true },
    { key: "user", label: "Username", required: true },
    { key: "password", label: "Password", required: true, secret: true },
    { key: "channel", label: "Channel", placeholder: "#general" },
  ] },
  { id: "matrix", name: "Matrix", category: "Chat", scheme: "matrix", fields: [
    { key: "host", label: "Homeserver", required: true, placeholder: "matrix.org" },
    { key: "user", label: "Username", required: true },
    { key: "token", label: "Access Token", required: true, secret: true },
    { key: "room", label: "Room ID", required: true },
  ] },
  { id: "zulip", name: "Zulip", category: "Chat", scheme: "zulip", fields: [
    { key: "botname", label: "Bot Name", required: true },
    { key: "organization", label: "Organization", required: true },
    { key: "token", label: "API Token", required: true, secret: true },
    { key: "stream", label: "Stream", placeholder: "(optional)" },
  ] },

  { id: "pushbullet", name: "Pushbullet", category: "Push", scheme: "pbul", fields: [
    { key: "access_token", label: "Access Token", required: true, secret: true },
    { key: "device", label: "Device ID", placeholder: "(optional)" },
  ] },
  { id: "pushsafer", name: "Pushsafer", category: "Push", scheme: "psafer", fields: [
    { key: "private_key", label: "Private Key", required: true, secret: true },
  ] },
  { id: "techulus", name: "Techulus Push", category: "Push", scheme: "push", fields: [
    { key: "api_key", label: "API Key", required: true, secret: true },
  ] },

  { id: "smtp", name: "SMTP Email", category: "Email", scheme: "mailto", fields: [
    { key: "host", label: "SMTP Host", required: true, placeholder: "smtp.gmail.com" },
    { key: "port", label: "Port", required: true, placeholder: "587" },
    { key: "user", label: "Username", required: true },
    { key: "password", label: "Password", required: true, secret: true },
    { key: "to", label: "Recipient", required: true, placeholder: "you@example.com" },
  ] },
  { id: "mailgun", name: "Mailgun", category: "Email", scheme: "mailgun", fields: [
    { key: "domain", label: "Domain", required: true, placeholder: "mg.example.com" },
    { key: "api_key", label: "API Key", required: true, secret: true },
    { key: "to", label: "Recipient", required: true },
  ] },
  { id: "sendgrid", name: "SendGrid", category: "Email", scheme: "sendgrid", fields: [
    { key: "api_key", label: "API Key", required: true, secret: true },
    { key: "from", label: "From", required: true },
    { key: "to", label: "Recipient", required: true },
  ] },
  { id: "mailjet", name: "Mailjet", category: "Email", scheme: "mailjet", fields: [
    { key: "api_key", label: "API Key", required: true, secret: true },
    { key: "secret_key", label: "Secret Key", required: true, secret: true },
    { key: "to", label: "Recipient", required: true },
  ] },

  { id: "twilio", name: "Twilio", category: "SMS", scheme: "twilio", fields: [
    { key: "account_sid", label: "Account SID", required: true, secret: true },
    { key: "auth_token", label: "Auth Token", required: true, secret: true },
    { key: "from", label: "From Number", required: true, placeholder: "+15551234567" },
    { key: "to", label: "To Number(s)", required: true, placeholder: "+15557654321" },
  ] },
  { id: "vonage", name: "Vonage (Nexmo)", category: "SMS", scheme: "nexmo", fields: [
    { key: "api_key", label: "API Key", required: true, secret: true },
    { key: "api_secret", label: "API Secret", required: true, secret: true },
    { key: "from", label: "From", required: true },
    { key: "to", label: "To", required: true },
  ] },
  { id: "clicksend", name: "ClickSend", category: "SMS", scheme: "clicksend", fields: [
    { key: "user", label: "Username", required: true },
    { key: "password", label: "Password", required: true, secret: true },
    { key: "to", label: "To Number", required: true },
  ] },
  { id: "messagebird", name: "MessageBird", category: "SMS", scheme: "msgbird", fields: [
    { key: "api_key", label: "API Key", required: true, secret: true },
    { key: "from", label: "From", required: true },
    { key: "to", label: "To", required: true },
  ] },

  { id: "ifttt", name: "IFTTT", category: "Automation", scheme: "ifttt", fields: [
    { key: "webhook_key", label: "Webhook Key", required: true, secret: true },
    { key: "events", label: "Events", required: true, placeholder: "arm_event" },
  ] },
  { id: "webex", name: "Webex Teams", category: "Chat", scheme: "wxteams", fields: [
    { key: "token", label: "Bot Token", required: true, secret: true },
    { key: "room_id", label: "Room ID", required: true },
  ] },
  { id: "homeassistant", name: "Home Assistant", category: "Automation", scheme: "hassio", fields: [
    { key: "host", label: "Host", required: true, placeholder: "homeassistant.local" },
    { key: "token", label: "Long-Lived Token", required: true, secret: true },
  ] },
];

// Pre-seeded channels so the screen feels populated.
const INITIAL_CHANNELS = [
  {
    id: 1,
    name: "Discord — #arm-rips",
    type: "apprise",
    serviceId: "discord",
    enabled: true,
    config: { webhook_id: "1098765432109876543", webhook_token: "•••••••••••••", thread_id: "" },
    events: ["job.started", "rip.complete", "transcode.complete", "job.failed", "manual.wait"],
    templates: {},
    lastSentAt: Date.now() - 1000 * 60 * 4,
    lastStatus: "ok",
    lastError: null,
    sent24h: 12,
    failed24h: 0,
  },
  {
    id: 2,
    name: "Pushover — Phone",
    type: "apprise",
    serviceId: "pushover",
    enabled: true,
    config: { user_key: "•••••••••••••", app_token: "•••••••••••••", priority: "1" },
    events: ["job.failed", "manual.wait"],
    templates: {
      "job.failed": { title: "🚨 ARM failed on {job_title}", body: "Job {job_id} failed at {occurred_at}. Check logs." },
    },
    lastSentAt: Date.now() - 1000 * 60 * 60 * 2,
    lastStatus: "ok",
    lastError: null,
    sent24h: 1,
    failed24h: 0,
  },
  {
    id: 3,
    name: "Home Assistant webhook",
    type: "webhook",
    serviceId: null,
    enabled: true,
    config: { url: "https://hass.lan/api/webhook/arm-events", secret: "•••••••••" },
    events: ["job.started", "rip.complete", "transcode.complete"],
    templates: {},
    lastSentAt: Date.now() - 1000 * 60 * 12,
    lastStatus: "warn",
    lastError: "HTTP 502 from upstream (will retry)",
    sent24h: 7,
    failed24h: 1,
  },
  {
    id: 4,
    name: "Post-rip cleanup script",
    type: "bash",
    serviceId: null,
    enabled: false,
    config: { path: "/opt/arm/scripts/post-rip.sh", args: "--notify --color" },
    events: ["transcode.complete"],
    templates: {},
    lastSentAt: Date.now() - 1000 * 60 * 60 * 26,
    lastStatus: "ok",
    lastError: null,
    sent24h: 0,
    failed24h: 0,
  },
];

window.ARM_DATA = { EVENTS, TEMPLATE_VARS, SERVICES, INITIAL_CHANNELS };
})();
