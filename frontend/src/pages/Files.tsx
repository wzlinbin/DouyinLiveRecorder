import { DeleteOutlined, EditOutlined, ReloadOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, message, Modal, Popconfirm, Select, Space, Table, Tooltip, Typography } from 'antd'
import type { Key } from 'react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminApi, getErrorMessage } from '../api/client'
import FilePreview from '../components/FilePreview'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { useAppStore } from '../stores/appStore'
import type { RecordedFile } from '../types/admin'
import { fileName, formatBytes, formatDateTime, formatDuration, formatSource } from '../utils/format'

type RenameFormValues = {
  filename: string
}

const transcodableFormats = new Set(['ts', 'flv', 'mkv', 'mov', 'webm'])

function canTranscode(file: RecordedFile) {
  return transcodableFormats.has((file.format || '').toLowerCase())
}

function Files() {
  const token = useAppStore((state) => state.token)
  const [files, setFiles] = useState<RecordedFile[]>([])
  const [loading, setLoading] = useState(false)
  const [actionKey, setActionKey] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<string | undefined>()
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [renamingFile, setRenamingFile] = useState<RecordedFile | null>(null)
  const [renameForm] = Form.useForm<RenameFormValues>()

  const loadFiles = useCallback(async () => {
    setLoading(true)
    try {
      setFiles(await adminApi.files(status ? { status } : undefined))
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    loadFiles()
  }, [loadFiles])

  const filteredFiles = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) {
      return files
    }
    return files.filter((file) => file.local_path.toLowerCase().includes(normalized))
  }, [files, query])

  const transcodeFile = async (file: RecordedFile) => {
    setActionKey(`transcode:${file.id}`)
    try {
      await adminApi.transcodeFile(token, file.id, { delete_origin: false, reencode_h264: false })
      message.success('补转码已完成，文件已登记到上传队列')
      await loadFiles()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setActionKey(null)
    }
  }

  const deleteFile = async (file: RecordedFile) => {
    setActionKey(`delete:${file.id}`)
    try {
      await adminApi.deleteFile(token, file.id)
      message.success('文件已删除')
      setSelectedRowKeys((keys) => keys.filter((key) => key !== file.id))
      await loadFiles()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setActionKey(null)
    }
  }

  const deleteSelected = async () => {
    const ids = selectedRowKeys.map(Number)
    if (!ids.length) {
      return
    }
    setActionKey('delete:selected')
    try {
      const results = await Promise.allSettled(ids.map((id) => adminApi.deleteFile(token, id)))
      const succeededIds = ids.filter((_, index) => results[index].status === 'fulfilled')
      const failedResults = results.filter((result) => result.status === 'rejected')
      if (succeededIds.length) {
        message.success(`已删除 ${succeededIds.length} 个文件`)
      }
      if (failedResults.length) {
        const firstError = failedResults[0]
        const reason = firstError.status === 'rejected' ? getErrorMessage(firstError.reason) : ''
        message.error(`${failedResults.length} 个文件删除失败${reason ? `：${reason}` : ''}`)
      }
      setSelectedRowKeys((keys) => keys.filter((key) => !succeededIds.includes(Number(key))))
      await loadFiles()
    } finally {
      setActionKey(null)
    }
  }

  const openRename = (file: RecordedFile) => {
    setRenamingFile(file)
    renameForm.setFieldsValue({ filename: fileName(file.local_path) })
  }

  const saveRename = async (values: RenameFormValues) => {
    if (!renamingFile) {
      return
    }
    setActionKey(`rename:${renamingFile.id}`)
    try {
      await adminApi.renameFile(token, renamingFile.id, values.filename)
      message.success('文件已重命名')
      setRenamingFile(null)
      await loadFiles()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setActionKey(null)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="文件管理"
        subtitle="查看自动录制、自动转码和自动上传登记的文件；这里主要用于排查、重命名和删除异常记录。"
        extra={
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadFiles}>
            刷新
          </Button>
        }
      />

      <Alert
        type="info"
        showIcon
        message="正常流程不需要手动转码"
        description="录制完成后的转码和上传由后台自动处理。只有发现非 MP4 文件未被自动处理时，才需要在这里使用“补转码”。"
      />

      <Card>
        {filteredFiles.length ? (
          <div className="preview-grid" style={{ marginBottom: 16 }}>
            {filteredFiles.slice(0, 3).map((file) => (
              <FilePreview key={file.id} file={file} />
            ))}
          </div>
        ) : null}
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索文件路径"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            style={{ width: 280 }}
          />
          <Select
            allowClear
            placeholder="状态"
            value={status}
            onChange={setStatus}
            style={{ width: 160 }}
            options={[
              { value: 'ready', label: '就绪' },
              { value: 'uploaded', label: '已上传' },
              { value: 'failed', label: '失败' },
            ]}
          />
          <Popconfirm
            title="删除选中文件"
            description="会同时删除磁盘文件和后台记录。"
            okText="删除"
            cancelText="取消"
            onConfirm={deleteSelected}
            disabled={!selectedRowKeys.length}
          >
            <Button danger icon={<DeleteOutlined />} disabled={!selectedRowKeys.length} loading={actionKey === 'delete:selected'}>
              批量删除
            </Button>
          </Popconfirm>
        </Space>
        <Table<RecordedFile>
          rowKey="id"
          loading={loading}
          dataSource={filteredFiles}
          pagination={{ pageSize: 25, showSizeChanger: true }}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
          }}
          columns={[
            {
              title: '文件名',
              dataIndex: 'local_path',
              render: (path) => (
                <div>
                  <Typography.Text strong>{fileName(path)}</Typography.Text>
                  <div className="muted">{path}</div>
                </div>
              ),
            },
            { title: '大小', dataIndex: 'size_bytes', width: 120, render: formatBytes },
            { title: '时长', dataIndex: 'duration_seconds', width: 100, render: formatDuration },
            { title: '格式', dataIndex: 'format', width: 90 },
            { title: '来源', dataIndex: 'source', width: 130, render: formatSource },
            { title: '状态', dataIndex: 'status', width: 120, render: (value) => <StatusBadge status={value} /> },
            { title: '创建时间', dataIndex: 'created_at', width: 180, render: formatDateTime },
            {
              title: '操作',
              width: 230,
              render: (_, file) => (
                <Space wrap>
                  {canTranscode(file) ? (
                    <Tooltip title="用于自动转码失败后的手动补救">
                      <Button size="small" icon={<SyncOutlined />} loading={actionKey === `transcode:${file.id}`} onClick={() => transcodeFile(file)}>
                        补转码
                      </Button>
                    </Tooltip>
                  ) : null}
                  <Button size="small" icon={<EditOutlined />} onClick={() => openRename(file)}>
                    重命名
                  </Button>
                  <Popconfirm
                    title="删除文件"
                    description="会同时删除磁盘文件和后台记录。"
                    okText="删除"
                    cancelText="取消"
                    onConfirm={() => deleteFile(file)}
                  >
                    <Button size="small" danger icon={<DeleteOutlined />} loading={actionKey === `delete:${file.id}`}>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="重命名文件"
        open={!!renamingFile}
        onCancel={() => setRenamingFile(null)}
        onOk={() => renameForm.submit()}
        confirmLoading={renamingFile ? actionKey === `rename:${renamingFile.id}` : false}
        destroyOnClose
      >
        <Form form={renameForm} layout="vertical" onFinish={saveRename}>
          <Form.Item name="filename" label="新文件名" rules={[{ required: true, message: '请输入文件名' }]}>
            <Input placeholder="example.mp4" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Files
