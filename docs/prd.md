# FigPrism — 科研顶会画图灵感与配色拆解平台 PRD (v2.0 完整版)

## 1. 产品定位与核心目标

**FigPrism** 是一个**以学术图表（Figure）为一等公民**的科研绘图灵感收集、检索、构图拆解与配色提取平台。系统自动从 `Hugging Face Daily`、`arXiv`、`OpenReview` 与 `DBLP` 筛选特定研究方向的六大顶会录用论文与高热讨论工作，高精度提取其中的**方法架构图**与**数据实验图**；支持登录用户通过链接或本地 PDF 在线补充论文，并提供多子图聚光灯拆解、科研级深浅配对取色、原始矢量图下载与灵感看板（Moodboard）管理。

### 1.1 核心非功能性指标
1. **首屏秒开与渐进懒加载**：重资产存储于远端 WebDAV，服务器本地保留 SQLite 索引与轻量缩略图镜像；配合 `BlurHash` 占位、固定宽高比防抖骨架与 Cloudflare 边缘缓存，瀑布流首屏可交互时间（TTI）通常控制在 `500ms` 以内。
2. **流式原子化热更新**：无论是定时同步还是在线上传单篇 PDF，后台每处理完 **1 张图** 即刻落盘并通过 `SSE (Server-Sent Events)` 推送至前端增量渲染，无需等待整批任务完成。
3. **动态领域可扩展**：研究领域、三级召回词库与视觉判图准则均由配置文件与数据库双端驱动，无需修改业务代码即可扩展新领域并单独触发历史代表作冷启动。
4. **读写权限安全隔离**：支持公网免登录 `Guest` 只读访问（看图、搜索、吸管取色、下载矢量图），登录用户独享收藏夹看板、双轨历史记录、在线加论文与切图修正，默认关闭公网公开注册。

---

## 2. 技术栈与系统架构

* **部署环境**：Linux 云服务器（Docker Compose 单仓编排），前置 **Cloudflare** 域名代理与 CDN 缓存，远端连接 **WebDAV** 存储卷（异步 `httpx` WebDAV 客户端或 `rclone` 守护进程）。
* **前端技术栈**：`Next.js (App Router, TypeScript)` + `React` + `Tailwind CSS` + `shadcn/ui` + `Lucide Icons`，状态管理采用 `TanStack Query` + `Zustand`。
* **后端技术栈**：`Python 3.11+` + `FastAPI` + `SQLite (开启 WAL 并发读写模式 + FTS5 全文检索引擎)`。
* **认证与权限**：`JWT (HttpOnly, Secure, SameSite=Lax Cookie)` + `Argon2` 密码哈希，RBAC 权限中间件。
* **切图与色彩引擎**：
  * 源码提取：arXiv e-print tarball 解包 + TeX 宏展开解析 `figure / figure* / subfigure / tikzpicture`。
  * 版面检测与矢量吸附：轻量独立包 `doclayout-yolo`（ONNX Runtime / PyTorch，单页 CPU 推理通常约 `0.15~0.3s`）+ `PyMuPDF (fitz)`（矢量墨迹吸附微调、450 DPI 超采样光栅化、局部矢量 PDF 切片导出、内嵌字体与单双栏检测）+ `OpenCV`（多子图模板匹配定位）。
  * 色彩科学：`Pillow` + `numpy / scikit-learn`（`OKLCH` 感知均匀色彩空间背景剥离与同色相深浅配对聚类）。
* **视觉判图双驱动引擎 (`VisionJudge`)**：
  * `openai_mini` 模式（默认全自动）：调用 OpenAI 标准视觉小模型（如 `gpt-4.1-mini` / `gpt-4o-mini`，开启 Structured Outputs JSON Schema 强约束），完成图表分类、细分打标与切图完整性自检。
  * `codex_subagent` 模式（Agent 协同与疑难精修）：支持导出待判图/待修图清单，由 Codex CLI 定时任务派生并发视觉 Subagent 批量打标，或针对疑难切偏图表读取整页高清渲染图执行重定位裁切。

---

## 3. 视觉美学与 UI/UX 详细设计规范（浅色画廊体系）

### 3.1 浅色系设计哲学：「画廊装裱感 (Editorial Gallery Matting)」
由于绝大多数科研图表自身为 `#FFFFFF` 纯白背景，若网页底色同样使用纯白，图表边缘会与页面粘连；若使用深色模式，白底图表会产生刺眼眩光。因此全站采用**微冷宣纸灰画布 + 纯白装裱卡片 + 零干扰中性强调色**的浅色设计体系，确保 UI 本身不抢夺科研图表自身的配色视觉焦点。

#### 全局色彩设计语义 Token
| Token 名称 | 色值 (HEX) | 适用位置与视觉作用 |
| :--- | :--- | :--- |
| `--bg-canvas` | `#F6F7F9` | 全局页面底层画布背景（柔和微冷灰，与纯白卡片拉开自然层次，久看不累） |
| `--bg-surface` | `#FFFFFF` | 瀑布流卡片底板、详情侧边栏、模态框背景（还原论文原生白纸环境，无偏色） |
| `--bg-subtle` | `#EEF1F6` | 未激活筛选胶囊、输入框底色、代码展示块底色、悬浮次级按钮 |
| `--bg-drafting` | `#F1F5F9` | 详情页大图检视器底层画布（配合 `#CBD5E1` `16px` 间距微弱点阵，营造设计软件白板质感） |
| `--border-hairline` | `#E2E8F0` | 卡片默认 `1px` 细描边、分割线（干净克制） |
| `--border-hover` | `#CBD5E1` | 卡片悬停描边、输入框聚焦前描边 |
| `--text-primary` | `#0F172A` | 主标题、核心正文、激活态标签文字（深石板黑，高对比易读） |
| `--text-secondary` | `#475569` | 论文作者、图注 Caption 正文、次级按钮文字 |
| `--text-muted` | `#94A3B8` | 宽高比数值、字体参数、时间戳、快捷键提示符 |
| `--accent-ink` | `#18181B` | 主操作按钮底色（如「+ 添加论文」、激活态胶囊），保持无彩色中性克制 |
| `--accent-brand` | `#4F46E5` | 焦点环、聚光灯选中边框、交互链接点缀色（辅以 `#EEF2FF` 浅靛蓝底色） |
| `--badge-oral` | `#FEF3C7` / `#B45309` | `Oral / Spotlight` 顶会荣誉徽章（暖琥珀浅底深字） |
| `--status-warn` | `#FEF9C3` / `#A16207` | `待复核切图 (needs_review)` 温和提示色 |

#### 字体排印规范
* **界面与中文**：`Inter`, `Geist Sans`, `PingFang SC`, `HarmonyOS Sans SC`, `Microsoft YaHei`, `sans-serif`。
* **图注阅读字体**：默认无衬线，详情页支持一键切换 `Source Serif 4 / Newsreader` 学术衬线体阅读长 Caption。
* **工程参数与代码**：`JetBrains Mono`, `Geist Mono`, `monospace`（用于展示 `HEX` 色值、宽高比 `2.42:1`、arXiv ID 与 `TikZ` 代码）。

---

### 3.2 核心页面布局与交互细节

#### 页面一：灵感瀑布流主页 (`/`)
1. **吸顶毛玻璃导航栏（高度 `56px`，`backdrop-filter: blur(12px)`，底色 `rgba(246, 247, 249, 0.88)`）**
   * **左侧**：`FigPrism` 极简棱镜图标 + **全局命令搜索框**（宽度 `360px`，支持快捷键 `⌘K / Ctrl+K` 唤醒；支持搜标题、方法名、Caption 词、字体名如 `font:Helvetica`、宽高比如 `ratio:>2.0`，若直接粘贴 arXiv 链接则提示一键抓取）。
   * **中部快捷视图切换器（Segmented Control）**：`[全部精选]` | `[方法架构图]` | `[数据实验图]`（默认自动折叠 `Case Study` 噪音图，右侧提供小开关 `[显示定性 Case]`）。
   * **右侧功能区**：
     * `Guest` 视角：显示轻量胶囊 `[访客只读]` + `[登录]` 按钮。
     * `User / Admin` 视角：深色主按钮 `[+ 添加论文]`、`[灵感看板]`、`[浏览与取色足迹]`、后台任务脉冲呼吸灯（有同步任务时亮起柔和绿点）及个人头像菜单（含列数密度切换：`舒适 3 列 / 标准 4 列 / 紧凑 5 列`）。
2. **三维正交折叠筛选栏（位于导航栏下方，支持一键收起释放纵向视野）**
   * **第一行（研究领域与子标签）**：横向排列领域圆角胶囊（如 `● 多模态与幻觉`、`● 后训练策略`、`● 推理扩展`、`● 自演化 RSI`、`● 记忆机制`、`● 数据筛选`），点击某个领域后，其下方平滑展开该领域的细分 `sub_tags` 供二次收窄（支持多选并集/交集）。
   * **第二行（版式 × 顶会 × 图表类型 × 色谱）**：
     * **顶会芯片**：`ICLR` `ICML` `CVPR` `ACL` `EMNLP` `NeurIPS` `HF 高热` + `[★ 仅看 Oral/Spotlight]` 开关；
     * **版式与跨栏图标组**：`[单栏论文]` `[双栏论文]` | `[▭ 通栏宽图]` `[▯ 半栏窄图]`；
     * **图表形态芯片**：`Teaser` `主框架 Pipeline` `局部机制` `折线/Scaling` `柱状/消融` `散点/雷达` `热力分布`；
     * **12 色相科研色谱球**：一排 `16px` 圆形柔和色球（红、橙、琥珀、翠绿、青、天蓝、钴蓝、靛紫、品红、莫兰迪低饱和、冷暖撞色），点击色球即可筛选包含对应主色系的图表；
     * 最右侧显示实时计数 `共 1,420 张图表` 与 `[重置筛选]`。
3. **瀑布流卡片解剖结构 (`FigureCard`)**
   * **响应式列数**：`≥1536px` 默认 4 列（保证复杂架构图字迹清晰可读），`1100~1535px` 3 列，`768~1099px` 2 列，`<768px` 1 列；卡片间距 `20px`，圆角 `12px`。
   * **静止态（极简克制，突出图表本身）**：
     * **装裱留白区**：卡片上部分为 `#FFFFFF` 纯白画框，四周固定 `12px` 内边距（确保贴边裁切的矢量图不会紧贴卡片圆角边缘），严格按图片真实 `aspect_ratio` 预设容器高度，加载前呈现柔和 `BlurHash` 渐变，图片加载完成后 `200ms` 淡入，避免页面跳动（CLS ≈ 0）。
     * **组合图角标**：若该图包含多个子图（如 `(a)(b)(c)`），左上角悬浮半透明磨砂白小胶囊 `[田 含 3 子图]`。
     * **底部信息条（高度 `38px`，顶部分割线 `#F1F5F9`）**：左侧显示顶会年份徽章（如 `ICLR'26`）+ 版式简写（`双栏·通栏`）；右侧整齐排列 **5 枚 `14×14px` 圆角主色块**——**无需点开大图，鼠标直接点击小色块即可一键复制 `HEX` 色值**，并在卡片上方弹出轻提示 `已复制 #2B6CB0`。
   * **悬停态微交互（Hover，`160ms ease-out`）**：
     * 卡片轻微上浮 `2px`，阴影变为柔和弥散投影 `0 10px 28px -8px rgba(15, 23, 42, 0.08)`，边框加深至 `#CBD5E1`。
     * 画框右上角淡入两个快捷圆形图标按钮：`[⭐ 收入看板]`（点击默认存入最近使用的看板，长按/悬停旁侧箭头可秒选其他看板；未登录访客悬停提示 `登录后可收藏`）与 `[↗ 原文 P.4]`（一键新标签页打开 PDF 并精准跳至第 4 页）。
     * 画框底部浮现一层极浅渐变条，展示单行截断的图号与标题（如 `Fig. 2: Overview of GRPO Co-Evolution Framework`）。

---

#### 页面二：图表深度拆解抽屉 (`Figure Inspector Modal`)
点击任意卡片弹出居中大尺寸工作台模态框（宽 `92vw`、高 `90vh`，最大宽 `1680px`，圆角 `16px`，背景遮罩 `rgba(15, 23, 42, 0.35)` 毛玻璃），支持全键盘流式操作：
* **全局快捷键**：`← / →` 切换上一张/下一张图；`Space` 适应窗口 / `100%` 切换；`I` 开启/关闭放大镜吸管；数字键 `1~9` 依次切换子图 `(a)~(i)` 聚光灯，`0` 回到整图；`S` 收藏当前图；`Esc` 关闭。

1. **左舱：高精度交互画布区（占宽 `68%`，点阵浅灰底 `#F1F5F9`）**
   * **顶部悬浮胶囊控制栏（居中悬浮于画布上方 `16px`）**：
     * **多子图聚光灯切换器（仅当检测到 `≥2` 个子图时显示）**：显示 `[整图概览]` `[(a)]` `[(b)]` `[(c)]` 胶囊及 `[悬停热区感应]` 开关。点击 `[(b)]` 或在开启感应后鼠标移入子图 `(b)` 区域时，画布其余子图区域平滑叠加 `45%` 不透明度深石板灰遮罩（`rgba(15, 23, 42, 0.45)`），唯独子图 `(b)` 保持 `100%` 纯白高亮并带 `2px` 精致描边。
     * **画布工具组**：`[吸管取色 (I)]`、`[- 缩放比例 +]`、`[适应屏幕]`、`[背景切换：点阵灰 / 纯白]`。
     * **切图纠错入口（仅登录用户可见）**：`[✂️ 3秒框选重切]`、`[✨ 让 Codex 精修]`（若该图处于 `needs_review` 状态，此处亮起温和琥珀色提示点）。
   * **像素级放大镜吸管（Loupe Eyedropper）**：激活后鼠标变为十字准星，旁侧跟随一个直径 `112px` 的圆形高清像素网格放大镜（放大 8 倍），中心格高亮当前像素，底部实时显示 `#HEX` 色值；左键单击即复制色值，并自动飞入登录用户的「取色历史剪贴板」。

2. **右舱：科研参数与配色拆解面板（占宽 `32%`，最小宽 `380px`，纯白底 `#FFFFFF` 独立滚动）**
   * **模块 1：论文头部与多源直达**
     * 展示完整论文标题、作者列表、录用标签（如 `ICML 2026 Oral`、`HF 👍 86`）。
     * 一排轻量外链胶囊：`[arXiv PDF #Page 3]`、`[arXiv HTML]`、`[HF 讨论区]`、`[OpenReview 审稿页]`、`[预览 WebDAV 原文]`。
   * **模块 2：智能联动图注 (`Caption`)**
     * 完整展示提取出的原文 Caption，自动高亮其中的 `(a)`、`[Left]` 等标记——**点击文字里的 `(b)` 同样会联动触发左侧画布聚焦子图 `(b)`**。
   * **模块 3：科研黄金配对色板（随聚光灯动态切换整图配色 / 当前子图独立配色）**
     * **「浅色填充底 + 同色相深色描边」配对胶囊**：直观还原顶会架构图精髓——每个配对展示为一个左侧填满浅底色（如 `#EBF3FA`）、外圈套着 `2px` 同色系深描边（如 `#2563EB`）的双层色卡，分别标出 `Fill` 与 `Stroke` 的色值，点击任一半边直接复制。
     * **重点强调色与坐标轴灰阶参考行**。
     * **多格式一键导出栏**：顶部提供格式切换小标签 `HEX` | `RGB` | `Matplotlib` | `LaTeX xcolor` | `Tailwind/CSS`，下方文本框实时生成对应代码（如 `\definecolor{figBlueFill}{HTML}{EBF3FA}`），支持一键复制整套调色盘。
   * **模块 4：画图工程透视与矢量资产下载**
     * 紧凑四宫格展示：`宽高比 2.38 : 1`、`排版属性 双栏论文 · 通栏宽图`、`内嵌字体 Helvetica Neue, Arial`、`提取方式 TeX 原生矢量`。
     * 主下载按钮：`[⬇️ 下载原始矢量 PDF]`（若当前聚光灯正锁定在子图 `(b)` 且存在独立源码子文件，按钮自动变为双选：`[⬇️ 下载子图 (b) 矢量 PDF]` | `[整图切片 PDF]`，可直接拖入 Illustrator、Figma 或 PPT 无损拆解箭头与圆角）。
     * 若 `has_tikz == true`，额外展示 `[</> 查看与复制 TikZ / PGFPlots 源码]` 折叠抽屉（带 LaTeX 语法高亮）。
   * **模块 5：钉入灵感看板**
     * 下拉选择目标看板 + 单行备忘输入框（占位提示：*“记一笔灵感，如：学它用虚线区分 Rollout 与更新流...”*）+ `[保存至看板]`（若处于子图聚焦态，支持勾选 `默认锁定在子图 (b)`）。

---

#### 页面三：网页 3 秒手动框选重切器（详情页内嵌态）
当登录用户在详情页点击 `[✂️ 3秒框选重切]` 时，左侧画布无需跳转新页面，直接平滑切换为 **PDF 原页高清裁切工作台**：
* 画布加载该图所在的完整 PDF 页面（顶部带 `[◀ 上一页]` `[第 4 / 18 页]` `[下一页 ▶]`，应对跨页排版）。
* 原裁切框以带 8 个拖拽控制点的蓝色选框呈现；用户可直接拖拽修正或重新拉框。
* 顶部默认勾选 **`[✨ 松手自动矢量墨迹吸附]`**：用户只需粗略框住图表，松开鼠标瞬间，选框自动贴合底层 PDF 真实矢量路径与坐标轴文字外沿并留出均匀 `8pt` 白边。
* 点击 `[确认重切并刷新配色]`，约 `1~2 秒` 完成 450 DPI 重渲染、WebDAV 覆盖与配色重算，即刻回到高清检视态。

---

#### 页面四：在线「+ 添加论文」模态框与右下角流式任务浮窗
1. **双 Tab 极简录入弹窗（宽 `540px`）**
   * **Tab 1：`通过链接或编号添加`**：单行大输入框，支持粘贴 `arXiv ID / 链接`、`HF Papers 链接` 或 `OpenReview 链接`，粘贴后自动异步预览识别出的论文标题。
   * **Tab 2：`上传本地 PDF 文件`**：浅灰虚线拖拽区（上限 `50MB`），拖入后前端秒算 `SHA-256` 判重，并提示是否嗅探到内置 arXiv 编号。
   * **底部快捷归档选项（可选）**：手动补充领域标签、自定义会议标记（如 `CVPR 2026` 或 `盲审预印本`）、勾选 `[解析完成后自动收入看板：▾ 选择看板]`。
2. **非阻塞流式进度胶囊（固定于右下角 `24px`）**
   * 提交后弹窗立即关闭，右下角浮现精致白底进度卡片：`正在拆解 2602.12345 · 已切出 3/6 张图`，进度条平滑推进。
   * 每切完 1 张图，瀑布流顶部浮现一条不打断当前阅读滚动位置的温和胶囊：`✨ 刚有 3 张新图表热更新入库 [点击刷入顶部]`。

---

#### 页面五：灵感收藏看板 (`/collections`) 与双轨足迹 (`/history`)
1. **灵感收藏看板 (`Moodboard`)**：
   * 左侧为看板目录树（如 `新论文 Fig.1 动机图参考`、`GRPO 训练曲线配色`、`左图右表紧凑排版`），右侧为网格画布。
   * 每张收藏卡片下方直接常驻显示用户当时写下的**黄色便利贴风格浅色备忘录**与 5 色条；若收藏时锁定了某个子图，卡片自动微缩高亮对应区域。
   * 看板右上角提供 **`[📦 打包导出本看板]`**：一键下载 `.zip` 压缩包，内含所有收藏图表的**原始矢量 `.pdf`、450 DPI `.webp` 大图以及汇总生成的 `palettes.tex / palettes.py` 色卡文件**。
2. **个人双轨历史页 (`/history`)**：
   * **Tab A `最近浏览图表`**：按「今天 / 昨天 / 本周 / 更早」时间轴分组展示点开过的图表卡片。
   * **Tab B `吸管取色剪贴板`**：以精致色卡贴片形式按时间倒序排列用户每次用放大镜吸取或点击复制过的颜色，左侧为大色块与 `HEX / RGB`，右侧关联来源论文缩略小图（点击色块再次复制，点击小图跳回原图）。

---

## 4. 账号体系与角色权限矩阵 (Auth & RBAC)

默认设置环境变量 `ALLOW_PUBLIC_SIGNUP=false`（关闭公网自由注册，防止匿名爬虫消耗模型额度或污染 WebDAV）。首次部署通过环境变量或 CLI 创建管理员主账号；管理员可在 `/admin` 生成一次性邀请链接或直接开设团队/好友子账号。

| 功能模块 | `Guest`（未登录访客） | `User`（已登录成员） | `Admin`（管理员/站长） |
| :--- | :---: | :---: | :---: |
| 瀑布流浏览、三维标签过滤、全文检索、12 色相筛选 | 支持 | 支持 | 支持 |
| 查看 450 DPI 超清大图、多子图聚光灯切换、放大镜吸管取色 | 支持 | 支持 | 支持 |
| 一键复制多格式配色、下载原始矢量 PDF、查看 TikZ 源码、跳转原文 | 支持 | 支持 | 支持 |
| **灵感收藏夹看板 (Moodboard)**：创建、收藏、写笔记、打包导出 | 仅提示登录 | **独立私有空间** | **独立私有空间** |
| **双轨个人足迹**：图表浏览历史 + 吸管/复制取色剪贴板历史 | 不记录 | **自动云端同步** | **自动云端同步** |
| **在线添加单篇论文**（粘贴 arXiv/OpenReview 链接或上传本地 PDF） | 禁止 | **支持** | **支持** |
| **切图纠错**：3 秒手动画框重切、呼叫 Codex 异步修图、修正图表标签 | 禁止 | **支持** | **支持** |
| **系统控制中心 (`/admin`)**：动态增删改领域词库、触发同步/冷启动、账号管理 | 禁止 | 禁止 | **支持** |

---

## 5. 动态可扩展领域引擎与预置词库

研究领域定义于 `config/domains.yaml` 并与 SQLite `domains` 表双向同步。新增研究方向无需改动代码，只需在后台或配置文件新增词条即可立即参与日常增量同步，并支持单独对该新领域执行历史论文回溯。

### 5.1 三级精准召回匹配规则
* `phrases`：不区分大小写的短语匹配（检索标题、摘要与 HF `ai_keywords`）。
* `acronyms`：**严格大小写敏感的全词边界匹配**（避免 `OPD`、`VCD`、`TTT`、`LESS` 等缩写误匹配普通英文词汇）。
* `exclude_terms`：负向排除词（当命中排除词且未命中核心强特征短语时自动过滤，剔除跨学科重名噪音）。

### 5.2 初始预置 6 大核心领域词库

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
1. **Hugging Face Daily 通道（每日高热流）**：
   * 调用免密钥 HF Daily API 与匿名 HF MCP，每日获取最新 50 篇论文元数据、摘要、`ai_keywords` 与 `upvotes`。
   * 准入条件：`upvotes ≥ 20`（阈值可配置）**且**命中任一激活领域的召回规则。
2. **arXiv + 三级顶会录用核验通道（定向顶会流）**：
   * 调用免密钥 arXiv MCP / API 按激活领域词库检索候选论文，随后经过**三级免密录用校验器**（仅保留命中 `ICML / ICLR / CVPR / ACL / EMNLP / NeurIPS` 正式录用或满足 HF 高热的论文）：
     1. **第一级（arXiv 元数据直读）**：解析 `comment` 与 `journal_ref` 字段匹配六大顶会及年份（排除含 `Submitted to`、`Under review`、`Preprint` 的未定稿表述，Workshop 默认关闭但可开关配置）。
     2. **第二级（OpenReview API v2 核验）**：对未注明但落入会议周期的论文，按标准化标题查询公开免密的 OpenReview API v2，精准获取 `ICLR`、`ICML`、`NeurIPS` 的 `Accept` 状态及 `Oral / Spotlight / Poster` 细分等级。
     3. **第三级（DBLP 公开检索 API 核验）**：补齐 `CVPR`、`ACL`、`EMNLP` 正式会议录用记录。

### 6.2 2025–2026 六大顶会代表作冷启动 (`figprism backfill`)
* 首次建库或新增研究领域时，自动拉取 **2025–2026 年六大顶会**中命中各激活领域的录用论文。
* **优选截断策略**：每个领域默认精选 Top `50` 篇代表作（数量可配置），按以下权重排序优选：`Oral` → `Spotlight` → `HF Daily 历史高赞` → `OpenAlex 近期高引用增速`，确保初始图库画风精良、代表性强。

### 6.3 在线单篇论文手动入库（链接 + 本地 PDF 双通道）
* 登录用户提交链接（arXiv / HF / OpenReview）或上传本地 PDF（单文件 `≤ 50MB`）时，默认启用 `force_include=true`，跳过点赞数与顶会门槛直接拆解入库。
* 本地上传 PDF 先计算 `SHA-256` 判重，再扫描首页页眉/边栏水印：若识别到合法 `arXiv ID`，自动关联 arXiv 元数据并尝试拉取 TeX 源码走无损提取；若为纯本地盲审稿/预印本，则生成 `local_{ulid}` 标识，提取首页标题与作者后直接进入 PDF 矢量吸附裁切流水线。

### 6.4 单栏 / 双栏与跨栏规格自动识别
* **论文级版式 (`single` / `double`)**：有 TeX 源码时直接解析 `\documentclass` 与会议宏包（如 `iclr`、`neurips` 为单栏；`icml`、`cvpr`、`acl`、`twocolumn` 为双栏）；仅 PDF 时通过 `PyMuPDF` 统计正文第 2~3 页文本块的水平坐标双峰分布判定。
* **图片级跨栏 (`full` / `column`)**：根据 `\begin{figure*}` vs `\begin{figure}` 或裁切框宽度占版心宽度比例（`> 65%` 标为通栏宽图，其余标为半栏窄图）自动打标。

---

## 7. 高精度切图、多子图聚光灯与科研配色引擎

### 7.1 三级混合切图流水线 + 矢量墨迹吸附 (Vector-Ink Snap)

#### Tier 1：arXiv TeX 源码原生提取（覆盖约 85%~90% 的 arXiv 论文）
* 从 `export.arxiv.org/e-print/{arxiv_id}` 下载源码包（严格遵守约 3 秒/次的请求礼仪间隔），递归展开 `\input` 解析所有 `figure / figure*` 环境、`\caption` 与标签。
* **三种结构智能分流**：
  1. **单文件完整原图**：环境内仅含单个 `\includegraphics` 且无外层复杂拼合标注时，直接提取作者上传的一手 `.pdf / .eps / 高清位图` 作为 **L3 原始矢量资产**，并用 `PyMuPDF` 按 **450 DPI** 渲染超清 WebP。
  2. **原生 TikZ / PGFPlots 代码图**：提取完整 `tikzpicture` LaTeX 绘图代码存入数据库供网页端查看复制，同时转入 Tier 2 从论文正式 PDF 整块裁切渲染图。
  3. **多子图组合拼图（含多个 `\subfigure` / `\subfloat` / 多张 `\includegraphics`）**：**不在瀑布流中拆成零碎小图**；先将源码包内的各独立子图 `.pdf` 保存为子资产，再携带主图 Caption 锚点转入 Tier 2 整块裁切完整大图，保留原汁原味的跨子图排版比例与共享图例。

#### Tier 2：轻量 `DocLayout-YOLO` + `PyMuPDF` 矢量墨迹吸附（处理无源码 PDF 与多子图整图）
1. **视觉语义定界**：使用轻量 `doclayout-yolo` 识别页面内的 `figure`、`figure_caption`、`table`、`text`（正文段落）及页眉页脚，分离“左图右表 (`minipage`)”并记录 `confidence` 分数。
2. **矢量墨迹吸附精修 (`Vector-Ink Snap`)**：
   * 以 YOLO 预测的 `figure` 框作为初始种子框 `B_init`，将同页的正文段落、`table`、`figure_caption`、页眉页脚设为排斥区 `Z_exclude`；
   * 调用 `PyMuPDF` 读取该页底层的真实矢量路径（`page.get_drawings()`）、内嵌图像矩形（`page.get_image_rects()`）和细粒度文字块（`page.get_text("rawdict")`）；
   * 对所有不落入 `Z_exclude` 且与 `B_init` 相交（或间距小于 `6pt` 吸附阈值）的底层几何元素求精确最小外接并集 `B_tight`，自动向外包住贴边的坐标轴标题与悬浮图例、向内收紧多余留白；
   * 在 `B_tight` 四周均匀扩展 `8pt` 安全留白（不侵入排斥区），按 **450 DPI** 超采样光栅化生成超清 WebP，并用 `page.show_pdf_page()` 导出对应的局部矢量 `.pdf` 切片。

#### Tier 3：多子图热区定位与视觉质检 (`VisionJudge`)
* **子图热区计算**：若存在 TeX 独立子图文件，使用 `OpenCV` 多尺度模板匹配（`cv2.matchTemplate`）在整图上算出各子图精确归一化坐标 `[x1, y1, x2, y2]` 并关联 `\subfigure[...]` 子图注；若无源码但存在 `(a)(b)(c)` 结构，结合 PDF 文本锚点与空白通道分割（或 `VisionJudge` 返回的子图框）生成聚光灯热区，并对每个子图单独运行一次局部配色提取。
* **分类与裁切质检**：`VisionJudge`（支持 `openai_mini` 全自动或 `codex_subagent` 协同模式）根据压缩预览图与 Caption 判定图表视觉类型（`Teaser`、`Pipeline`、`Micro-Mechanism`、`Curve`、`Bar`、`Scatter/Radar`、`Heatmap`、`Case Study`）及细分领域标签，同时输出 `crop_ok` 布尔值；若 `confidence ≤ 0.75` 或 `crop_ok == false`，自动标记 `review_status = needs_review`。
* **工程参数透视**：自动用 `PyMuPDF` 提取图片精确宽高比与内嵌字体家族名称（清洗子集前缀如 `BCDFEE+ArialMT` → `Arial`）。

---

### 7.2 科研级配色提取引擎 (`OKLCH Scientific Palette`)
1. **背景与坐标轴剥离**：将采样图转换至感知均匀的 `OKLCH` 色彩空间，剔除高亮纯白底像素（`L ≥ 0.96` 且 `C ≤ 0.02`）与黑灰坐标轴文字像素（`C ≤ 0.025`，单独聚类出 1~2 个边框灰参考色）。
2. **「浅色填充底 + 同色相深色描边」成对识别**：对彩色像素聚类提取 5~6 个主色；检测色相角接近（`ΔHue ≤ 25°`）但明度存在显著阶差（如浅底 `L > 0.85` 与深框 `L < 0.60`）的颜色对，自动组装为科研配对色卡。
3. **色彩检索索引**：入库时将主色映射至 12 色相桶与饱和度标签写入索引表，支撑前端毫秒级按色系筛选。

---

## 8. 存储架构、Cloudflare 协同与防卡顿规范

### 8.1 冷热分离目录结构
* **远端 WebDAV（重资产唯一持久真源）**：
  ```text
  /figprism/
    └── papers/{year_or_uploads}/{doc_uid}/
         ├── metadata.json               # 完整论文、图表、子图坐标与配色备份（支持灾难恢复）
         ├── paper.pdf                   # 论文完整原文 PDF
         └── figures/
              ├── fig_01_thumb.webp      # L1: 宽度 480px WebP 缩略图 (约 25~45KB)
              ├── fig_01_hd.webp         # L2: 450 DPI 超清大图 WebP (约 300~800KB)
              ├── fig_01_raw.pdf         # L3: 原始矢量 PDF 或局部矢量切片
              ├── fig_01_sub_a_raw.pdf   # (可选) TeX 源码中的独立子图矢量原文件
              └── fig_01_tikz.tex        # (可选) 提取出的原生 TikZ 源码
  ```
* **服务器本地磁盘（轻量高速热层）**：
  * `data/figprism.db`：SQLite 数据库（存全部元数据、`blurhash`、宽高尺寸、配色、账号、收藏夹与历史记录）。
  * `data/thumb_mirror/`：**L1 缩略图本地持久镜像**（每张约 `35KB`，1 万张仅占约 `350MB` 本地空间，使瀑布流浏览完全不穿透等待远端 WebDAV）。
  * `data/hd_lru_cache/`：L2 超清大图与单页重切预览的本地 LRU 磁盘缓存池（默认上限 `2GB`，超限自动淘汰最久未访问文件）。

### 8.2 Cloudflare 缓存头隔离与流式热更新规范
1. **公开静态图像边缘加速**：
   * `/api/assets/thumb/{id}.webp?v={hash}` 与 `/api/assets/hd/{id}.webp?v={hash}` 返回 `Cache-Control: public, max-age=31536000, immutable`。一旦用户手动画框重切或 Codex 精修完成，后端更新 `version_hash`，前端 URL 自动换参绕过旧缓存。
2. **账号私有接口严禁缓存**：
   * `/api/auth/*`、`/api/me/*`、`/api/collections/*`、`/api/ingest/*`、`/api/admin/*` 统一返回 `Cache-Control: private, no-store`，避免 Cloudflare 边缘节点串号缓存用户状态。
3. **SSE 实时热更新防缓冲**：
   * `/api/stream/events` 返回 `Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`，保障每切出一张图前端即时收到事件。
4. **WebDAV 目录扫描自愈**：
   * 支持执行 `figprism rebuild-from-webdav`（或后台按钮触发）：扫描远端 WebDAV 各目录下的 `metadata.json` 与缩略图，支持服务器迁移热恢复，也支持直接往 WebDAV 按规范放入文件后热加载展示。

---

## 9. 数据库 Schema 与统一 CLI 契约

### 9.1 SQLite 核心表结构
* **账号与个性化表**：
  * `users`：`id, username (UNIQUE), password_hash, role ('admin'|'user'), is_active, created_at`
  * `invite_codes`：`code (PK), created_by, used_by, expires_at, created_at`
  * `collections`：`id, user_id, name, description, cover_figure_id, sort_order, updated_at`
  * `collection_items`：`id, collection_id, figure_id, focused_subitem_id (NULLABLE), user_note, sort_order, created_at`
  * `view_history`：`id, user_id, figure_id, viewed_at`（唯一联合索引 `(user_id, figure_id)`）
  * `palette_history`：`id, user_id, figure_id, subitem_id (NULLABLE), hex_code, copied_format, created_at`
* **领域、论文与图表核心表**：
  * `domains`：`id, slug (UNIQUE), name, color_dot, arxiv_cats_json, phrases_json, acronyms_json, exclude_terms_json, sub_tags_json, vlm_criteria, is_active, created_at`
  * `papers`：`id, doc_uid (UNIQUE, 存 arxiv_id 或 local_ulid), arxiv_id (NULLABLE), file_sha256, source_type ('arxiv'|'hf'|'upload'), title, authors_json, abstract, venue, venue_year, venue_tier ('oral'|'spotlight'|'poster'|NULL), hf_upvotes, layout_type ('single'|'double'), source_urls_json, webdav_pdf_path, uploaded_by (NULLABLE), published_at, created_at`
  * `paper_domains`：`paper_id, domain_id, matched_sub_tags_json`
  * `figures`：`id, paper_id, fig_label, page_number, page_bbox_json, archetype, span_type ('full'|'column'), caption, width, height, aspect_ratio, blurhash, fonts_json, palette_json, color_buckets_json, has_tikz, tikz_code, extract_method ('tex_raw'|'pdf_snap_crop'), confidence, review_status ('ok'|'needs_review'|'fixing'), webdav_thumb_path, webdav_hd_path, webdav_raw_path, version_hash, created_at`
  * `figure_subitems`：`id, figure_id, sub_label ('a'|'b'...), sub_caption, norm_bbox_json, aspect_ratio, palette_json, webdav_raw_sub_path`
  * `jobs` & `repair_queue`：管理同步/冷启动/单篇上传进度日志及 Codex 异步重切队列。

### 9.2 统一 CLI 命令契约（供系统 Cron、Web 后端与 Codex 共用）
```bash
# 1. 初始化站长管理员账号
figprism auth create-admin --username admin --password "<your_password>"

# 2. 日常定时增量同步（拉取 HF Daily + 近期 arXiv 顶会核验，逐张原子化流式热入库）
figprism sync --source all --days 3 --vision-driver openai_mini

# 3. 2025-2026 六大顶会代表作冷启动（支持全量或针对新增单个领域独立回溯）
figprism backfill --years 2025,2026 --domains all --limit-per-domain 50

# 4. 单篇论文极速拆解入库（兼容 arXiv ID/链接、HF/OpenReview 链接或本地 PDF 路径）
figprism ingest --input "[https://arxiv.org/abs/2503.12345](https://arxiv.org/abs/2503.12345)" --force-include
figprism ingest --pdf "/tmp/paper.pdf" --domains "post-training,rsi-self-evolve" --venue "ICLR 2026"

# 5. Codex Subagent 协同接口（获取待判图/待精修队列，或写回重切坐标）
figprism queue list --type review_or_repair --json
figprism recrop --figure-id 1042 --page 4 --bbox "0.08,0.12,0.92,0.48" --snap-vector

# 6. 从远端 WebDAV 目录全量扫描重建本地 SQLite 与缩略图镜像
figprism rebuild-from-webdav
```

---

## 10. 分阶段实施与验收里程碑 (Milestones)

1. **M1 工程底座、浅色 UI 框架与权限存储通路**
   * 初始化 Monorepo（`backend/` FastAPI + SQLite WAL + FTS5，`frontend/` Next.js + Tailwind 浅色画廊设计 Token），打通 JWT 认证（Guest/User/Admin 隔离）、WebDAV 异步存储、本地缩略图热镜像与 `config/domains.yaml` 双向同步加载。
2. **M2 矢量吸附切图、多子图定位与科研配色引擎**
   * 实现 Tier 1 TeX 源码提取 + Tier 2 `doclayout-yolo` 与 `PyMuPDF Vector-Ink Snap` 450 DPI 裁切、多子图模板匹配热区提取、OKLCH 深浅配色配对算法、`VisionJudge` 双模判图器，跑通在线链接与本地 PDF 上传 `ingest` 全链路。
3. **M3 多源免密召回与 2025–2026 顶会冷启动**
   * 接入 HF Daily、arXiv、OpenReview v2 与 DBLP 三级核验器，实现精确短语 + 大小写敏感缩写 + 负向排除词匹配，完成 `sync` 增量流与 `backfill` 代表作冷启动脚本。
4. **M4 交互打磨、收藏夹看板、修图闭环与部署交付**
   * 完成零抖动 BlurHash 瀑布流、三维正交与 12 色相筛选、详情页**多子图聚光灯 + 像素放大镜吸管**、3 秒手动画框重切与 Codex 异步精修队列、Moodboard 收藏夹批量矢量包导出、双轨历史页、SSE 实时热更新以及 Docker Compose + Cloudflare 缓存头配置。
