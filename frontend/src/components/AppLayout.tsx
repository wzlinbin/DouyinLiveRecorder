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
import { useAppStore } from '../stores/appStore'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/rooms', icon: <VideoCameraOutlined />, label: '直播间' },
  { key: '/jobs', icon: <PlaySquareOutlined />, label: '录制任务' },
  { key: '/files', icon: <FileOutlined />, label: '文件管理' },
  { key: '/uploads', icon: <CloudUploadOutlined />, label: '转码上传' },
  { key: '/douyin', icon: <DownloadOutlined />, label: 'Douyin 下载' },
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

  const activeKey = useMemo(() => {
    return menuItems.find((item) => location.pathname.startsWith(item.key))?.key || '/dashboard'
  }, [location.pathname])

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
              placeholder="X-Admin-Token"
              value={draftToken}
              onChange={(event) => setDraftToken(event.target.value)}
            />
            <Button
              type="primary"
              onClick={() => {
                setToken(draftToken)
                message.success(draftToken.trim() ? '管理员 Token 已保存' : '管理员 Token 已清空')
              }}
            >
              保存
            </Button>
          </Space.Compact>
          <Tag color={token ? 'success' : 'warning'}>{token ? 'Token 已保存' : 'Token 未保存'}</Tag>
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default AppLayout
