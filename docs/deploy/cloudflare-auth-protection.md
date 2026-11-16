# FigPrism：用自有 Cloudflare 账号提供 Turnstile 认证保护

网站：`https://figprism.ai4any.com`。应用继续部署在现有服务器。

## 当前部署状态

- **Turnstile 已在用户自己的 Cloudflare 账号创建并启用**，即管理 `zhcanfly.com` 的账号。
- Widget 名称：`FigPrism login and registration`。
- 允许的 hostname：`figprism.ai4any.com`；模式：`Managed`；pre-clearance：`no_clearance`。
- 登录与注册均启用服务端 Siteverify 校验、hostname/action 校验和 token 防重放。
- Site Key 与 Secret Key 保存在服务器 `config/local.yaml`，该文件被 Git 忽略。
- 应用端每 IP、每账号每分钟 10 次限流继续生效，计数跨进程共享。
- 源站已配置可信 Cloudflare 网段与真实客户端 IP；不信任任意来源伪造的转发头。
- **没有修改 `ai4any.com` 的 DNS 或 WAF**。本账号不具备该 zone 的管理权。

## 1. 为什么无需管理 ai4any.com 的 Cloudflare 账号

Turnstile 是独立的人机验证服务，其所属账号不必与网站域名的管理账号相同。
可以在自己账号的 Turnstile 中手动添加网站 hostname，即使它不在该账号的 DNS zone 列表中。
网站拥有者负责将公钥放入页面、将私钥放入服务器，并验证用户提交的 token。

因此，本项目的分工是：

| 资源 | 管理位置 |
| --- | --- |
| Turnstile widget 与密钥 | 用户自己管理 zhcanfly.com 的 Cloudflare 账号 |
| 登录、注册、限流与 token 校验 | FigPrism 本地服务器 |
| figprism.ai4any.com 的解析记录 | 现有可操作的 DNS 记录；无需为 Turnstile 修改 |
| ai4any.com 的 WAF / 边缘限流 | 另一个账号；本次未配置，也不是 Turnstile 的前提 |

Turnstile 不要求网站经过 Cloudflare 代理。WAF 边缘规则则需要对应 zone 的权限和代理流量。

## 2. 查看、重建或轮换 widget

登录自己的 Cloudflare 账号，进入 **Turnstile**，找到上述名称的现有 widget。
日常维护优先使用现有组件，不要重复创建。

重建时选择：

| 配置项 | 值 |
| --- | --- |
| 名称 | `FigPrism login and registration` |
| Hostname | `figprism.ai4any.com`（手动输入，不必在已有 zone 列表中选择） |
| Widget mode | `Managed` |
| Pre-clearance | 不启用 |

不要因为账号管理的是 zhcanfly.com 就把 hostname 填成 zhcanfly.com。
这里必须填写浏览器实际展示登录页的 hostname，不带协议、端口或路径。
不添加 localhost 或不属于本项目的站点。兼容域名仅做跳转时无需加入。

轮换 Secret Key 后，按下一节更新服务器配置并重启后端。
不要把 Secret Key、API Token 写进 Git、PR、聊天消息、命令行参数或截图。

## 3. 服务器密钥配置与生效

目录：`/root/code/FigPrism`。
私密配置：`config/local.yaml`，仅修改其中的 turnstile 段：

```yaml
turnstile:
  enabled: true
  site_key: "当前 widget 的 Site Key"
  secret_key: "同一 widget 的 Secret Key"
  allowed_hostnames:
    - figprism.ai4any.com
```

保留其他配置，尤其是**根级 secret_key（会话签名密钥）**、WebDAV、模型配置和现有 CSRF Origin。
本项目保留旧域名 Origin 映射；allowed_hostnames 仍填浏览器地址栏里的实际域名。

配置在后端进程内缓存。确认没有该 backend 承接的网页入库任务后执行：

```bash
cd /root/code/FigPrism
docker compose restart backend
curl -fsS http://127.0.0.1:8101/api/health
curl -fsS http://127.0.0.1:8101/api/auth/challenge-config
```

最后一个接口应返回 enabled=true 与公开 Site Key，不能包含 Secret Key。
仅修改密钥不需要重建前端。`docker compose up -d` 本身不保证重启未变化的容器。
保留正在独立进程中执行的论文批次，不因更新验证配置重启其他服务。

## 4. 已有防爆破保护

- 登录/注册请求先经过服务端每 IP 每分钟 10 次限制。
- 通过人机验证后，还受每账号每分钟 10 次限制。
- 开启 Turnstile 后，缺少 token、token 过期/已使用、域名或 action 不匹配均拒绝。
- 人机验证服务异常时返回错误，不静默放行；用户可重新验证后重试。
- 邀请码/链接的次数消费与注册在同一个数据库事务中完成；删除邀请立即阻止后续注册。

Nginx 只信任 Cloudflare 官方网段的 CF-Connecting-IP，并用校验后的单一地址覆盖 X-Forwarded-For。
配置文件：`deploy/cloudflare-realip.conf`；现有源站已部署，**不要重复添加 include**。
重建服务器时核对 [IPv4 网段](https://www.cloudflare.com/ips-v4) 和 [IPv6 网段](https://www.cloudflare.com/ips-v6)，执行 nginx -t 后再 reload。

## 5. WAF 边缘限流：当前不依赖

目前没有 ai4any.com 的 zone 管理权，无法在自己的账号中给它设置 WAF。
这不影响上面的 Turnstile 和应用限流，无需为此迁移域名或修改 CNAME。

若以后获得该 zone 的管理权限，可再给登录/注册接口增加边缘限流。
套餐字段能力不同：Free 通常只能按 Path 匹配，Pro 可加 Host，Business/Enterprise 可加 Method。
不能为了绕过套餐限制直接删除 Host 条件，把规则意外应用到同 zone 的其他站点。
若将来迁移到自己控制的 fig.zhcanfly.com，可在自己的 zone 中管理这些规则；这不是本次部署方案。

## 6. 验收与故障排查

1. 用真实浏览器打开登录弹窗和“邀请码注册”，确认出现验证组件。
2. 完成验证后登录/注册成功；密码错误后能重新验证并重试。
3. 不带 token 的认证请求被拒绝，不能绕过页面直接调用接口。
4. token 重复使用、错误 hostname/action 被拒绝；私有接口仍返回 private,no-store。
5. 查看自己账号下 Turnstile Analytics 的服务端校验记录。

常见问题：

- Widget 域名错误：检查允许的 hostname 与浏览器地址栏。
- 前端通过但后端失败：核对密钥配对、hostname/action、token 有效期及重复使用。
- 自动化浏览器被拦截：这可能是正常的反自动化判断；用真实浏览器做人工验收。不要在生产注入测试 token 或关闭校验来让测试通过。
- 网络或密钥故障导致无法登录：仅站点管理员在服务器临时将 turnstile.enabled 改为 false 并重启 backend；保留应用限流，修复后重新启用。

隔离测试使用测试桩。Cloudflare 测试密钥的响应没有真实 action，不能代替生产密钥验证完整链路。

## 官方参考

- [Turnstile 独立部署与前后端流程](https://developers.cloudflare.com/turnstile/get-started/)
- [添加独立 hostname](https://developers.cloudflare.com/turnstile/additional-configuration/hostname-management/)
- [服务端 Siteverify 校验](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/)
- [WAF 限流套餐能力](https://developers.cloudflare.com/learning-paths/application-security/rate-limiting/features/)

## 本次启用验证记录（2026-11-16）

已核对 widget 所属账号、hostname、Managed 模式及 no_clearance 配置。
后端配置接口 enabled=true；缺少 token 的登录/注册请求以及伪造 token 都被拒绝。
认证防护专项 9 项测试通过，线上真实组件正常显示人工勾选框。
自动化浏览器停在真人确认步骤，未代替用户勾选；实际通过挑战后的登录请用自己的浏览器完成一次验收。
