from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .analytics_service import AnalyticsService
from .command_worker_service import CommandWorkerService
from .config_service import ConfigService, guess_platform
from .db import db
from .douyin_collection_service import DouyinCollectionService
from .download_watch_service import DownloadWatchService
from .recorder_process_service import RecorderProcessService
from .recording_service import RecordingService
from .repository import Repository
from .runtime_config import admin_token
from .schemas import (
    ConfigSectionPatch,
    DouyinSingleRequest,
    DouyinUserRequest,
    DownloadWatchSettingsPatch,
    RecordedFileRenameRequest,
    RecordedFileTranscodeRequest,
    RoomCreate,
    RoomPatch,
    YouTubeOAuthCompleteRequest,
    YouTubeOAuthStartRequest,
)
from .path_service import ensure_allowed_path
from .transcode_service import TranscodeService
from .upload_service import UploadService
from .youtube_oauth_service import YouTubeOAuthService

repository = Repository(db)
config_service = ConfigService(repository)
recording_service = RecordingService(repository)
upload_service = UploadService(repository)
transcode_service = TranscodeService(repository)
download_watch_service = DownloadWatchService(repository, transcode_service)
douyin_service = DouyinCollectionService(repository)
analytics_service = AnalyticsService(repository)
youtube_oauth_service = YouTubeOAuthService(repository)
recorder_process_service = RecorderProcessService(repository)
command_worker_service = CommandWorkerService(repository, recorder_process_service)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    imported = config_service.import_once()
    if imported:
        repository.add_event("startup", "已完成初始 ini 导入")
    stop_event = asyncio.Event()
    watch_task = asyncio.create_task(download_watch_service.run_loop(stop_event))
    upload_task = asyncio.create_task(upload_service.run_loop(stop_event))
    command_task = asyncio.create_task(command_worker_service.run_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        for task in (watch_task, upload_task, command_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="DouyinLiveRecorder Admin", version="0.1.0", lifespan=lifespan)
app.mount(
    "/assets",
    StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False),
    name="frontend-assets",
)


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = admin_token()
    if not expected:
        raise HTTPException(status_code=503, detail="服务端未配置 后台管理 Token")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="管理员 Token 无效")


def frontend_build_available() -> bool:
    return FRONTEND_INDEX.is_file()


def build_dashboard_data() -> dict[str, Any]:
    active_statuses = ("pending", "probing", "recording", "stopping")
    active_placeholders = ",".join("?" for _ in active_statuses)
    rooms = repository.list_rooms()
    latest_jobs = repository.list_rows("recording_jobs", order_by="id DESC", limit=200)
    active_jobs = repository.list_rows(
        "recording_jobs",
        where=f"status IN ({active_placeholders})",
        params=active_statuses,
        order_by="id DESC",
        limit=20,
    )
    recent_uploads = repository.list_rows("upload_records", order_by="id DESC", limit=10)
    recent_events = repository.list_rows("events", order_by="id DESC", limit=12)
    watch_records = repository.list_rows("download_watch_records", order_by="id DESC", limit=8)
    metrics = repository.list_rows("youtube_metrics", order_by="metric_date DESC, id DESC", limit=8)
    runtime = recorder_process_service.runtime_status()

    latest_job_by_room: dict[int, dict[str, Any]] = {}
    for job in latest_jobs:
        room_id = int(job["room_id"])
        if room_id not in latest_job_by_room:
            latest_job_by_room[room_id] = job

    rooms_with_status = []
    for room in rooms:
        latest_job = latest_job_by_room.get(int(room["id"]))
        rooms_with_status.append(
            {
                **room,
                "latest_job": latest_job,
                "display_status": latest_job["status"] if latest_job else ("idle" if room.get("enabled") else "disabled"),
            }
        )

    return {
        "summary": {
            "rooms_total": repository.count_rows("rooms", where="deleted_at IS NULL"),
            "rooms_enabled": repository.count_rows("rooms", where="enabled = 1 AND deleted_at IS NULL"),
            "active_jobs": repository.count_rows(
                "recording_jobs",
                where=f"status IN ({active_placeholders})",
                params=active_statuses,
            ),
            "files_today": repository.count_rows(
                "recorded_files",
                where="created_at >= datetime(date('now', 'localtime'))",
            ),
            "uploads_pending": repository.count_rows("upload_records", where="status = ?", params=("pending",)),
            "uploads_failed": repository.count_rows("upload_records", where="status = ?", params=("failed",)),
            "douyin_running": repository.count_rows(
                "douyin_collection_tasks",
                where="status IN (?, ?)",
                params=("queued", "running"),
            ),
            "runtime_processes": len(runtime),
            "watch_registered": repository.count_rows(
                "download_watch_records",
                where="status = ?",
                params=("registered",),
            ),
            "metrics_cached": len(metrics),
        },
        "rooms": rooms_with_status,
        "active_jobs": active_jobs,
        "recent_uploads": recent_uploads,
        "recent_events": recent_events,
        "recording_runtime": runtime,
        "download_watch": {
            "settings": download_watch_service.get_settings(),
            "records": watch_records,
        },
        "metrics": metrics,
    }


@app.get("/", response_model=None)
def index() -> HTMLResponse | FileResponse:
    if frontend_build_available():
        return FileResponse(FRONTEND_INDEX)

    initial_state = json.dumps({"tokenConfigured": bool(admin_token())}, ensure_ascii=False)
    template = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DouyinLiveRecorder 后台管理</title>
  <style>
    :root {
      --panel: rgba(255,255,255,0.88);
      --ink: #1e2430;
      --muted: #6a7281;
      --line: rgba(90, 76, 60, 0.14);
      --accent: #b6512d;
      --success: #256f4f;
      --warn: #996019;
      --danger: #9d2c2c;
      --shadow: 0 18px 40px rgba(46, 34, 24, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(240, 201, 180, 0.65), transparent 28%),
        radial-gradient(circle at right 10% top 15%, rgba(158, 186, 194, 0.35), transparent 24%),
        linear-gradient(180deg, #f8f3eb 0%, #f2ece3 100%);
      color: var(--ink);
    }
    .shell { max-width: 1440px; margin: 0 auto; padding: 28px 20px 40px; }
    .hero {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: flex-start;
      padding: 24px 26px;
      border: 1px solid var(--line);
      border-radius: 26px;
      background: linear-gradient(145deg, rgba(255,253,250,0.96), rgba(249,242,234,0.86));
      box-shadow: var(--shadow);
    }
    .title { margin: 0; font-size: 30px; line-height: 1.1; letter-spacing: 0.02em; }
    .subtitle { margin: 10px 0 0; max-width: 760px; color: var(--muted); line-height: 1.6; }
    .toolbar { min-width: 320px; display: grid; gap: 10px; }
    .toolbar-row { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0 22px; }
    .card, .section {
      border: 1px solid var(--line);
      border-radius: 22px;
      background: var(--panel);
      backdrop-filter: blur(8px);
      box-shadow: var(--shadow);
    }
    .card { padding: 18px; min-height: 132px; }
    .eyebrow { color: var(--muted); font-size: 12px; letter-spacing: 0.1em; text-transform: uppercase; }
    .metric { margin-top: 14px; font-size: 34px; font-weight: 700; }
    .metric-note { margin-top: 8px; color: var(--muted); font-size: 13px; }
    .layout { display: grid; grid-template-columns: 1.45fr 1fr; gap: 18px; align-items: start; }
    .stack { display: grid; gap: 18px; }
    .section { padding: 18px; }
    .section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; }
    h2, h3 { margin: 0; font-size: 18px; }
    .muted { color: var(--muted); }
    .mini { font-size: 12px; }
    .pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 10px;
      background: rgba(182, 81, 45, 0.1);
      color: var(--accent);
      font-size: 12px;
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 600;
    }
    .status::before {
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: currentColor;
      opacity: 0.85;
    }
    .status.recording, .status.running, .status.completed, .status.uploaded, .status.registered { color: var(--success); background: rgba(37, 111, 79, 0.1); }
    .status.pending, .status.probing, .status.stopping, .status.uploading, .status.queued, .status.stable { color: var(--warn); background: rgba(153, 96, 25, 0.1); }
    .status.failed, .status.completed_with_errors, .status.interrupted { color: var(--danger); background: rgba(157, 44, 44, 0.1); }
    .status.idle, .status.disabled, .status.not_required { color: var(--muted); background: rgba(106, 114, 129, 0.12); }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    button, input, select { font: inherit; }
    button {
      border: 0;
      border-radius: 12px;
      padding: 9px 14px;
      cursor: pointer;
      transition: transform .15s ease, opacity .15s ease;
    }
    button:hover { transform: translateY(-1px); }
    button:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }
    .primary { background: var(--accent); color: white; }
    .secondary { background: rgba(30, 36, 48, 0.08); color: var(--ink); }
    .ghost { background: rgba(255,255,255,0.75); color: var(--ink); border: 1px solid var(--line); }
    .danger { background: rgba(157, 44, 44, 0.12); color: var(--danger); }
    .inline-form { display: grid; grid-template-columns: 2fr 1fr 120px 100px auto; gap: 10px; margin-bottom: 14px; }
    input, select {
      width: 100%;
      border-radius: 12px;
      border: 1px solid rgba(30, 36, 48, 0.12);
      background: rgba(255,255,255,0.92);
      padding: 10px 12px;
      color: var(--ink);
    }
    table { width: 100%; border-collapse: collapse; }
    th, td {
      padding: 12px 10px;
      border-top: 1px solid rgba(30, 36, 48, 0.08);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }
    th {
      color: var(--muted);
      font-weight: 600;
      font-size: 12px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .list { display: grid; gap: 10px; }
    .item {
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(30, 36, 48, 0.08);
    }
    .item-title {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: baseline;
      margin-bottom: 6px;
    }
    .item-title strong { font-size: 14px; }
    .empty {
      padding: 18px;
      border-radius: 16px;
      border: 1px dashed rgba(30, 36, 48, 0.14);
      color: var(--muted);
      text-align: center;
      background: rgba(255,255,255,0.55);
    }
    .banner {
      margin-top: 12px;
      border-radius: 16px;
      padding: 12px 14px;
      background: rgba(255,255,255,0.68);
      border: 1px solid rgba(30, 36, 48, 0.08);
      color: var(--muted);
    }
    .two-col { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    code {
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
      background: rgba(30, 36, 48, 0.06);
      padding: 2px 6px;
      border-radius: 8px;
    }
    @media (max-width: 1100px) {
      .layout { grid-template-columns: 1fr; }
    }
    @media (max-width: 900px) {
      .hero { flex-direction: column; }
      .toolbar { min-width: 0; width: 100%; }
      .toolbar-row { justify-content: flex-start; }
      .inline-form { grid-template-columns: 1fr; }
      .two-col { grid-template-columns: 1fr; }
      table, thead, tbody, tr, th, td { display: block; }
      thead { display: none; }
      tr {
        margin-top: 12px;
        padding: 12px;
        border-radius: 16px;
        background: rgba(255,255,255,0.72);
        border: 1px solid rgba(30, 36, 48, 0.08);
      }
      td { border-top: 0; padding: 6px 0; }
      td::before {
        content: attr(data-label);
        display: block;
        margin-bottom: 4px;
        color: var(--muted);
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div>
        <p class="eyebrow">DouyinLiveRecorder Admin</p>
        <h1 class="title">后台管理</h1>
        <p class="subtitle">
          这里聚合了直播间、录制任务、上传队列、下载监控和最近事件。默认只读，填入
          <code>后台管理 Token</code> 后即可直接在页面里执行启动、停止、扫描和刷新操作。
        </p>
      </div>
      <div class="toolbar">
        <label class="mini muted" for="token-input">管理员 Token</label>
        <input id="token-input" type="password" placeholder="输入 X-Admin-Token，用于页面内操作">
        <div class="toolbar-row">
          <button id="save-token" class="secondary">保存 Token</button>
          <button id="refresh-page" class="primary">刷新总览</button>
        </div>
        <div class="banner" id="status-banner">页面初始化中...</div>
      </div>
    </section>

    <section class="grid" id="summary-grid"></section>

    <section class="layout">
      <div class="stack">
        <section class="section">
          <div class="section-head">
            <div>
              <h2>直播间管理</h2>
              <div class="muted mini">新增直播间、切换启用状态，并直接发起开始/停止录制。</div>
            </div>
            <div class="actions">
              <button id="reload-rooms" class="ghost">重新加载</button>
            </div>
          </div>
          <form id="create-room-form" class="inline-form">
            <input name="url" placeholder="直播间 URL，例如 https://live.douyin.com/xxx" required>
            <input name="name" placeholder="主播名，可选">
            <select name="quality">
              <option value="原画">原画</option>
              <option value="蓝光">蓝光</option>
              <option value="超清">超清</option>
              <option value="高清">高清</option>
              <option value="标清">标清</option>
              <option value="流畅">流畅</option>
            </select>
            <select name="enabled">
              <option value="true">启用</option>
              <option value="false">禁用</option>
            </select>
            <button class="primary" type="submit">新增直播间</button>
          </form>
          <div id="rooms-table"></div>
        </section>

        <section class="section">
          <div class="section-head">
            <div>
              <h2>运行概览</h2>
              <div class="muted mini">当前活跃任务、运行中的录制进程和缓存的 YouTube 指标。</div>
            </div>
            <div class="actions">
              <span class="pill">/api/dashboard</span>
            </div>
          </div>
          <div class="two-col">
            <div>
              <h3>活跃任务</h3>
              <div id="active-jobs" class="list"></div>
            </div>
            <div>
              <h3>录制进程</h3>
              <div id="runtime-list" class="list"></div>
            </div>
          </div>
        </section>
      </div>

      <div class="stack">
        <section class="section">
          <div class="section-head">
            <div>
              <h2>上传队列</h2>
              <div class="muted mini">最近上传记录和失败状态。</div>
            </div>
            <div class="actions">
              <button id="refresh-metrics" class="ghost">刷新 YouTube 指标</button>
            </div>
          </div>
          <div id="uploads-list" class="list"></div>
        </section>

        <section class="section">
          <div class="section-head">
            <div>
              <h2>下载监控</h2>
              <div class="muted mini">监控目录配置和最近登记记录。</div>
            </div>
            <div class="actions">
              <button id="scan-watch" class="ghost">立即扫描</button>
            </div>
          </div>
          <div id="download-watch-panel"></div>
        </section>

        <section class="section">
          <div class="section-head">
            <div>
              <h2>最近事件</h2>
              <div class="muted mini">用于快速排查后台状态变化。</div>
            </div>
          </div>
          <div id="events-list" class="list"></div>
        </section>
      </div>
    </section>
  </div>
  <script>
    const state = __INITIAL_STATE__;
    const dashboardUrl = '/api/dashboard';
    const tokenInput = document.getElementById('token-input');
    const statusBanner = document.getElementById('status-banner');
    const summaryGrid = document.getElementById('summary-grid');
    const roomsTable = document.getElementById('rooms-table');
    const activeJobs = document.getElementById('active-jobs');
    const runtimeList = document.getElementById('runtime-list');
    const uploadsList = document.getElementById('uploads-list');
    const downloadWatchPanel = document.getElementById('download-watch-panel');
    const eventsList = document.getElementById('events-list');
    const tokenStorageKey = 'douyin-live-recorder-admin-token';

    tokenInput.value = localStorage.getItem(tokenStorageKey) || '';

    function authHeaders(extra = {}) {
      const token = tokenInput.value.trim();
      return token ? {...extra, 'X-Admin-Token': token} : extra;
    }

    function setBanner(message, type = 'info') {
      const background = type === 'error'
        ? 'rgba(157, 44, 44, 0.1)'
        : type === 'success'
          ? 'rgba(37, 111, 79, 0.1)'
          : 'rgba(255,255,255,0.68)';
      const color = type === 'error'
        ? 'var(--danger)'
        : type === 'success'
          ? 'var(--success)'
          : 'var(--muted)';
      statusBanner.style.background = background;
      statusBanner.style.color = color;
      statusBanner.textContent = message;
    }

    function statusClass(value) {
      return String(value || 'idle').replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();
    }

    function escapeHtml(value) {
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function statusBadge(value) {
      const text = escapeHtml(value || 'idle');
      return `<span class="status ${statusClass(value)}">${text}</span>`;
    }

    function renderEmpty(target, text) {
      target.innerHTML = `<div class="empty">${escapeHtml(text)}</div>`;
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, options);
      const data = await response.json().catch(() => ({detail: '响应不是合法 JSON'}));
      if (!response.ok) {
        throw new Error(data.detail || `请求失败: ${response.status}`);
      }
      return data;
    }

    function summaryCard(title, value, note) {
      return `
        <article class="card">
          <div class="eyebrow">${escapeHtml(title)}</div>
          <div class="metric">${escapeHtml(value)}</div>
          <div class="metric-note">${escapeHtml(note)}</div>
        </article>
      `;
    }

    function renderSummary(summary) {
      summaryGrid.innerHTML = [
        summaryCard('直播间', `${summary.rooms_enabled} / ${summary.rooms_total}`, '已启用 / 总数'),
        summaryCard('活跃录制', String(summary.active_jobs), `运行进程 ${summary.runtime_processes}`),
        summaryCard('今日文件', String(summary.files_today), `下载监控已登记 ${summary.watch_registered}`),
        summaryCard('待上传', String(summary.uploads_pending), `失败 ${summary.uploads_failed}`),
        summaryCard('Douyin 任务', String(summary.douyin_running), `缓存指标 ${summary.metrics_cached}`),
      ].join('');
    }

    const qualityOptions = ['原画', '蓝光', '超清', '高清', '标清', '流畅'];
    let editingRoomId = null;
    let lastDashboard = null;

    function qualitySelectHtml(currentValue) {
      const current = currentValue || '原画';
      return qualityOptions
        .map((value) => `<option value="${escapeHtml(value)}" ${value === current ? 'selected' : ''}>${escapeHtml(value)}</option>`)
        .join('');
    }

    function renderRoomEditRow(room) {
      return `
        <tr data-room-id="${room.id}" class="editing">
          <td data-label="房间">
            <input class="edit-name" value="${escapeHtml(room.name || '')}" placeholder="主播名">
            <input class="edit-url" value="${escapeHtml(room.url || '')}" placeholder="直播间 URL" style="margin-top:6px">
          </td>
          <td data-label="平台">
            <span class="muted mini">${escapeHtml(room.platform || 'unknown')}</span>
          </td>
          <td data-label="清晰度">
            <select class="edit-quality">${qualitySelectHtml(room.quality)}</select>
          </td>
          <td data-label="状态">${statusBadge(room.display_status)}</td>
          <td data-label="最近任务">
            <span class="muted mini">编辑模式</span>
          </td>
          <td data-label="操作">
            <div class="actions">
              <button class="primary" data-action="save-edit-room" data-room-id="${room.id}">保存</button>
              <button class="ghost" data-action="cancel-edit-room" data-room-id="${room.id}">取消</button>
            </div>
          </td>
        </tr>
      `;
    }

    function renderRooms(rooms) {
      if (!rooms.length) {
        renderEmpty(roomsTable, '暂无直播间，先在上方新增一个。');
        return;
      }
      const rows = rooms.map((room) => {
        if (editingRoomId === room.id) {
          return renderRoomEditRow(room);
        }
        const latestJob = room.latest_job;
        const active = latestJob && ['pending', 'probing', 'recording', 'stopping'].includes(latestJob.status);
        const toggleLabel = room.enabled ? '禁用' : '启用';
        return `
          <tr data-room-id="${room.id}">
            <td data-label="房间">
              <strong>${escapeHtml(room.name || '未命名主播')}</strong>
              <div class="muted mini">${escapeHtml(room.url)}</div>
            </td>
            <td data-label="平台">${escapeHtml(room.platform || 'unknown')}</td>
            <td data-label="清晰度">${escapeHtml(room.quality || '-')}</td>
            <td data-label="状态">${statusBadge(room.display_status)}</td>
            <td data-label="最近任务">
              ${latestJob ? `<div>#${latestJob.id}</div><div class="muted mini">${escapeHtml(latestJob.updated_at || '')}</div>` : '<span class="muted mini">暂无任务</span>'}
            </td>
            <td data-label="操作">
              <div class="actions">
                <button class="ghost" data-action="edit-room" data-room-id="${room.id}" ${active ? 'disabled' : ''} title="${active ? '请先停止录制再编辑' : ''}">编辑</button>
                <button class="secondary" data-action="toggle-room" data-room-id="${room.id}" data-enabled="${room.enabled ? '1' : '0'}">${toggleLabel}</button>
                <button class="primary" data-action="start-room" data-room-id="${room.id}" ${active ? 'disabled' : ''}>开始录制</button>
                <button class="danger" data-action="stop-room" data-room-id="${room.id}" ${active ? '' : 'disabled'}>停止录制</button>
              </div>
            </td>
          </tr>
        `;
      }).join('');
      roomsTable.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>房间</th>
              <th>平台</th>
              <th>清晰度</th>
              <th>状态</th>
              <th>最近任务</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }

    function renderItemList(target, items, renderer, emptyText) {
      if (!items.length) {
        renderEmpty(target, emptyText);
        return;
      }
      target.innerHTML = items.map(renderer).join('');
    }

    function renderDashboard(data) {
      lastDashboard = data;
      renderSummary(data.summary);
      renderRooms(data.rooms || []);
      renderItemList(
        activeJobs,
        data.active_jobs || [],
        (job) => `
          <div class="item">
            <div class="item-title">
              <strong>任务 #${job.id}</strong>
              ${statusBadge(job.status)}
            </div>
            <div class="mini muted">房间 #${job.room_id} · 创建于 ${escapeHtml(job.created_at || '')}</div>
          </div>
        `,
        '当前没有活跃录制任务。'
      );
      renderItemList(
        runtimeList,
        data.recording_runtime || [],
        (runtime) => `
          <div class="item">
            <div class="item-title">
              <strong>任务 #${runtime.job_id}</strong>
              <span class="pill">PID ${escapeHtml(runtime.pid)}</span>
            </div>
            <div class="mini muted">输出目录：${escapeHtml(runtime.output_dir || '')}</div>
          </div>
        `,
        '当前没有运行中的录制子进程。'
      );
      renderItemList(
        uploadsList,
        data.recent_uploads || [],
        (upload) => {
          const failureLine = upload.status === 'failed' && upload.failure_reason
            ? `<div class="mini" style="color: var(--danger)">失败原因：${escapeHtml(upload.failure_reason)}</div>`
            : '';
          const actions = upload.status === 'failed'
            ? `<div class="actions" style="margin-top:8px"><button class="ghost" data-action="retry-upload" data-upload-id="${upload.id}">重试上传</button></div>`
            : '';
          return `
            <div class="item">
              <div class="item-title">
                <strong>#${upload.id} · ${escapeHtml(upload.title || upload.local_path || '未命名文件')}</strong>
                ${statusBadge(upload.status)}
              </div>
              <div class="mini muted">${escapeHtml(upload.local_path || '')}</div>
              <div class="mini muted">YouTube ID：${escapeHtml(upload.youtube_video_id || '未生成')} · 重试 ${escapeHtml(upload.retry_count || 0)} 次</div>
              ${failureLine}
              ${actions}
            </div>
          `;
        },
        '暂无上传记录。'
      );

      const settings = data.download_watch?.settings || {};
      const records = data.download_watch?.records || [];
      downloadWatchPanel.innerHTML = `
        <div class="banner">
          <div><strong>监控开关：</strong>${settings.enabled ? '已启用' : '已关闭'}</div>
          <div><strong>轮询间隔：</strong>${escapeHtml(settings.poll_interval_seconds || 0)} 秒</div>
          <div><strong>稳定检测：</strong>${escapeHtml(settings.stable_checks || 0)} 次</div>
          <div><strong>目录：</strong>${escapeHtml((settings.directories || []).join('，') || '未配置')}</div>
        </div>
      `;
      const recordsContainer = document.createElement('div');
      recordsContainer.className = 'list';
      downloadWatchPanel.appendChild(recordsContainer);
      renderItemList(
        recordsContainer,
        records,
        (record) => `
          <div class="item">
            <div class="item-title">
              <strong>${escapeHtml(record.local_path || '')}</strong>
              ${statusBadge(record.status)}
            </div>
            <div class="mini muted">稳定次数 ${escapeHtml(record.stable_count || 0)} · 编码状态 ${escapeHtml(record.encoding_status || 'not_required')}</div>
          </div>
        `,
        '下载监控还没有记录。'
      );

      renderItemList(
        eventsList,
        data.recent_events || [],
        (event) => `
          <div class="item">
            <div class="item-title">
              <strong>${escapeHtml(event.event_type)}</strong>
              <span class="mini muted">${escapeHtml(event.created_at || '')}</span>
            </div>
            <div>${escapeHtml(event.message || '')}</div>
          </div>
        `,
        '最近还没有事件。'
      );
    }

    async function loadDashboard() {
      try {
        const data = await fetchJson(dashboardUrl);
        renderDashboard(data);
        setBanner('后台概览已刷新。');
      } catch (error) {
        setBanner(error.message, 'error');
      }
    }

    async function mutate(url, method, body) {
      const options = {
        method,
        headers: authHeaders(body ? {'Content-Type': 'application/json'} : {}),
      };
      if (body) {
        options.body = JSON.stringify(body);
      }
      return fetchJson(url, options);
    }

    document.getElementById('save-token').addEventListener('click', () => {
      localStorage.setItem(tokenStorageKey, tokenInput.value.trim());
      setBanner(tokenInput.value.trim() ? '管理员 Token 已保存到本地浏览器。' : '已清空本地保存的 Token。', 'success');
    });

    document.getElementById('refresh-page').addEventListener('click', loadDashboard);
    document.getElementById('reload-rooms').addEventListener('click', loadDashboard);

    document.getElementById('create-room-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      try {
        await mutate('/api/rooms', 'POST', {
          url: form.get('url'),
          name: form.get('name'),
          quality: form.get('quality'),
          enabled: form.get('enabled') === 'true',
        });
        event.currentTarget.reset();
        setBanner('直播间已创建。', 'success');
        await loadDashboard();
      } catch (error) {
        setBanner(error.message, 'error');
      }
    });

    roomsTable.addEventListener('click', async (event) => {
      const button = event.target.closest('button[data-action]');
      if (!button) {
        return;
      }
      const roomId = Number(button.dataset.roomId);
      const action = button.dataset.action;
      try {
        if (action === 'start-room') {
          await mutate(`/api/rooms/${roomId}/start`, 'POST');
          setBanner(`已请求开始录制房间 #${roomId}。`, 'success');
        } else if (action === 'stop-room') {
          await mutate(`/api/rooms/${roomId}/stop`, 'POST');
          setBanner(`已请求停止录制房间 #${roomId}。`, 'success');
        } else if (action === 'toggle-room') {
          const enabled = button.dataset.enabled === '1';
          await mutate(`/api/rooms/${roomId}`, 'PATCH', {enabled: !enabled});
          setBanner(`房间 #${roomId} 已${enabled ? '禁用' : '启用'}。`, 'success');
        } else if (action === 'edit-room') {
          editingRoomId = roomId;
          renderRooms((lastDashboard && lastDashboard.rooms) || []);
          setBanner(`正在编辑房间 #${roomId}。`);
          return;
        } else if (action === 'cancel-edit-room') {
          editingRoomId = null;
          renderRooms((lastDashboard && lastDashboard.rooms) || []);
          setBanner('已取消编辑。');
          return;
        } else if (action === 'save-edit-room') {
          const row = button.closest('tr');
          if (!row) {
            return;
          }
          const nameInput = row.querySelector('.edit-name');
          const urlInput = row.querySelector('.edit-url');
          const qualitySelect = row.querySelector('.edit-quality');
          const url = (urlInput && urlInput.value || '').trim();
          if (!url) {
            setBanner('直播间 URL 不能为空。', 'error');
            return;
          }
          await mutate(`/api/rooms/${roomId}`, 'PATCH', {
            name: nameInput ? nameInput.value.trim() : '',
            url,
            quality: qualitySelect ? qualitySelect.value : undefined,
          });
          editingRoomId = null;
          setBanner(`房间 #${roomId} 已更新。`, 'success');
        }
        await loadDashboard();
      } catch (error) {
        setBanner(error.message, 'error');
      }
    });

    uploadsList.addEventListener('click', async (event) => {
      const button = event.target.closest('button[data-action="retry-upload"]');
      if (!button) {
        return;
      }
      const uploadId = button.dataset.uploadId;
      button.disabled = true;
      try {
        await mutate(`/api/uploads/${uploadId}/retry`, 'POST');
        setBanner(`已请求重试上传 #${uploadId}。`, 'success');
        await loadDashboard();
      } catch (error) {
        setBanner(error.message, 'error');
        button.disabled = false;
      }
    });

    document.getElementById('scan-watch').addEventListener('click', async () => {
      try {
        const result = await mutate('/api/download-watch/scan', 'POST');
        setBanner(`扫描完成：发现 ${result.candidates} 个候选文件，登记 ${result.registered} 个。`, 'success');
        await loadDashboard();
      } catch (error) {
        setBanner(error.message, 'error');
      }
    });

    document.getElementById('refresh-metrics').addEventListener('click', async () => {
      try {
        const result = await mutate('/api/metrics/videos/refresh', 'POST');
        setBanner(`YouTube 指标刷新完成：请求 ${result.requested} 个视频，更新 ${result.updated} 条记录。`, 'success');
        await loadDashboard();
      } catch (error) {
        setBanner(error.message, 'error');
      }
    });

    if (!state.tokenConfigured) {
      setBanner('服务端尚未配置 后台管理 Token，当前页面仅能查看只读数据。');
    } else {
      setBanner('后台已就绪，点击“刷新总览”或直接操作页面。');
    }
    loadDashboard();
  </script>
</body>
</html>
"""
    return HTMLResponse(template.replace("__INITIAL_STATE__", initial_state))


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    return build_dashboard_data()


@app.get("/api/auth/check", dependencies=[Depends(require_admin_token)])
def check_auth() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/config")
def list_config() -> dict[str, list[dict]]:
    return {"data": config_service.list_settings()}


@app.get("/api/config/{section}")
def get_config_section(section: str) -> dict:
    return config_service.get_section(section)


@app.patch("/api/config/{section}", dependencies=[Depends(require_admin_token)])
def update_config_section(section: str, request: ConfigSectionPatch) -> dict:
    return config_service.update_section(section, request.values)


@app.post("/api/config/import", dependencies=[Depends(require_admin_token)])
def import_config() -> dict[str, int]:
    return config_service.import_ini()


@app.post("/api/config/export", dependencies=[Depends(require_admin_token)])
def export_config() -> dict[str, int]:
    return config_service.export_ini()


@app.get("/api/youtube/oauth/status")
def youtube_oauth_status() -> dict[str, Any]:
    return youtube_oauth_service.status()


@app.post("/api/youtube/data-api/check", dependencies=[Depends(require_admin_token)])
def check_youtube_data_api() -> dict[str, Any]:
    return youtube_oauth_service.check_data_api_access()


@app.post("/api/youtube/oauth/start", dependencies=[Depends(require_admin_token)])
def start_youtube_oauth(request: YouTubeOAuthStartRequest) -> dict[str, str]:
    try:
        return youtube_oauth_service.start(request.redirect_uri)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/youtube/oauth/complete", dependencies=[Depends(require_admin_token)])
def complete_youtube_oauth(request: YouTubeOAuthCompleteRequest) -> dict[str, Any]:
    try:
        return youtube_oauth_service.complete(request.code, request.state)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/rooms")
def list_rooms() -> dict[str, list[dict]]:
    return {"data": repository.list_rooms()}


@app.post("/api/rooms", dependencies=[Depends(require_admin_token)])
def create_room(request: RoomCreate) -> dict:
    platform = request.platform if request.platform != "unknown" else guess_platform(request.url)
    return repository.create_room(request.url, request.name, platform, request.quality, request.enabled)


@app.patch("/api/rooms/{room_id}", dependencies=[Depends(require_admin_token)])
def update_room(room_id: int, request: RoomPatch) -> dict:
    data = request.model_dump(exclude_unset=True)
    if data.get("url") and not data.get("platform"):
        data["platform"] = guess_platform(data["url"])
    try:
        room = repository.update_room(room_id, data)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not room:
        raise HTTPException(status_code=404, detail="直播间不存在")
    return room


@app.delete("/api/rooms/{room_id}", dependencies=[Depends(require_admin_token)])
def delete_room(room_id: int) -> dict[str, bool]:
    try:
        room = repository.delete_room(room_id)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not room:
        raise HTTPException(status_code=404, detail="直播间不存在")
    repository.add_event("room_deleted", f"直播间 #{room_id} 已删除", level="warning")
    return {"deleted": True}


@app.post("/api/rooms/{room_id}/start", dependencies=[Depends(require_admin_token)])
def start_room(room_id: int) -> dict:
    return recording_service.start_room(room_id)


@app.post("/api/rooms/{room_id}/stop", dependencies=[Depends(require_admin_token)])
def stop_room(room_id: int) -> dict:
    return recording_service.stop_room(room_id)


@app.get("/api/jobs")
def list_jobs(status: str | None = None, limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, list[dict]]:
    if status:
        return {"data": repository.list_rows("recording_jobs", where="status = ?", params=(status,), limit=limit)}
    return {"data": repository.list_rows("recording_jobs", limit=limit)}


@app.delete("/api/jobs/{job_id}", dependencies=[Depends(require_admin_token)])
def delete_job(job_id: int) -> dict[str, bool]:
    try:
        deleted = repository.delete_recording_job(job_id)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="录制任务不存在")
    repository.add_event("recording_job_deleted", f"录制任务 #{job_id} 已删除", level="warning")
    return {"deleted": True}


@app.get("/api/task-commands")
def list_task_commands(status: str | None = None, limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, list[dict]]:
    if status:
        return {"data": repository.list_rows("task_commands", where="status = ?", params=(status,), limit=limit)}
    return {"data": repository.list_rows("task_commands", limit=limit)}


@app.get("/api/recording-runtime")
def recording_runtime() -> dict[str, list[dict]]:
    return {"data": recorder_process_service.runtime_status()}


@app.get("/api/files")
def list_files(
    room_id: int | None = None,
    job_id: int | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, list[dict]]:
    clauses = []
    params: list[Any] = []
    if room_id is not None:
        clauses.append("room_id = ?")
        params.append(room_id)
    if job_id is not None:
        clauses.append("job_id = ?")
        params.append(job_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if date_from:
        clauses.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("created_at <= ?")
        params.append(date_to)
    return {"data": repository.list_rows("recorded_files", where=" AND ".join(clauses), params=tuple(params), limit=limit)}


def get_recorded_file_or_404(file_id: int) -> dict:
    recorded = repository.get_row("recorded_files", file_id)
    if not recorded:
        raise HTTPException(status_code=404, detail="文件记录不存在")
    return recorded


@app.post("/api/files/{file_id}/transcode", dependencies=[Depends(require_admin_token)])
def transcode_file(file_id: int, request: RecordedFileTranscodeRequest) -> dict:
    recorded = get_recorded_file_or_404(file_id)
    source_path = ensure_allowed_path(recorded["local_path"])
    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(status_code=404, detail="源文件不存在")
    repository.update_recorded_file_path(file_id, source_path)
    try:
        target_path = transcode_service.transcode_to_mp4(
            source_path,
            delete_origin=request.delete_origin,
            reencode_h264=request.reencode_h264,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return repository.register_file(
        target_path,
        source="transcode",
        job_id=recorded.get("job_id"),
        room_id=recorded.get("room_id"),
    )


@app.patch("/api/files/{file_id}/rename", dependencies=[Depends(require_admin_token)])
def rename_file(file_id: int, request: RecordedFileRenameRequest) -> dict:
    recorded = get_recorded_file_or_404(file_id)
    source_path = ensure_allowed_path(recorded["local_path"])
    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(status_code=404, detail="源文件不存在")
    filename = request.filename.strip()
    if not filename or Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="文件名不能包含路径分隔符")
    target_path = ensure_allowed_path(source_path.parent / filename)
    if target_path.parent != source_path.parent:
        raise HTTPException(status_code=400, detail="目标文件必须保留在原目录")
    if target_path.exists():
        raise HTTPException(status_code=409, detail="目标文件已存在")
    source_path.rename(target_path)
    try:
        updated = repository.update_recorded_file_path(file_id, target_path)
    except ValueError as error:
        target_path.rename(source_path)
        raise HTTPException(status_code=409, detail=str(error)) from error
    repository.add_event("file_renamed", f"文件已从 {source_path.name} 重命名为 {target_path.name}", file_id=file_id)
    return updated or get_recorded_file_or_404(file_id)


@app.delete("/api/files/{file_id}", dependencies=[Depends(require_admin_token)])
def delete_file(file_id: int) -> dict[str, bool]:
    recorded = get_recorded_file_or_404(file_id)
    source_path = ensure_allowed_path(recorded["local_path"])
    if source_path.exists() and source_path.is_file():
        try:
            source_path.unlink()
        except PermissionError as error:
            raise HTTPException(status_code=409, detail="文件正在使用，无法删除") from error
        except OSError as error:
            raise HTTPException(status_code=409, detail=f"文件无法删除：{error}") from error
    deleted = repository.delete_recorded_file(file_id)
    repository.add_event("file_deleted", f"文件已删除：{source_path.name}", level="warning", file_id=file_id)
    return {"deleted": deleted}


@app.get("/api/uploads")
def list_uploads(status: str | None = None, limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, list[dict]]:
    if status:
        return {"data": repository.list_rows("upload_records", where="status = ?", params=(status,), limit=limit)}
    return {"data": repository.list_rows("upload_records", limit=limit)}


@app.post("/api/uploads/{upload_id}/retry", dependencies=[Depends(require_admin_token)])
def retry_upload(upload_id: int) -> dict:
    return upload_service.retry(upload_id)


@app.get("/api/download-watch")
def get_download_watch() -> dict[str, Any]:
    return {
        "settings": download_watch_service.get_settings(),
        "records": repository.list_rows("download_watch_records", limit=100),
    }


@app.post("/api/download-watch/scan", dependencies=[Depends(require_admin_token)])
def scan_download_watch() -> dict[str, int]:
    return download_watch_service.scan_once()


@app.patch("/api/download-watch/settings", dependencies=[Depends(require_admin_token)])
def update_download_watch_settings(request: DownloadWatchSettingsPatch) -> dict:
    return download_watch_service.update_settings(request.model_dump(exclude_unset=True))


@app.post("/api/douyin/download", dependencies=[Depends(require_admin_token)])
async def create_douyin_download(request: DouyinSingleRequest) -> dict:
    return douyin_service.create_single_task(
        request.url, request.output_dir, request.proxy, request.request_cookie(), request.overwrite
    )


@app.post("/api/douyin/user-download", dependencies=[Depends(require_admin_token)])
async def create_douyin_user_download(request: DouyinUserRequest) -> dict:
    return douyin_service.create_user_task(
        request.url, request.output_dir, request.proxy, request.request_cookie(), request.max_items, request.overwrite
    )


@app.get("/api/douyin/tasks")
def list_douyin_tasks(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, list[dict]]:
    return {"data": repository.list_rows("douyin_collection_tasks", limit=limit)}


@app.get("/api/douyin/tasks/{task_id}")
def get_douyin_task(task_id: int) -> dict[str, Any]:
    task = repository.get_row("douyin_collection_tasks", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="抖音下载任务不存在")
    items = repository.list_rows("douyin_downloaded_items", where="task_id = ?", params=(task_id,), order_by="id ASC")
    return {"task": task, "items": items}


@app.delete("/api/douyin/tasks/{task_id}", dependencies=[Depends(require_admin_token)])
def delete_douyin_task(task_id: int) -> dict[str, bool]:
    try:
        deleted = repository.delete_douyin_task(task_id)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="抖音下载任务不存在")
    repository.add_event("douyin_task_deleted", f"抖音下载任务 #{task_id} 已删除", level="warning")
    return {"deleted": True}


@app.get("/api/metrics/videos")
def list_metrics() -> dict[str, list[dict]]:
    return {"data": analytics_service.list_video_metrics()}


@app.post("/api/metrics/videos/refresh", dependencies=[Depends(require_admin_token)])
def refresh_metrics() -> dict[str, int]:
    return analytics_service.refresh_video_metrics()


@app.get("/api/events/recent")
def recent_events(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, list[dict]]:
    return {"data": repository.list_rows("events", limit=limit)}


@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
def frontend_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="接口不存在")
    if not frontend_build_available():
        raise HTTPException(status_code=404, detail="前端构建文件不存在")
    return FileResponse(FRONTEND_INDEX)
