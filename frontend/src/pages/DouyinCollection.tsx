import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { Button, Card, Form, Input, InputNumber, message, Popconfirm, Radio, Space, Switch, Table } from 'antd'
import type { Key } from 'react'
import { useCallback, useEffect, useState } from 'react'
import { adminApi, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import TaskProgress from '../components/TaskProgress'
import { useAppStore } from '../stores/appStore'
import type { DouyinTask } from '../types/admin'
import { formatDateTime, formatTaskType } from '../utils/format'

type DownloadMode = 'single' | 'user'

type DouyinFormValues = {
  mode: DownloadMode
  url: string
  output_dir?: string
  cookie?: string
  proxy?: string
  max_items?: number
  overwrite: boolean
}

function DouyinCollection() {
  const token = useAppStore((state) => state.token)
  const [tasks, setTasks] = useState<DouyinTask[]>([])
  const [loading, setLoading] = useState(false)
  const [deletingTaskId, setDeletingTaskId] = useState<number | null>(null)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [form] = Form.useForm<DouyinFormValues>()
  const mode = Form.useWatch('mode', form)

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try {
      setTasks(await adminApi.douyinTasks())
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTasks()
  }, [loadTasks])

  const createTask = async (values: DouyinFormValues) => {
    try {
      if (values.mode === 'user') {
        await adminApi.createDouyinUser(token, {
          url: values.url,
          output_dir: values.output_dir,
          cookie: values.cookie,
          proxy: values.proxy,
          max_items: values.max_items || 10,
          overwrite: values.overwrite,
        })
      } else {
        await adminApi.createDouyinSingle(token, {
          url: values.url,
          output_dir: values.output_dir,
          cookie: values.cookie,
          proxy: values.proxy,
          overwrite: values.overwrite,
        })
      }
      message.success('抖音下载任务已创建')
      form.resetFields()
      form.setFieldsValue({ mode: 'single', overwrite: false, max_items: 10 })
      await loadTasks()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const activeStatuses = ['queued', 'running']

  const deleteTask = async (task: DouyinTask) => {
    setDeletingTaskId(task.id)
    try {
      await adminApi.deleteDouyinTask(token, task.id)
      message.success('任务已删除')
      setSelectedRowKeys((keys) => keys.filter((key) => key !== task.id))
      await loadTasks()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setDeletingTaskId(null)
    }
  }

  const deleteSelected = async () => {
    const ids = selectedRowKeys.map(Number)
    if (!ids.length) {
      return
    }
    setDeletingTaskId(-1)
    try {
      const results = await Promise.allSettled(ids.map((id) => adminApi.deleteDouyinTask(token, id)))
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
      await loadTasks()
    } finally {
      setDeletingTaskId(null)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="抖音下载"
        subtitle="创建单视频或用户批量下载任务，并追踪任务进度。"
        extra={
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadTasks}>
            刷新
          </Button>
        }
      />

      <div className="split-grid">
        <Card title="新建下载任务">
          <Form form={form} layout="vertical" initialValues={{ mode: 'single', overwrite: false, max_items: 10 }} onFinish={createTask}>
            <Form.Item name="mode" label="任务类型">
              <Radio.Group
                options={[
                  { label: '单视频', value: 'single' },
                  { label: '用户批量', value: 'user' },
                ]}
                optionType="button"
                buttonStyle="solid"
              />
            </Form.Item>
            <Form.Item name="url" label="抖音链接" rules={[{ required: true, message: '请输入抖音链接' }]}>
              <Input placeholder="视频或用户主页链接" />
            </Form.Item>
            {mode === 'user' ? (
              <Form.Item name="max_items" label="最大下载数量">
                <InputNumber min={1} max={200} style={{ width: '100%' }} />
              </Form.Item>
            ) : null}
            <Form.Item name="output_dir" label="输出目录">
              <Input placeholder="可选，留空使用默认下载目录" />
            </Form.Item>
            <Form.Item name="cookie" label="登录凭证">
              <Input.TextArea rows={3} placeholder="可选" />
            </Form.Item>
            <Form.Item name="proxy" label="代理">
              <Input placeholder="例如 http://127.0.0.1:7890" />
            </Form.Item>
            <Form.Item name="overwrite" label="覆盖已有文件" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Button type="primary" htmlType="submit" icon={<PlusOutlined />} block>
              创建任务
            </Button>
          </Form>
        </Card>

        <Card title="任务进度">
          <Space wrap style={{ marginBottom: 16 }}>
            <Popconfirm
              title="删除选中任务"
              description="只删除下载任务记录，不删除已经登记的文件。排队或运行中的任务不能删除。"
              okText="删除"
              cancelText="取消"
              onConfirm={deleteSelected}
              disabled={!selectedRowKeys.length}
            >
              <Button danger icon={<DeleteOutlined />} disabled={!selectedRowKeys.length} loading={deletingTaskId === -1}>
                批量删除
              </Button>
            </Popconfirm>
          </Space>
          <Table<DouyinTask>
            rowKey="id"
            loading={loading}
            dataSource={tasks}
            pagination={{ pageSize: 10, showSizeChanger: true }}
            rowSelection={{
              selectedRowKeys,
              onChange: setSelectedRowKeys,
              getCheckboxProps: (task) => ({ disabled: activeStatuses.includes(task.status) }),
            }}
            columns={[
              { title: 'ID', dataIndex: 'id', width: 70, render: (id) => `#${id}` },
              { title: '类型', dataIndex: 'task_type', width: 100, render: formatTaskType },
              { title: '状态', dataIndex: 'status', width: 110, render: (status) => <StatusBadge status={status} pulse /> },
              { title: '进度', render: (_, task) => <TaskProgress done={task.progress_done} total={task.progress_total || task.max_items} /> },
              { title: '更新时间', dataIndex: 'updated_at', width: 180, render: formatDateTime },
              {
                title: '操作',
                width: 110,
                render: (_, task) =>
                  activeStatuses.includes(task.status) ? null : (
                    <Popconfirm
                      title="删除任务"
                      description="只删除下载任务记录，不删除已经登记的文件。"
                      okText="删除"
                      cancelText="取消"
                      onConfirm={() => deleteTask(task)}
                    >
                      <Button type="link" danger icon={<DeleteOutlined />} loading={deletingTaskId === task.id}>
                        删除
                      </Button>
                    </Popconfirm>
                  ),
              },
            ]}
          />
        </Card>
      </div>
    </div>
  )
}

export default DouyinCollection
