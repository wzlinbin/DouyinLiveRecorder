import { Empty, Typography } from 'antd'
import type { EventRecord } from '../types/admin'
import { formatDateTime } from '../utils/format'
import StatusBadge from './StatusBadge'

type RealtimeLogProps = {
  events: EventRecord[]
}

const eventTypeText: Record<string, string> = {
  startup: '系统启动',
  config_update: '配置更新',
  config_export: '配置导出',
  config_import: '配置导入',
  room_deleted: '直播间删除',
  recording_start_requested: '请求开始录制',
  recording_stop_requested: '请求停止录制',
  recording_process_started: '录制进程启动',
  recording_process_stopped: '录制进程停止',
  recording_process_finished: '录制进程结束',
  recording_job_deleted: '录制任务删除',
  file_renamed: '文件重命名',
  file_deleted: '文件删除',
  transcode_completed: '转码完成',
  transcode_failed: '转码失败',
  upload_retry_requested: '请求重试上传',
  upload_completed: '上传完成',
  upload_disabled: '上传已停用',
  upload_loop_error: '上传轮询错误',
  download_watch_settings: '下载监控设置更新',
  download_watch_registered: '下载监控登记文件',
  download_watch_error: '下载监控错误',
  douyin_task_created: '抖音下载任务创建',
  douyin_task_completed: '抖音下载任务完成',
  douyin_task_failed: '抖音下载任务失败',
  douyin_task_deleted: '抖音下载任务删除',
  douyin_item_downloaded: '抖音文件下载完成',
  youtube_metrics_refreshed: 'YouTube 指标刷新',
  youtube_oauth_started: 'YouTube 授权开始',
  youtube_oauth_completed: 'YouTube 授权完成',
  command_worker_error: '命令执行错误',
}

function translateEventType(type: string) {
  return eventTypeText[type] || type.replace(/_/g, ' ')
}

function translateEventMessage(message: string) {
  const replacements: Array<[RegExp, string]> = [
    [/^Initial ini import completed$/, '已完成初始 ini 导入'],
    [/^Updated ini section (.+)$/, '已更新 ini 配置段：$1'],
    [/^Exported (\d+) sections and (\d+) rooms$/, '已导出 $1 个配置段和 $2 个直播间'],
    [/^Imported (\d+) setting sections and (\d+) room lines$/, '已导入 $1 个配置段和 $2 条直播间配置'],
    [/^Room (\d+) deleted$/, '直播间 #$1 已删除'],
    [/^Start requested for room (\d+)$/, '已请求开始录制直播间 #$1'],
    [/^Stop requested for room (\d+)$/, '已请求停止录制直播间 #$1'],
    [/^Recording process started with pid (\d+)$/, '录制进程已启动，PID $1'],
    [/^Recording process stopped for job (\d+)$/, '录制任务 #$1 的进程已停止'],
    [/^Recording process exited with code (.+)$/, '录制进程退出，退出码 $1'],
    [/^Recording job (\d+) deleted$/, '录制任务 #$1 已删除'],
    [/^Renamed (.+) to (.+)$/, '文件已从 $1 重命名为 $2'],
    [/^Deleted (.+)$/, '文件已删除：$1'],
    [/^Transcoded (.+) to MP4$/, '文件已转码为 MP4：$1'],
    [/^Registered downloaded file (.+)$/, '下载监控已登记文件：$1'],
    [/^Download watch settings updated$/, '下载监控设置已更新'],
    [/^Retry requested for upload (\d+)$/, '已请求重试上传 #$1'],
    [/^Upload (\d+) completed$/, '上传 #$1 已完成'],
    [/^YouTube client secret file is missing$/, '缺少 YouTube 客户端密钥文件'],
    [/^Created YouTube OAuth authorization URL$/, '已生成 YouTube OAuth 授权链接'],
    [/^Saved YouTube OAuth token$/, '已保存 YouTube OAuth 令牌'],
    [/^Refreshed metrics for (\d+) videos$/, '已刷新 $1 个视频的指标'],
    [/^Douyin (.+) task created$/, '抖音下载任务已创建：$1'],
    [/^Douyin task (\d+) (.+)$/, '抖音下载任务 #$1 状态：$2'],
    [/^Downloaded Douyin item (.+)$/, '抖音条目已下载：$1'],
  ]
  for (const [pattern, replacement] of replacements) {
    if (pattern.test(message)) {
      return message.replace(pattern, replacement)
    }
  }
  return message
}

function RealtimeLog({ events }: RealtimeLogProps) {
  if (!events.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无事件" />
  }

  return (
    <div className="log-list">
      {events.map((event) => (
        <div className="log-item" key={event.id}>
          <div className="toolbar-row" style={{ justifyContent: 'space-between' }}>
            <Typography.Text strong>{translateEventType(event.event_type)}</Typography.Text>
            <StatusBadge status={event.level} />
          </div>
          <Typography.Text>{translateEventMessage(event.message)}</Typography.Text>
          <Typography.Text type="secondary">{formatDateTime(event.created_at)}</Typography.Text>
        </div>
      ))}
    </div>
  )
}

export default RealtimeLog
