# 019 — 可删除的邀请码与登录注册防自动化保护

- **Status**: `In Progress`
- **Created**: `2026-11-16`
- **Target PRD Sections**: `§3.2 用户管理 / §4 认证 / 管理 API`

## 1. 用户需求

- 支持手动填写邀请码注册。
- 邀请码与邀请链接都可设置使用次数、删除失效。
- 登录与注册加入验证码和防爆破保护。
- 核对 Cloudflare 能力，使用 Turnstile 实现人机校验。

## 2. 邀请交互

- 管理员创建邀请时选择“邀请链接”或“邀请码”。
- 链接保持原有高熵随机 token，兼容已发出的链接。
- 邀请码采用 16 位无歧义大写随机字符，分组显示方便填写。
- 手填邀请码忽略字母大小写、空格和分组横线；链接 token 保持精确匹配。
- 两类邀请均默认 1 次、可设 1–1000 次，7 天有效。
- 展示类型、已用、上限、剩余次数与失效状态。
- 删除操作需在界面内确认，确认后立即禁止继续注册。
- 删除不影响已经注册的用户及其收藏。
- 登录弹窗增加“邀请码注册”入口及可编辑邀请码输入框。
- 从邀请链接打开时自动进入注册模式并预填邀请凭据。
- 删除后的邀请不在列表中显示，旧链接与旧码仍永久失效。

## 3. 邀请契约

- invite_codes 新增 kind（link/code，旧记录默认 link）。
- invite_codes 新增 deleted_at（可空），保留已消耗次数用于审计。
- POST /api/admin/invites 新增可选 kind，保留 max_uses。
- DELETE /api/admin/invites/{code} 撤销对应邀请。
- GET /api/admin/invites 排除已删除记录并返回 kind。
- 注册在原事务中验证删除状态及剩余额度，消耗次数仍原子化。
- 不开放面向访客的邀请码有效性探测接口。

## 4. Cloudflare Turnstile

- 登录、注册共用 managed 模式 widget，按操作设置 action。
- 后端必须调用 Siteverify，校验 success、hostname 与 action。
- token 有效期 5 分钟；本地保存已消耗 token 的摘要，阻止并发重放。
- 缺失、伪造、过期、重放或站点不符均拒绝；服务异常不静默放行。
- 失败后重置 widget，允许重试；切换模式或关闭弹窗清空 token。
- 站点公钥通过 GET /api/auth/challenge-config 下发，私钥仅保存在本地私密配置。
- 未配置的开发测试环境允许显式关闭；生产启用后不可由客户端关闭。
- 生产允许域名仅限 FigPrism 的当前与兼容域名。
- 提供测试密钥/模拟服务用于测试，不将测试密钥上线。

## 5. 防爆破与代理

- 保留每客户端登录/注册每分钟 10 次的限流，计数改为 SQLite 跨进程共享。
- 对用户名增加独立限流，防止更换 IP 集中撞同一账号。
- 计数键使用摘要，清理过期窗口，返回 429 与 Retry-After。
- Nginx 仅信任 Cloudflare 官方网段的 CF-Connecting-IP。
- 转发到应用的 X-Forwarded-For 使用经过校验的单一客户端地址。
- 不启用未经当前账户管理的域名 WAF 规则，不更改 DNS。

## 6. 配置与安全

- 新增 turnstile 配置：enabled、site_key、secret_key、allowed_hostnames。
- secret_key 不进入 Git、不下发客户端、不写日志。
- 所有私有管理与认证配置响应继续 private,no-store。
- 新增 auth_rate_limits 和 auth_challenge_uses 表，计数与摘要重启保留。
- 保护用户密码、会话与现有私有看板权限。
- 不修改论文处理、缓存分池或入库并发策略。

## 7. 验收与部署

- 两类邀请分别创建、复制、消费次数及删除；并发删除/注册边界正确。
- 邀请码输入规范化不改变旧链接 token 的大小写语义。
- 登录、注册模式切换与邀请链接预填正常。
- 校验成功/缺失/重放/错误 action/错误 hostname/外部失败路径。
- 验证限流共享、过期恢复、代理头可信边界。
- 后端测试、类型检查、生产构建与相关 E2E 通过。
- 生产配置后验证真实 widget；无法自动通过的人机挑战需明确交付验证限制。
- 分阶段提交并 push；不停止其他会话的论文入库任务。
- 用户验收后再更新主 PRD。

## 8. 验证与交付

- 后端 80 项测试通过，包含邀请码规范化、软删除、计数、验证失败、并发重放与限流持久化。
- 7 项相关页面回归通过；隔离环境实际手输邀请码注册、计数更新、删除失效通过。
- 类型检查、本地和 Docker 生产构建通过。
- 用户随后授权使用自有 Cloudflare 账号创建 Turnstile；widget 允许 hostname 为 figprism.ai4any.com，不修改另一账号的 DNS / WAF。
- 操作交接文档：docs/deploy/cloudflare-auth-protection.md。
- 生产 Turnstile 已配置真实密钥并启用；密钥仅在忽略的本地配置中，部署文档已改为自有账号方案。

### 2026-11-16 自有账号启用验证

- 已在管理 zhcanfly.com 的账号创建 Managed widget，允许 hostname 仅 figprism.ai4any.com，pre-clearance 为 no_clearance。
- 私密配置写入后只重启 backend；challenge-config 确认 enabled=true。
- Siteverify 可达且拒绝无效 token；线上登录/注册缺失 token 与伪造 token 均返回 403。
- 认证防护专项 9 项通过；真实组件正常显示人工勾选框，真人通过后的实际登录仍需用户浏览器完成。
- 未改变域名解析或另一账号 WAF，部署文档已去除必须由另一账号配置 Turnstile 的错误前提。
