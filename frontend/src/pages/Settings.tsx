import { CheckCircleOutlined, LinkOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Form, Input, message, Space, Steps, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminApi, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import { useAppStore } from '../stores/appStore'
import type { YouTubeDataApiCheck, YouTubeOAuthStatus } from '../types/admin'

function Settings() {
  const token = useAppStore((state) => state.token)
  const [oauthStatus, setOauthStatus] = useState<YouTubeOAuthStatus | null>(null)
  const [dataApiCheck, setDataApiCheck] = useState<YouTubeDataApiCheck | null>(null)
  const [authUrl, setAuthUrl] = useState('')
  const [oauthLoading, setOauthLoading] = useState(false)
  const [checkingDataApi, setCheckingDataApi] = useState(false)
  const [oauthForm] = Form.useForm<{ code: string }>()

  const oauthStep = useMemo(() => {
    if (!oauthStatus?.client_secret_exists) {
      return 1
    }
    if (oauthStatus.token_exists && oauthStatus.token_valid && dataApiCheck?.ok) {
      return 5
    }
    if (oauthStatus.token_exists && oauthStatus.token_valid) {
      return 4
    }
    if (authUrl) {
      return 3
    }
    return 2
  }, [authUrl, dataApiCheck, oauthStatus])

  const loadOAuthStatus = useCallback(async () => {
    try {
      setOauthStatus(await adminApi.youtubeOAuthStatus())
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }, [])

  useEffect(() => {
    loadOAuthStatus()
  }, [loadOAuthStatus])

  const startOAuth = async () => {
    if (!token) {
      message.error('请先在右上角输入正确的管理员令牌并点击保存。')
      return
    }
    setOauthLoading(true)
    try {
      const result = await adminApi.startYoutubeOAuth(token, 'http://localhost')
      setAuthUrl(result.auth_url)
      setDataApiCheck(null)
      message.success('授权链接已生成')
      await loadOAuthStatus()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setOauthLoading(false)
    }
  }

  const openAuthUrl = () => {
    if (authUrl) {
      window.open(authUrl, '_blank', 'noopener,noreferrer')
    }
  }

  const completeOAuth = async ({ code }: { code: string }) => {
    if (!token) {
      message.error('请先在右上角输入正确的管理员令牌并点击保存。')
      return
    }
    setOauthLoading(true)
    try {
      const result = await adminApi.completeYoutubeOAuth(token, code)
      message.success(result.token_valid ? 'Google 令牌已生成并保存' : '令牌已保存，请稍后验证授权状态')
      oauthForm.resetFields()
      setAuthUrl('')
      setDataApiCheck(null)
      await loadOAuthStatus()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setOauthLoading(false)
    }
  }

  const checkDataApi = async () => {
    if (!token) {
      message.error('请先在右上角输入正确的管理员令牌并点击保存。')
      return
    }
    setCheckingDataApi(true)
    try {
      const result = await adminApi.checkYouTubeDataApi(token)
      setDataApiCheck(result)
      if (result.ok) {
        message.success(result.message)
      } else {
        message.warning(result.message)
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setCheckingDataApi(false)
    }
  }

  const apiCheckAlertType = dataApiCheck?.ok ? 'success' : dataApiCheck ? 'warning' : 'info'

  return (
    <div className="page-stack">
      <PageHeader
        title="设置"
        subtitle="完成 YouTube Data API v3 开通、Google 授权和上传权限检测。"
        extra={
          <Button icon={<ReloadOutlined />} loading={oauthLoading} onClick={loadOAuthStatus}>
            刷新状态
          </Button>
        }
      />

      <div className="split-grid">
        <Card title="如何开通 YouTube Data API v3">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              这一步是在 Google Cloud 里给当前客户端密钥所属项目开通 YouTube Data API v3。没有开通时，即使 Google 令牌生成成功，后续上传或指标检测也可能返回权限错误。
            </Typography.Paragraph>
            <Steps
              direction="vertical"
              current={dataApiCheck?.ok ? 5 : 0}
              items={[
                {
                  title: '打开 Google Cloud 控制台',
                  description: '进入控制台后，登录准备用来上传视频的 Google 账号。',
                },
                {
                  title: '选择客户端密钥对应的项目',
                  description: '项目必须和 config/youtube_client_secret.json 里的客户端密钥属于同一个 Google Cloud 项目。',
                },
                {
                  title: '进入“API 和服务”',
                  description: '在左侧菜单打开“API 和服务”，再进入“库”页面。',
                },
                {
                  title: '搜索并启用 YouTube Data API v3',
                  description: '搜索 YouTube Data API v3，进入详情页后点击“启用”。如果已经启用，会看到管理或已启用状态。',
                },
                {
                  title: '检查 OAuth 同意屏幕',
                  description: '如果应用处于测试模式，把当前 Google 账号加入测试用户；否则授权时可能被 Google 拒绝。',
                },
                {
                  title: '回到本页重新授权并检测',
                  description: '点击右侧“生成授权链接”，完成授权后保存 Google 令牌，再点击“检测 API 权限”。',
                },
              ]}
            />
            <Space wrap>
              <Button href="https://console.cloud.google.com/apis/library/youtube.googleapis.com" target="_blank" rel="noreferrer">
                打开 API 启用页面
              </Button>
              <Button href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer">
                打开凭据页面
              </Button>
              <Button href="https://console.cloud.google.com/apis/credentials/consent" target="_blank" rel="noreferrer">
                打开同意屏幕
              </Button>
            </Space>
          </Space>
        </Card>

        <Card title="YouTube 授权向导">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Alert
              type={apiCheckAlertType}
              showIcon
              message={dataApiCheck?.message || '前提：Google Cloud 项目必须已开启 YouTube Data API v3。'}
              description={
                dataApiCheck?.detail ||
                '按左侧步骤启用 API 后，重新生成授权链接并保存 Google 令牌，最后点击“检测 API 权限”确认当前账号可以访问 YouTube Data API v3。'
              }
            />

            <Steps
              current={oauthStep}
              direction="vertical"
              items={[
                { title: '开启 YouTube Data API v3', description: '按左侧步骤在 Google Cloud 控制台启用该 API' },
                { title: '检查客户端密钥文件', description: oauthStatus?.client_secret_exists ? '已找到' : '请先配置客户端密钥 JSON 文件' },
                { title: '生成 Google 授权链接', description: authUrl ? '授权链接已生成' : '使用当前 ini 路径创建授权链接' },
                { title: '登录并复制回跳地址或授权码', description: '完成授权后，复制浏览器地址栏中的完整回跳地址或授权码参数' },
                { title: '保存 Google 令牌', description: oauthStatus?.token_valid ? '令牌可用于 YouTube 上传' : '等待提交授权结果' },
                { title: '检测当前账号 API 权限', description: dataApiCheck?.ok ? 'YouTube Data API v3 可访问' : '使用当前令牌实际请求 YouTube Data API v3' },
              ]}
            />

            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="客户端密钥">{oauthStatus?.client_secret_path || '-'}</Descriptions.Item>
              <Descriptions.Item label="令牌文件">{oauthStatus?.token_path || '-'}</Descriptions.Item>
              <Descriptions.Item label="令牌状态">
                {oauthStatus?.token_valid ? '令牌已可用' : oauthStatus?.token_exists ? '令牌存在但需要重新授权' : '尚未生成令牌'}
              </Descriptions.Item>
              <Descriptions.Item label="检测权限">
                {oauthStatus?.data_api_scope_valid ? '已包含检测权限' : '旧令牌可能需要重新授权'}
              </Descriptions.Item>
            </Descriptions>

            {oauthStatus?.token_error ? <Alert type="warning" showIcon message={oauthStatus.token_error} /> : null}
            {!oauthStatus?.client_secret_exists ? (
              <Alert
                type="warning"
                showIcon
                message="未找到客户端密钥文件"
                description="请在 YouTube上传 配置段中确认“youtube客户端密钥文件路径”指向真实的 Google OAuth 客户端密钥 JSON 文件。"
              />
            ) : null}

            <Space wrap>
              <Button type="primary" icon={<LinkOutlined />} loading={oauthLoading} disabled={!oauthStatus?.client_secret_exists} onClick={startOAuth}>
                生成授权链接
              </Button>
              <Button icon={<ReloadOutlined />} loading={oauthLoading} onClick={loadOAuthStatus}>
                检查状态
              </Button>
              <Button icon={<CheckCircleOutlined />} disabled={!authUrl} onClick={openAuthUrl}>
                打开授权页
              </Button>
              <Button icon={<CheckCircleOutlined />} loading={checkingDataApi} disabled={!oauthStatus?.token_exists} onClick={checkDataApi}>
                检测 API 权限
              </Button>
            </Space>

            {authUrl ? <Input.TextArea value={authUrl} readOnly autoSize={{ minRows: 2, maxRows: 5 }} /> : null}

            <Form form={oauthForm} layout="vertical" onFinish={completeOAuth}>
              <Form.Item
                name="code"
                label="授权后的回跳地址或授权码"
                rules={[{ required: true, message: '请输入 Google 授权后得到的地址或授权码' }]}
              >
                <Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} placeholder="例如：http://localhost/?state=...&code=..." />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={oauthLoading}>
                保存 Google 令牌
              </Button>
            </Form>
          </Space>
        </Card>
      </div>
    </div>
  )
}

export default Settings
