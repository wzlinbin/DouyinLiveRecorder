import type { ReactNode } from 'react'

type PageHeaderProps = {
  title: string
  subtitle?: string
  extra?: ReactNode
}

function PageHeader({ title, subtitle, extra }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div>
        <h1 className="page-title">{title}</h1>
        {subtitle ? <div className="page-subtitle">{subtitle}</div> : null}
      </div>
      {extra ? <div className="toolbar-row">{extra}</div> : null}
    </div>
  )
}

export default PageHeader
