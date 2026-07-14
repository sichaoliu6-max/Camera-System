# 访客预约申请系统原型

本工程根据 `访客预约申请产品方案.md` 实现访客预约系统原型，包含微信小程序、网页端、后端 API 和 OA 审批流程。

## 存储模式

- 本机原型调试推荐使用 `VMS_STORAGE=json`，数据文件为 `data/vms-store.json`。
- 正式部署推荐使用 `VMS_STORAGE=mysql`，后端会连接 MySQL 并自动执行 `mysql_schema.sql` 中的幂等建表脚本。
- 已废除 SQL Server 存储，旧的 `sqlserver_schema.sql`、`pyodbc` 和 `VMS_SQLSERVER_*` 配置不再使用。

## 本地运行

1. 安装 Python 依赖：

```powershell
pip install -r .\requirements.txt
```

2. 使用本机原型配置：

项目根目录已提供 `.env.example`。复制为 `.env` 后可直接使用本地 JSON 存储：

```powershell
Copy-Item .\.env.example .\.env
```

关键配置：

```text
PORT=18088
VMS_STORAGE=json
```

3. 如需改用 MySQL，创建 MySQL 数据库和账号：

```sql
CREATE DATABASE vms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'vms_user'@'%' IDENTIFIED BY 'change_me';
GRANT ALL PRIVILEGES ON vms.* TO 'vms_user'@'%';
FLUSH PRIVILEGES;
```

4. MySQL 模式下配置环境变量或 `.env`：

```powershell
$env:PORT="18088"
$env:VMS_STORAGE="mysql"
$env:VMS_MYSQL_HOST="127.0.0.1"
$env:VMS_MYSQL_PORT="3306"
$env:VMS_MYSQL_DATABASE="vms"
$env:VMS_MYSQL_USER="vms_user"
$env:VMS_MYSQL_PASSWORD="change_me"
```

5. 启动服务：

```powershell
python .\server.py
```

打开网页端：

```text
http://127.0.0.1:18088/web/
```

MySQL 模式下，服务启动时会自动执行 `mysql_schema.sql` 中的幂等建表脚本。空库首次启动会自动写入一组基础员工和样例预约数据。

## 小程序配置

小程序源码位于 `miniprogram`。本机调试时 `miniprogram/app.js` 中的 `apiBase` 已配置为：

```js
apiBase: "http://127.0.0.1:18088"
```

部署前必须把 `apiBase` 改成正式 HTTPS 后端域名，例如：

```js
apiBase: "https://vms.example.com"
```

微信小程序正式环境必须使用 HTTPS 域名，不能使用 IP、内网地址或 `http://`。本地调试时可在微信开发者工具中开启“不校验合法域名”。

## 主要接口

- `POST /api/appointments`：提交预约并创建 OA 流程。
- `GET /api/appointments`：查询预约列表。
- `GET /api/appointments/{applicationNo}`：查询预约详情。
- `GET /api/appointments/{applicationNo}/visitors/{visitorId}/qr`：获取访客二维码 token。
- `GET /api/oa/tasks`：OA 待办。
- `POST /api/oa/tasks/{applicationNo}/action`：原型内置 OA 审批动作。
- `POST /api/oa/callback`：真实 OA 审批回传入口。
- `GET /api/guard/today`：门卫查询今日预约。
- `POST /api/guard/qr/verify`：门卫扫码校验。
- `POST /api/guard/checkin`：确认入厂。
- `POST /api/guard/checkout`：确认离厂并失效二维码。
- `GET /api/admin/export`：导出 CSV 报表。

## ECS 部署流程

以下以 Alibaba Cloud Linux / CentOS 系 ECS 为例。推荐架构是：ECS 跑 Python 后端和 Nginx，MySQL 可以安装在 ECS 本机，也可以使用阿里云 RDS MySQL。正式生产更建议用 RDS MySQL。

### 1. 准备云资源

1. 购买 ECS，建议至少 `2 vCPU / 4 GB`，系统盘 40 GB 起。
2. 购买域名并完成备案。
3. 在域名 DNS 中添加 A 记录，例如 `vms.example.com` 指向 ECS 公网 IP。
4. ECS 安全组放行：
   - `22`：SSH 管理。
   - `80`：HTTP，用于证书签发和跳转。
   - `443`：HTTPS，网页端和小程序正式访问。
   - `18088` 不建议公网放行，只让 Nginx 反向代理到本机。
5. 如果用 RDS MySQL，在 RDS 白名单中加入 ECS 内网 IP。

### 2. 安装基础环境

```bash
sudo dnf update -y || sudo yum update -y
sudo dnf install -y python3 python3-pip python3-virtualenv nginx git || sudo yum install -y python3 python3-pip nginx git
python3 --version
```

如果使用 ECS 本机 MySQL：

```bash
sudo dnf install -y mysql-server || sudo yum install -y mysql-server
sudo systemctl enable --now mysqld
sudo mysql_secure_installation
```

### 3. 创建 MySQL 数据库

登录 MySQL：

```bash
mysql -uroot -p
```

执行：

```sql
CREATE DATABASE vms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'vms_user'@'%' IDENTIFIED BY '请替换成强密码';
GRANT ALL PRIVILEGES ON vms.* TO 'vms_user'@'%';
FLUSH PRIVILEGES;
```

如果 MySQL 和后端在同一台 ECS，也可以把账号限制为：

```sql
CREATE USER 'vms_user'@'127.0.0.1' IDENTIFIED BY '请替换成强密码';
GRANT ALL PRIVILEGES ON vms.* TO 'vms_user'@'127.0.0.1';
FLUSH PRIVILEGES;
```

### 4. 上传代码

在 ECS 上创建目录：

```bash
sudo mkdir -p /opt/vms
sudo chown -R $USER:$USER /opt/vms
```

把本机 `C:\Users\Administrator\Documents\VMS` 上传到 `/opt/vms`。可用 Git、SCP、宝塔面板或压缩包上传。上传后确认：

```bash
cd /opt/vms
ls
```

应能看到 `server.py`、`web/`、`miniprogram/`、`mysql_schema.sql`、`requirements.txt`。

### 5. 创建 Python 虚拟环境

```bash
cd /opt/vms
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 6. 配置后端环境变量

创建 `/opt/vms/.env`：

```bash
cat > /opt/vms/.env <<'EOF'
PORT=18088
VMS_MYSQL_HOST=127.0.0.1
VMS_MYSQL_PORT=3306
VMS_MYSQL_DATABASE=vms
VMS_MYSQL_USER=vms_user
VMS_MYSQL_PASSWORD=请替换成强密码
VMS_MYSQL_CHARSET=utf8mb4
EOF
```

如果使用 RDS MySQL，把 `VMS_MYSQL_HOST` 改成 RDS 内网地址。

### 7. 创建 systemd 服务

创建 `/etc/systemd/system/vms.service`：

```bash
sudo tee /etc/systemd/system/vms.service > /dev/null <<'EOF'
[Unit]
Description=VMS Visitor Management Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/vms
EnvironmentFile=/opt/vms/.env
ExecStart=/opt/vms/.venv/bin/python /opt/vms/server.py
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
EOF
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vms
sudo systemctl status vms
```

检查接口：

```bash
curl http://127.0.0.1:18088/api/config
```

### 8. 配置 Nginx 反向代理

创建 `/etc/nginx/conf.d/vms.conf`：

```nginx
server {
    listen 80;
    server_name vms.example.com;

    location / {
        proxy_pass http://127.0.0.1:18088;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

检查并启动：

```bash
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

此时网页端地址是：

```text
http://vms.example.com/web/
```

### 9. 配置 HTTPS

使用 Certbot 申请免费证书：

```bash
sudo dnf install -y certbot python3-certbot-nginx || sudo yum install -y certbot python3-certbot-nginx
sudo certbot --nginx -d vms.example.com
```

完成后访问：

```text
https://vms.example.com/web/
```

微信小程序正式环境必须配置 HTTPS 域名，所以这一步是必须的。

### 10. 部署小程序

1. 打开微信开发者工具。
2. 导入 [miniprogram](C:/Users/Administrator/Documents/VMS/miniprogram) 目录。
3. 修改 [miniprogram/app.js](C:/Users/Administrator/Documents/VMS/miniprogram/app.js:3)：

```js
apiBase: "https://vms.example.com"
```

4. 在微信公众平台小程序后台配置服务器域名：
   - 进入“开发管理”。
   - 进入“开发设置”。
   - 在“服务器域名”中添加 `request` 合法域名：`https://vms.example.com`。
5. 微信开发者工具中点击“上传”。
6. 到微信公众平台提交体验版或正式审核。

### 11. 上线检查

```bash
sudo systemctl status vms
sudo journalctl -u vms -n 100 --no-pager
curl https://vms.example.com/api/config
curl https://vms.example.com/web/
```

MySQL 检查：

```bash
mysql -uvms_user -p vms -e "SHOW TABLES;"
mysql -uvms_user -p vms -e "SELECT COUNT(*) FROM vms_appointment;"
```

### 12. 常见问题

- 小程序请求失败：检查 `apiBase` 是否为 HTTPS 域名，微信后台是否配置合法域名。
- 后端启动失败：先看 `journalctl -u vms -n 100 --no-pager`，多数是 MySQL 地址、账号、密码或数据库未创建。
- 网页打不开：检查安全组 80/443、Nginx 配置、域名解析。
- 数据库为空：首次启动后端会自动建表并写入基础数据；如果没有，说明后端未成功连接 MySQL。
- 生产环境不要开放 MySQL 3306 到公网；使用 RDS 白名单或 ECS 内网访问。
