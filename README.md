# FigPrism

以论文图表为中心的科研灵感库。Next.js + FastAPI + SQLite（WAL/FTS5），WebDAV 保存原文与图像，本机保存索引、缩略图及有上限的高清缓存。

生产地址：**https://figprsim.zhcanfly.com**（按指定域名拼写）。服务运行在本机 Docker Compose，Nginx 提供 HTTPS；Cloudflare 仅维护 DNS A 记录，未启用代理、Tunnel 或 Workers。

## 已实现

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
# Cloudflare A: figprsim.zhcanfly.com -> 本机 IPv4，proxied=false。
```

容器仅暴露 `127.0.0.1:8100`（API）及 `127.0.0.1:3100`（Web）；Nginx 分别代理，上传上限 52MB，SSE 禁用缓冲。数据库、模型及缓存挂载 `./data`，配置挂载 `./config`。重启策略为 `unless-stopped`，日志自动轮转。

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
E2E_BASE_URL=https://figprsim.zhcanfly.com npm run test:e2e --prefix frontend
```

## 运行边界

- 自动识别不保证每张图都完美。低置信度、几何兜底或模型拒绝的结果标为“待复核”，支持手动重切；组合图保持整体，并为可靠识别的子图提供独立聚光灯。
- 450 DPI 渲染设有 2400 万像素安全上限；超大原图适当降低光栅分辨率，矢量 PDF 不受影响。EPS 源资产暂不转换，回退到论文 PDF 矢量裁切。源码宏解析覆盖常见 `input/include`、figure、includegraphics、subfigure 与 TikZ，不执行 TeX。
- 第三方模型必须支持图片与结构化输出；响应不符合约定时保留图表并进入复核队列，不伪造分类成功。`codex_subagent` 模式只导出队列，实际 Codex 精修由外部任务领取；本服务不自行启动 Codex 进程。
- WebDAV 跨区域上传可能较慢。实现分块传输、重试和逐图发布，不承诺 PRD 中的 1–2 秒远端重切或 500ms 全网首屏指标。断电中的在线任务会标记失败，可重新提交；已有部分图表可继续处理。
- 首批内容为真实论文，未核验的会议标记保留 Preprint。2025–2026 全量代表作需按需运行 backfill，默认不一次性下载每领域 50 篇。
- WebDAV 备份覆盖论文/图表元数据及资产；**账号、会话、私有看板和历史只在 SQLite**，迁移时还需安全备份数据库与 `config/local.yaml`。不要只依赖资产重建恢复账号。

技术依据及第三方组件见 [docs/implementation.md](docs/implementation.md)。

首批真实论文导入由本机 `figprism-bootstrap.service` 托管，可用 `journalctl -u figprism-bootstrap -f` 查看进度。它不影响浏览；远端资产成功保存后，图表逐张出现在首页。该一次性导入结束后无需常驻，日常更新由上述 timer 承担。
