// Hand-typed projections of the wire schemas that the UI actually reads.
// `openapi-typescript` writes ./generated.ts at build time; we re-export the
// few types the views care about so the rest of the codebase imports from one
// spot (and we can swap the source of truth later without touching call sites).

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  expires_at: string
  password_must_change: boolean
}

export interface PasswordChangeRequest {
  current_password: string
  new_password: string
}

export type JobStatus =
  | 'created'
  | 'awaiting_user_id'
  | 'identified'
  | 'ripping'
  | 'ripped'
  | 'ripped_partial'
  | 'abandoned'
  | 'failed'

export type DiscType = 'dvd' | 'bluray' | 'cd' | 'data' | 'unknown'

export interface JobView {
  id: string
  drive_id: string
  disc_type: DiscType
  status: JobStatus
  title: string | null
  year: number | null
  metadata_json: Record<string, unknown>
  resumed_from_crash: boolean
}

export interface TrackView {
  id: string
  job_id: string
  kind: string
  index: number
  source_ref: string
  status: string
  output_path: string | null
  size_bytes: number | null
  duration_seconds: number | null
  attempts: number
  last_error: string | null
}

export interface JobDetailView {
  job: JobView
  tracks: TrackView[]
}

export interface DriveView {
  id: string
  hostname: string
  device_path: string
  display_name: string | null
  status: string
  last_seen_at: string | null
  default_session_id: string | null
}

export interface DriveUpdateRequest {
  display_name?: string | null
  default_session_id?: string | null
}

export type MediaType = 'movie' | 'tv' | 'music' | 'data' | 'iso'

export type TrackSelection = 'main_feature' | 'all_tracks' | 'archive' | 'custom'

export type IdentificationMode = 'required' | 'skip' | 'deferred_placeholder'

export type OutputMode = 'tracks' | 'iso' | 'data_copy'

export type TranscodeTool = 'handbrake' | 'abcde' | 'none'

export type ContainerFormat = 'mkv' | 'mp4' | 'webm' | 'flac' | 'mp3' | 'ogg' | 'iso' | 'none'

export type HwPreference = 'cpu_only' | 'any'

export type VideoCodec = 'h264' | 'h265' | 'av1'

export type SessionApplicationStatus =
  | 'waiting_identify'
  | 'queued'
  | 'running'
  | 'done'
  | 'done_partial'
  | 'failed'
  | 'cancelled'

export type TranscodeTaskStatus = 'queued' | 'in_progress' | 'done' | 'failed'

export interface TrackFilters {
  min_duration_seconds?: number | null
  max_duration_seconds?: number | null
  title_indices?: number[] | null
  title_indices_exclude?: number[] | null
}

export interface SessionView {
  id: string
  name: string
  media_type: MediaType
  is_builtin: boolean
  rip_preset_id: string
  transcode_preset_id: string | null
  output_path_template: string
  overrides_json: Record<string, unknown> | null
  created_by_user_id: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SessionCreateRequest {
  name: string
  media_type: MediaType
  rip_preset_id: string
  transcode_preset_id?: string | null
  output_path_template: string
  overrides_json?: Record<string, unknown> | null
}

export interface SessionUpdateRequest {
  name?: string
  rip_preset_id?: string
  transcode_preset_id?: string | null
  output_path_template?: string
  overrides_json?: Record<string, unknown> | null
}

export interface SessionCloneRequest {
  name: string
}

export interface RipPresetView {
  id: string
  name: string
  media_type: MediaType
  is_builtin: boolean
  track_selection: TrackSelection
  identification_mode: IdentificationMode
  output_mode: OutputMode
  track_filters_json: TrackFilters | null
  created_by_user_id: string | null
  created_at: string | null
  updated_at: string | null
}

export interface RipPresetCreateRequest {
  name: string
  media_type: MediaType
  track_selection: TrackSelection
  identification_mode: IdentificationMode
  output_mode: OutputMode
  track_filters_json?: TrackFilters | null
}

export type RipPresetUpdateRequest = Partial<Omit<RipPresetCreateRequest, 'media_type'>>

export interface TranscodePresetView {
  id: string
  name: string
  media_type: MediaType
  is_builtin: boolean
  tool: TranscodeTool
  preset_ref: string | null
  preset_json: Record<string, unknown> | null
  container: ContainerFormat
  codec: VideoCodec | null
  hw_preference: HwPreference | null
  extra_args: string | null
  created_by_user_id: string | null
  created_at: string | null
  updated_at: string | null
}

export interface TranscodePresetCreateRequest {
  name: string
  media_type: MediaType
  tool: TranscodeTool
  preset_ref?: string | null
  preset_json?: Record<string, unknown> | null
  container: ContainerFormat
  codec?: VideoCodec | null
  hw_preference?: HwPreference | null
  extra_args?: string | null
}

export type TranscodePresetUpdateRequest = Partial<Omit<TranscodePresetCreateRequest, 'media_type'>>

export interface SessionApplicationView {
  id: string
  session_id: string
  job_id: string
  status: SessionApplicationStatus
  overrides_json: Record<string, unknown> | null
  overwrite: boolean
  created_by_user_id: string | null
  created_at: string | null
  completed_at: string | null
}

export interface TranscodeTaskView {
  id: string
  session_application_id: string
  source_track_id: string
  status: TranscodeTaskStatus
  output_path: string | null
  progress_pct: number
  attempts: number
  claimed_by: string | null
  claim_heartbeat_at: string | null
  last_error: string | null
  created_at: string | null
  updated_at: string | null
}

// Phase 7: WS event payloads (typed events on `transcode.events`).
export interface TranscodeProgressPayload {
  task_id: string
  progress_pct: number
  eta_seconds: number | null
  current_pass: string | null
}

export interface TranscodeTaskEventPayload {
  task_id: string
  session_application_id: string
  output_path?: string | null
  size_bytes?: number | null
  duration_seconds?: number | null
  sha256?: string | null
  last_error?: string | null
}

export interface TranscodeSessionEventPayload {
  session_application_id: string
  session_id: string
  job_id: string
  status?: string
}

export interface ApplySessionRequest {
  session_id: string
  overwrite?: boolean
}

export interface CollisionInfo {
  output_path: string
  existing_task_id: string | null
  on_filesystem: boolean
}

export interface ApplySessionResponse {
  session_application: SessionApplicationView
  tasks: TranscodeTaskView[]
  collisions: CollisionInfo[]
  idempotent: boolean
}

export interface TemplatePreviewRequest {
  template: string
  media_type: MediaType
  has_transcode_preset: boolean
}

export interface TemplatePreviewResponse {
  expansion: string
}

export interface ConfigView {
  tmdb_api_key: string | null
  omdb_api_key: string | null
  musicbrainz_user_agent: string | null
  auto_transcode_on_idle: boolean
  block_on_miss: boolean
  default_retention_policy: string
  notification_apprise_urls: string[]
  notifications_enabled: boolean
  updated_by_user_id: string | null
  updated_at: string | null
}

export interface ConfigUpdateRequest {
  tmdb_api_key?: string | null
  omdb_api_key?: string | null
  musicbrainz_user_agent?: string | null
  auto_transcode_on_idle?: boolean
  block_on_miss?: boolean
  default_retention_policy?: string
  notification_apprise_urls?: string[]
  notifications_enabled?: boolean
}

export interface DiagnosticsServiceView {
  name: string
  log_level: string
}

export interface DiagnosticsResponse {
  services: DiagnosticsServiceView[]
  bug_report_zip_url: string | null
}
