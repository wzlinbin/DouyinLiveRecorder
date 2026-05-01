export function asBool(value: boolean | number | string | null | undefined) {
  return value === true || value === 1 || value === '1' || value === 'true'
}

export function formatBytes(bytes?: number | null) {
  if (!bytes) {
    return '0 B'
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** index
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`
}

export function formatDuration(seconds?: number | null) {
  if (!seconds) {
    return '-'
  }
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = total % 60
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
    : `${minutes}:${String(rest).padStart(2, '0')}`
}

export function formatDateTime(value?: string | null) {
  if (!value) {
    return '-'
  }
  const normalized = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value.replace(' ', 'T')}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export function fileName(path: string) {
  return path.split(/[\\/]/).pop() || path
}

export function dirName(path: string) {
  const normalized = path.replace(/[\\/]+$/, '')
  const index = Math.max(normalized.lastIndexOf('\\'), normalized.lastIndexOf('/'))
  return index > 0 ? normalized.slice(0, index) : normalized
}

export function formatSource(value?: string | null) {
  const sourceText: Record<string, string> = {
    recording: '录制',
    download_watch: '下载监控',
    transcode: '转码',
    douyin: '抖音下载',
    unittest: '测试',
  }
  const normalized = (value || '').toLowerCase()
  return sourceText[normalized] || value || '-'
}

export function formatPrivacy(value?: string | null) {
  const privacyText: Record<string, string> = {
    public: '公开',
    private: '私密',
    unlisted: '不公开列出',
  }
  const normalized = (value || '').toLowerCase()
  return privacyText[normalized] || value || '-'
}

export function formatTaskType(value?: string | null) {
  const taskTypeText: Record<string, string> = {
    single: '单视频',
    user: '用户批量',
    user_batch: '用户批量',
  }
  const normalized = (value || '').toLowerCase()
  return taskTypeText[normalized] || value || '-'
}
