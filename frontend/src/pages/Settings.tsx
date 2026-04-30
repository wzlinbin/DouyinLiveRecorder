import { DownloadOutlined, ReloadOutlined, SaveOutlined, UploadOutlined } from '@ant-design/icons'
import { Button, Card, Form, Input, List, message, Select, Space, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminApi, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import { useAppStore } from '../stores/appStore'
import type { ConfigSection, ConfigSetting } from '../types/admin'

function asEditableText(value: unknown) {
  if (typeof value === 'string') {
    return value
  }
  return JSON.stringify(value, null, 2)
}

function parseEditableText(value: string) {
  const trimmed = value.trim()
  if (!trimmed) {
    return ''
  }
  if (trimmed === 'true') {
    return true
  }
  if (trimmed === 'false') {
    return false
  }
  if (!Number.isNaN(Number(trimmed)) && /^-?\d+(\.\d+)?$/.test(trimmed)) {
    return Number(trimmed)
  }
  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function Settings() {
  const token = useAppStore((state) => state.token)
  const [settings, setSettings] = useState<ConfigSetting[]>([])
  const [selectedCategory, setSelectedCategory] = useState<string>()
  const [section, setSection] = useState<ConfigSection | null>(null)
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm<Record<string, string>>()

  const categories = useMemo(() => {
    return Array.from(new Set(settings.map((setting) => setting.category))).filter(Boolean)
  }, [settings])

  const loadSettings = useCallback(async () => {
    setLoading(true)
    try {
      const nextSettings = await adminApi.config()
      setSettings(nextSettings)
      const nextCategory = selectedCategory || nextSettings[0]?.category
      if (nextCategory) {
        setSelectedCategory(nextCategory)
        const nextSection = await adminApi.configSection(nextCategory)
        setSection(nextSection)
        form.setFieldsValue(
          Object.fromEntries(Object.entries(nextSection.values || {}).map(([key, value]) => [key, asEditableText(value)])),
        )
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [form, selectedCategory])

  useEffect(() => {
    loadSettings()
  }, [loadSettings])

  const changeCategory = async (category: string) => {
    setSelectedCategory(category)
    setLoading(true)
    try {
      const nextSection = await adminApi.configSection(category)
      setSection(nextSection)
      form.setFieldsValue(
        Object.fromEntries(Object.entries(nextSection.values || {}).map(([key, value]) => [key, asEditableText(value)])),
      )
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  const saveSection = async (values: Record<string, string>) => {
    if (!section) {
      return
    }
    try {
      const parsedValues = Object.fromEntries(Object.entries(values).map(([key, value]) => [key, parseEditableText(value)]))
      await adminApi.updateConfigSection(token, section.section || selectedCategory || '', parsedValues)
      message.success('配置已保存')
      await loadSettings()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const importConfig = async () => {
    try {
      await adminApi.importConfig(token)
      message.success('已从 ini 导入配置')
      await loadSettings()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const exportConfig = async () => {
    try {
      await adminApi.exportConfig(token)
      message.success('已导出配置到 ini')
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="设置"
        subtitle="分段编辑通用配置，并支持从 ini 导入或导出。"
        extra={
          <>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={loadSettings}>
              刷新
            </Button>
            <Button icon={<DownloadOutlined />} onClick={importConfig}>
              导入
            </Button>
            <Button icon={<UploadOutlined />} onClick={exportConfig}>
              导出
            </Button>
          </>
        }
      />

      <div className="split-grid">
        <Card title="配置分段">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Select
              style={{ width: '100%' }}
              placeholder="选择配置分段"
              value={selectedCategory}
              options={categories.map((category) => ({ label: category, value: category }))}
              onChange={changeCategory}
            />
            <List
              dataSource={settings.filter((setting) => !selectedCategory || setting.category === selectedCategory)}
              renderItem={(setting) => (
                <List.Item>
                  <List.Item.Meta
                    title={setting.key}
                    description={
                      <Typography.Text type="secondary" ellipsis>
                        {asEditableText(setting.value)}
                      </Typography.Text>
                    }
                  />
                </List.Item>
              )}
            />
          </Space>
        </Card>

        <Card title={selectedCategory ? `编辑 ${selectedCategory}` : '编辑配置'}>
          <Form form={form} layout="vertical" onFinish={saveSection}>
            {section
              ? Object.keys(section.values || {}).map((key) => (
                  <Form.Item key={key} name={key} label={key}>
                    <Input.TextArea autoSize={{ minRows: 1, maxRows: 6 }} />
                  </Form.Item>
                ))
              : null}
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} disabled={!section}>
              保存当前分段
            </Button>
          </Form>
        </Card>
      </div>
    </div>
  )
}

export default Settings
