import { Badge, Tag } from 'antd'
import type { StatusLevel } from '../types/admin'

const statusText: Record<string, string> = {
  idle: '空闲',
  disabled: '禁用',
  pending: '等待中',
  probing: '探测中',
  recording: '录制中',
  stopping: '停止中',
  completed: '已完成',
  completed_with_errors: '部分失败',
  interrupted: '已中断',
  failed: '失败',
  ready: '就绪',
  uploading: '上传中',
  uploaded: '已上传',
  queued: '排队中',
  running: '运行中',
  registered: '已登记',
  candidate: '候选',
  stable: '稳定',
  not_required: '无需处理',
  not_running: '未运行',
  skipped: '已跳过',
  retrying: '重试中',
  info: '信息',
  warning: '警告',
  error: '错误',
}

const levelMap: Record<string, StatusLevel> = {
  completed: 'success',
  recording: 'processing',
  running: 'processing',
  uploaded: 'success',
  registered: 'success',
  ready: 'success',
  stable: 'success',
  pending: 'warning',
  probing: 'warning',
  stopping: 'warning',
  queued: 'warning',
  uploading: 'warning',
  retrying: 'warning',
  candidate: 'warning',
  warning: 'warning',
  failed: 'error',
  interrupted: 'error',
  completed_with_errors: 'error',
  error: 'error',
  disabled: 'default',
  idle: 'default',
  info: 'default',
  not_required: 'default',
  not_running: 'default',
  skipped: 'default',
}

const tagColor: Record<StatusLevel, string> = {
  success: 'success',
  processing: 'processing',
  warning: 'warning',
  error: 'error',
  default: 'default',
}

type StatusBadgeProps = {
  status?: string | null
  pulse?: boolean
}

function StatusBadge({ status, pulse = false }: StatusBadgeProps) {
  const normalized = (status || 'idle').toLowerCase()
  const level = levelMap[normalized] || 'default'
  const label = statusText[normalized] || status || '未知'

  if (pulse && level === 'processing') {
    return <Badge status="processing" text={label} />
  }

  return <Tag color={tagColor[level]}>{label}</Tag>
}

export default StatusBadge
