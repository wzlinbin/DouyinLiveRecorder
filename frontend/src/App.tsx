import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Rooms = lazy(() => import('./pages/Rooms'))
const Jobs = lazy(() => import('./pages/Jobs'))
const Files = lazy(() => import('./pages/Files'))
const Uploads = lazy(() => import('./pages/Uploads'))
const DouyinCollection = lazy(() => import('./pages/DouyinCollection'))
const DownloadWatch = lazy(() => import('./pages/DownloadWatch'))
const Settings = lazy(() => import('./pages/Settings'))

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#2f8cff',
          borderRadius: 8,
          colorBgBase: '#0d1117',
          colorBgContainer: '#171c26',
          colorBgElevated: '#1d2430',
          colorBorder: '#2f3a4a',
          colorText: '#eef4ff',
          colorTextSecondary: '#9da9bb',
          fontFamily:
            'Inter, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
        },
        components: {
          Layout: {
            bodyBg: '#0d1117',
            headerBg: '#111722',
            siderBg: '#111722',
          },
          Card: {
            colorBgContainer: '#171c26',
          },
          Table: {
            headerBg: '#1d2430',
            rowHoverBg: '#202938',
          },
        },
      }}
    >
      <Suspense fallback={<div className="route-loading">加载中...</div>}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/rooms" element={<Rooms />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/files" element={<Files />} />
            <Route path="/uploads" element={<Uploads />} />
            <Route path="/douyin" element={<DouyinCollection />} />
            <Route path="/download-watch" element={<DownloadWatch />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </ConfigProvider>
  )
}

export default App
