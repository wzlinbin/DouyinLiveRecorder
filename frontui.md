# titok2youtube 前端UI系统设计方案

## 1. 技术选型

| 选项 | 选择 |
|------|------|
| 框架 | React 18 + Ant Design 5.x |
| 构建工具 | Vite |
| 状态管理 | Zustand |
| 样式 | Tailwind CSS + Ant Design 暗黑主题 |
| 部署 | 前后端分离（独立构建，API代理） |

## 2. 项目结构

```
frontend/
├── public/
├── src/
│   ├── api/              # API 调用层
│   ├── components/       # 通用组件
│   ├── pages/           # 页面组件
│   ├── stores/          # Zustand stores
│   ├── types/           # TS 类型定义
│   ├── App.tsx
│   └── main.tsx
├── package.json
└── vite.config.ts
```

## 3. 页面规划

### 3.1 仪表盘 (Dashboard)
- 系统状态概览卡片（在线房间数、录制中任务、上传队列）
- 实时事件流（最近50条日志）
- 快捷操作入口
- 系统健康状态指示

### 3.2 直播间管理 (Rooms)
- 直播间列表（表格视图）
  - 平台图标、名称、URL、画质
  - 状态指示（在线/离线/录制中）
  - 启用/禁用切换
- 新增直播间表单
- 编辑直播间抽屉
- 快捷操作：立即开始/停止录制

### 3.3 录制任务 (Jobs)
- 任务列表（Tab: 进行中/已完成/失败）
- 任务详情抽屉
  - 开始/结束时间
  - 配置快照
  - 关联文件列表
  - 错误信息（如有）

### 3.4 文件管理 (Files)
- 录制文件列表
  - 文件名、路径、大小、时长、格式
  - 状态标签（就绪/转码中/已上传）
- 文件操作：转码、重命名、删除
- 批量选择操作

### 3.5 转码与上传 (Transcode & Upload)
- 上传队列状态
- YouTube 指标仪表盘
  - 视频播放量、点赞、评论趋势
  - 上传历史记录
- 上传任务详情

### 3.6 Douyin 下载 (Douyin Collection)
- 下载任务列表
- 新建下载任务表单
  - 单视频 / 用户批量下载
  - Cookie 配置
  - 代理设置
  - 输出目录
- 任务进度追踪

### 3.7 下载监控 (Download Watch)
- 监控目录列表
- 监控设置面板
  - 轮询间隔
  - 稳定性检查次数
  - 转码设置
- 监控记录表格

### 3.8 设置 (Settings)
- 通用配置编辑（分段）
- 配置导入/导出
- API Token 管理

## 4. 核心组件设计

| 组件 | 用途 |
|------|------|
| StatusBadge | 状态徽章（在线/离线/录制中/错误） |
| PlatformIcon | 平台图标（抖音/快手/虎牙等） |
| RealtimeLog | 实时日志流组件 |
| FilePreview | 文件预览卡片 |
| MetricChart | YouTube 指标图表 |
| TaskProgress | 任务进度条 |

## 5. 主题配置

```typescript
// Ant Design 暗黑主题定制
{
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#1890ff',
    borderRadius: 8,
    colorBgContainer: '#1f1f2e',
    colorBgElevated: '#252536',
  }
}
```

## 6. 实现顺序

1. **基础设施**：项目初始化、路由、API层、类型定义
2. **布局组件**：侧边栏、顶部栏、布局框架
3. **核心页面**：仪表盘 → 直播间管理 → 任务管理
4. **功能页面**：文件管理 → 上传管理 → Douyin下载
5. **优化完善**：实时事件流、图表可视化、细节打磨
