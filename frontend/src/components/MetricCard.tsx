import type { ReactNode } from 'react'
import { Card, Space, Typography } from 'antd'

type MetricCardProps = {
  title: string
  value: ReactNode
  caption?: string
  icon?: ReactNode
}

function MetricCard({ title, value, caption, icon }: MetricCardProps) {
  return (
    <Card className="metric-card">
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Typography.Text type="secondary">{title}</Typography.Text>
          {icon}
        </Space>
        <div className="metric-value">{value}</div>
        {caption ? <div className="metric-caption">{caption}</div> : null}
      </Space>
    </Card>
  )
}

export default MetricCard
