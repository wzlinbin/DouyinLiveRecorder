import {
  CloudUploadOutlined,
  DashboardOutlined,
  DownloadOutlined,
  FileOutlined,
  FileSearchOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlaySquareOutlined,
  SettingOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { Button, Input, Layout, Menu, message, Space, Tag, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { adminApi, getErrorMessage } from '../api/client'
import { useAppStore } from '../stores/appStore'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/rooms', icon: <VideoCameraOutlined />, label: '直播间' },
  { key: '/jobs', icon: <PlaySquareOutlined />, label: '录制任务' },
  { key: '/files', icon: <FileOutlined />, label: '文件管理' },
  { key: '/uploads', icon: <CloudUploadOutlined />, label: '上传队列' },
  { key: '/douyin', icon: <DownloadOutlined />, label: '抖音下载' },
  { key: '/download-watch', icon: <FileSearchOutlined />, label: '下载监控' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const token = useAppStore((state) => state.token)
  const setToken = useAppStore((state) => state.setToken)
  const [collapsed, setCollapsed] = useState(false)
  const [draftToken, setDraftToken] = useState(token)
  const [checkingToken, setCheckingToken] = useState(false)

  const activeKey = useMemo(() => {
    return menuItems.find((item) => location.pathname.startsWith(item.key))?.key || '/dashboard'
  }, [location.pathname])

  const saveToken = async () => {
    const normalized = draftToken.trim()
    if (!normalized) {
      setToken('')
      message.success('管理员令牌已清空')
      return
    }
    setCheckingToken(true)
    try {
      await adminApi.checkAuth(normalized)
      setToken(normalized)
      message.success('管理员令牌校验通过，已保存')
    } catch (error) {
      setToken('')
      message.error(getErrorMessage(error))
    } finally {
      setCheckingToken(false)
    }
  }

  return (
    <Layout className="app-shell">
      <Sider width={232} collapsible collapsed={collapsed} trigger={null}>
        <div className="app-logo">
          <span className="app-logo-mark">T2</span>
          {!collapsed ? <span>titok2youtube</span> : null}
        </div>
        <Menu
          mode="inline"
          selectedKeys={[activeKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderInlineEnd: 0 }}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <Space>
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((value) => !value)}
            />
            <Typography.Text type="secondary">后台控制台</Typography.Text>
          </Space>
          <Space.Compact style={{ maxWidth: 420, width: '100%' }}>
            <Input.Password
              placeholder="管理员令牌"
              value={draftToken}
              onChange={(event) => setDraftToken(event.target.value)}
              onPressEnter={saveToken}
            />
            <Button type="primary" loading={checkingToken} onClick={saveToken}>
              保存
            </Button>
          </Space.Compact>
          <Tag color={token ? 'success' : 'warning'}>{token ? '令牌已校验' : '令牌未校验'}</Tag>
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default AppLayout
