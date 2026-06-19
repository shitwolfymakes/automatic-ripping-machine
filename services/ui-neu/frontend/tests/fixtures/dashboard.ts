import type { DashboardData } from '$lib/api/dashboard';

export const emptyDashboard: DashboardData = {
    db_available: true,
    arm_online: true,
    active_jobs: [],
    drives_online: 0,
    drive_names: {},
    notification_count: 0,
    ripping_enabled: true,
    makemkv_key_valid: null,
    makemkv_key_checked_at: null,
    transcoder_online: true,
    transcoder_stats: null,
    active_transcodes: []
};

export const emptyJobs = {
    jobs: [],
    total: 0,
    page: 1,
    per_page: 25
};

export const emptyStats = {
    total: 0,
    success: 0,
    failed: 0,
    pending: 0
};
