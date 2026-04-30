import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { Button, Card, Form, Input, InputNumber, message, Radio, Switch, Table } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { adminApi, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import TaskProgress from '../components/TaskProgress'
import { useAppStore } from '../stores/appStore'
import type { DouyinTask } from '../types/admin'

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
      message.success('Douyin 下载任务已创建')
      form.resetFields()
      form.setFieldsValue({ mode: 'single', overwrite: false, max_items: 10 })
      await loadTasks()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Douyin 下载"
        subtitle="创建单视频或用户批量下载任务，并追踪任务进度。"
        extra={
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadTasks}>
            刷新
          </Button>
        }
      />

      <div className="split-grid">
        <Card title="新建下载任务">
          <Form
            form={form}
            layout="vertical"
            initialValues={{ mode: 'single', overwrite: false, max_items: 10 }}
            onFinish={createTask}
          >
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
            <Form.Item name="url" label="Douyin URL" rules={[{ required: true, message: '请输入 Douyin URL' }]}>
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
            <Form.Item name="cookie" label="Cookie">
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
          <Table<DouyinTask>
            rowKey="id"
            loading={loading}
            dataSource={tasks}
            pagination={{ pageSize: 6 }}
            columns={[
              { title: 'ID', dataIndex: 'id', width: 70, render: (id) => `#${id}` },
              { title: '类型', dataIndex: 'task_type', width: 100 },
              { title: '状态', dataIndex: 'status', width: 110, render: (status) => <StatusBadge status={status} pulse /> },
              {
                title: '进度',
                render: (_, task) => <TaskProgress done={task.progress_done} total={task.progress_total || task.max_items} />,
              },
              { title: '更新时间', dataIndex: 'updated_at', width: 180 },
            ]}
          />
        </Card>
      </div>
    </div>
  )
}

export default DouyinCollection
