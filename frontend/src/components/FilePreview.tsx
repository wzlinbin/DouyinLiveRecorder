import { FileOutlined } from '@ant-design/icons'
import { Card, Space, Typography } from 'antd'
import type { RecordedFile } from '../types/admin'
import { fileName, formatBytes, formatDuration } from '../utils/format'
import StatusBadge from './StatusBadge'

type FilePreviewProps = {
  file: RecordedFile
}

function FilePreview({ file }: FilePreviewProps) {
  return (
    <Card size="small" className="file-preview">
      <Space align="start">
        <span className="file-preview-icon">
          <FileOutlined />
        </span>
        <div>
          <Typography.Text strong>{fileName(file.local_path)}</Typography.Text>
          <div className="muted">{file.local_path}</div>
          <Space size={8} wrap style={{ marginTop: 8 }}>
            <StatusBadge status={file.status} />
            <span>{formatBytes(file.size_bytes)}</span>
            <span>{file.format || '未知格式'}</span>
            <span>{formatDuration(file.duration_seconds)}</span>
          </Space>
        </div>
      </Space>
    </Card>
  )
}

export default FilePreview
