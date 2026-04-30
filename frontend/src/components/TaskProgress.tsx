import { Progress } from 'antd'

type TaskProgressProps = {
  done: number
  total: number
}

function TaskProgress({ done, total }: TaskProgressProps) {
  const percent = total > 0 ? Math.round((done / total) * 100) : 0
  return (
    <div>
      <div className="progress-meta">
        <span>进度</span>
        <span>
          {done}/{total}
        </span>
      </div>
      <Progress percent={percent} size="small" />
    </div>
  )
}

export default TaskProgress
