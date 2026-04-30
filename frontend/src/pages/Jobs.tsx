import { ReloadOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Drawer, message, Table, Tabs } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminApi, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import type { RecordedFile, RecordingJob } from '../types/admin'
import { fileName, formatBytes, formatDuration } from '../utils/format'

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
  const [activeTab, setActiveTab] = useState('active')
  const [jobs, setJobs] = useState<RecordingJob[]>([])
  const [files, setFiles] = useState<RecordedFile[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedJob, setSelectedJob] = useState<RecordingJob | null>(null)

  const loadJobs = useCallback(async () => {
    setLoading(true)
    try {
      const nextJobs = await adminApi.jobs(statusFilter(activeTab))
      setJobs(
        activeTab === 'active'
          ? nextJobs.filter((job) => ['pending', 'probing', 'recording', 'stopping'].includes(job.status))
          : nextJobs,
      )
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
        <Tabs activeKey={activeTab} items={tabs} onChange={setActiveTab} />
        <Table<RecordingJob>
          rowKey="id"
          loading={loading}
          dataSource={jobs}
          columns={[
            { title: '任务 ID', dataIndex: 'id', width: 100, render: (id) => `#${id}` },
            { title: '房间', dataIndex: 'room_id', width: 100, render: (id) => `#${id}` },
            { title: '状态', dataIndex: 'status', width: 120, render: (status) => <StatusBadge status={status} pulse /> },
            { title: '开始时间', dataIndex: 'started_at', render: (value) => value || '-' },
            { title: '结束时间', dataIndex: 'ended_at', render: (value) => value || '-' },
            { title: '更新时间', dataIndex: 'updated_at' },
            {
              title: '操作',
              width: 100,
              render: (_, job) => (
                <Button type="link" onClick={() => setSelectedJob(job)}>
                  详情
                </Button>
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
              <Descriptions.Item label="房间">#{selectedJob.room_id}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{selectedJob.started_at || '-'}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{selectedJob.ended_at || '-'}</Descriptions.Item>
              <Descriptions.Item label="Worker">{selectedJob.worker_id || '-'}</Descriptions.Item>
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
