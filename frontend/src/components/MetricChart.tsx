import { Empty } from 'antd'
import type { YoutubeMetric } from '../types/admin'

type MetricChartProps = {
  data: YoutubeMetric[]
  metric: 'view_count' | 'like_count' | 'comment_count'
  label: string
}

function MetricChart({ data, metric, label }: MetricChartProps) {
  const points = Object.values(
    data.reduce<Record<string, { metric_date: string; value: number }>>((acc, item) => {
      const current = acc[item.metric_date] || { metric_date: item.metric_date, value: 0 }
      current.value += item[metric]
      acc[item.metric_date] = current
      return acc
    }, {}),
  )
    .sort((a, b) => a.metric_date.localeCompare(b.metric_date))
    .slice(-14)

  if (points.length < 2) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无足够指标数据" />
  }

  const width = 640
  const height = 210
  const padding = 28
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(max - min, 1)
  const step = (width - padding * 2) / Math.max(points.length - 1, 1)

  const coordinates = points.map((point, index) => {
    const x = padding + index * step
    const y = height - padding - ((point.value - min) / span) * (height - padding * 2)
    return { x, y, point }
  })

  const line = coordinates.map(({ x, y }) => `${x},${y}`).join(' ')
  const area = `${padding},${height - padding} ${line} ${width - padding},${height - padding}`

  return (
    <div className="metric-chart" aria-label={label}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        <defs>
          <linearGradient id={`chart-fill-${metric}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2f8cff" stopOpacity="0.36" />
            <stop offset="100%" stopColor="#2f8cff" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} className="chart-axis" />
        <polygon points={area} fill={`url(#chart-fill-${metric})`} />
        <polyline points={line} className="chart-line" />
        {coordinates.map(({ x, y, point }) => (
          <g key={`${point.metric_date}-${metric}`}>
            <circle cx={x} cy={y} r="3.5" className="chart-point" />
            <title>
              {point.metric_date}: {point.value}
            </title>
          </g>
        ))}
      </svg>
      <div className="chart-footer">
        <span>{points[0].metric_date}</span>
        <span>{label}</span>
        <span>{points[points.length - 1].metric_date}</span>
      </div>
    </div>
  )
}

export default MetricChart
