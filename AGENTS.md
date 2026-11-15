# FigPrism — Codex / Agent 全局行为守则 (AGENTS.md)

> **强制前置约束**：每次在 FigPrism 仓库中规划、修改代码或维护文档前，必须先阅读本文件与 `docs/PRD.md` 的相关章节。子目录 `frontend/AGENTS.md` 为 Next.js 框架自动生成的版本规则，必须保留原样，不得删除。

---

## 1. 文档真相源与 3 步增量开发闭环

仓库采用 **「唯一主 PRD + 编号增量规格单」** 架构，杜绝多份文档冲突或手工维护长文档：

```text
FigPrism/
├── AGENTS.md                        # 全局工程约束与协作守则（每次改代码前必读）
└── docs/
    ├── PRD.md                       # 唯一全局真相源（始终代表系统“当前已落地最新状态”）
    ├── implementation.md            # 架构实现、安全边界、并发与上线验收记录
    └── specs/                       # 历次迭代增量开发单（按三位编号递增，50~150 行）
        ├── 001-paper-deck-warm-ui.md  # [Status: Merged] 图组胶片归集与暖宣纸配色补丁
        └── _template.md               # 新增功能规格单模板与标准指令速查
```

### 日常迭代严格遵循以下 3 步：
1. **立项写小单（50~150 行）**：新增需求统一基于 `docs/specs/_template.md` 新建 `docs/specs/00X-<slug>.md`，顶部标注 `Status: Draft` 或 `Status: In Progress`，仅描述本次增量，**立项阶段不直接修改 `docs/PRD.md`**。
2. **精准按单实现**：开发时以 `docs/PRD.md` 作为全局基线（配色 Token、权限矩阵、存储与并发约束），**仅实现目标 `docs/specs/00X-*.md` 中明确声明的增量范围**；严禁顺手实现其他 `Draft` 规格单内容或擅自扩大改动面。
3. **验收后同步合入主 PRD（关键闭环）**：收到用户“验收通过 / 合入 PRD”指令后，必须同步执行：
   * 将最终实际落地的 **SQLite 表结构、API 契约、CLI 参数、UI/UX 规则** 原地更新进 `docs/PRD.md` 对应章节；
   * **直接删除 `docs/PRD.md` 中已被替代的旧描述**（严禁在主 PRD 末尾堆叠补丁段落，确保主 PRD 无内部矛盾）；
   * 将对应 `docs/specs/00X-*.md` 顶部状态更新为 `Status: Merged`，并简要记录最终落地微调项（如有）。

---

## 2. 视觉与前端全局铁律（护眼暖宣纸体系）

所有前端页面与新增组件必须严格服从 `docs/PRD.md` 第 3.1 节与 `frontend/src/app/globals.css` 中的语义变量：

1. **暖燕麦画布 + 象牙米白表面**：
   * 全局底层背景统一使用 `var(--bg-canvas)`（`#EDEAE4`），卡片/抽屉/弹窗统一使用 `var(--bg-surface)`（`#FAF8F5`），次级槽位/胶囊使用 `var(--bg-subtle)`（`#E3DFD7`）。
   * **严禁硬编码 `bg-white`**（避免高亮度眩光破坏全站纸感）。
2. **消灭发虚浅灰字**：
   * 视觉层级通过**字重、字号与底色块**区分，严禁使用 `text-gray-300/400/500`、`text-slate-300/400/500`、`text-zinc-400`、`text-neutral-400` 等低对比浅灰文字类。
   * 所有可读文本只允许使用三级浓墨暖黑：`--text-primary`（`#181615`，主标题/激活项）、`--text-secondary`（`#36322E`，正文/图注/未选中标签）、`--text-tertiary`（`#57524B`，全站可读辅助字最浅下限）；`--text-placeholder`（`#706A62`）仅限输入框占位符。
3. **固定纸感融合与原始像素取色保真**：
   * 图表装裱区固定使用 `--bg-figure-mat`（`#FAF8F5`），展示态科研图表 `<img>` 固定挂载 `.fig-paper-blend`（`mix-blend-mode: multiply; filter: contrast(1.02)`），**不提供纸感/纯白背景切换开关**。
   * 详情页放大镜吸管（Loupe Eyedropper）与色板导出**必须从离屏未混合原始 `<canvas>`（`getImageData`）或原始资产读取 RGB/HEX**，严禁采集混合后的屏幕暖色像素。
4. **Next.js 版本规范**：
   * 修改前端路由、服务端组件或构建配置前，先查阅 `frontend/node_modules/next/dist/docs/` 内与当前安装版本一致的官方文档。

---

## 3. 权限、安全与缓存隔离红线

1. **三级 RBAC 与私有空间归属**：
   * `Guest` 仅限公开浏览、检索、吸管取色、复制色板、下载矢量图与查看 TikZ；
   * `User` 独享私有灵感看板（`collections`）、双轨历史（`view_history` / `palette_history`）、在线加论文（`/api/ingest/*`）与切图纠错/标签修正；所有私有资源读写必须校验 `user_id` 归属；
   * `Admin` 独享 `/admin` 与 `/api/admin/*`（邀请码签发、用户启停、领域词库配置、同步/冷启动/重建与流水线监控）；
   * 默认关闭公开自由注册，`/api/auth/register` 必须校验未过期且未使用的一次性 `invite_code`。
2. **会话与防跨站伪造**：
   * 会话采用 `HttpOnly`、`SameSite=Lax`（生产开启 `Secure`）的签名 JWT Cookie（`figprism_session`）配合 SQLite `sessions (jti)` 服务端撤销校验；密码统一使用 `Argon2`。
   * 所有修改状态的浏览器写请求必须通过 `Origin` / `Sec-Fetch-Site` 同源校验。
3. **HTTP 缓存与流式头部契约**：
   * 私有与管理接口（`/api/auth/*`、`/api/me/*`、`/api/collections/*`、`/api/ingest/*`、`/api/jobs`、`/api/admin/*`）必须返回 `Cache-Control: private, no-store`。
   * 公开图表资产（`/api/assets/{thumb|hd|raw}/{id}.*?v={version_hash}`）必须校验 `version_hash`（旧版本或失配返回 `404`），命中时返回 `Cache-Control: public, max-age=31536000, immutable`。
   * SSE 流（`/api/stream/events`）必须返回 `Cache-Control: no-cache` 与 `X-Accel-Buffering: no`。
4. **外部输入与文件安全边界**：
   * 外网抓取严格限制在学术域名白名单内并逐跳校验重定向；
   * TeX 源码包仅在内存中限额解析（限制文件数与解压体积，拒绝路径穿越与符号链接），**严禁执行任何 TeX 编译命令**；
   * PDF 限制单文件 `≤ 50MB`、页数 `≤ 150`、光栅化上限 `24MP`；WebDAV 路径严格拒绝 `..` 穿越。

---

## 4. 存储、并发与运维不变量

1. **先持久资产、后发布索引**：新入库或重切生成的 WebP / PDF 资产必须**先成功写入远端 WebDAV（并同步本地 `thumb_mirror`）**，随后才允许写入/更新 SQLite `figures` 记录与推送 SSE 事件；重切必须刷新 `version_hash` 并异步更新论文级 `metadata.json`。
2. **跨进程共享并发预算**：Web 服务、CLI 与 `systemd` 定时任务通过数据目录内核文件锁共享阶段并发配额（`backend/figprism/concurrency.py`）；PyMuPDF 渲染与 `DocLayout-YOLO` ONNX 推理必须在短生命周期独立子进程（`backend/figprism/processing.py`）中执行，避免跨线程对象污染与内存常驻。
3. **敏感文件与运行态隔离**：严禁将 `config/local.yaml`、`config/*.txt`、`data/`（SQLite、缓存、QA 产物、模型权重）提交进 Git。注意账号、会话、私有看板与历史仅存于 SQLite，`rebuild-from-webdav` 只恢复公开论文与图表资产。

---

## 5. 交付前必跑验证清单

每次完成代码修改准备交付前，按改动范围运行以下检查并确保全部通过：

```bash
# 1. 后端单元与集成测试（权限、安全、并发、切图、配色、聚合分页）
.venv/bin/pytest backend/tests -q

# 2. 前端类型检查与生产构建
npm run typecheck --prefix frontend
npm run build --prefix frontend

# 3. 涉及前端交互 / Feed / 检视器 / 权限链路时的端到端回归
.venv/bin/python scripts/setup_e2e.py
npm run test:e2e --prefix frontend
```
