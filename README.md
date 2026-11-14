# FigPrism

以论文图表为中心的科研灵感库。Next.js + FastAPI + SQLite（WAL/FTS5），WebDAV 保存原文与图像，本机保存索引、缩略图及有上限的高清缓存。

生产地址：**https://figprism.ai4any.com**。服务运行在本机 Docker Compose，Nginx 提供 HTTPS；域名 A 记录直接指向本机。旧域名 `fig.zhcanfly.com` 和 `figprsim.zhcanfly.com` 保留并重定向至新地址。

## 已实现

- 默认按论文归集的胶片图组（悬停预览、原地展开）、横排画册与单图平铺三态视图；同文缩略导航和 ↑ / ↓ 切图。
- 暖纸护眼配色、高对比文字、固定启用的纸感融合；吸管始终读取原始未混合像素。
- 访客看图、全文检索（支持 `font:Helvetica`、`ratio:>2.0`）、领域/子标签/会议/版式/形态/色相筛选。
- 高清图表检视器、BlurHash 缩略图占位、子图聚光灯、像素吸管、HEX/RGB/Matplotlib/LaTeX/CSS 配色导出、矢量 PDF 与 TikZ 下载。
- 邀请制账号、Argon2 密码、可撤销 Cookie 会话、角色权限、私有看板、笔记、ZIP 导出、浏览和取色历史。
- 链接/本地 PDF 入库、SHA-256 判重、TeX 安全解析、DocLayout-YOLO ONNX CPU 检测、矢量墨迹吸附、450 DPI 渲染、科学配色及子图热区。
- 手动重切、标签修正、精修任务队列、逐图 SSE 更新；WebDAV 元数据备份与重建。
- HF Daily / arXiv 召回、OpenReview / DBLP 录用核验、OpenAlex 引用排序、2025–2026 冷启动命令、管理界面和每日同步。

## 本地开发

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r backend/requirements.lock
uv pip install --python .venv/bin/python -e './backend[test]' --no-deps
# 测试依赖若未安装：uv pip install --python .venv/bin/python pytest pytest-asyncio
npm ci --prefix frontend

# 将非标准配置转换成标准 YAML；不会覆盖已有文件。
.venv/bin/python scripts/convert_config.py --source config --output config/local.yaml
.venv/bin/python scripts/download_layout.py

# 分别运行两个终端：
FIGPRISM_PUBLIC_ORIGIN=http://127.0.0.1:3100 FIGPRISM_COOKIE_SECURE=false \
  .venv/bin/uvicorn figprism.main:app --host 127.0.0.1 --port 8100
npm run dev --prefix frontend
```

配置示例见 `config/settings.example.yaml`。实际 `config/local.yaml`、原始文本配置、管理员凭据及 `data/` 均被 Git 排除。提供的 123 云盘配置中的 `dir` 是网页面包屑，账号已映射到 `paper` 目录；转换器在该映射下使用独立 `/figprism` 子目录。

## 生产部署

```bash
docker compose build
docker compose up -d
# Nginx 初始配置为 deploy/nginx.conf；申请证书后以 /etc/nginx 中的生效配置为准。
# DNS A: figprism.ai4any.com -> 本机 IPv4。
```

旧域名跳转配置在 `deploy/nginx.previous.conf` 和 `deploy/nginx.legacy.conf`，其 DNS 记录和 HTTPS 证书保留用于兼容原有链接。

新域名证书使用 Certbot 的 Nginx 插件签发，`certbot.timer` 每日检查续期。可执行 `certbot renew --cert-name figprism.ai4any.com --dry-run` 验证。

为不中断在途入库任务，后端继续使用 Compose 中的原有 `FIGPRISM_PUBLIC_ORIGIN=https://fig.zhcanfly.com`；新域名 Nginx 仅将精确匹配的新站 Origin 转为后端原有可信 Origin，其他来源原样转发并由后端拒绝。该映射与 Compose 配置需配套保留，Cookie 仍在新域名下使用 Secure / HttpOnly。

当前生产 Compose 项目为 `figprism-v2`，容器仅暴露 `127.0.0.1:8101`（API）及 `127.0.0.1:3111`（Web）；Nginx 分别代理，上传上限 52MB，SSE 禁用缓冲。数据库、模型及缓存挂载 `./data`，配置挂载 `./config`。重启策略为 `unless-stopped`，日志自动轮转。

首个管理员通过 CLI 创建（密码交互输入，不放进命令历史）：

```bash
docker compose exec backend figprism auth create-admin --username admin
```

本次部署已创建管理员，首次访问资料仅保存在服务器 **`config/admin-access.txt`**，文件权限为 `0600`。不要提交该文件。管理员可在 `/admin` 创建一次性邀请链接。

## 常用维护

```bash
docker compose ps
docker compose logs --tail=100 backend

docker compose exec backend figprism sync --source all --days 3 --limit 3
docker compose exec backend figprism backfill --years 2025,2026 --domains all --limit-per-domain 50
docker compose exec backend figprism ingest --input https://arxiv.org/abs/2501.00663 --force-include
# 容器内路径；例如先 docker compose cp paper.pdf backend:/tmp/paper.pdf
docker compose exec backend figprism ingest --pdf /tmp/paper.pdf --domains memory

docker compose exec backend figprism queue list --type review_or_repair --json
docker compose exec backend figprism recrop --figure-id <id> --page 4 --bbox 0.08,0.12,0.92,0.48 --snap-vector
docker compose exec backend figprism rebuild-from-webdav

systemctl status figprism-sync.timer
systemctl list-timers figprism-sync.timer
```

每日同步配置在 `deploy/systemd/`，北京时间 06:15 开始（随机延迟最多 5 分钟），每领域最多 3 篇。可在管理界面手动触发更大批次。每次新增领域后，可单独运行对应领域的 backfill；词库编辑会同步到 `config/domains.yaml`。

## 验证

```bash
.venv/bin/pytest backend/tests -q
npm run typecheck --prefix frontend
npm run build --prefix frontend
```

Playwright 测试连接实际服务，使用专门的测试账号（`data/qa/e2e-account.json`，不提交）。运行前执行 `scripts/setup_e2e.py`，浏览器位置由 `PLAYWRIGHT_CHROMIUM_PATH` 指定。真实图表测试需要图库至少一张图。

```bash
.venv/bin/python scripts/setup_e2e.py
E2E_BASE_URL=https://figprism.ai4any.com npm run test:e2e --prefix frontend
```

## 运行边界

- 自动识别不保证每张图都完美。低置信度、几何兜底或模型拒绝的结果标为“待复核”，支持手动重切；组合图保持整体，并为可靠识别的子图提供独立聚光灯。
- 450 DPI 渲染设有 2400 万像素安全上限；超大原图适当降低光栅分辨率，矢量 PDF 不受影响。EPS 源资产暂不转换，回退到论文 PDF 矢量裁切。源码宏解析覆盖常见 `input/include`、figure、includegraphics、subfigure 与 TikZ，不执行 TeX。
- 第三方模型必须支持图片与结构化输出；响应不符合约定时保留图表并进入复核队列，不伪造分类成功。`codex_subagent` 模式只导出队列，实际 Codex 精修由外部任务领取；本服务不自行启动 Codex 进程。
- WebDAV 跨区域上传可能较慢。实现分块传输、重试和逐图发布，不承诺 PRD 中的 1–2 秒远端重切或 500ms 全网首屏指标。断电中的在线任务会标记失败，可重新提交；已有部分图表可继续处理。
- 首批内容为真实论文，未核验的会议标记保留 Preprint。2025–2026 全量代表作需按需运行 backfill，默认不一次性下载每领域 50 篇。
- WebDAV 备份覆盖论文/图表元数据及资产；**账号、会话、私有看板和历史只在 SQLite**，迁移时还需安全备份数据库与 `config/local.yaml`。不要只依赖资产重建恢复账号。

## 分阶段并发控制

`config/local.yaml` 的 `pipeline` 段控制以下共享限额，示例见 `config/settings.example.yaml`：

| 阶段 | 默认并发 |
| --- | ---: |
| 元数据召回、会议核验 | 4 |
| PDF / TeX 下载 | 3 |
| 同时处理论文 | 2 |
| PDF 计算子进程 | 2（每进程 1 个 ONNX 线程） |
| 视觉判图请求 | 3 |
| WebDAV 上传请求 | 4 |
| 全局在途图表 | 6（每篇最多 3 张） |

网页、CLI 和定时任务通过共享数据卷中的内核文件锁使用同一套限额。PDF 原文上传与版面分析重叠，图表渲染、判图、上传交错执行；公开图表前等待原文和该图全部资产持久化。相同 PDF/论文身份串行去重；重切只锁目标图表；WebDAV 元数据备份按论文串行并合并重复快照。恢复全库时使用独占维护锁。

arXiv 起始请求间隔跨进程保持至少 3 秒。瞬时网络错误及 408/425/429/5xx 按有限次数重试并尊重 Retry-After；权限错误直接失败。取消任务会终止计算子进程，保留已发布图表；重新提交失败论文时跳过已有图表，不会重复插入。网页最多接纳 12 个顶层待处理任务，每用户仍限 3 个。

管理员页面显示每阶段实时运行数和上限，也可运行：

```bash
docker compose exec backend figprism pipeline status
```

调整 `pipeline` 后，应在任务结束后重启后端，并重启/重新运行正在使用旧配置的 CLI 或定时任务，保证所有进程使用一致的限额。CPU 渲染使用独立短生命周期进程，避免 PyMuPDF 在线程之间共享对象；进程启动有少量开销，但内存可随计算完成释放。

可用 `.venv/bin/python scripts/benchmark_pipeline.py` 运行不访问外网的调度基准。固定模拟延迟下，3 篇 / 18 张图的单路模式为 5.95 秒，新并发配置为 2.54 秒，约 2.34 倍；这不是生产网络吞吐保证。

技术依据及第三方组件见 [docs/implementation.md](docs/implementation.md)。

首批真实论文导入由本机 `figprism-bootstrap.service` 托管，可用 `journalctl -u figprism-bootstrap -f` 查看进度。它不影响浏览；远端资产成功保存后，图表逐张出现在首页。该一次性导入结束后无需常驻，日常更新由上述 timer 承担。


## 论文图组（PRD v2.1）

首页默认 Deck：每张卡片对应一篇论文，胶片条悬停即可切换主图、图号和配色，点击任意图进入检视器；卡片可原地展开为两列图表。Swimlane 按论文横排展示 210px 高图表，支持横向滚轮/拖拽及整组收藏。Flat 保留单图瀑布流。视图选择保存到 localStorage。

`GET /api/figures/feed?group_by=paper` 先应用所有筛选条件，再在 SQL 层按论文分页（默认 16 组）；返回 `paper`、`hero_figure_id`、自然图号排序的 `matched_figures`。代表图优先级为 Pipeline / Framework、Teaser、Micro-Mechanism、实验图。`group_by=none` 按单图分页，旧 `/api/figures` 保持兼容。`GET /api/papers/{id}/figures` 提供完整同文导航；批量收藏接口检查看板所有者并保留已有笔记。

护眼融合使用显示层 `mix-blend-mode: multiply` 和 `contrast(1.02)`，原始 WebP / PDF 文件、导出色值和离屏取色 canvas 都不变。图片装裱区固定使用暖纸底色，不再提供纸感或纯白背景切换，旧版关闭偏好也不会改变显示。

本次 v2.1 使用并行实例发布，旧 `figprism` 容器继续处理切换前已接受的任务；新流量进入 `figprism-v2`。`figprism-drain-legacy.timer` 每两分钟检查一次，确认没有在途/排队任务和附加计算进程后，才停止记录中的旧容器。它不会删除数据库、资产或容器日志。`data/.pipeline/recovery-exempt.json` 在此期间保护旧任务及批次子任务，避免新实例启动时将它们误标为失败；旧运行环境回收后自动移除。
