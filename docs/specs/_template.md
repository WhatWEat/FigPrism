# 00X — <功能简短标题>

- **Status**: `Draft` <!-- Draft | In Progress | Merged -->
- **Created**: `YYYY-MM-DD`
- **Target PRD Sections**: `§3.2 / §7.X / §9.1 / §9.2`（填写验收后需同步更新的 `docs/PRD.md` 章节）

> **篇幅约束**：本单仅描述相对于 `docs/PRD.md` 的**本次增量**，控制在 **50 ~ 150 行**以内；全局暖宣纸配色 Token、三级 RBAC 权限、WebDAV 版本化存储与并发约束默认继承 `AGENTS.md` 与 `docs/PRD.md`，无需重复抄写。

---

## 1. 背景与痛点 (Why)
- 当前行为/痛点：（1~2 句话说明现状缺口）
- 本次目标：（1~2 句话说明交付后的用户价值）

## 2. 范围边界 (Scope)
- **In Scope（本次必做）**：
  - [ ] 增量点 1
  - [ ] 增量点 2
- **Out of Scope（本次不做）**：
  - 明确排除项（防止开发范围蔓延）

## 3. 交互与视觉增量 (UI / UX Delta)
- **入口位置**：（如：`Figure Inspector` 右舱模块 3 下方 / 顶栏搜索框语法扩展）
- **交互状态与反馈**：（正常态、加载态、空状态、快捷键、移动端适配）
- **权限可见性**：`Guest` / `User` / `Admin` 各自的行为差异
- **视觉约束**：严格复用 `var(--bg-surface)`、`var(--bg-subtle)` 与 `#181615 / #36322E / #57524B` 浓墨文字体系，新增展示图保持 `.fig-paper-blend`。

## 4. 数据、接口与命令增量 (Schema / API / CLI Delta)
- **SQLite 表结构变更**（若无写“无”）：
  - 新增表 / 字段及迁移兼容方式（`init_db()` 幂等演进）
- **HTTP API 契约**（若无写“无”）：
  - `METHOD /api/...`：请求参数、响应 JSON、缓存头（`private, no-store` 或版本化缓存）与权限要求
- **后台任务 / CLI / 存储变更**（若无写“无”）：
  - 是否涉及分阶段并发锁、WebDAV 持久化顺序或新增 `figprism` 子命令

## 5. 验收与回归清单 (Acceptance Criteria)
- [ ] 功能验收项 1
- [ ] 功能验收项 2（含权限越权拦截、异常兜底）
- [ ] `.venv/bin/pytest backend/tests -q` 通过（附新增回归单测）
- [ ] `npm run typecheck --prefix frontend && npm run build --prefix frontend` 通过
- [ ] （若改前端核心流）Playwright E2E 回归通过

---

## 附：日常加新功能 3 步闭环指令速查（给 Codex 下发时直接复制）

1. **立项写小单**：复制本模板为 `docs/specs/00X-xxx.md`，只写本次增量（或口述点子让 Codex 先按本模板生成 `Status: Draft` 小单供确认）。
2. **精准喂上下文实现**：
   > “请先阅读 `AGENTS.md`，参考 `docs/PRD.md` 的全局暖宣纸配色 Token、RBAC 权限与存储并发架构，**仅实现 `docs/specs/00X-xxx.md` 中定义的增量功能**，并补齐对应测试。”
3. **验收后顺手合入主 PRD**：
   > “`00X` 号功能已验收通过，请把最终落地的表结构、API 和交互规则同步合入 `docs/PRD.md` 对应章节（删掉已被替代的旧描述），并在 `docs/specs/00X-xxx.md` 顶部标上 `Status: Merged`。”
