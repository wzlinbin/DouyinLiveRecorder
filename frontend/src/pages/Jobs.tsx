import { DeleteOutlined, PauseCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Drawer, message, Popconfirm, Space, Table, Tabs } from 'antd'
import type { Key } from 'react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminApi, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { useAppStore } from '../stores/appStore'
import type { RecordedFile, RecordingJob } from '../types/admin'
import { fileName, formatBytes, formatDateTime, formatDuration } from '../utils/format'

const tabs = [
  { key: 'active', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '失败' },
]

function statusFilter(tab: string) {
  if (tab === 'completed') {
    return 'completed'
  }
  if (tab === 'failed') {
    return 'failed'
  }
  return undefined
}

function Jobs() {
  const token = useAppStore((state) => state.token)
  const [activeTab, setActiveTab] = useState('active')
  const [jobs, setJobs] = useState<RecordingJob[]>([])
  const [files, setFiles] = useState<RecordedFile[]>([])
  const [loading, setLoading] = useState(false)
  const [stoppingJobId, setStoppingJobId] = useState<number | null>(null)
  const [deletingJobId, setDeletingJobId] = useState<number | null>(null)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [selectedJob, setSelectedJob] = useState<RecordingJob | null>(null)

  const loadJobs = useCallback(async () => {
    setLoading(true)
    try {
      const nextJobs = await adminApi.jobs(statusFilter(activeTab))
      setJobs(activeTab === 'active' ? nextJobs.filter((job) => ['pending', 'probing', 'recording', 'stopping'].includes(job.status)) : nextJobs)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [activeTab])

  useEffect(() => {
    loadJobs()
  }, [loadJobs])

  useEffect(() => {
    if (!selectedJob) {
      setFiles([])
      return
    }
    adminApi
      .files({ job_id: selectedJob.id })
      .then(setFiles)
      .catch((error) => message.error(getErrorMessage(error)))
  }, [selectedJob])

  const activeStatuses = ['pending', 'probing', 'recording', 'stopping']

  const stopJob = async (job: RecordingJob) => {
    setStoppingJobId(job.id)
    try {
      await adminApi.stopRoom(token, job.room_id)
      message.success('已提交停止录制命令')
      await loadJobs()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setStoppingJobId(null)
    }
  }

  const deleteJob = async (job: RecordingJob) => {
    setDeletingJobId(job.id)
    try {
      await adminApi.deleteJob(token, job.id)
      message.success('任务已删除')
      setSelectedRowKeys((keys) => keys.filter((key) => key !== job.id))
      if (selectedJob?.id === job.id) {
        setSelectedJob(null)
      }
      await loadJobs()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setDeletingJobId(null)
    }
  }

  const deleteSelected = async () => {
    const ids = selectedRowKeys.map(Number)
    if (!ids.length) {
      return
    }
    setDeletingJobId(-1)
    try {
      const results = await Promise.allSettled(ids.map((id) => adminApi.deleteJob(token, id)))
      const succeededIds = ids.filter((_, index) => results[index].status === 'fulfilled')
      const failedResults = results.filter((result) => result.status === 'rejected')
      if (succeededIds.length) {
        message.success(`已删除 ${succeededIds.length} 个任务`)
      }
      if (failedResults.length) {
        const firstError = failedResults[0]
        const reason = firstError.status === 'rejected' ? getErrorMessage(firstError.reason) : ''
        message.error(`${failedResults.length} 个任务删除失败${reason ? `：${reason}` : ''}`)
      }
      setSelectedRowKeys((keys) => keys.filter((key) => !succeededIds.includes(Number(key))))
      if (selectedJob && succeededIds.includes(selectedJob.id)) {
        setSelectedJob(null)
      }
      await loadJobs()
    } finally {
      setDeletingJobId(null)
    }
  }

  const parsedSnapshot = useMemo(() => {
    if (!selectedJob?.config_snapshot) {
      return '{}'
    }
    try {
      return JSON.stringify(JSON.parse(selectedJob.config_snapshot), null, 2)
    } catch {
      return selectedJob.config_snapshot
    }
  }, [selectedJob])

  return (
    <div className="page-stack">
      <PageHeader
        title="录制任务"
        subtitle="按状态查看录制任务，并在详情里检查配置快照、关联文件和错误信息。"
        extra={
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadJobs}>
            刷新
          </Button>
        }
      />

      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
          <Popconfirm
            title="删除选中任务"
            description="只删除任务记录，不删除已经登记的文件。进行中的任务不能删除。"
            okText="删除"
            cancelText="取消"
            onConfirm={deleteSelected}
            disabled={!selectedRowKeys.length}
          >
            <Button danger icon={<DeleteOutlined />} disabled={!selectedRowKeys.length} loading={deletingJobId === -1}>
              批量删除
            </Button>
          </Popconfirm>
        </Space>
        <Tabs activeKey={activeTab} items={tabs} onChange={setActiveTab} />
        <Table<RecordingJob>
          rowKey="id"
          loading={loading}
          dataSource={jobs}
          pagination={{ pageSize: 25, showSizeChanger: true }}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
            getCheckboxProps: (job) => ({ disabled: activeStatuses.includes(job.status) }),
          }}
          columns={[
            { title: '任务 ID', dataIndex: 'id', width: 100, render: (id) => `#${id}` },
            { title: '直播间', dataIndex: 'room_id', width: 100, render: (id) => `#${id}` },
            { title: '状态', dataIndex: 'status', width: 120, render: (status) => <StatusBadge status={status} pulse /> },
            { title: '开始时间', dataIndex: 'started_at', render: formatDateTime },
            { title: '结束时间', dataIndex: 'ended_at', render: formatDateTime },
            { title: '更新时间', dataIndex: 'updated_at', render: formatDateTime },
            {
              title: '操作',
              width: 170,
              render: (_, job) => (
                <Space>
                  <Button type="link" onClick={() => setSelectedJob(job)}>
                    详情
                  </Button>
                  {activeStatuses.includes(job.status) ? (
                    <Popconfirm
                      title="停止录制"
                      description="会停止当前录制进程，并保存已经生成的文件。"
                      okText="停止"
                      cancelText="取消"
                      onConfirm={() => stopJob(job)}
                    >
                      <Button type="link" danger icon={<PauseCircleOutlined />} loading={stoppingJobId === job.id}>
                        停止
                      </Button>
                    </Popconfirm>
                  ) : null}
                  {!activeStatuses.includes(job.status) ? (
                    <Popconfirm
                      title="删除任务"
                      description="只删除任务记录，不删除已经登记的文件。"
                      okText="删除"
                      cancelText="取消"
                      onConfirm={() => deleteJob(job)}
                    >
                      <Button type="link" danger icon={<DeleteOutlined />} loading={deletingJobId === job.id}>
                        删除
                      </Button>
                    </Popconfirm>
                  ) : null}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Drawer title={selectedJob ? `任务 #${selectedJob.id}` : '任务详情'} width={620} open={!!selectedJob} onClose={() => setSelectedJob(null)}>
        {selectedJob ? (
          <div className="page-stack">
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="状态">
                <StatusBadge status={selectedJob.status} />
              </Descriptions.Item>
              <Descriptions.Item label="直播间">#{selectedJob.room_id}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatDateTime(selectedJob.started_at)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDateTime(selectedJob.ended_at)}</Descriptions.Item>
              <Descriptions.Item label="执行进程">{selectedJob.worker_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="错误">{selectedJob.error_message || '-'}</Descriptions.Item>
            </Descriptions>

            <Card title="关联文件" size="small">
              <Table<RecordedFile>
                rowKey="id"
                size="small"
                dataSource={files}
                pagination={false}
                columns={[
                  { title: '文件', dataIndex: 'local_path', render: (path) => fileName(path) },
                  { title: '大小', dataIndex: 'size_bytes', width: 100, render: formatBytes },
                  { title: '时长', dataIndex: 'duration_seconds', width: 90, render: formatDuration },
                  { title: '状态', dataIndex: 'status', width: 90, render: (status) => <StatusBadge status={status} /> },
                ]}
              />
            </Card>

            <Card title="配置快照" size="small">
              <pre className="mono" style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                {parsedSnapshot}
              </pre>
            </Card>
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}

export default Jobs
