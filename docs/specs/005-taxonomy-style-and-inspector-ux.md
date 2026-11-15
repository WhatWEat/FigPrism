# 005 — 方法架构图与数据实验图分类解耦、方法画风拆解与检视器交互升级

- **Status**: `Merged`
- **Created**: `2026-11-14`
- **Merged**: `2026-11-14`
- **Source**: 用户提交 `Spec 002` + 检视器拖拽缩放/同文滑动与页面微交互优化需求
- **Target PRD Sections**: `§2 / §3.2 / §7.1 / §9.1 / §9.2 / §9.3`

---

## 1. 背景与目标
1. **彻底隔离「方法架构图」与「数据实验图」二级筛选面板**：消除顶栏切换大类时底部混排子类型标签的问题，切换大类时自动清理跨大类互斥筛选参数（含前端 Store 与 URL Query）。
2. **修复顶栏一级 Tab 计数徽章错位**：后端在通用过滤后、大类与子类过滤前独立统计 `tab_counts`（`all` / `method` / `data_chart`），前端固定渲染在三个一级 Tab 旁。
3. **新增方法图三维审美标签（画风 × 骨架 × 巧思）与实验图排版形态标签**：独立存储 `vision_judge_system.md` 与 `vision_judge_schema.json`，支持入库判图与 `figprism retag-taxonomy` 免重切存量回填。
4. **修复检视器画布缩放/拖拽与底部同文滑动体验，并微调页面交互质感**：保持现有整体框架与暖宣纸配色不变，让大图自适应窗口、支持滚轮缩放与按住拖拽平移，并为底部同文图表条增加拖拽滑动、左右翻页按钮与分类快筛。

## 2. 范围边界
- **In Scope**：
  - [x] SQLite `figures` 幂等扩展 `macro_category`、`sub_type`、`primary_style`、`secondary_style`、`layout_topology`、`craft_badges_json`、`chart_layout`、`style_confidence`、`style_reason`、`taxonomy_locked` 及 3 个复合索引，兼容存量 `archetype` 自动映射。
  - [x] 新增 `backend/prompts/vision_judge_system.md` 与 `backend/prompts/vision_judge_schema.json`，接入 `vision.py` 与 `PATCH /api/figures/{id}`（人工修改置 `taxonomy_locked = 1`）。
  - [x] 扩展 `GET /api/figures/feed` 与 `GET /api/papers/{pid}/figures` 支持强隔离参数校验并返回 `tab_counts`。
  - [x] 新增 `figprism retag-taxonomy --scope all --concurrency 8 --vision-driver openai_mini` 免重切并发补标命令。
  - [x] 前端实现一级 Tab 独立计数、跨 Tab 互斥状态重置、三视图专属筛选面板（`method` 三行含巧思多选下拉、`data_chart` 两行、`all` 快捷分流条）及暖纸胶囊层次微美化。
  - [x] 检视器画布支持真实适应窗口尺寸、光标中心滚轮/双击缩放、放大后按住拖拽平移；底部同文条支持鼠标拖拽滑动、左右箭头翻页与同文快速筛选。
- **Out of Scope（禁改边界）**：
  - 不修改 PDF 切图定位与 `Vector-Ink Snap` 几何计算逻辑；
  - 不修改 WebDAV 文件路径结构与版本缓存 Hash 策略；
  - 不修改 OKLCH 科研配色聚类算法及账号收藏夹核心逻辑。

## 3. 数据与接口增量摘要
- **SQLite `figures` 新增列**：`macro_category`, `sub_type`, `primary_style`, `secondary_style`, `layout_topology`, `craft_badges_json`, `chart_layout`, `style_confidence`, `style_reason`, `taxonomy_locked`。
- **API `GET /api/figures/feed`**：
  - 支持通用参数（兼容 `domain/domains`, `venue/venues`, `layout/paper_layout`, `span/span_type`, `color/color_bucket`, `show_cases/include_cases`, `sub_tags`, `q`, `honors`）；
  - 支持 `macro_category = all | method | data_chart`（兼容 `view`）；
  - `method` 专属：`method_type`, `visual_style`, `topology`, `craft`（非 `method` 时后端忽略）；
  - `data_chart` 专属：`chart_type`, `chart_layout`（非 `data_chart` 时后端忽略）；
  - 响应新增 `tab_counts: { all: {papers, figures}, method: {papers, figures}, data_chart: {papers, figures} }`。
- **CLI**：`figprism retag-taxonomy --scope all --concurrency 8 --vision-driver openai_mini`。

## 4. 验收清单
- [x] 一级 Tab 各自固定显示准确独立计数，切换 Tab 时跨类子筛选参数与 URL Query 自动清空。
- [x] `method` / `data_chart` / `all` 面板严格隔离，无跨类标签混排；后端忽略跨类残留参数。
- [x] 人工修改分类后 `taxonomy_locked=1`，`retag-taxonomy` 自动跳过锁定记录并成功回填线上未锁定存量图表（`235/235` 全量回填成功，`failed=0`）。
- [x] 检视器默认完整适应视口，滚轮/双击/按钮缩放围绕锚点平滑变化，放大后可按住鼠标拖拽平移，且离屏吸管取色精度完全不受影响；同文导航支持拖拽、左右箭头翻页与方法/实验快筛。
- [x] `pytest`（45 passed）、`npm run typecheck`、`npm run build` 及线上 Playwright E2E（10/10 passed）全部通过。

## 5. 最终落地记录
- 针对线上推理型视觉小模型（带 `reasoning_content` 输出）将 `vision.py` 单次 `max_tokens` 提升至 `4096`，并在用户消息中显式锁定全部必填 JSON 字段名与 Markdown 代码围栏剥离逻辑，确保 `json_schema` 与 `json_object` 上游网关均 100% 稳定返回完整分类、画风与置信度字段。
- 所有增量表结构、API 契约、CLI 命令与 UI 交互规则已同步合入 `docs/PRD.md`。
