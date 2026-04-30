export type ApiList<T> = {
  data: T[]
}

export type StatusLevel = 'success' | 'processing' | 'warning' | 'error' | 'default'

export type Room = {
  id: number
  url: string
  name: string
  platform: string
  quality: string
  enabled: boolean | number
  source: string
  created_at: string
  updated_at: string
  latest_job?: RecordingJob | null
  display_status?: string
}

export type RecordingJob = {
  id: number
  room_id: number
  status: string
  started_at?: string | null
  ended_at?: string | null
  error_message: string
  config_snapshot: string
  worker_id: string
  created_at: string
  updated_at: string
}

export type RecordedFile = {
  id: number
  job_id?: number | null
  room_id?: number | null
  local_path: string
  file_identity: string
  size_bytes: number
  format: string
  segment_index: number
  duration_seconds?: number | null
  checksum: string
  source: string
  status: string
  created_at: string
  updated_at: string
}

export type UploadRecord = {
  id: number
  recorded_file_id?: number | null
  downloaded_item_id?: number | null
  file_identity: string
  local_path: string
  youtube_video_id: string
  title: string
  privacy_status: string
  status: string
  failure_reason: string
  retry_count: number
  upload_config_version: string
  created_at: string
  updated_at: string
}

export type DownloadWatchSettings = {
  enabled: boolean
  directories: string[]
  poll_interval_seconds: number
  stable_checks: number
  transcode_non_mp4: boolean
  delete_origin_after_transcode: boolean
  reencode_h264: boolean
}

export type DownloadWatchRecord = {
  id: number
  source_dir: string
  local_path: string
  file_identity: string
  observed_size: number
  observed_mtime: number
  stable_count: number
  status: string
  encoding_status: string
  recorded_file_id?: number | null
  error_message: string
  first_seen_at: string
  registered_at?: string | null
  updated_at: string
}

export type DouyinTask = {
  id: number
  task_type: string
  input_url: string
  status: string
  max_items: number
  progress_total: number
  progress_done: number
  error_message: string
  created_at: string
  started_at?: string | null
  ended_at?: string | null
  updated_at: string
}

export type DouyinDownloadedItem = {
  id: number
  task_id: number
  aweme_id: string
  author: string
  description: string
  local_path: string
  file_identity: string
  source_url: string
  status: string
  error_message: string
  recorded_file_id?: number | null
  created_at: string
  updated_at: string
}

export type YoutubeMetric = {
  id: number
  youtube_video_id: string
  metric_date: string
  view_count: number
  like_count: number
  comment_count: number
  fetched_at: string
}

export type EventRecord = {
  id: number
  event_type: string
  message: string
  job_id?: number | null
  file_id?: number | null
  upload_id?: number | null
  douyin_task_id?: number | null
  level: string
  created_at: string
}

export type RuntimeProcess = {
  job_id: number
  room_id?: number
  pid: number
  output_dir: string
  started_at?: string
}

export type DashboardSummary = {
  rooms_total: number
  rooms_enabled: number
  active_jobs: number
  files_today: number
  uploads_pending: number
  uploads_failed: number
  douyin_running: number
  runtime_processes: number
  watch_registered: number
  metrics_cached: number
}

export type DashboardData = {
  summary: DashboardSummary
  rooms: Room[]
  active_jobs: RecordingJob[]
  recent_uploads: UploadRecord[]
  recent_events: EventRecord[]
  recording_runtime: RuntimeProcess[]
  download_watch: {
    settings: DownloadWatchSettings
    records: DownloadWatchRecord[]
  }
  metrics: YoutubeMetric[]
}

export type ConfigSetting = {
  key: string
  value: unknown
  category: string
  updated_at?: string
}

export type ConfigSection = {
  section: string
  values: Record<string, unknown>
}
