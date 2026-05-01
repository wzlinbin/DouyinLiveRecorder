import { ReloadOutlined, SaveOutlined, ScanOutlined } from '@ant-design/icons'
import { Button, Card, Form, InputNumber, message, Select, Switch, Table } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { adminApi, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { useAppStore } from '../stores/appStore'
import type { DownloadWatchRecord, DownloadWatchSettings } from '../types/admin'
import { dirName, fileName, formatBytes, formatDateTime } from '../utils/format'

type WatchFormValues = DownloadWatchSettings & {
  directoriesText?: string[]
}

function DownloadWatch() {
  const token = useAppStore((state) => state.token)
  const [settings, setSettings] = useState<DownloadWatchSettings | null>(null)
  const [records, setRecords] = useState<DownloadWatchRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm<WatchFormValues>()

  const loadWatch = useCallback(async () => {
    setLoading(true)
    try {
      const data = await adminApi.downloadWatch()
      setSettings(data.settings)
      setRecords(data.records)
      form.setFieldsValue({ ...data.settings, directoriesText: data.settings.directories })
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [form])

  useEffect(() => {
    loadWatch()
  }, [loadWatch])

  const saveSettings = async (values: WatchFormValues) => {
    try {
      await adminApi.updateDownloadWatch(token, {
        enabled: values.enabled,
        directories: values.directoriesText || [],
        poll_interval_seconds: values.poll_interval_seconds,
        stable_checks: values.stable_checks,
        transcode_non_mp4: values.transcode_non_mp4,
        delete_origin_after_transcode: values.delete_origin_after_transcode,
        reencode_h264: values.reencode_h264,
      })
      message.success('下载监控设置已保存')
      await loadWatch()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const scanOnce = async () => {
    try {
      const result = await adminApi.scanDownloadWatch(token)
      message.success(`扫描完成：候选 ${result.candidates} 个，登记 ${result.registered} 个`)
      await loadWatch()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="下载监控"
        subtitle="配置监控目录、轮询间隔、稳定性检查和转码策略，并查看最近监控记录。"
        extra={
          <>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={loadWatch}>
              刷新
            </Button>
            <Button type="primary" icon={<ScanOutlined />} onClick={scanOnce}>
              立即扫描
            </Button>
          </>
        }
      />

      <div className="split-grid">
        <Card title="监控设置">
          <Form form={form} layout="vertical" onFinish={saveSettings}>
            <Form.Item name="enabled" label="启用监控" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="directoriesText" label="监控目录">
              <Select mode="tags" placeholder="输入完整目录路径后回车" tokenSeparators={[',']} />
            </Form.Item>
            <Form.Item name="poll_interval_seconds" label="轮询间隔（秒）">
              <InputNumber min={2} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="stable_checks" label="稳定性检查次数">
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="transcode_non_mp4" label="非 MP4 自动转码" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="reencode_h264" label="强制 H.264 重新编码" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="delete_origin_after_transcode" label="转码后删除原文件" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} block>
              保存设置
            </Button>
          </Form>
        </Card>

        <Card title="当前状态">
          <div className="compact-list">
            <div className="compact-item">监控开关：{settings?.enabled ? '已启用' : '已关闭'}</div>
            <div className="compact-item">轮询间隔：{settings?.poll_interval_seconds ?? 0} 秒</div>
            <div className="compact-item">稳定检查：{settings?.stable_checks ?? 0} 次</div>
            <div className="compact-item">目录数量：{settings?.directories.length ?? 0}</div>
          </div>
        </Card>
      </div>

      <Card title="监控记录">
        <Table<DownloadWatchRecord>
          rowKey="id"
          loading={loading}
          dataSource={records}
          pagination={{ pageSize: 25, showSizeChanger: true }}
          columns={[
            { title: '文件', dataIndex: 'local_path', render: (path) => fileName(path) },
            { title: '完整目录', dataIndex: 'local_path', render: (path) => dirName(path) },
            { title: '大小', dataIndex: 'observed_size', width: 110, render: formatBytes },
            { title: '稳定次数', dataIndex: 'stable_count', width: 100 },
            { title: '状态', dataIndex: 'status', width: 110, render: (status) => <StatusBadge status={status} /> },
            { title: '编码', dataIndex: 'encoding_status', width: 120, render: (status) => <StatusBadge status={status} /> },
            { title: '更新时间', dataIndex: 'updated_at', width: 180, render: formatDateTime },
          ]}
        />
      </Card>
    </div>
  )
}

export default DownloadWatch
