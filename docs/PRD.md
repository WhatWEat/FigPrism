# FigPrism — 科研顶会画图灵感与配色拆解平台 PRD（全局唯一真相源）

> **文档状态**：`Current Truth`（已合入 `docs/specs/001` ~ `005` 及线上并发与安全基线）  
> **维护约定**：本文档始终代表系统**当前已落地最新状态**。新增功能请先在 `docs/specs/00X-xxx.md` 立项，验收通过后再同步更新对应章节并删除被替代的旧描述（详见根目录 `AGENTS.md`）。

---

## 1. 产品定位与核心目标

**FigPrism** 是一个**以学术图表（Figure）为一等公民、以论文图组为默认浏览单元**的科研绘图灵感收集、检索、构图拆解与配色提取平台。系统自动从 `Hugging Face Daily`、`arXiv`、`OpenReview` 与 `DBLP` 筛选特定研究方向的六大顶会录用论文与高热讨论工作，高精度提取其中的**方法架构图**与**数据实验图**；支持登录用户通过链接或本地 PDF 在线补充论文，并提供论文图组胶片速览、多子图聚光灯拆解、科研级深浅配对取色、原始矢量图下载与灵感看板（Moodboard）管理。

### 1.1 核心非功能性指标
1. **轻量本地热层与渐进懒加载**：重资产持久化于远端 WebDAV，服务器本地保留 SQLite 索引、轻量 L1 缩略图镜像与有上限的 L2 高清 LRU 缓存；配合 `BlurHash` 占位、固定宽高比防抖骨架（CLS ≈ 0）与不可变版本化缓存头，保障列表流畅浏览。
2. **流式原子化热更新**：无论是定时同步还是在线上传单篇 PDF，后台每处理并持久化完 **1 张图** 的远端资产即刻写入索引并通过 `SSE (Server-Sent Events)` 推送至前端增量提示，无需等待整批任务完成。
3. **动态领域可扩展**：研究领域、三级召回词库与视觉判图准则均由 `config/domains.yaml` 与 SQLite `domains` 表双向同步驱动，无需修改业务代码即可扩展新领域并单独触发历史代表作冷启动。
4. **读写权限与安全隔离**：支持公网免登录 `Guest` 只读访问（看图、搜索、吸管取色、下载矢量图），登录用户独享收藏夹看板、双轨历史记录、在线加论文与切图修正；默认关闭公网公开注册（仅支持管理员签发一次性邀请链接）。

---

## 2. 技术栈与系统架构

* **生产与部署环境**：Linux 云服务器（Docker Compose 编排，主域名 `https://figprism.ai4any.com`，Nginx + Let's Encrypt 提供 HTTPS 终止与旧域名 308 永久跳转，Cloudflare 提供 DNS 解析），远端连接 **WebDAV** 存储卷（异步 `httpx` 分块流式上传与传输重试）。
* **前端技术栈**：`Next.js (App Router, TypeScript, standalone 构建)` + `React` + `Tailwind CSS` + `Lucide Icons`，状态管理采用 `TanStack Query` + `Zustand`。
* **后端技术栈**：`Python 3.11+` + `FastAPI` + `SQLite (WAL 并发读写模式 + FTS5 全文检索引擎)` + 跨进程内核文件锁分阶段并发调度。
* **认证与安全边界**：`JWT (HttpOnly, Secure, SameSite=Lax Cookie: figprism_session)` + SQLite `sessions (jti)` 服务端会话撤销 + `Argon2` 密码哈希 + RBAC 权限校验 + 写请求 `Origin / Sec-Fetch-Site` 同源校验。
* **切图与色彩引擎**：
  * 源码提取：arXiv e-print 压缩包内存安全限额解析（不解压落地、不跟随符号链接、不执行 TeX 编译），展开常见 `\input / \include` 解析 `figure / figure* / subfigure / tikzpicture`。
  * 版面检测与矢量吸附：独立短生命周期 CPU 子进程运行 `doclayout-yolo`（ONNX Runtime，单进程单推理线程）+ `PyMuPDF (fitz)`（矢量墨迹吸附微调、最高 450 DPI 且不超过 24MP 安全上限的超采样光栅化、局部矢量 PDF 切片导出、内嵌字体与单双栏检测）+ `OpenCV`（多子图模板匹配定位）。
  * 色彩科学：`Pillow` + `numpy / scikit-learn`（`OKLab` 聚类与 `OKLCH` 感知均匀色彩空间背景剥离、淡彩填充保留及同色相深浅描边配对）。
* **视觉判图双驱动引擎 (`VisionJudge`)**：
  * `openai_mini` 模式（默认全自动）：基于独立提示词与 Schema 文件（`backend/prompts/vision_judge_system.md`、`backend/prompts/vision_judge_schema.json`）调用视觉模型，单次请求完成强隔离层级分类（`macro_category` × `sub_type`）、方法图三维审美拆解（画风 `primary_style/secondary_style` × 拓扑骨架 `layout_topology` × 局部巧思 `craft_badges`）、实验图排版形态（`chart_layout`）、领域 `sub_tags` 与切图完整性自检；响应异常或低置信度时保留图表并标为 `needs_review`。
  * `codex_subagent` 模式（外部协同）：导出待判图/待精修队列（`figprism queue list`），供外部任务批量判图或调用 `figprism recrop` 写回精修裁切框。

---

## 3. 视觉美学与 UI/UX 详细设计规范（护眼暖宣纸画廊体系）

### 3.1 护眼暖宣纸配色体系与「消灭灰字」规范
科研图表多为纯白底色，为消除纯白眩光并杜绝浅灰文字发虚晃眼，全站采用 **「暖燕麦宣纸画布 + 柔和象牙米白卡片 + 浓墨高对比实字 + 固定纸感柔光融合」** 的浅色出版物设计体系，确保久看不累且不抢夺科研图表自身的配色焦点。

1. **消除白底眩光**：全站底层使用暖燕麦宣纸色（`#EDEAE4`），卡片与面板使用柔和象牙米白（`#FAF8F5`），严禁在常规界面容器硬编码纯白 `bg-white`。
2. **严禁靠“把字变浅灰”区分层级**：视觉主次由**字重、字号大小与背景色块**承担，所有可读文字统一使用高对比暖炭黑浓墨色系，全站可读文字最浅下限为 `#57524B`（AA+ 对比度）。
3. **固定纸感柔光融合 (`Paper Blend`) 与取色保真**：图表装裱底板固定为 `--bg-figure-mat`（`#E6E2DA`），所有展示态科研图片 `<img>` 固定挂载 `.fig-paper-blend`（`mix-blend-mode: multiply; filter: contrast(1.02)`），使图表白底自然融入暖纸底板（界面不提供纸感或纯白背景切换开关）。该融合仅作用于屏幕显示层——原始 WebP/PDF 资产、导出色板代码以及检视器离屏 `<canvas>` 放大镜吸管读取的 `RGB / HEX` 像素值均完全保持原论文未混合真值。

#### 全局色彩设计语义 Token
| CSS 变量名 | 色值 (HEX) | 对比度参考 | 适用位置与视觉作用 |
| :--- | :--- | :--- | :--- |
| `--bg-canvas` | `#EDEAE4` | 基准画布 | 全局网页底层画布背景（暖燕麦宣纸灰，柔和不刺眼，与卡片自然拉开层次） |
| `--bg-topbar` | `rgba(237, 234, 228, 0.90)` | — | 吸顶导航栏毛玻璃背景（与暖纸画布同色系过渡） |
| `--bg-surface` | `#FAF8F5` | — | 卡片主体、详情右侧面板、弹窗与下拉菜单底色（柔和象牙米白） |
| `--bg-subtle` | `#E3DFD7` | — | 卡片内嵌缩略图胶片槽、未选中胶囊、次级底块与代码块底色（暖沙灰） |
| `--bg-subtle-hover` | `#D8D3C8` | — | 胶囊按钮、胶片槽悬停加深态 |
| `--bg-drafting` | `#E6E2DA` | — | 详情抽屉左侧大图检视画布底色（配微弱点阵，久看大图不晃眼） |
| `--bg-figure-mat` | `#E6E2DA` | — | 图表装裱内衬固定暖纸底板 |
| `--border-hairline` | `#D6D1C7` | — | 卡片默认 `1px` 细描边与分割线 |
| `--border-strong` | `#B8B1A4` | — | 卡片悬停描边、交互控件强调描边 |
| `--text-primary` | `#181615` | `~14.2 : 1` (AAA) | 主标题、激活态按钮文字、论文名（浓墨炭黑） |
| `--text-secondary` | `#36322E` | `~10.1 : 1` (AAA) | 图注 Caption 正文、作者、常规正文（深暖褐黑实字） |
| `--text-tertiary` | `#57524B` | `~6.3 : 1` (AA+) | 辅助元数据（宽高比、字体名、页码、时间、快捷键；全站最浅可读字色下限） |
| `--text-placeholder` | `#706A62` | `~4.6 : 1` (AA) | 仅限输入框未输入时的占位提示词 |
| `--accent-ink` | `#1F1D1A` | — | 主操作按钮与选中态胶囊底色（配 `#FAF8F5` 米白字，保持无彩色克制） |
| `--accent-brand` | `#3730A3` | — | 焦点环、聚光灯选中边框、交互链接点缀色（深靛青） |

#### `globals.css` 基础覆盖契约
```css
:root {
  --background: 38 18% 91%;          /* #EDEAE4 */
  --foreground: 20 7% 9%;            /* #181615 */
  --card: 36 33% 97%;                /* #FAF8F5 */
  --card-foreground: 20 7% 9%;
  --popover: 36 33% 97%;
  --popover-foreground: 20 7% 9%;
  --primary: 36 8% 11%;              /* #1F1D1A */
  --primary-foreground: 36 33% 97%;  /* #FAF8F5 */
  --secondary: 38 15% 87%;           /* #E3DFD7 */
  --secondary-foreground: 30 8% 20%; /* #36322E */
  --muted: 38 15% 87%;
  --muted-foreground: 32 7% 32%;     /* #57524B */
  --accent: 36 16% 82%;              /* #D8D3C8 */
  --accent-foreground: 20 7% 9%;
  --border: 38 15% 81%;              /* #D6D1C7 */
  --input: 38 15% 81%;
  --ring: 244 55% 41%;               /* #3730A3 */
}

.fig-paper-blend {
  mix-blend-mode: multiply;
  filter: contrast(1.02);
}
```

#### 字体排印规范
* **界面与中文**：`Inter`, `Arial`, `PingFang SC`, `Microsoft YaHei`, `sans-serif`。
* **图注阅读字体**：默认无衬线，详情页支持一键切换学术衬线体阅读长 Caption。
* **工程参数与代码**：`SFMono-Regular`, `Consolas`, `Liberation Mono`, `monospace`（用于展示 `HEX` 色值、宽高比、arXiv ID 与 `TikZ` 代码）。

---

### 3.2 核心页面布局与交互细节

#### 页面一：灵感画廊主页 (`/`)
1. **吸顶毛玻璃导航栏（`backdrop-filter: blur(12px)`，底色 `var(--bg-topbar)`）**
   * **左侧**：`FigPrism` 棱镜标识 + **全局命令搜索框**（支持快捷键 `⌘K / Ctrl+K` 唤醒；支持全文搜标题/Caption、按字体过滤如 `font:Helvetica`、按宽高比过滤如 `ratio:>2.0`，若直接粘贴 arXiv 链接则提示一键抓取入库）。
   * **中部导航**：`画廊`、`灵感看板 (/collections)`、`足迹 (/history)`（管理员额外可见 `控制台 (/admin)`）。
   * **右侧功能区**：
     * `Guest` 视角：显示 `[访客只读]` 标识 + `[登录]` 按钮。
     * `User / Admin` 视角：深墨主按钮 `[+ 添加论文]`、后台任务进度入口及个人头像下拉菜单（含单图平铺模式的列数密度切换与退出登录）。
2. **多维正交折叠筛选栏与工具条**
   * **领域与细分标签行**：横向排列领域胶囊（如 `● 多模态与幻觉`、`● 后训练策略`、`● 推理与计算扩展`、`● 自演化与递归改进`、`● 记忆机制`、`● 数据筛选与合成`），选中领域后展开对应 `sub_tags` 支持二次收窄（支持并集 `any` / 交集 `all` 切换），右侧支持折叠/展开筛选面板。
   * **会议 × 荣誉 × 版式 × 色谱行**：
     * **顶会筛选**：`ICLR` `ICML` `CVPR` `ACL` `EMNLP` `NeurIPS` `HF 高热` + `[★ Oral / Spotlight]` 开关；
     * **版式与跨栏筛选**：论文版式（`single` 单栏 / `double` 双栏）、图片跨栏（`full` 通栏宽图 / `column` 半栏窄图）；
     * **12 色相科研色谱球**：红、橙、琥珀、翠绿、青、天蓝、钴蓝、靛紫、品红、莫兰迪低饱和、冷暖撞色等色球，一键筛选对应主色系图表，右侧提供 `[重置筛选]`。
   * **视图分类、独立计数徽章与强隔离二级筛选面板**：
     * **左侧一级大类 Tab**：`[全部精选 N]` | `[方法架构图 M]` | `[数据实验图 D]`，各自固定渲染当前通用过滤条件（领域/顶会/版式/色系/关键词）下后端独立统计的 `tab_counts` 图表数；切换一级大类时自动清空跨大类互斥子筛选状态并同步清理 URL Query。
     * **右侧列表控制**：排序切换（`最新收录` / `讨论热度`）、`[显示定性案例]` 开关（默认折叠 `case_study` 噪音图），以及持久化至 `localStorage`（`figprism-view-mode`）的**三态视图切换器**：
       1. **`[图组胶片流 (Deck)]`（系统默认）**：1 张卡片 = 1 篇论文，通过主舞台 + 内嵌缩略图胶片条归集展示同篇论文命中的全部图表。
       2. **`[横排画册流 (Swimlane)]`**：每篇论文独占一整行横向等高画廊，平铺扫读全套图表。
       3. **`[单图平铺流 (Flat)]`**：单张图表独立卡片瀑布流。
     * **下方强隔离分类精筛面板 (`.taxonomy-panel`)**：
       * 当激活 **`方法架构图 (method)`** 时渲染专属三行面板（严禁出现实验图标签）：
         1. **方法类型**：`全部方法图` | `💡 概念总览 (concept_teaser)` | `🏗️ 方法主框架 (system_pipeline)` | `🔬 局部算子机制 (micro_mechanism)`，右侧配紧凑多选下拉 **`[🧩 局部巧思 ▾]`**（`冻结/可训标识`、`图+实验混排`、`Prompt 卡片`、`独立图例框`）；
         2. **画风质感**：`全部画风` | `📐 朴素框图` | `🌿 清新图标` | `✨ 高级渐变` | `🍱 稠密全景` | `⚡ 大开大合` | `🧮 张量数理` | `🧊 立体轴测` | `📰 刊物极简`（同时匹配主/次画风）；
         3. **构图骨架**：`全部骨架` | `➡️ 串联流水线` | `🔍 局部放大展开` | `⚖️ 正反双轨对比` | `🪟 多阶段分栏` | `🔄 循环博弈闭环` | `🌿 分支/采样树`。
       * 当激活 **`数据实验图 (data_chart)`** 时渲染专属两行面板（严禁出现方法图标签）：
         1. **实验图类型**：`全部实验图` | `📈 折线 / Scaling` | `📊 柱状 / 消融与胜率` | `🎯 帕累托 / 散点气泡` | `🕸️ 多维雷达图` | `🎻 分布 / 箱线 / 密度` | `🟧 热力 / 矩阵图`；
         2. **排版形态**：`全部排版` | `🖼️ 单图特写` | `田 多子图网格 (1×N / 2×2)` | `🔎 带局部放大窗 (Inset)` | `🔀 双轴 / 柱线组合`。
       * 当激活 **`全部精选 (all)`** 时不混排任何二级子类按钮，仅渲染快捷分流引导条，一键进入方法图或实验图精筛面板。
3. **默认模式：「论文图组胶片卡 (`PaperDeckCard`)」解剖结构**
   * **层 1：精简论文眉栏**：左侧展示顶会年份与荣誉徽章（如 `ICLR'26 Oral`）+ 版式标记（`双栏`）；右侧当命中图表数 `>= 2` 时显示 **`[共 N 张图 · 展开平铺 ▾]`**。
   * **层 2：主图动态舞台 (`Hero Stage`)**：
     * 默认展示该论文在当前筛选条件下的最高优先级代表图（权重顺序：`system_pipeline` > `concept_teaser` > `micro_mechanism` > 实验数据图子类 > `qualitative_case`；同权重按原论文自然图号排序）。
     * 严格按图片真实 `aspect_ratio` 与 `BlurHash` 渲染，挂载 `.fig-paper-blend`，左下角悬浮当前预览图的图号、子类与主画风标签（如 `Fig. 2 · 方法主框架 · 清新图标`），点击直接打开 `Figure Inspector` 并定位到当前图。
   * **层 3：内嵌常驻微缩胶片条 (`Inline Filmstrip`)**：
     * 当该论文命中图表数 `>= 2` 时常驻显示（底色 `var(--bg-subtle)`），横向排列高度固定 `50px`、按真实比例自适应宽度的微缩图，当前激活项带 `2px` 深墨边框 `#181615`，超出宽度支持滚轮/触控板横向平滑滚动并提示右侧剩余张数。
     * **视口预热与悬停零延迟切图 (`Hover-to-Scrub`)**：卡片进入视口（`IntersectionObserver`）时静默预加载同组缩略图；鼠标滑过或键盘聚焦任意微缩图时，无需点击即刻同步切换上方主舞台大图、图号标签与底部 5 色科研色板；单击微缩图直接打开该图详情抽屉。
     * **卡片原地展开 (`Inline Expand`)**：点击眉栏 `[展开平铺 ▾]`，卡片原地展开为内部 `2 列` 紧凑子网格并排展示该论文全部命中图表；点击 `[收起 ▴]` 恢复胶片形态。
   * **层 4：联动配色与操作底栏**：左侧单行截断显示论文标题（`#181615` 浓墨实字），右侧排列当前主舞台激活图的 **5 枚圆角主色块**（点击直接复制 `HEX` 色值并记录取色历史）及快捷 `[⭐ 收藏当前图]` 按钮。
4. **备选模式一：「横排画册流 (`Paper Swimlane View`)」**
   * 单列纵向排列「论文画册行」卡片：行头部展示完整论文标题、顶会徽章、领域胶囊、`[↗ 原文 PDF]` 与 **`[一键收藏整篇好图]`**（原子化批量存入目标看板并保留已有笔记）；行内容区以固定高度 `210px` 从左至右并排铺开该论文全部命中图表（附 `Fig. X` 与 5 色点），支持滚轮与鼠标拖拽横向浏览。
5. **备选模式二：「单图平铺流 (`FigureCard`)」**
   * 单张图表独立装裱卡片：暖纸内衬 + `BlurHash` 防抖占位，多子图左上角展示 `[含 N 子图]` 角标；悬停浮现快捷收藏与 `[↗ 原文 P.X]` 页码直达；底栏展示顶会/跨栏信息与 5 枚一键复制 `HEX` 色块。

---

#### 页面二：图表深度拆解抽屉 (`Figure Inspector Modal`)
点击任意图表弹出居中大尺寸工作台模态框（宽 `92vw`、高 `90vh`，最大宽 `1680px`），支持全键盘流式操作：
* **全局快捷键**：`← / →` 在当前列表上下文切换上一张/下一张图；`↑ / ↓` 在**同一篇论文的其余图表（Sibling Figures）**之间上下跳转；`Space` 适应窗口 / 放大切换；`I` 开启/关闭放大镜吸管；数字键 `1~9` 依次切换子图 `(a)~(i)` 聚光灯，`0` 回到整图；`S` 收藏当前图；`Esc` 关闭。

1. **左舱：高精度交互画布区（点阵暖白底）**
   * **顶部悬浮胶囊控制栏**：
     * **画布工具组**：`[上一张 / 下一张]`、`[吸管取色 (I)]`、`[- 缩放比例 +]`、`[适应窗口]`。
     * **多子图聚光灯切换器（检测到 `>= 2` 个子图时显示）**：提供 `[整图]` `[(a)]` `[(b)]` ... 胶囊及 `[悬停热区感应]` 开关。聚焦某子图时，其余区域叠加深色半透明遮罩，目标子图高亮显示。
     * **切图纠错入口（仅登录用户可见）**：`[框选重切]`、`[请求精修]`（`needs_review` 状态带温和提示标记）。
   * **自适应视口缩放与拖拽平移（Stage Fit, Wheel Zoom & Drag-Pan）**：默认 `100%`（适应窗口）态通过 `ResizeObserver` 实测画布可用宽高，使任意宽高比图表完整落入视口无纵向溢出；支持以鼠标光标为锚点的滚轮无级缩放（`50% ~ 400%`）与双击快速放大/还原，放大超出视口后支持按住鼠标左键自由拖拽平移（`grab / grabbing`）。高清图慢网切换期间保持已挂载预览与居中状态条，杜绝白屏闪烁或晚到请求覆盖当前选中图。
   * **像素级放大镜吸管（Loupe Eyedropper）**：激活后鼠标旁跟随高清像素网格放大镜并实时显示 `#HEX`；底层强制从**离屏未混合原始图像 `<canvas>`** 执行 `getImageData()` 取样，确保缩放平移、护眼融合与科研原色取样精度互不干扰；左键单击即复制色值并同步至登录用户的「取色剪贴板」。
   * **底部「同篇论文图表 (`Sibling Figures`)」横向导航与快筛条**：默认继承外层画廊筛选上下文并支持一键切换 `[查看同篇全部图表 / 仅看当前筛选]`（未命中外层筛选的同文图表以虚线与 `· 其他` 标记区分）；当同文同时包含方法图与实验图时提供 `全部 / 方法 / 实验` 快捷切换，轨道支持滚轮、鼠标按住拖拽横向滑动及溢出时的左右翻页箭头按钮。
2. **右舱：科研参数与配色拆解面板（象牙米白底 `--bg-surface: #FAF8F5` 独立滚动）**
   * **模块 1：论文头部、三维审美徽章与多源直达**：展示完整论文标题、作者列表、录用等级、外层筛选命中状态，以及当前图表的子类、主/次画风、构图骨架、局部巧思或实验图排版胶囊徽章（人工校准锁定项显示 `已锁定` 标记），并附 `[原文 P.X]`、`[arXiv HTML]`、`[HF 讨论]`、`[OpenReview]` 直达外链。
   * **模块 2：智能联动图注 (`Caption`)**：完整展示原文 Caption（支持切换学术衬线体），自动识别 `(a)~(i)` 标记并与左侧子图聚光灯双向联动。
   * **模块 3：科研黄金配对色板（随聚光灯动态切换整图 / 子图独立配色）**：
     * 展示 **「浅色填充底 (`Fill`) + 同色相深色描边 (`Stroke`)」配对胶囊**、主色块及坐标轴灰阶参考色，点击任一色块直接复制。
     * 提供 `HEX` | `RGB` | `Matplotlib` | `LaTeX` | `CSS` 五种格式实时代码生成与一键整套复制。
   * **模块 4：画图工程透视、分类锁定编辑与矢量资产下载**：
     * 展示精确宽高比、排版跨栏属性（单/双栏 · 通栏/半栏）、清洗后的内嵌字体家族名称与提取方式（`TeX 原始矢量` / `PDF 矢量切片`）。
     * 提供 `[下载矢量 PDF]`（锁定拥有独立源文件的子图时支持单独下载子图原始矢量 PDF）与高清 WebP 下载；若含 `tikz_code`，提供折叠抽屉查看与一键复制 `TikZ / PGFPlots` 源码。
     * 登录用户可直接编辑图表大类/子类及对应画风、拓扑骨架或实验排版形态，保存后自动置 `taxonomy_locked = 1`，防止后续批量重刷覆盖人工校准结果。
   * **模块 5：钉入灵感看板**：选择目标看板、填写灵感备忘录（支持勾选锁定当前聚焦子图）并一键保存。

---

#### 页面三：网页 3 秒手动框选重切器（详情页内嵌态）
登录用户在详情页点击 `[✂️ 3秒框选重切]` 时，左侧画布直接切换为 **PDF 原页高清裁切工作台**：
* 加载该图所在的完整 PDF 页面（顶部支持 `[◀ 上一页]` `[第 X / N 页]` `[下一页 ▶]` 翻页）。
* 支持拖拽调整裁切框或重新拉框，默认开启 **`[✨ 松手自动矢量墨迹吸附]`**（贴合底层 PDF 矢量路径与文字外沿并留出均匀白边）。
* 点击确认后，后台重新生成超清 WebP 与局部矢量 PDF 切片、重算 OKLCH 配色、更新 `version_hash` 并覆盖远端备份，前端即刻无缓存串号刷新。

---

#### 页面四：在线「+ 添加论文」模态框与流式任务进度
1. **双通道录入弹窗（仅登录用户可用）**：
   * **链接或编号通道**：支持粘贴 `arXiv ID / 链接`、`HF Papers 链接` 或 `OpenReview 链接`，支持异步预览识别论文标题。
   * **本地 PDF 上传通道**：支持拖入单文件 `≤ 50MB` 的 PDF，前端计算 `SHA-256` 预判重并嗅探内置 arXiv ID。
   * 支持附带自定义领域标签与会议名称提交入库。
2. **非阻塞任务跟踪与 SSE 热更新**：
   * 提交后返回异步 `job_id`，右下角/任务面板展示实时拆解进度；
   * 后台每持久化完 1 张新图表即推送 `SSE` 事件，画廊顶部浮现不打断当前阅读位置的增量刷新提示条。

---

#### 页面五：灵感收藏看板 (`/collections`)、双轨足迹 (`/history`) 与管理台 (`/admin`)
1. **灵感收藏看板 (`Moodboard`)**：
   * 左侧管理多个私有看板（新建、重命名、删除），右侧网格展示收藏图表、常驻灵感笔记与 5 色条（锁定子图时自动提示/还原聚焦区域）。
   * 支持 **`[📦 打包导出本看板]`**：一键下载 `.zip`（单次上限 `100` 张图 / `200MB`），内含所有收藏图表的原始矢量 `.pdf`、超清 `.webp`、汇总生成的 `palettes.tex`、`palettes.py` 及 `notes.json`。
2. **个人双轨足迹 (`/history`)**：
   * **最近浏览图表 (`views`)**：按访问时间倒序记录点开过的图表卡片。
   * **吸管取色剪贴板 (`colors`)**：按时间倒序记录每次吸管取色或点击复制过的 `HEX` 色卡、格式及来源图表缩略图，支持再次复制与一键跳回原图。
3. **系统控制中心 (`/admin`，仅管理员)**：
   * 管理用户启停与生成 7 天有效的一次性注册邀请链接；
   * 在线增删改研究领域词库（保存时双向写回 SQLite 与 `config/domains.yaml`）；
   * 手动触发日常 `sync`、领域 `backfill` 或 `rebuild-from-webdav`，查看待复核/修图队列以及**分阶段并发流水线实时容量监控**。

---

## 4. 账号体系与角色权限矩阵 (Auth & RBAC)

系统默认关闭无邀请码公开注册。首次部署通过 CLI（`figprism auth create-admin`）创建管理员；普通成员仅能通过管理员在 `/admin` 生成的一次性邀请链接完成注册。停用账号时立即清除其全部活跃服务端会话（`sessions`）。

| 功能模块 | `Guest`（未登录访客） | `User`（已登录成员） | `Admin`（管理员/站长） |
| :--- | :---: | :---: | :---: |
| 图组胶片流 / 画册流 / 平铺流浏览、多维筛选、全文与色相检索 | 支持 | 支持 | 支持 |
| 查看超清大图、同文图表切换、多子图聚光灯、离屏原色吸管取色 | 支持 | 支持 | 支持 |
| 一键复制多格式配色、下载原始矢量 PDF、查看 TikZ 源码、跳转原文 | 支持 | 支持 | 支持 |
| **灵感收藏夹看板 (`collections`)**：CRUD、批量整组收藏、笔记、ZIP 导出 | 仅提示登录 | **独立私有空间** | **独立私有空间** |
| **双轨个人足迹**：图表浏览历史 + 取色剪贴板历史 | 不记录 | **自动云端同步** | **自动云端同步** |
| **在线添加单篇论文**（学术链接抓取或本地 PDF 上传） | 禁止 | **支持** | **支持** |
| **切图纠错与打标**：网页框选重切、提交异步精修队列、修正图表标签 | 禁止 | **支持** | **支持** |
| **系统控制中心 (`/admin`)**：邀请码与账号管理、领域词库配置、同步触发、并发监控 | 禁止 | 禁止 | **支持** |

---

## 5. 动态可扩展领域引擎与预置词库

研究领域定义于 `config/domains.yaml` 并与 SQLite `domains` 表双向同步。新增研究方向无需改动代码，只需在后台或配置文件新增词条即可参与日常增量同步，并支持单独对该领域执行历史论文回溯。

### 5.1 三级精准召回匹配规则
* `phrases`：不区分大小写的短语匹配（检索标题、摘要与 HF 关键词）。
* `acronyms`：**严格大小写敏感的全词边界匹配**（避免 `OPD`、`VCD`、`TTT`、`LESS` 等缩写误匹配普通英文单词）。
* `exclude_terms`：负向排除词（命中排除词且未命中核心强特征短语时自动过滤，剔除跨学科重名噪音）。

### 5.2 预置 6 大核心领域词库

#### 1. 多模态与幻觉 (`multimodal-hallucination`)
* **细分标签 (`sub_tags`)**：`VLM / Omni 架构`、`Contrastive Decoding (对比解码)`、`Attention / Logit 干预`、`Visual Grounding & 细粒度感知`、`Visual Token 压缩与对齐`
* **核心短语 (`phrases`)**：`"multimodal hallucination"`, `"object hallucination"`, `"visual hallucination"`, `"cross-modal hallucination"`, `"relation hallucination"`, `"event hallucination"`, `"hallucination mitigation"`, `"modality bias"`, `"language prior"`, `"faithfulness in multimodal"`, `"contrastive decoding"`, `"visual contrastive decoding"`, `"instruction contrastive decoding"`, `"layer contrastive"`, `"logit calibration"`, `"logit lens"`, `"attention intervention"`, `"attention sink"`, `"attention steering"`, `"activation steering"`, `"head-level intervention"`, `"representation engineering"`, `"vision-language model"`, `"multimodal large language model"`, `"omni-modal"`, `"any-to-any multimodal"`, `"unified multimodal"`, `"native multimodal"`, `"visual grounding"`, `"referring expression"`, `"region-level alignment"`, `"set-of-mark"`, `"visual prompting"`, `"visual token pruning"`, `"visual token merging"`, `"dynamic resolution"`
* **敏感缩写 (`acronyms`)**：`"VLM"`, `"LVLM"`, `"MLLM"`, `"VCD"`, `"DoLa"`, `"OPERA"`, `"HALC"`, `"POPE"`, `"MMHal"`

#### 2. 后训练策略 (`post-training`)
* **细分标签 (`sub_tags`)**：`RL 策略 (GRPO/PPO/RLOO)`、`在线/自蒸馏 (OPD/OPSD)`、`偏好对齐 (DPO/SimPO)`、`过程奖励与验证器 (PRM/RLVR)`、`Rollout 与熵正则控制`
* **核心短语 (`phrases`)**：`"post-training"`, `"reinforcement learning from verifiable rewards"`, `"group relative policy optimization"`, `"policy gradient"`, `"advantage estimation"`, `"entropy collapse"`, `"entropy regularization"`, `"clip-higher"`, `"length penalty"`, `"overlong filtering"`, `"asynchronous rollout"`, `"off-policy reinforcement learning"`, `"importance sampling"`, `"on-policy distillation"`, `"on-policy self-distillation"`, `"self-distillation"`, `"generalized knowledge distillation"`, `"reverse KL"`, `"forward KL"`, `"trajectory distillation"`, `"rationale distillation"`, `"logit distillation"`, `"white-box distillation"`, `"teacher-student rollout"`, `"privileged context distillation"`, `"direct preference optimization"`, `"iterative preference"`, `"online preference"`, `"step-level preference"`, `"token-level preference"`, `"process reward model"`, `"outcome reward model"`, `"generative reward model"`, `"rubric-based reward"`, `"rule-based verifier"`, `"credit assignment"`, `"reward hacking"`
* **敏感缩写 (`acronyms`)**：`"RLVR"`, `"GRPO"`, `"DAPO"`, `"Dr.GRPO"`, `"PPO"`, `"RLOO"`, `"REINFORCE++"`, `"VinePPO"`, `"GSPO"`, `"OPD"`, `"OPSD"`, `"GKD"`, `"DPO"`, `"SimPO"`, `"ORPO"`, `"KTO"`, `"PRM"`, `"ORM"`, `"GenRM"`, `"RLHF"`, `"RLAIF"`

#### 3. 推理与计算扩展 (`reasoning`)
* **细分标签 (`sub_tags`)**：`Long CoT & Test-Time Scaling`、`MCTS / 搜索树推理`、`LLM Routing & 动态算力分配`、`Latent / 隐空间连续推理`、`Diffusion / 非自回归推理`
* **核心短语 (`phrases`)**：`"test-time scaling"`, `"test-time compute"`, `"inference-time scaling"`, `"long chain-of-thought"`, `"deliberative reasoning"`, `"slow thinking"`, `"self-correction"`, `"self-verification"`, `"backtracking"`, `"cognitive behaviors"`, `"overthinking"`, `"token-efficient reasoning"`, `"reasoning compression"`, `"concise reasoning"`, `"Monte Carlo Tree Search"`, `"tree of thoughts"`, `"graph of thoughts"`, `"beam search reasoning"`, `"best-of-N"`, `"weighted self-consistency"`, `"lookahead search"`, `"compute-optimal scaling"`, `"LLM routing"`, `"model routing"`, `"query routing"`, `"cascade inference"`, `"difficulty-aware routing"`, `"adaptive computation"`, `"early exit"`, `"budget-constrained reasoning"`, `"speculative reasoning"`, `"collaborative decoding"`, `"latent reasoning"`, `"continuous thought"`, `"implicit chain-of-thought"`, `"looped transformer"`, `"recurrent depth"`, `"diffusion language model"`, `"masked diffusion"`, `"diffusion reasoning"`, `"denoising chain-of-thought"`, `"timestep routing"`
* **敏感缩写 (`acronyms`)**：`"CoT"`, `"Long-CoT"`, `"MCTS"`, `"ToT"`, `"Coconut"`, `"dLLM"`, `"MDLM"`

#### 4. 自演化与递归改进 (`rsi-self-evolve`)
* **细分标签 (`sub_tags`)**：`RSI (递归自我改进)`、`Self-Play / 双模型协同演化`、`Questioner-Solver 课程生成`、`无外部数据自举 (Zero-Data)`、`Agent 工作流与代码自演化`
* **核心短语 (`phrases`)**：`"recursive self-improvement"`, `"self-evolving"`, `"self-evolution"`, `"self-improving"`, `"self-bootstrapping"`, `"autonomous improvement"`, `"continual self-improvement"`, `"zero-data reinforcement learning"`, `"label-free reinforcement learning"`, `"self-rewarding"`, `"meta-rewarding"`, `"self-play"`, `"asymmetric self-play"`, `"co-evolution"`, `"questioner-solver"`, `"proposer-solver"`, `"challenger-solver"`, `"generator-verifier"`, `"adversarial self-play"`, `"multi-agent debate"`, `"multi-agent co-evolution"`, `"automatic curriculum"`, `"curriculum evolution"`, `"self-questioning"`, `"self-challenging"`, `"frontier problem generation"`, `"evol-instruct"`, `"instruction evolution"`, `"failure-driven synthesis"`, `"error-driven synthesis"`, `"experience replay"`, `"workflow evolution"`, `"automated agent design"`
* **敏感缩写 (`acronyms`)**：`"RSI"`, `"SPIN"`, `"SPAG"`, `"SPC"`, `"STaR"`, `"ReST"`, `"R-Zero"`, `"AlphaEvolve"`

#### 5. 记忆机制 (`memory`)
* **细分标签 (`sub_tags`)**：`Agent 长期/情景/图谱记忆`、`参数化与神经记忆 (TTT/Titans)`、`KV Cache 压缩与淘汰`、`记忆读写与反思巩固`
* **核心短语 (`phrases`)**：`"agent memory"`, `"long-term memory"`, `"episodic memory"`, `"semantic memory"`, `"working memory"`, `"hierarchical memory"`, `"memory consolidation"`, `"memory reflection"`, `"memory retrieval"`, `"graph memory"`, `"experience memory"`, `"lifelong agent"`, `"memory bank"`, `"neural memory"`, `"test-time training"`, `"test-time memorization"`, `"fast weights"`, `"surprise-based memory"`, `"associative memory"`, `"memory-augmented transformer"`, `"explicit memory layer"`, `"linear attention memory"`, `"recurrent memory"`, `"knowledge editing"`, `"KV cache compression"`, `"KV cache eviction"`, `"token eviction"`, `"context compression"`, `"gist token"`, `"landmark attention"`, `"infinite context"`, `"memory slots"`
* **敏感缩写 (`acronyms`)**：`"TTT"`, `"Titans"`, `"MemGPT"`, `"HippoRAG"`, `"SnapKV"`, `"H2O"`, `"StreamingLLM"`
* **负向排除词 (`exclude_terms`)**：`"DRAM"`, `"SRAM"`, `"NAND flash"`, `"non-volatile memory"`, `"resistive memory"`, `"ferroelectric"`, `"Alzheimer"`, `"hippocampal slice"`

#### 6. 数据筛选与合成 (`data-selection`)
* **细分标签 (`sub_tags`)**：`Coreset / 数据剪枝与去重`、`Influence / 梯度归因筛选`、`Data Mixing / 动态领域配比`、`Rollout / 合成轨迹质检过滤`
* **核心短语 (`phrases`)**：`"data selection"`, `"data pruning"`, `"coreset selection"`, `"data attribution"`, `"influence function"`, `"gradient matching"`, `"data valuation"`, `"Data Shapley"`, `"instruction following difficulty"`, `"perplexity filtering"`, `"learnability score"`, `"reducible holdout loss"`, `"data mixing"`, `"domain mixing"`, `"domain reweighting"`, `"dynamic data mixing"`, `"online batch selection"`, `"curriculum data selection"`, `"submodular selection"`, `"facility location"`, `"semantic deduplication"`, `"data curation"`, `"model-based filtering"`, `"quality classifier"`, `"synthetic data curation"`, `"synthetic data filtering"`, `"trajectory filtering"`, `"rollout filtering"`, `"rejection sampling"`, `"difficulty calibration"`, `"pass-rate filtering"`, `"zero-variance filtering"`, `"seed selection"`
* **敏感缩写 (`acronyms`)**：`"LESS"`, `"TRAK"`, `"IFD"`, `"DEITA"`, `"DoReMi"`, `"RegMix"`, `"SemDeDup"`, `"FineWeb"`, `"DCLM"`
* **负向排除词 (`exclude_terms`)**：`"feature selection in microarray"`, `"antenna selection"`, `"portfolio selection"`, `"genomic selection"`

---

## 6. 论文召回、免密顶会核验与冷启动流水线

### 6.1 免密钥多源数据接入
1. **Hugging Face Daily 通道（每日高热流）**：调用免密 HF Daily API 获取近期论文元数据、摘要与 `upvotes`，准入条件为 `upvotes ≥ hf_min_upvotes`（默认 `20`）且命中任一激活领域召回规则。
2. **arXiv + 三级顶会录用核验通道（定向顶会流）**：按激活领域词库检索候选论文（跨进程严格遵守 arXiv 请求起始间隔 `≥ 3s`），经三级免密录用校验器筛选 `ICML / ICLR / CVPR / ACL / EMNLP / NeurIPS` 正式录用记录（排除 `Submitted to`、`Under review`、Workshop 与拒稿）：
   * **第一级**：解析 arXiv `comment` 与 `journal_ref`；
   * **第二级**：查询 OpenReview API v2 核验 `ICLR / ICML / NeurIPS` 录用状态与 `oral / spotlight / poster` 等级；
   * **第三级**：查询 DBLP 公开检索 API 精确核验标准化标题，补齐 `CVPR / ACL / EMNLP` 主会记录。

### 6.2 2025–2026 六大顶会代表作冷启动 (`figprism backfill`)
* 支持按年份与指定领域拉取六大顶会录用论文，按 `Oral` → `Spotlight` → `HF 高赞` → `OpenAlex 引用信号` 排序优选代表作。

### 6.3 在线单篇论文手动入库（链接 + 本地 PDF 双通道）
* 登录用户提交学术白名单链接（arXiv / HF / OpenReview）或上传本地 PDF（`≤ 50MB`、`≤ 150` 页）时直接进入拆解流水线。
* 本地 PDF 先算 `SHA-256` 判重，再扫描首页水印识别 `arXiv ID` 尝试关联元数据与 TeX 源码；纯本地稿件自动生成唯一 `doc_uid` 进入 PDF 矢量吸附裁切流水线。中断或失败的论文保留已发布图表，再次提交时自动断点续跑并跳过已入库图表。

### 6.4 单栏 / 双栏与跨栏规格自动识别
* **论文级版式 (`single` / `double`)**：优先解析 TeX `\documentclass` 与会议宏包，无源码时通过 `PyMuPDF` 统计正文文本块水平坐标分布判定。
* **图片级跨栏 (`full` / `column`)**：依据 `figure*` vs `figure` 或裁切框占版心宽度比例自动打标。

---

## 7. 高精度切图、多子图聚光灯、科研配色与分阶段并发

### 7.1 三级混合切图流水线 + 矢量墨迹吸附 (`Vector-Ink Snap`)
1. **Tier 1：arXiv TeX 源码内存安全提取**
   * 在内存中限额解析源码包，展开常见 `\input / \include` 识别 `figure / figure*`、`\caption` 与子图结构：
     * **单文件完整矢量原图**：直接提取源 `.pdf`（或高清位图；EPS 自动回退至论文 PDF 矢量切片）作为原始资产，并按最高 **450 DPI**（受 24MP 像素上限保护）光栅化生成超清 WebP。
     * **原生 TikZ / PGFPlots 图**：保存 `tikzpicture` 源码至 `tikz_code`，转入 Tier 2 从论文正式 PDF 整块裁切渲染图。
     * **多子图组合拼图**：保持整图排版完整性不拆散，先提取独立子图源 PDF 资产，再转入 Tier 2 裁切完整拼图。
2. **Tier 2：`DocLayout-YOLO` + `PyMuPDF` 矢量墨迹吸附**
   * `doclayout-yolo`（ONNX CPU）定位页面内 `figure` 初始种子框，并将正文段落、`table`、`figure_caption` 及页眉页脚设为排斥区；
   * 结合 `PyMuPDF` 底层真实矢量路径（`get_drawings`）、图像矩形与文字几何边界执行吸附收紧与安全留白扩展，辅以基于图注锚点的漏检兜底，导出局部矢量 `.pdf` 切片与超清/缩略 WebP。
3. **Tier 3：多子图热区定位与 `VisionJudge` 结构化分层判图**
   * 利用 `OpenCV` 多尺度模板匹配或 PDF 子图标签锚点计算子图归一化坐标 `[x1, y1, x2, y2]`，并为每个子图独立提取局部配色；
   * `VisionJudge` 严格按隔离层级输出 `macro_category`（`method` | `data_chart` | `case_study`）、对应专属 `sub_type`（方法图：`concept_teaser` / `system_pipeline` / `micro_mechanism`；实验图：`line_scaling` / `bar_ablation` / `scatter_pareto` / `radar_polar` / `distribution_density` / `heatmap_matrix`；定性图：`qualitative_case`），以及方法图专属三维标签（8 类 `primary_style/secondary_style`、6 类 `layout_topology`、4 项 `craft_badges`）或实验图专属 4 类 `chart_layout`（跨大类字段强制规范化为 `NULL` / `[]`，并自动同步向后兼容 `archetype`）；低置信度、几何兜底或模型异常结果自动标记 `review_status = 'needs_review'`。

### 7.2 科研级配色提取引擎 (`OKLab / OKLCH Scientific Palette`)
* 在 `OKLab` 空间聚类并在 `OKLCH` 空间剥离纯白背景与中性坐标轴灰阶，刻意保留科研架构图常用的低饱和淡彩填充色；
* 自动匹配同色相角、具显著明度阶差的「浅色填充底 + 深色描边」科研配对色卡（主力描边优先于边缘抗锯齿过渡像素），并映射至 12 色相桶支撑按色检索。

### 7.3 跨进程分阶段并发调度 (`Staged Concurrency`)
Web 后端、CLI 与定时任务通过数据卷内核文件锁共享同一套并发配额（可在 `config/local.yaml` 的 `pipeline` 段配置）：
* 默认上限：元数据/核验 `4`、PDF/TeX 下载 `3`、并发处理论文 `2`、独立 CPU 计算子进程 `2`（每进程 1 个推理线程）、视觉判图请求 `3`、WebDAV 上传请求 `4`、全局在途图表 `6`（单篇上限 `3`）；Web 端顶层待处理任务上限 `12`（单用户上限 `3`）。
* 原文 PDF 上传与版面计算重叠执行，单张图渲染、判图与上传流水化交错；但**必须等原文与当前图表全部版本化资产上传完成后**，才发布 SQLite 图表记录与 SSE 事件。

---

## 8. 存储架构、缓存隔离与容灾规范

### 8.1 冷热分离存储布局
* **远端 WebDAV（公开论文与图表重资产唯一持久真源）**：
  * 按论文目录保存原文 `paper.pdf`、带内容版本标识的图表资产（`thumb.webp`、`hd.webp`、`raw.pdf` 及可选子图矢量 PDF）与完整 `metadata.json` 快照（按论文加锁串行更新，防止旧快照覆盖新图）。
* **服务器本地磁盘（`data/`）**：
  * `data/figprism.db`：SQLite 主库（论文/图表索引、全文检索表，以及**仅存于 SQLite 的账号、会话、私有看板与个人历史**）。
  * `data/thumb_mirror/`：L1 缩略图本地持久镜像，列表浏览零远端穿透。
  * `data/hd_lru_cache/`：L2 超清大图与重切单页预览的本地 LRU 磁盘缓存池（超限按最近最少访问自动淘汰）。

### 8.2 HTTP 缓存头隔离与灾难恢复
1. **版本化静态图像不可变缓存**：`/api/assets/{thumb|hd|raw}/{id}.*?v={version_hash}` 强校验 `version_hash`（不匹配或旧版本直接返回 `404`），命中时返回 `Cache-Control: public, max-age=31536000, immutable`；重切后切换 `version_hash` 即刻绕过旧缓存。
2. **私有与状态接口禁缓存**：认证、个人历史、收藏看板、入库任务与管理接口统一返回 `Cache-Control: private, no-store`。
3. **SSE 无缓冲推送**：`/api/stream/events` 返回 `Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`。
4. **WebDAV 扫描重建与备份边界**：`figprism rebuild-from-webdav` 支持在独占维护锁下扫描远端 `metadata.json` 重建公开论文与图表索引；服务器迁移时须额外备份 `data/figprism.db` 与 `config/local.yaml` 以保留账号与私有看板数据。

---

## 9. 数据库 Schema、核心 API 与统一 CLI 契约

### 9.1 SQLite 核心表结构（`backend/figprism/db.py`）
* **认证、看板与个人足迹表**：
  * `users`：`id (PK), username (UNIQUE), password_hash, role ('admin'|'user'), is_active, created_at`
  * `sessions`：`jti (PK), user_id, expires_at`
  * `invite_codes`：`code (PK), created_by, used_by, expires_at, created_at`
  * `collections`：`id (PK), user_id, name, description, updated_at`
  * `collection_items`：`id (PK), collection_id, figure_id, focused_subitem_id, user_note, created_at`（唯一约束 `(collection_id, figure_id)`）
  * `view_history`：`user_id, figure_id, viewed_at`（联合主键 `(user_id, figure_id)`）
  * `palette_history`：`id (PK), user_id, figure_id, hex_code, copied_format, created_at`
* **领域、论文、图表与任务表**：
  * `domains`：`slug (PK), config (JSON), is_active`
  * `papers`：`id (PK), doc_uid (UNIQUE), file_sha256 (UNIQUE), title, authors (JSON), abstract, source_type, arxiv_id, venue, venue_year, venue_tier, hf_upvotes, layout_type, source_urls (JSON), domains (JSON), webdav_pdf_path, ingest_status, pdf_uploaded, uploaded_by, created_at`
  * `figures`：`id (PK), paper_id, fig_label, page_number, bbox (JSON), archetype, macro_category ('method'|'data_chart'|'case_study'), sub_type, primary_style, secondary_style, layout_topology, craft_badges_json (JSON), chart_layout, style_confidence, style_reason, taxonomy_locked (0|1), span_type, caption, width, height, aspect_ratio, blurhash, fonts (JSON), palette (JSON), color_buckets (JSON), subitems (JSON), tikz_code, extract_method, sub_tags (JSON), confidence, review_status, asset_base, version_hash, created_at`（建有复合索引 `idx_figures_macro_subtype`、`idx_figures_method_style`、`idx_figures_chart_layout`）
  * `asset_transfers`：`remote_path (PK), local_path, content_type, attempts, synced, last_error, updated_at`（本地持久暂存与后台 WebDAV 异步重试上传队列）
  * `figures_fts`：`FTS5(figure_id UNINDEXED, title, caption, fonts)`（附删除同步触发器）
  * `jobs`：`id (PK), user_id, kind, status, progress, message, payload (JSON), created_at, updated_at`
  * `repair_queue`：`id (PK), figure_id, requested_by, status, created_at`
  * `events`：`id (PK AUTOINCREMENT), kind, payload (JSON), created_at`（滚动保留最近 2000 条供 SSE 消费）

### 9.2 核心 HTTP API 契约（`/api`）
* **图表流与检视**：
  * `GET /api/figures/feed?group_by=paper|none`（默认 `group_by=paper`，每页默认 `16` 个论文组）：支持通用过滤参数（`domain/domains`, `sub_tags`, `tag_mode`, `venue/venues`, `layout/paper_layout`, `span/span_type`, `color/color_bucket`, `q`, `honors`, `show_cases/include_cases`）与强隔离大类参数 `macro_category=all|method|data_chart`（当 `macro_category=method` 时仅激活 `method_type`, `visual_style`, `topology`, `craft`；当 `macro_category=data_chart` 时仅激活 `chart_type`, `chart_layout`；跨大类残留参数后端自动忽略）。返回分页 `items`、命中 `total_papers` / `total_figures`，以及在通用过滤后、大类与子类过滤前独立统计的 `tab_counts: { all: {papers, figures}, method: {papers, figures}, data_chart: {papers, figures} }`。
  * `GET /api/figures`：单图平铺分页列表（共享同一套强隔离过滤参数）。
  * `GET /api/papers/{pid}/figures`：按自然图号排序获取指定论文的图表列表（支持传入外层画廊过滤参数返回命中子集与论文总图表数 `total` / `matched_count`，驱动检视器同文切换条与范围切换）。
  * `GET /api/figures/{fid}` / `PATCH /api/figures/{fid}` / `POST /api/figures/{fid}/view`：单图详情、登录用户分类与画风/排版修正（自动规范化跨大类互斥字段为 `NULL`/`[]`，置 `taxonomy_locked = 1` 并异步备份论文 `metadata.json`）及浏览足迹记录。
  * `GET /api/assets/{thumb|hd|raw}/{filename}?v={version_hash}` 及 `GET /api/figures/{fid}/subitems/{sid}/raw`、`GET /api/papers/{pid}/pdf`：版本校验静态资产与原文读取。
  * `GET /api/figures/{fid}/page`、`POST /api/figures/{fid}/recrop`、`POST /api/figures/{fid}/repair`：PDF 原页预览、框选矢量吸附重切与精修入队。
* **入库、实时流与个人空间**：
  * `GET /api/ingest/preview`、`POST /api/ingest/check`、`POST /api/ingest/link`、`POST /api/ingest/pdf`、`GET /api/jobs`、`GET /api/stream/events`。
  * `GET|POST /api/collections`、`GET|PATCH|DELETE /api/collections/{cid}`、`PUT /api/collections/{cid}/items`、`PUT /api/collections/{cid}/items/bulk`（校验所有权与全部图表存在性，去重写入并保留已有笔记与子图聚焦）、`DELETE /api/collections/{cid}/items/{fid}`、`GET /api/collections/{cid}/export`。
  * `POST /api/me/palette-history`、`GET /api/me/history?kind=views|colors`。
* **认证与管理**：
  * `GET /api/auth/me`、`POST /api/auth/login`、`POST /api/auth/logout`、`POST /api/auth/register`。
  * `GET /api/admin/overview`、`GET /api/admin/pipeline`、`POST /api/admin/invites`、`PATCH /api/admin/users/{uid}`、`PUT /api/admin/domains`、`POST /api/admin/sync`。

### 9.3 统一 CLI 命令契约
```bash
# 1. 初始化站长管理员账号（交互输入密码或读取 FIGPRISM_ADMIN_PASSWORD）
figprism auth create-admin --username admin

# 2. 日常定时增量同步（HF Daily + 近期 arXiv 顶会核验，逐图流式发布）
figprism sync --source all --days 3 --limit 50 --vision-driver openai_mini

# 3. 2025-2026 六大顶会代表作冷启动（支持全量或指定单个领域回溯）
figprism backfill --years 2025,2026 --domains all --limit-per-domain 50

# 4. 单篇论文拆解入库（兼容学术链接或本地 PDF 路径）
figprism ingest --input "https://arxiv.org/abs/2501.00663" --force-include
figprism ingest --pdf "/tmp/paper.pdf" --domains "post-training,rsi-self-evolve" --venue "ICLR 2026"

# 5. 待复核/待精修队列查询与重切写回
figprism queue list --type review_or_repair --json
figprism recrop --figure-id <id> --page 4 --bbox "0.08,0.12,0.92,0.48" --snap-vector

# 6. 存量图表免重切并发回填分层分类与三维画风/排版标签（自动跳过 taxonomy_locked=1）
figprism retag-taxonomy --scope all --concurrency 8 --vision-driver openai_mini

# 7. 从远端 WebDAV 全量扫描重建公开论文与图表索引
figprism rebuild-from-webdav

# 8. 查看跨进程分阶段并发流水线实时负载与配额
figprism pipeline status
```
