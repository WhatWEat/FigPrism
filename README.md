<div align="center">

# FigPrism

### 以学术图表为一等公民的顶会科研绘图审美、构图拆解与配色灵感平台

**A Figure-First Research Gallery & Aesthetic Deconstruction Workspace for AI / ML Papers**

[![Live Site](https://img.shields.io/badge/Live_Demo-figprism.ai4any.com-3730a3?style=for-the-badge)](https://figprism.ai4any.com)
[![GitHub](https://img.shields.io/badge/GitHub-WhatWEat%2FFigPrism-181615?style=for-the-badge&logo=github)](https://github.com/WhatWEat/FigPrism)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-1f1d1a?style=flat-square&logo=nextdotjs)](https://nextjs.org/)
[![React 19](https://img.shields.io/badge/React-19-1f1d1a?style=flat-square&logo=react)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python_3.12-1f1d1a?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![SQLite FTS5](https://img.shields.io/badge/SQLite-WAL_%2B_FTS5-1f1d1a?style=flat-square&logo=sqlite)](https://www.sqlite.org/)

🌐 **在线体验**：[**https://figprism.ai4any.com**](https://figprism.ai4any.com) &nbsp;|&nbsp; 📖 **全局规格**：[docs/PRD.md](docs/PRD.md) &nbsp;|&nbsp; 🛠️ **架构文档**：[docs/implementation.md](docs/implementation.md)

</div>

---

写论文画图没灵感、配完色总觉得发脏、在几百页 PDF 里反复翻找高颜值架构图与 Scaling Curve？

**FigPrism** 是一个专为 AI / ML 研究者打造的**「以科研图表为一等公民（Figure-First）」**审美与检索平台：自动从 `arXiv`、`Hugging Face Daily Papers`、`OpenReview`、`DBLP` 与 `CVF Open Access` 收集顶会论文，抽取出**高保真矢量切片与 450 DPI 超清图表**，通过视觉大模型完成**方法架构画风 × 空间拓扑骨架 × 局部巧思**与**实验图表排版**结构化拆解，并在感知均匀的 **OKLab / OKLCH** 空间提取「浅色填充 + 同色相深色描边」成对科研配色，支持一键导出 `Matplotlib` / `LaTeX xcolor` / `CSS`。

> ✨ 无需登录即可直接浏览公开图库、三维精细筛选、像素级吸管取色、导出配色代码与下载矢量 PDF / TikZ 源码。
> 🤖 本项目全栈由 **Gemini Carbon（产品设计与增量 PRD）× Codex（代码实现、容器发布与端到端回归）** 双 Agent 闭环协作打造。

---

## ✨ 核心亮点 (Why FigPrism?)

### 1. 🎞️ 论文图组胶片流 (`Paper Deck`) + 三态浏览视图
- **按篇归集，不再被同篇散落大图刷屏**：默认以「论文图组卡」呈现每篇论文的 Hero 主视觉、顶会录用徽章（`ICLR / ICML / CVPR / NeurIPS / ACL / EMNLP` + `Oral / Spotlight`）、整篇去重总色板与图表清单。
- **胶片条零延迟悬停切图**：桌面端悬停底部缩略图胶片带，即时切换主图展示与单图专属色板；支持卡片内直接展开同文全图。
- **三态视图一键切换**：支持 **论文图组流 (`Deck`)**、**横排画册流 (`Swimlane`)** 与 **单图瀑布流 (`Flat`)**，偏好持久化在本地浏览器。

### 2. 🧭 方法架构图 × 数据实验图强隔离精筛体系
彻底告别“方法图和折线图混排筛选”，在顶栏切换大类时自动切换并隔离专属筛选项，同时实时展示各分类桶独立计数：

#### 方法架构图三维审美拆解（定位 × 画风 × 骨架 × 巧思）
| 维度 | 支持标签 |
| --- | --- |
| **功能定位 (`sub_type`)** | 💡 概念总览 (`concept_teaser`) · 🏗️ 方法主框架 (`system_pipeline`) · 🔬 局部算子机制 (`micro_mechanism`) |
| **8 类视觉画风 (`primary / secondary_style`)** | 📐 朴素框图 · 🌿 清新图标 · ✨ 高级渐变 · 🍱 稠密全景 · ⚡ 大开大合 · 🧮 张量数理 · 🧊 立体轴测 · 📰 刊物极简 |
| **6 类空间拓扑 (`layout_topology`)** | ➡️ 串联流水线 · 🔍 局部放大展开 · ⚖️ 正反双轨对比 · 🪟 多阶段分栏 · 🔄 循环博弈闭环 · 🌿 分支/采样树 |
| **4 项局部巧思 (`craft_badges`)** | ❄️🔥 冻结/可训标识 · 📊 图+实验混排 · 💬 Prompt 卡片 · 🗂️ 独立图例框 |

#### 数据实验图双维细分（图形 × 排版）
| 维度 | 支持标签 |
| --- | --- |
| **6 类统计图形 (`sub_type`)** | 📈 折线 / Scaling · 📊 柱状 / 消融与胜率 · 🎯 帕累托 / 散点气泡 · 🕸️ 多维雷达图 · 🎻 分布 / 箱线 / 密度 · 🟧 热力 / 矩阵图 |
| **4 种排版形态 (`chart_layout`)** | 🖼️ 单图特写 · 田 多子图网格 (`1×N / 2×2`) · 🔎 局部放大窗 (`Inset`) · 🔀 双轴 / 柱线组合 |

### 3. 🎨 OKLab/OKLCH 科研级深浅配对取色 & 离屏原色吸管
- **精准剥离背景噪音**：自动过滤论文白底与坐标轴中性灰，在 `OKLab` 感知均匀空间聚类出主导色，并按 `OKLCH` 明度与色相角自动配对**浅色填充 (`Fill`) + 同色相深色描边 (`Stroke`)**。
- **科研工作流一键复制**：色卡支持直接复制 `HEX`、`RGB`、`Matplotlib Python List`、`LaTeX xcolor (\definecolor)` 与 `CSS` 变量。
- **护眼暖宣纸体系 + 像素级色彩零失真**：全站采用暖燕麦画布（`#EDEAE4`）与象牙米白表面（`#FAF8F5`），图表通过显示层 `multiply` 柔和融纸；详情页放大镜吸管（Loupe Eyedropper）严格从**离屏未混合原始图像**采样，确保取色 100% 忠于原始像素。

### 4. 🔍 高精度矢量切图 & 交互式检视器 (`Inspector`)
- **双通道高清提取**：优先解析 `arXiv` TeX 源码包提取原生矢量 PDF 子图与 **TikZ 源码**；无源码时通过 `DocLayout-YOLO` ONNX 神经版面分析 + `PyMuPDF` **矢量路径与非白墨迹包络吸附 (`Vector-Ink Snap`)**，生成最高 `450 DPI` WebP 与局部矢量 PDF 切片。
- **沉浸式检视体验**：支持滚轮无级缩放与拖拽平移、`(a)(b)(c)` **多子图聚光灯联动**、同篇图表快速切换（支持键盘 `↑ / ↓`），以及登录用户的 **网页端框选重切** 与分类纠错锁定。

### 5. 📚 6 大前沿 AI 领域词库 & 自动顶会核验
- 内置 6 个持续追踪的 AI 研究领域词库（可在 `/admin` 动态维护并同步到 `config/domains.yaml`）：
  `多模态与幻觉` · `后训练策略 (GRPO/DPO/RLVR)` · `推理与计算扩展` · `自演化与递归改进 (RSI)` · `记忆机制` · `数据筛选与合成`
- 联动 `HF Daily Papers`、`arXiv`、`OpenReview`、`DBLP` 与 `CVF Open Access` 自动核验会议录用信息与引用热度。
- 支持高级全文与元信息检索（如 `font:Helvetica`、`ratio:>2.0` 等组合条件）。

### 6. 📌 私有灵感看板 (`Moodboard`) & 一键打包导出
- 支持整篇论文批量收藏、单图/子图聚焦收藏与科研笔记记录，双轨记录浏览历史与取色历史。
- 一键导出 `figprism-moodboard.zip`，内含看板中全部图表的**高清 WebP、原生矢量 `.pdf`、`palettes.py`、`palettes.tex` 与 `notes.json`**。

---

## 🤖 AI-Native 研发闭环：Gemini Carbon (PRD) × Codex (实现)

FigPrism 全栈采用 **「唯一主 PRD + 编号增量规格单」** 的双 Agent 协同研发范式（详见 [AGENTS.md](AGENTS.md) 与 [docs/specs/_template.md](docs/specs/_template.md)）：

1. **立项写小单（Gemini Carbon 负责 PRD 与审美规格）**：
   每次迭代由 **Gemini Carbon** 进行产品设计、视觉审美拆解与边界推演，基于模板生成 50~150 行的独立增量开发单 `docs/specs/00X-<slug>.md`（明确数据库 Delta、API 契约、VLM Prompt 与 UI 交互验收标准），不直接手改长篇主文档。
2. **精准按单实现（Codex 负责代码落地与自动化验证）**：
   **Codex** 读取 [AGENTS.md](AGENTS.md) 全局红线与 [docs/PRD.md](docs/PRD.md) 基线，严格限定在目标 `00X` 规格单范围内完成前后端编码、容器构建、存量数据回填，并跑通 `pytest` + `tsc` + `Playwright E2E` 全链路验证。
3. **验收后自动合入主 PRD（文档零腐化闭环）**：
   线上验收通过后，由 **Codex** 将最终落地的表结构、API 与交互规则原地合入 [docs/PRD.md](docs/PRD.md)（直接替换旧描述，拒绝末尾堆叠补丁），并将规格单标记为 `Status: Merged`，让 `docs/PRD.md` 始终保持为干净、无冲突的唯一全局真相源。

---

## 🏗️ 技术架构 (Architecture)

| 模块 | 技术选型与核心实现 |
| --- | --- |
| **前端应用** | Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS 4 · TanStack Query · Zustand · BlurHash |
| **后端服务** | FastAPI · Python 3.12 · SQLite (WAL + FTS5 全文索引) · SSE 实时事件流 (`/api/stream/events`) |
| **图表提取** | Safe TeX Source Parser · `DocLayout-YOLO` ONNX CPU 推理 · `PyMuPDF` 矢量墨迹吸附与 450 DPI 渲染（短生命周期子进程隔离） |
| **视觉审美打标** | OpenAI Vision Structured Outputs（`backend/prompts/vision_judge_system.md` + JSON Schema） |
| **配色引擎** | `OKLab` 确定性感知聚类 + `OKLCH` 浅填充 / 深描边自动配对 (`backend/figprism/palette.py`) |
| **认证与安全** | 邀请制注册 · Argon2 密码哈希 · 可撤销服务端 Cookie 会话 (`HttpOnly`, `SameSite=Lax`) · 同源写校验 · 私有接口 `no-store` |
| **存储与并发** | 本地分层资产缓存（默认 3 GB 预算，含收藏专用池）+ WebDAV 异步备份队列 · 跨进程内核文件锁分阶段并发控制 |

---

## 🚀 快速开始 (Quick Start)

### 方式一：本地开发环境

#### 1. 准备后端环境与配置
```bash
git clone https://github.com/WhatWEat/FigPrism.git
cd FigPrism

# 安装 Python 依赖（推荐使用 uv，也可使用标准 python -m venv）
uv venv .venv
uv pip install --python .venv/bin/python -r backend/requirements.lock
uv pip install --python .venv/bin/python -e './backend[test]' --no-deps

# 准备配置文件（参考 config/settings.example.yaml 填写 WebDAV 与视觉模型配置）
cp config/settings.example.yaml config/local.yaml
# 如已有独立文本配置，也可运行：
# .venv/bin/python scripts/convert_config.py --source config --output config/local.yaml

# 下载 DocLayout-YOLO ONNX 版面模型（可选，无模型时自动回退几何检测并入复核队列）
.venv/bin/python scripts/download_layout.py
```

#### 2. 安装前端依赖并启动服务
```bash
npm ci --prefix frontend

# 终端 1：启动后端 API
FIGPRISM_PUBLIC_ORIGIN=http://127.0.0.1:3100 FIGPRISM_COOKIE_SECURE=false \
  .venv/bin/uvicorn figprism.main:app --host 127.0.0.1 --port 8100

# 终端 2：启动前端开发服务器（默认监听 http://127.0.0.1:3100）
npm run dev --prefix frontend
```

#### 3. 创建首个管理员账号
```bash
.venv/bin/figprism auth create-admin --username admin
```
登录后即可在 `/admin` 页面签发一次性注册邀请码、维护领域词库或触发论文同步任务。

---

### 方式二：Docker Compose 部署

```bash
# 确保已在 config/local.yaml 中完成生产环境配置
docker compose build
docker compose up -d

# 创建首个管理员
docker compose exec backend figprism auth create-admin --username admin
```

`compose.yaml` 默认编排了以下服务：
- `backend`：FastAPI API 与调度入口（暴露 `127.0.0.1:8101 -> 8100`）
- `frontend`：Next.js 生产 Web 服务（暴露 `127.0.0.1:3111 -> 3000`）
- `uploader`：后台异步 WebDAV 资产上传守护进程 (`figprism storage worker`)
- `coldstart`（可选 `maintenance` profile）：离线/冷启动回填任务容器

---

## 🛠️ CLI 常用命令速查

本地环境可使用 `.venv/bin/figprism`，Docker Compose 环境可在命令前加上 `docker compose exec backend`：

```bash
# 1. 增量抓取最近 3 天新论文并入库
figprism sync --source all --days 3 --limit 50

# 2. 按年份与领域批量回填顶会论文
figprism backfill --years 2025,2026 --domains all --limit-per-domain 50

# 3. 定向入库单篇 arXiv 论文或本地 PDF
figprism ingest --input https://arxiv.org/abs/2501.00663 --force-include
figprism ingest --pdf /path/to/paper.pdf --domains memory

# 4. 免重切刷新存量图表的三维画风、拓扑与实验排版标签（自动跳过用户手动锁定条目）
figprism retag-taxonomy --scope all --concurrency 8 --vision-driver openai_mini

# 5. 查看待复核队列与手动指定归一化坐标重切
figprism queue list --type review_or_repair --json
figprism recrop --figure-id <id> --page 4 --bbox 0.08,0.12,0.92,0.48 --snap-vector

# 6. 查看并发管线与存储队列状态 / 从 WebDAV 资产全量重建公开图库索引
figprism pipeline status
figprism storage status
figprism rebuild-from-webdav
```

---

## 🧪 测试与验证 (Verification)

```bash
# 后端单元与集成测试
.venv/bin/pytest backend/tests -q

# 前端类型检查与生产构建
npm run typecheck --prefix frontend
npm run build --prefix frontend

# 端到端浏览器回归（需先初始化 E2E 测试账号并设置浏览器路径）
.venv/bin/python scripts/setup_e2e.py
npm run test:e2e --prefix frontend
```

---

## 📖 项目结构与文档

```text
FigPrism/
├── AGENTS.md                        # 全局工程守则、配色红线与 3 步增量开发闭环
├── compose.yaml                     # Docker Compose 生产编排 (backend / frontend / uploader)
├── backend/
│   ├── figprism/                    # FastAPI 服务、TeX/PDF 切图、OKLab/OKLCH 配色、并发与存储引擎
│   ├── prompts/                     # VLM 视觉审美分类 System Prompt 与 JSON Schema
│   └── tests/                       # 后端单元与集成测试
├── frontend/
│   ├── src/                         # Next.js 16 App Router、图组胶片流、检视器与工作台组件
│   └── tests/                       # Playwright E2E 回归测试
├── config/
│   ├── domains.yaml                 # 6 大前沿 AI 领域动态词库
│   └── settings.example.yaml        # 配置文件示例
└── docs/
    ├── PRD.md                       # 唯一全局产品与技术规格真相源
    ├── implementation.md            # 架构实现细节、安全边界与并发验收记录
    └── specs/                       # 编号增量规格单 (001 ~ 015 + _template.md)
```
