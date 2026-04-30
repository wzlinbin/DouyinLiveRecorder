import {
  CloudUploadOutlined,
  FileDoneOutlined,
  FolderAddOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  SyncOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { Button, Card, Empty, List, message, Space, Table, Typography } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { adminApi, getErrorMessage } from '../api/client'
import MetricCard from '../components/MetricCard'
import PageHeader from '../components/PageHeader'
import PlatformIcon from '../components/PlatformIcon'
import RealtimeLog from '../components/RealtimeLog'
import StatusBadge from '../components/StatusBadge'
import { useAppStore } from '../stores/appStore'
import type { DashboardData, Room } from '../types/admin'
import { asBool } from '../utils/format'

function Dashboard() {
  const navigate = useNavigate()
  const token = useAppStore((state) => state.token)
  const dashboard = useAppStore((state) => state.dashboard)
  const setDashboard = useAppStore((state) => state.setDashboard)
  const [loading, setLoading] = useState(false)

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    try {
      const [data, events] = await Promise.all([adminApi.dashboard(), adminApi.events(50)])
      setDashboard({ ...data, recent_events: events })
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [setDashboard])

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  const data = dashboard as DashboardData | undefined
  const summary = data?.summary

  return (
    <div className="page-stack">
      <PageHeader
        title="仪表盘"
        subtitle="聚合直播间状态、录制进程、上传队列、下载监控和最近事件。"
        extra={
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadDashboard}>
            刷新
          </Button>
        }
      />

      <div className="metric-grid">
        <MetricCard
          title="直播间"
          value={summary?.rooms_total ?? 0}
          caption={`启用 ${summary?.rooms_enabled ?? 0} 个`}
          icon={<VideoCameraOutlined />}
        />
        <MetricCard
          title="活跃录制"
          value={summary?.active_jobs ?? 0}
          caption={`进程 ${summary?.runtime_processes ?? 0} 个`}
          icon={<FileDoneOutlined />}
        />
        <MetricCard
          title="上传队列"
          value={summary?.uploads_pending ?? 0}
          caption={`失败 ${summary?.uploads_failed ?? 0} 个`}
          icon={<CloudUploadOutlined />}
        />
        <MetricCard
          title="今日文件"
          value={summary?.files_today ?? 0}
          caption={`监控登记 ${summary?.watch_registered ?? 0} 个`}
          icon={<FileSearchOutlined />}
        />
      </div>

      <div className="dashboard-grid">
        <div className="page-stack">
          <Card title="快捷操作">
            <Space wrap>
              <Button type="primary" icon={<VideoCameraOutlined />} onClick={() => navigate('/rooms')}>
                管理直播间
              </Button>
              <Button icon={<FolderAddOutlined />} onClick={() => navigate('/douyin')}>
                新建下载任务
              </Button>
              <Button
                icon={<FileSearchOutlined />}
                onClick={async () => {
                  try {
                    const result = await adminApi.scanDownloadWatch(token)
                    message.success(`扫描完成：登记 ${result.registered} 个文件`)
                    await loadDashboard()
                  } catch (error) {
                    message.error(getErrorMessage(error))
                  }
                }}
              >
                扫描下载目录
              </Button>
              <Button
                icon={<SyncOutlined />}
                onClick={async () => {
                  try {
                    const result = await adminApi.refreshMetrics(token)
                    message.success(`指标刷新完成：更新 ${result.updated} 条`)
                    await loadDashboard()
                  } catch (error) {
                    message.error(getErrorMessage(error))
                  }
                }}
              >
                刷新 YouTube 指标
              </Button>
            </Space>
          </Card>

          <Card title="直播间概览">
            <Table<Room>
              rowKey="id"
              loading={loading}
              dataSource={data?.rooms || []}
              pagination={{ pageSize: 6 }}
              columns={[
                {
                  title: '房间',
                  dataIndex: 'name',
                  render: (_, room) => (
                    <Space>
                      <PlatformIcon platform={room.platform} />
                      <div>
                        <Typography.Text strong>{room.name || '未命名直播间'}</Typography.Text>
                        <div className="muted">{room.url}</div>
                      </div>
                    </Space>
                  ),
                },
                { title: '清晰度', dataIndex: 'quality', width: 100 },
                {
                  title: '启用',
                  dataIndex: 'enabled',
                  width: 90,
                  render: (enabled) => (asBool(enabled) ? '是' : '否'),
                },
                {
                  title: '状态',
                  dataIndex: 'display_status',
                  width: 120,
                  render: (status) => <StatusBadge status={status} pulse />,
                },
              ]}
            />
          </Card>

          <div className="split-grid">
            <Card title="活跃任务">
              <List
                dataSource={data?.active_jobs || []}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无活跃任务" /> }}
                renderItem={(job) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Space>
                          任务 #{job.id}
                          <StatusBadge status={job.status} />
                        </Space>
                      }
                      description={`房间 #${job.room_id} · ${job.updated_at}`}
                    />
                  </List.Item>
                )}
              />
            </Card>
            <Card title="录制进程">
              <List
                dataSource={data?.recording_runtime || []}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运行进程" /> }}
                renderItem={(runtime) => (
                  <List.Item>
                    <List.Item.Meta
                      title={`任务 #${runtime.job_id}`}
                      description={
                        <span>
                          PID {runtime.pid} · {runtime.output_dir}
                        </span>
                      }
                    />
                  </List.Item>
                )}
              />
            </Card>
          </div>
        </div>

        <div className="page-stack">
          <Card title="最近事件">
            <RealtimeLog events={data?.recent_events || []} />
          </Card>
          <Card title="最近上传">
            <List
              dataSource={data?.recent_uploads || []}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无上传记录" /> }}
              renderItem={(upload) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space>
                        {upload.title || upload.local_path}
                        <StatusBadge status={upload.status} />
                      </Space>
                    }
                    description={`重试 ${upload.retry_count} 次 · ${upload.updated_at}`}
                  />
                </List.Item>
              )}
            />
          </Card>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
