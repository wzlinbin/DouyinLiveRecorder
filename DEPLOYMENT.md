# 部署手册

当前项目部署方式：

```text
FastAPI 后端服务 + 后端托管 frontend/dist 前端静态文件
```

启动入口：

```bash
python -m server
```

部署配置统一放在：

```text
config/config.ini
```

不需要再把 `ADMIN_API_TOKEN`、监听地址、端口写到环境变量里。

---

## 一、项目目录说明

关键目录：

```text
titok2youtube/
├── server/                 # 后台管理服务 FastAPI
├── frontend/               # React/Vite 前端
├── src/                    # 录制、下载、上传核心逻辑
├── config/
│   ├── config.ini          # 主配置文件
│   ├── URL_config.ini      # 直播间 URL 配置
│   ├── admin.db            # 后台 SQLite 数据库
│   ├── youtube_client_secret.json
│   ├── youtube_token.json
│   └── youtube_upload_state.json
├── downloads/              # 默认下载/录制目录
├── requirements.txt
└── main.py                 # 原始录制入口
```

后台服务入口：

```bash
python -m server
```

默认监听：

```text
127.0.0.1:8000
```

---

## 二、部署前准备

### 1. 必需软件

需要安装：

```text
Python 3.11+
Node.js 20+
npm
ffmpeg
git
```

### 2. 重要配置文件

部署时请保留：

```text
config/config.ini
config/URL_config.ini
config/admin.db
```

如果使用 YouTube 上传，还需要：

```text
config/youtube_client_secret.json
config/youtube_token.json
config/youtube_upload_state.json
```

这些文件包含敏感信息，不建议提交到公开仓库。

---

## 三、配置 config.ini

打开：

```text
config/config.ini
```

确认或添加：

```ini
[后台管理]
ADMIN_API_TOKEN = 你的强密码
后台监听地址 = 127.0.0.1
后台监听端口 = 8000
```

### 本机访问配置

如果只在服务器本机访问：

```ini
[后台管理]
ADMIN_API_TOKEN = 你的强密码
后台监听地址 = 127.0.0.1
后台监听端口 = 8000
```

### 局域网或公网直接访问

如果需要外部机器访问：

```ini
[后台管理]
ADMIN_API_TOKEN = 你的强密码
后台监听地址 = 0.0.0.0
后台监听端口 = 8000
```

访问地址：

```text
http://服务器IP:8000
```

### 推荐公网部署方式

公网部署建议：

```ini
[后台管理]
ADMIN_API_TOKEN = 你的强密码
后台监听地址 = 127.0.0.1
后台监听端口 = 8000
```

然后通过 Nginx 反向代理，并开启 HTTPS。

---

## 四、Linux 部署

以下以 Ubuntu/Debian 为例。

### 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nodejs npm ffmpeg
```

检查版本：

```bash
python3 --version
node --version
npm --version
ffmpeg -version
```

### 2. 拉取项目

示例部署到 `/opt/titok2youtube`：

```bash
cd /opt
sudo git clone <你的仓库地址> titok2youtube
sudo chown -R $USER:$USER /opt/titok2youtube
cd /opt/titok2youtube
```

如果你是直接上传项目压缩包，解压到：

```text
/opt/titok2youtube
```

即可。

### 3. 创建 Python 虚拟环境

```bash
cd /opt/titok2youtube
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. 安装前端依赖并构建

```bash
npm --prefix frontend install
npm --prefix frontend run build
```

构建成功后会生成：

```text
frontend/dist/
```

后端会自动托管这个目录，不需要单独启动前端服务。

### 5. 修改配置

编辑：

```bash
nano config/config.ini
```

推荐公网反代配置：

```ini
[后台管理]
ADMIN_API_TOKEN = 换成你的强密码
后台监听地址 = 127.0.0.1
后台监听端口 = 8000
```

如果不使用 Nginx，直接暴露端口：

```ini
[后台管理]
ADMIN_API_TOKEN = 换成你的强密码
后台监听地址 = 0.0.0.0
后台监听端口 = 8000
```

### 6. 手动启动测试

```bash
source .venv/bin/activate
python -m server
```

访问：

```text
http://服务器IP:8000
```

健康检查：

```text
http://服务器IP:8000/health
```

如果配置为 `127.0.0.1`，可以在服务器上测试：

```bash
curl http://127.0.0.1:8000/health
```

### 7. systemd 后台运行

创建服务文件：

```bash
sudo nano /etc/systemd/system/titok2youtube.service
```

写入：

```ini
[Unit]
Description=titok2youtube admin service
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/titok2youtube
ExecStart=/opt/titok2youtube/.venv/bin/python -m server
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

注意：现在 Token、Host、Port 都在 `config/config.ini`，这里不需要写环境变量。

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now titok2youtube
```

查看状态：

```bash
sudo systemctl status titok2youtube
```

查看日志：

```bash
journalctl -u titok2youtube -f
```

重启：

```bash
sudo systemctl restart titok2youtube
```

停止：

```bash
sudo systemctl stop titok2youtube
```

---

## 五、Linux + Nginx 反向代理

公网部署推荐使用 Nginx + HTTPS。

### 1. 安装 Nginx

```bash
sudo apt install -y nginx
```

### 2. 修改 config.ini

建议后端只监听本机：

```ini
[后台管理]
ADMIN_API_TOKEN = 换成你的强密码
后台监听地址 = 127.0.0.1
后台监听端口 = 8000
```

### 3. 新建 Nginx 配置

```bash
sudo nano /etc/nginx/sites-available/titok2youtube
```

写入：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 500m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/titok2youtube /etc/nginx/sites-enabled/titok2youtube
sudo nginx -t
sudo systemctl reload nginx
```

访问：

```text
http://your-domain.com
```

### 4. 配置 HTTPS

安装 Certbot：

```bash
sudo apt install -y certbot python3-certbot-nginx
```

申请证书：

```bash
sudo certbot --nginx -d your-domain.com
```

完成后访问：

```text
https://your-domain.com
```

---

## 六、Windows 部署

以下以 Windows 10/11 为例。

### 1. 安装依赖

需要安装：

```text
Python 3.11+
Node.js 20+
Git
ffmpeg
```

建议安装方式：

- Python：从 Python 官网安装，并勾选 `Add Python to PATH`
- Node.js：安装 LTS 版本
- Git：安装 Git for Windows
- ffmpeg：下载 Windows 版本并加入系统 PATH，或放到项目可识别路径

检查：

```powershell
python --version
node --version
npm --version
git --version
ffmpeg -version
```

### 2. 拉取项目

```powershell
cd D:\
git clone <你的仓库地址> titok2youtube
cd D:\titok2youtube
```

如果是手动复制项目，确保目录类似：

```text
D:\titok2youtube
```

### 3. 创建 Python 虚拟环境

PowerShell：

```powershell
cd D:\titok2youtube
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果 PowerShell 禁止执行脚本，先运行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后重新激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

CMD：

```cmd
cd /d D:\titok2youtube
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

### 4. 安装前端依赖并构建

PowerShell 或 CMD：

```powershell
npm --prefix frontend install
npm --prefix frontend run build
```

构建成功后会生成：

```text
frontend\dist
```

### 5. 修改 config.ini

编辑：

```text
D:\titok2youtube\config\config.ini
```

本机访问：

```ini
[后台管理]
ADMIN_API_TOKEN = 换成你的强密码
后台监听地址 = 127.0.0.1
后台监听端口 = 8000
```

局域网访问：

```ini
[后台管理]
ADMIN_API_TOKEN = 换成你的强密码
后台监听地址 = 0.0.0.0
后台监听端口 = 8000
```

### 6. 手动启动

PowerShell：

```powershell
cd D:\titok2youtube
.\.venv\Scripts\Activate.ps1
python -m server
```

访问：

```text
http://127.0.0.1:8000
```

如果监听 `0.0.0.0`，局域网其他机器访问：

```text
http://你的Windows机器IP:8000
```

### 7. Windows 防火墙放行

如果局域网访问不了，需要放行端口。

PowerShell 管理员模式：

```powershell
New-NetFirewallRule `
  -DisplayName "titok2youtube 8000" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8000 `
  -Action Allow
```

### 8. Windows 后台运行方式

#### 方式 A：任务计划程序

1. 打开“任务计划程序”
2. 创建基本任务
3. 触发器选择“计算机启动时”或“登录时”
4. 操作选择“启动程序”
5. 程序填写：

```text
D:\titok2youtube\.venv\Scripts\python.exe
```

参数填写：

```text
-m server
```

起始于填写：

```text
D:\titok2youtube
```

#### 方式 B：使用 NSSM 注册为 Windows 服务

下载 NSSM 后：

```powershell
nssm install titok2youtube
```

配置：

```text
Path:
D:\titok2youtube\.venv\Scripts\python.exe

Arguments:
-m server

Startup directory:
D:\titok2youtube
```

启动服务：

```powershell
nssm start titok2youtube
```

停止服务：

```powershell
nssm stop titok2youtube
```

删除服务：

```powershell
nssm remove titok2youtube confirm
```

---

## 七、更新部署

### Linux 更新

```bash
cd /opt/titok2youtube
git pull

source .venv/bin/activate
pip install -r requirements.txt

npm --prefix frontend install
npm --prefix frontend run build

sudo systemctl restart titok2youtube
```

### Windows 更新

PowerShell：

```powershell
cd D:\titok2youtube
git pull

.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

npm --prefix frontend install
npm --prefix frontend run build
```

如果是手动启动，重启命令：

```powershell
python -m server
```

如果是 NSSM 服务：

```powershell
nssm restart titok2youtube
```

---

## 八、备份与迁移

部署前、更新前建议备份：

```text
config/config.ini
config/URL_config.ini
config/admin.db
config/youtube_client_secret.json
config/youtube_token.json
config/youtube_upload_state.json
downloads/
```

Linux 示例：

```bash
tar -czf titok2youtube-backup-$(date +%F).tar.gz \
  config/config.ini \
  config/URL_config.ini \
  config/admin.db \
  config/youtube_client_secret.json \
  config/youtube_token.json \
  config/youtube_upload_state.json \
  downloads
```

Windows 可以直接复制这些目录和文件到备份目录。

---

## 九、常见问题

### 1. 页面能打开，但操作提示 Token 错误

检查：

```ini
[后台管理]
ADMIN_API_TOKEN = 你的强密码
```

页面右上角或登录位置填写的 Token 必须和这里一致。

### 2. 外部机器访问不了

检查三点：

1. `config.ini` 是否监听 `0.0.0.0`

```ini
后台监听地址 = 0.0.0.0
```

2. 云服务器安全组是否放行 `8000`
3. 系统防火墙是否放行 `8000`

Linux UFW 示例：

```bash
sudo ufw allow 8000/tcp
```

Windows 防火墙见上文。

### 3. 前端页面 404 或没有新 UI

重新构建前端：

```bash
npm --prefix frontend run build
```

确认存在：

```text
frontend/dist/index.html
```

### 4. ffmpeg 相关功能失败

检查：

```bash
ffmpeg -version
```

如果命令不存在，需要安装 ffmpeg 并加入 PATH。

### 5. YouTube 上传失败

检查：

```text
config/youtube_client_secret.json
config/youtube_token.json
```

并确认 `config/config.ini` 中：

```ini
[YouTube上传]
youtube客户端密钥文件路径 = config/youtube_client_secret.json
youtube令牌文件路径 = config/youtube_token.json
```

### 6. 端口被占用

Linux：

```bash
sudo lsof -i :8000
```

Windows：

```powershell
netstat -ano | findstr :8000
```

可以改：

```ini
[后台管理]
后台监听端口 = 8010
```

然后重启服务。

---

## 十、推荐生产配置

公网部署推荐：

```ini
[后台管理]
ADMIN_API_TOKEN = 一个足够长的随机密码
后台监听地址 = 127.0.0.1
后台监听端口 = 8000
```

然后：

```text
Nginx / Caddy / IIS 反向代理
HTTPS
防火墙只开放 80/443
不要直接暴露 8000
```

最小启动命令：

```bash
python -m server
```

生产环境推荐由 systemd 或 NSSM 托管。
