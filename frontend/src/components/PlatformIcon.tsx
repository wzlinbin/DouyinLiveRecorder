import { GlobalOutlined, VideoCameraOutlined } from '@ant-design/icons'
import { Avatar, Tooltip } from 'antd'

const platformColor: Record<string, string> = {
  douyin: '#111827',
  tiktok: '#0f172a',
  kuaishou: '#fa8c16',
  huya: '#f59e0b',
  douyu: '#ff7a45',
  bilibili: '#13c2c2',
  youtube: '#f5222d',
}

type PlatformIconProps = {
  platform?: string | null
}

function platformName(platform?: string | null) {
  const normalized = (platform || 'unknown').toLowerCase()
  const names: Record<string, string> = {
    douyin: '抖音',
    tiktok: 'TikTok',
    kuaishou: '快手',
    huya: '虎牙',
    douyu: '斗鱼',
    bilibili: '哔哩哔哩',
    youtube: 'YouTube',
    unknown: '未知平台',
  }
  return names[normalized] || platform || '未知平台'
}

function PlatformIcon({ platform }: PlatformIconProps) {
  const normalized = (platform || 'unknown').toLowerCase()
  const label = platformName(platform)
  const letter = label.slice(0, 1).toUpperCase()

  return (
    <Tooltip title={label}>
      <Avatar
        size="small"
        style={{ background: platformColor[normalized] || '#2f8cff' }}
        icon={normalized === 'unknown' ? <GlobalOutlined /> : <VideoCameraOutlined />}
      >
        {letter}
      </Avatar>
    </Tooltip>
  )
}

export default PlatformIcon
