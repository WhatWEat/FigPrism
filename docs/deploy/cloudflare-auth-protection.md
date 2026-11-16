# FigPrism：在 ai4any.com 所属 Cloudflare 账号配置认证保护

目标网站：`https://figprism.ai4any.com`。应用仍部署在现有服务器，不迁移到 Cloudflare。
本文可以直接交给管理 `ai4any.com` 的同事或 Agent 执行。

## 交付边界

仓库提供邀请码/链接的次数限制与删除、登录/注册 Turnstile 接入、服务端校验和限流。
**当前账号没有配置另一个账号的 Turnstile 或 WAF；生产 Turnstile 默认关闭。**
完成下面的密钥配置并重新部署后，才会启用生产人机验证。
不要把 Secret Key、API Token 写进 Git、PR、聊天消息或截图。

## 1. 创建 Turnstile Widget

在正确的 Cloudflare 账号进入 **Turnstile → Add widget**：

| 配置项 | 值 |
| --- | --- |
| 名称 | `FigPrism login and registration` |
| Hostname | `figprism.ai4any.com` |
| Widget mode | `Managed` |
| Pre-clearance | 不启用；本项目使用表单 token 的 Siteverify 校验 |

不添加 `localhost`、通配域名或其他项目域名。
如需支持兼容域名直接显示登录页，可另加 `fig.zhcanfly.com`；仅做跳转时不需要。
保存生成的 **Site Key** 与 **Secret Key**。Turnstile 不要求 DNS 必须代理，但下文 WAF 边缘限流要求代理。

## 2. 在本地服务器填入私密配置

仓库目录：`/root/code/FigPrism`。
编辑已被 Git 忽略的 `config/local.yaml`，**只增加/更新 turnstile 段，保留原有所有配置**：

```yaml
turnstile:
  enabled: true
  site_key: "填入 Site Key"
  secret_key: "填入 Secret Key"
  allowed_hostnames:
    - figprism.ai4any.com
```

`allowed_hostnames` 必须是浏览器实际访问的域名，不是 Docker 服务名，也不根据旧的内部 CSRF Origin 填写。
本项目当前有旧域名 Origin 映射；不要为此次配置修改 `secret_key`、现有会话签名密钥或 CSRF Origin。

先检查是否存在需要保留的入库任务，再部署：

```bash
cd /root/code/FigPrism
docker compose ps
# 如有该 backend 容器承接的网页入库任务，请等任务结束；不要强杀。
docker compose build backend frontend
docker compose up -d --no-deps backend frontend
```

后端配置有进程缓存，修改 local.yaml 后必须重新启动后端才会生效。
`GET /api/auth/challenge-config` 应返回 `enabled: true` 和公开 Site Key，**不得包含 Secret Key**。

## 3. 配置 Cloudflare 边缘限流

进入 `ai4any.com` → **Security / WAF → Rate limiting rules**（后台菜单名称可能调整）。
先检查现有规则，避免覆盖已有规则；免费套餐可能只有一个规则名额。
确认 `figprism` DNS 记录已启用代理；不要改 IP 或对其他子域启用新规则。

规则名：`FigPrism authentication requests`。
匹配表达式：

```text
(http.host eq "figprism.ai4any.com"
 and http.request.method eq "POST"
 and http.request.uri.path in {"/api/auth/login" "/api/auth/register"})
```

推荐设置：

- 按客户端 IP 计数。
- 每个 IP **10 秒内超过 10 次**匹配请求时阻止 **10 秒**，作为边缘突发流量保护。
- Action 使用 **Block**，不要给 JSON API 返回需要交互的整页 Managed Challenge。
- 如果套餐支持自定义响应，返回 HTTP `429` 与 JSON 提示；不支持时使用默认阻止响应即可。
- 不匹配 `/api/assets/*`、`/api/stream/*`、论文导入或普通页面浏览。

免费套餐的时间窗口、动作和规则数量有限；如当前后台不允许上述参数，依据该套餐可选项调整，并记录最终值。不要为了配置规则自动升级付费套餐。
应用端另有每 IP、每账号每分钟 10 次限制，边缘规则不是它的替代品。

## 4. 核对源站真实 IP

Nginx 应仅信任 Cloudflare 官方网段提供的 `CF-Connecting-IP`；任意客户端自带的这个头不可信。
仓库提供 `deploy/cloudflare-realip.conf`，仅在 FigPrism 的 server 块内 include。
正式启用前核对它与 Cloudflare 当前官方 IP 网段是否一致：

- https://www.cloudflare.com/ips-v4
- https://www.cloudflare.com/ips-v6

```bash
sudo install -m 644 deploy/cloudflare-realip.conf /etc/nginx/snippets/figprism-cloudflare-realip.conf
# 在 FigPrism HTTPS server 块增加：
# include /etc/nginx/snippets/figprism-cloudflare-realip.conf;
# /api/ 与 /api/stream/ 中转发的 X-Forwarded-For 应为 $remote_addr，
# 不拼接访客自行发送的 X-Forwarded-For。
sudo nginx -t
sudo systemctl reload nginx
```

不要对来自任意网段的请求直接信任 CF-Connecting-IP。
如额外收紧源站防火墙，只允许 Cloudflare 回源，须先检查其他站点、SSH 与运维访问；这不是本次默认自动执行的操作。

## 5. 验收

1. 未登录打开登录弹窗，出现 Turnstile 验证；“邀请码注册”模式也有验证。
2. 用真实浏览器完成验证，正常登录和邀请码注册成功。
3. 密码错误后可以重新验证并重试，过期 token 不可继续提交。
4. 向登录、注册 API 发不带 `turnstile_token` 的请求，应被拒绝；不应因前端按钮隐藏而放行。
5. 同一个 token 二次使用应被拒绝；后端还校验 token 的 hostname 与 `login` / `register` action。
6. 连续失败请求触发 429；正常看图和已登录会话不受影响。
7. 邀请码或邀请链接删除后不能再注册；已注册账号仍可登录。
8. 检查 `/api/auth/*`、`/api/admin/*` 继续返回 `Cache-Control: private, no-store`。
9. 观察 Cloudflare Turnstile Analytics 的服务端校验记录，以及 WAF 规则命中情况。

自动化测试请使用隔离环境与测试桩。Cloudflare 测试密钥的响应没有真实 action，不能用测试密钥代替生产密钥，也不要为测试在生产关闭 hostname/action 校验。

## 6. 故障处理

- Widget 报域名错误：检查允许的 hostname 与浏览器地址栏。
- 前端验证成功但后端失败：检查两把密钥是否来自同一个 widget、hostname/action 是否正确、token 是否过期或重复。
- Turnstile 网络不可达：服务端会拒绝认证并提示重试，不能静默绕过。
- 需要恢复登录时：仅管理员在服务器将 `turnstile.enabled` 改为 `false` 并重启 backend；保留应用限流，修复后重新启用。不要修改前端伪造通过。

参考官方文档：

- [Turnstile 服务端校验](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/)
- [Turnstile Widget 创建](https://developers.cloudflare.com/turnstile/get-started/widget-management/dashboard/)
- [Rate limiting rules](https://developers.cloudflare.com/waf/rate-limiting-rules/)
- [套餐与限流能力](https://developers.cloudflare.com/learning-paths/application-security/rate-limiting/features/)
