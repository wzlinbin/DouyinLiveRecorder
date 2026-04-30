import axios from 'axios'
import type {
  ApiList,
  ConfigSection,
  ConfigSetting,
  DashboardData,
  DouyinDownloadedItem,
  DouyinTask,
  DownloadWatchRecord,
  DownloadWatchSettings,
  EventRecord,
  RecordedFile,
  RecordingJob,
  Room,
  UploadRecord,
  YoutubeMetric,
} from '../types/admin'

const api = axios.create({
  baseURL: '/api',
  timeout: 20000,
})

function authHeaders(token: string) {
  return token ? { 'X-Admin-Token': token } : undefined
}

export function getErrorMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 401) {
      return '管理员 Token 无效或未保存，请在右上角输入 X-Admin-Token 后点击保存。'
    }
    if (error.response?.status === 503) {
      return '服务端未配置 ADMIN_API_TOKEN，写操作暂不可用。'
    }
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') {
      return detail
    }
    return error.message
  }
  return error instanceof Error ? error.message : '请求失败'
}

export const adminApi = {
  async dashboard() {
    const { data } = await api.get<DashboardData>('/dashboard')
    return data
  },
  async rooms() {
    const { data } = await api.get<ApiList<Room>>('/rooms')
    return data.data
  },
  async createRoom(token: string, payload: Pick<Room, 'url' | 'name' | 'quality'> & { enabled: boolean }) {
    const { data } = await api.post<Room>('/rooms', payload, { headers: authHeaders(token) })
    return data
  },
  async updateRoom(token: string, roomId: number, payload: Partial<Pick<Room, 'url' | 'name' | 'quality' | 'enabled'>>) {
    const { data } = await api.patch<Room>(`/rooms/${roomId}`, payload, { headers: authHeaders(token) })
    return data
  },
  async deleteRoom(token: string, roomId: number) {
    const { data } = await api.delete<{ deleted: boolean }>(`/rooms/${roomId}`, { headers: authHeaders(token) })
    return data
  },
  async startRoom(token: string, roomId: number) {
    const { data } = await api.post<RecordingJob>(`/rooms/${roomId}/start`, undefined, { headers: authHeaders(token) })
    return data
  },
  async stopRoom(token: string, roomId: number) {
    const { data } = await api.post<RecordingJob>(`/rooms/${roomId}/stop`, undefined, { headers: authHeaders(token) })
    return data
  },
  async jobs(status?: string) {
    const { data } = await api.get<ApiList<RecordingJob>>('/jobs', { params: status ? { status } : undefined })
    return data.data
  },
  async files(params?: { room_id?: number; job_id?: number; status?: string }) {
    const { data } = await api.get<ApiList<RecordedFile>>('/files', { params })
    return data.data
  },
  async transcodeFile(token: string, fileId: number, payload: { delete_origin: boolean; reencode_h264: boolean }) {
    const { data } = await api.post<RecordedFile>(`/files/${fileId}/transcode`, payload, { headers: authHeaders(token) })
    return data
  },
  async renameFile(token: string, fileId: number, filename: string) {
    const { data } = await api.patch<RecordedFile>(`/files/${fileId}/rename`, { filename }, { headers: authHeaders(token) })
    return data
  },
  async deleteFile(token: string, fileId: number) {
    const { data } = await api.delete<{ deleted: boolean }>(`/files/${fileId}`, { headers: authHeaders(token) })
    return data
  },
  async uploads(status?: string) {
    const { data } = await api.get<ApiList<UploadRecord>>('/uploads', { params: status ? { status } : undefined })
    return data.data
  },
  async retryUpload(token: string, uploadId: number) {
    const { data } = await api.post<UploadRecord>(`/uploads/${uploadId}/retry`, undefined, { headers: authHeaders(token) })
    return data
  },
  async downloadWatch() {
    const { data } = await api.get<{ settings: DownloadWatchSettings; records: DownloadWatchRecord[] }>('/download-watch')
    return data
  },
  async scanDownloadWatch(token: string) {
    const { data } = await api.post<{ candidates: number; registered: number }>('/download-watch/scan', undefined, {
      headers: authHeaders(token),
    })
    return data
  },
  async updateDownloadWatch(token: string, payload: Partial<DownloadWatchSettings>) {
    const { data } = await api.patch<DownloadWatchSettings>('/download-watch/settings', payload, {
      headers: authHeaders(token),
    })
    return data
  },
  async douyinTasks() {
    const { data } = await api.get<ApiList<DouyinTask>>('/douyin/tasks')
    return data.data
  },
  async douyinTask(taskId: number) {
    const { data } = await api.get<{ task: DouyinTask; items: DouyinDownloadedItem[] }>(`/douyin/tasks/${taskId}`)
    return data
  },
  async createDouyinSingle(token: string, payload: { url: string; output_dir?: string; cookie?: string; proxy?: string; overwrite: boolean }) {
    const { data } = await api.post<DouyinTask>('/douyin/download', payload, { headers: authHeaders(token) })
    return data
  },
  async createDouyinUser(token: string, payload: { url: string; output_dir?: string; cookie?: string; proxy?: string; max_items: number; overwrite: boolean }) {
    const { data } = await api.post<DouyinTask>('/douyin/user-download', payload, { headers: authHeaders(token) })
    return data
  },
  async metrics() {
    const { data } = await api.get<ApiList<YoutubeMetric>>('/metrics/videos')
    return data.data
  },
  async refreshMetrics(token: string) {
    const { data } = await api.post<{ requested: number; updated: number }>('/metrics/videos/refresh', undefined, {
      headers: authHeaders(token),
    })
    return data
  },
  async events(limit = 50) {
    const { data } = await api.get<ApiList<EventRecord>>('/events/recent', { params: { limit } })
    return data.data
  },
  async config() {
    const { data } = await api.get<ApiList<ConfigSetting>>('/config')
    return data.data
  },
  async configSection(section: string) {
    const { data } = await api.get<ConfigSection>(`/config/${section}`)
    return data
  },
  async updateConfigSection(token: string, section: string, values: Record<string, unknown>) {
    const { data } = await api.patch<ConfigSection>(`/config/${section}`, { values }, { headers: authHeaders(token) })
    return data
  },
  async importConfig(token: string) {
    const { data } = await api.post<{ imported: number }>('/config/import', undefined, { headers: authHeaders(token) })
    return data
  },
  async exportConfig(token: string) {
    const { data } = await api.post<{ exported: number }>('/config/export', undefined, { headers: authHeaders(token) })
    return data
  },
}
