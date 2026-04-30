import { Empty, Typography } from 'antd'
import type { EventRecord } from '../types/admin'
import StatusBadge from './StatusBadge'

type RealtimeLogProps = {
  events: EventRecord[]
}

function RealtimeLog({ events }: RealtimeLogProps) {
  if (!events.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无事件" />
  }

  return (
    <div className="log-list">
      {events.map((event) => (
        <div className="log-item" key={event.id}>
          <div className="toolbar-row" style={{ justifyContent: 'space-between' }}>
            <Typography.Text strong>{event.event_type}</Typography.Text>
            <StatusBadge status={event.level} />
          </div>
          <Typography.Text>{event.message}</Typography.Text>
          <Typography.Text type="secondary">{event.created_at}</Typography.Text>
        </div>
      ))}
    </div>
  )
}

export default RealtimeLog
