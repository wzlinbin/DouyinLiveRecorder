** 项目上下文摘要（后台管理页升级）

生成时间：2026-04-30 16:00:35

**# 1. 相似实现分析

**实现1**: server/app.py
 - 模式：FastAPI 路由直接编排服务层，首页内联 HTML + 原生 JavaScript 作为轻量后台入口。
 - 可复用：`require_admin_token`、`/api/rooms`、`/api/jobs`、`/api/uploads`、`/api/download-watch`、`/api/events/recent`。
 - 需注意：首页当前更偏调试面板，中文文案存在乱码，适合原位升级而不是另起一套前端。

**实现2**: server/repository.py
 - 模式：Repository 统一负责 SQLite 读写，服务层通过它聚合状态和事件。
 - 可复用：`list_rows()`、`get_row()`、`add_event()`、`active_job_for_room()`、`retry_upload()`、`register_file()`。
 - 需注意：现有查询模式偏通用表查询，新增后台概览时优先复用通用查询，避免引入新 ORM 或重复 SQL 层。

**实现3**: tests/test_server_api.py
 - 模式：`unittest` + `fastapi.testclient.TestClient`，通过真实 API 调用验证行为。
 - 可复用：`TestClient(app)`、`X-Admin-Token` 鉴权模式、现有断言风格 `assertEqual`/`assertTrue`。
 - 需注意：测试以接口结果和关键副作用为主，适合补充概览接口和首页内容的回归测试。

**实现4**: server/download_watch_service.py
 - 模式：服务层读取 settings，复用 repository 记录状态和事件，给 API 返回结构化设置与记录。
 - 可复用：`get_settings()`、`scan_once()` 返回值结构，可直接展示在管理页。
 - 需注意：页面不应自行拼下载监控业务规则，应直接消费服务层输出。

**# 2. 项目约定

**命名约定**: Python 文件与函数使用英文蛇形命名；FastAPI 路由路径使用 `/api/...` 形式；数据库表名为复数蛇形命名。

**文件组织**: `server/` 放后台服务、路由和数据库；`src/` 放原有采集/上传核心；`tests/` 放 API 和行为测试。

**导入顺序**: 先标准库，再第三方库，最后项目内相对导入。

**代码风格**: 类型注解较完整，函数职责偏单一，字符串响应多用字典；当前首页使用内联 HTML/JS，不额外引入模板目录。

**# 3. 可复用组件清单

`server/repository.py`: 通用数据读取、事件写入、任务/上传状态更新

`server/recording_service.py`: 直播间启动/停止录制幂等控制

`server/upload_service.py`: 上传重试和后台上传循环

`server/download_watch_service.py`: 下载监控设置、手动扫描和记录读取

`server/analytics_service.py`: YouTube 指标查询与刷新

`server/recorder_process_service.py`: 当前录制进程运行态查询

**# 4. 测试策略

**测试框架**: `unittest`

**测试模式**: FastAPI API 测试 + 少量 mock 进程行为

**参考文件**: tests/test_server_api.py

**覆盖要求**: 概览接口正常返回；首页 HTML 含核心管理入口；已有录制/上传测试不回归。

**# 5. 依赖和集成点

**外部依赖**: FastAPI、Pydantic、Google API 客户端、SQLite

**内部依赖**: `server/app.py` 聚合各服务；服务层统一经 `Repository` 访问 `Database`

**集成方式**: 路由直接调用服务层；后台循环通过 FastAPI lifespan 启动

**配置来源**: `config/config.ini`、`config/URL_config.ini` 首次导入数据库；后续后台读数据库 settings

**# 6. 技术选型理由

**为什么用这个方案**: 现有仓库已经采用 FastAPI + 内联 HTML 起步，继续在服务端增强页面和聚合接口，成本最低、风险最小。

**优势**: 不引入新构建链；直接复用现有 API 和服务；能最快把“可调试”提升到“可管理”。

**劣势和风险**: 单文件 HTML 会变长；前端交互复杂度上升时需要控制结构，避免继续膨胀。

**# 7. 关键风险点

**并发问题**: 概览接口不能写库，避免和 worker 写事务冲突。

**边界条件**: 无数据场景要返回 0 和空数组；未配置 `ADMIN_API_TOKEN` 时只允许只读页面行为。

**性能瓶颈**: 首页不应一次性抓太多明细；最近事件和列表应限量。

**安全考虑**: 页面操作通过 Header 传 token；概览接口只返回已有公开字段，不暴露敏感配置明文。

**# 8. 最新开发进度（2026-04-30）

**已完成**: 后台首页已升级为管理型仪表盘，包含 `/api/dashboard` 概览、直播间列表、活跃录制、上传队列、下载监控、最近事件和 YouTube 指标刷新入口。

**本轮新增**: 上传队列支持失败记录一键重试；直播间列表支持页面内编辑名称、URL 和清晰度。

**验证状态**: `.venv/Scripts/python.exe -m unittest tests.test_server_api -v` 已通过，当前 9 个测试全部成功；首页内联脚本已通过 `node --check` 语法检查。

**下一步建议**: 优先补下载监控设置编辑，其次补文件浏览或配置编辑；如果继续增加页面模块，应评估拆分静态资源以控制 `server/app.py` 体积。
