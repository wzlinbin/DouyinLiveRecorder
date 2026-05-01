import { ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Drawer, Empty, List, message, Space, Table, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminApi, getErrorMessage } from '../api/client'
import MetricChart from '../components/MetricChart'
import MetricCard from '../components/MetricCard'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { useAppStore } from '../stores/appStore'
import type { UploadRecord, YoutubeMetric } from '../types/admin'
import { fileName, formatDateTime, formatPrivacy } from '../utils/format'

function Uploads() {
  const token = useAppStore((state) => state.token)
  const [uploads, setUploads] = useState<UploadRecord[]>([])
  const [metrics, setMetrics] = useState<YoutubeMetric[]>([])
  const [loading, setLoading] = useState(false)
  const [refreshingMetrics, setRefreshingMetrics] = useState(false)
  const [retryingUploadId, setRetryingUploadId] = useState<number | null>(null)
  const [selectedUpload, setSelectedUpload] = useState<UploadRecord | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [nextUploads, nextMetrics] = await Promise.all([adminApi.uploads(), adminApi.metrics()])
      setUploads(nextUploads)
      setMetrics(nextMetrics)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const totals = useMemo(() => {
    return metrics.reduce(
      (acc, metric) => ({
        views: acc.views + metric.view_count,
        likes: acc.likes + metric.like_count,
        comments: acc.comments + metric.comment_count,
      }),
      { views: 0, likes: 0, comments: 0 },
    )
  }, [metrics])

  const retryUpload = async (upload: UploadRecord) => {
    setRetryingUploadId(upload.id)
    try {
      await adminApi.retryUpload(token, upload.id)
      message.success('已提交重试上传')
      await loadData()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setRetryingUploadId(null)
    }
  }

  const refreshMetrics = async () => {
    setRefreshingMetrics(true)
    try {
      const result = await adminApi.refreshMetrics(token)
      message.success(`指标刷新完成：更新 ${result.updated} 条`)
      await loadData()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setRefreshingMetrics(false)
    }
  }

  const selectedMetrics = useMemo(() => {
    if (!selectedUpload?.youtube_video_id) {
      return []
    }
    return metrics
      .filter((metric) => metric.youtube_video_id === selectedUpload.youtube_video_id)
      .sort((a, b) => b.metric_date.localeCompare(a.metric_date))
  }, [metrics, selectedUpload])

  return (
    <div className="page-stack">
      <PageHeader
        title="上传队列"
        subtitle="查看自动上传状态、失败重试和 YouTube 指标缓存。"
        extra={
          <>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={loadData}>
              刷新
            </Button>
            <Button type="primary" icon={<SyncOutlined />} loading={refreshingMetrics} onClick={refreshMetrics}>
              刷新指标
            </Button>
          </>
        }
      />

      <div className="metric-grid">
        <MetricCard title="播放量" value={totals.views.toLocaleString()} caption="已缓存视频合计" />
        <MetricCard title="点赞" value={totals.likes.toLocaleString()} caption="已缓存视频合计" />
        <MetricCard title="评论" value={totals.comments.toLocaleString()} caption="已缓存视频合计" />
        <MetricCard title="上传记录" value={uploads.length} caption={`失败 ${uploads.filter((item) => item.status === 'failed').length} 个`} />
      </div>

      <Card title="上传队列">
        <Table<UploadRecord>
          rowKey="id"
          loading={loading}
          dataSource={uploads}
          pagination={{ pageSize: 25, showSizeChanger: true }}
          columns={[
            {
              title: '文件',
              dataIndex: 'local_path',
              render: (path, upload) => (
                <div>
                  <Typography.Text strong>{upload.title || fileName(path)}</Typography.Text>
                  <div className="muted">{path}</div>
                </div>
              ),
            },
            { title: '可见性', dataIndex: 'privacy_status', width: 120, render: formatPrivacy },
            { title: '状态', dataIndex: 'status', width: 120, render: (value) => <StatusBadge status={value} pulse /> },
            { title: '重试次数', dataIndex: 'retry_count', width: 100 },
            { title: 'YouTube 视频 ID', dataIndex: 'youtube_video_id', width: 160, render: (value) => value || '-' },
            {
              title: '操作',
              width: 170,
              render: (_, upload) => (
                <Space>
                  <Button type="link" onClick={() => setSelectedUpload(upload)}>
                    详情
                  </Button>
                  <Button type="link" disabled={upload.status !== 'failed'} loading={retryingUploadId === upload.id} onClick={() => retryUpload(upload)}>
                    重试
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <div className="split-grid">
        <Card title="播放趋势">
          <MetricChart data={metrics} metric="view_count" label="播放量" />
        </Card>
        <Card title="互动趋势">
          <div className="page-stack">
            <MetricChart data={metrics} metric="like_count" label="点赞" />
            <MetricChart data={metrics} metric="comment_count" label="评论" />
          </div>
        </Card>
      </div>

      <Card title="指标历史">
        <List
          dataSource={metrics.slice(0, 12)}
          renderItem={(metric) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <span className="mono">{metric.youtube_video_id}</span>
                    <span>{metric.metric_date}</span>
                  </Space>
                }
                description={`播放 ${metric.view_count} · 点赞 ${metric.like_count} · 评论 ${metric.comment_count}`}
              />
            </List.Item>
          )}
        />
      </Card>

      <Drawer title={selectedUpload ? `上传 #${selectedUpload.id}` : '上传详情'} width={620} open={!!selectedUpload} onClose={() => setSelectedUpload(null)}>
        {selectedUpload ? (
          <div className="page-stack">
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="标题">{selectedUpload.title || fileName(selectedUpload.local_path)}</Descriptions.Item>
              <Descriptions.Item label="本地路径">{selectedUpload.local_path}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <StatusBadge status={selectedUpload.status} />
              </Descriptions.Item>
              <Descriptions.Item label="可见性">{formatPrivacy(selectedUpload.privacy_status)}</Descriptions.Item>
              <Descriptions.Item label="YouTube 视频 ID">{selectedUpload.youtube_video_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="重试次数">{selectedUpload.retry_count}</Descriptions.Item>
              <Descriptions.Item label="失败原因">{selectedUpload.failure_reason || '-'}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(selectedUpload.created_at)}</Descriptions.Item>
              <Descriptions.Item label="更新时间">{formatDateTime(selectedUpload.updated_at)}</Descriptions.Item>
            </Descriptions>

            <Card title="单视频趋势" size="small">
              {selectedMetrics.length ? (
                <div className="page-stack">
                  <MetricChart data={selectedMetrics} metric="view_count" label="播放量" />
                  <MetricChart data={selectedMetrics} metric="like_count" label="点赞" />
                  <MetricChart data={selectedMetrics} metric="comment_count" label="评论" />
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无该视频指标" />
              )}
            </Card>

            <Card title="指标明细" size="small">
              <Table<YoutubeMetric>
                rowKey="id"
                size="small"
                dataSource={selectedMetrics}
                pagination={{ pageSize: 6 }}
                columns={[
                  { title: '日期', dataIndex: 'metric_date' },
                  { title: '播放', dataIndex: 'view_count' },
                  { title: '点赞', dataIndex: 'like_count' },
                  { title: '评论', dataIndex: 'comment_count' },
                ]}
              />
            </Card>
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}

export default Uploads
