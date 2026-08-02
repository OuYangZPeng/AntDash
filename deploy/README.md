# AntDash 服务端部署脚本（deploy/）

一键把整个工程的后端（FastAPI）部署到腾讯云轻量服务器（海外节点，免备案）。

## 包含文件

| 文件 | 作用 |
|---|---|
| `setup_server.sh` | 主脚本：装依赖 → 克隆 GitHub 代码 → 建 venv → 配 systemd → 配 Nginx → 申请 HTTPS |
| `antdash.service.template` | systemd unit 模板（变量占位，由脚本注入目录/端口）|
| `nginx-antdash.conf.template` | Nginx 反代模板（含 WebSocket 升级头）|

## 服务器上执行

```bash
# 1. SSH 登录海外轻量服务器
ssh root@<你的服务器公网IP>

# 2. 一键部署（域名作为参数）
bash <(curl -sSL https://raw.githubusercontent.com/OuYangZPeng/AntDash/main/deploy/setup_server.sh) \
     --domain www.antdash.com
```

或先把脚本传上去再跑：

```bash
scp deploy/setup_server.sh root@<IP>:/root/
ssh root@<IP> 'bash /root/setup_server.sh --domain www.antdash.com'
```

## 前置条件

1. **DNS 解析**：域名 `www.antdash.com` 的 A 记录指向服务器公网 IP（certbot 申请证书时会校验）。
2. **防火墙**：腾讯云控制台放行 TCP 22 / 80 / 443（8080 无需对外）。
3. 服务器系统为 Ubuntu 22.04（apt 系）。

## 可选参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--domain` | （必填）| 你的域名，如 `www.antdash.com` |
| `--dir` | `/opt/AntDash` | 代码克隆目录 |
| `--port` | `8080` | 后端监听端口 |
| `--ssh-repo` | 关 | 默认用 HTTPS 克隆（无需服务器配 GitHub SSH key）|

## 验证

- 后端本机：`curl http://127.0.0.1:8080/docs`
- 域名 HTTPS：浏览器打开 `https://www.antdash.com/docs`
- App：安装已构建的 `app-release.apk`，登录 `13800000001` / 任意验证码

## 常用运维命令

```bash
systemctl status antdash        # 查看后端状态
journalctl -u antdash -f        # 查看后端日志
systemctl restart antdash       # 重启后端
certbot renew --dry-run         # 测试证书自动续期
```
