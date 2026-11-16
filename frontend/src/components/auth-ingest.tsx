"use client";
import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link2,
  UploadCloud,
  FileText,
  Check,
  ArrowRight,
  LockKeyhole,
} from "lucide-react";
import { api, post } from "@/lib/api";
import { useUI } from "@/lib/store";
import { Domain, Board } from "@/lib/types";
import { Modal, Spinner, ErrorMessage } from "./ui";
import { AuthChallenge } from "./auth-challenge";
export function AuthModal() {
  const ui = useUI();
  const query = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [token, setToken] = useState("");
  const [challengeAttempt, setChallengeAttempt] = useState(0);
  const challenge = useQuery({
    queryKey: ["auth-challenge-config"],
    queryFn: () =>
      api<{ enabled: boolean; site_key: string | null }>(
        "/auth/challenge-config",
      ),
    enabled: ui.loginOpen,
    staleTime: 0,
  });
  useEffect(() => {
    setToken("");
    setChallengeAttempt((n) => n + 1);
  }, [mode, ui.loginOpen]);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("invite");
    if (code) {
      setInvite(code);
      setMode("register");
      ui.openLogin();
    }
  }, []);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post(mode === "register" ? "/auth/register" : "/auth/login", {
        username,
        password,
        ...(mode === "register" ? { invite_code: invite.trim() } : {}),
        turnstile_token: token,
      });
      await query.invalidateQueries({ queryKey: ["me"] });
      useUI.setState({ loginOpen: false });
      setPassword("");
      setInvite("");
      setMode("login");
      ui.notify("欢迎回来，开始收集灵感吧");
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
      setToken("");
      setChallengeAttempt((n) => n + 1);
    }
  }
  return (
    <Modal
      open={ui.loginOpen}
      onOpenChange={(loginOpen) => useUI.setState({ loginOpen })}
      title={mode === "register" ? "加入 FigPrism" : "登录你的灵感空间"}
      description="收藏图表、同步配色，以及整理下一篇论文的灵感。"
    >
      <form onSubmit={submit} className="form">
        <div className="auth-mode">
          <button
            type="button"
            className={mode === "login" ? "active" : ""}
            onClick={() => {
              setMode("login");
              setError(null);
            }}
          >
            已有账号
          </button>
          <button
            type="button"
            className={mode === "register" ? "active" : ""}
            onClick={() => {
              setMode("register");
              setError(null);
            }}
          >
            邀请码注册
          </button>
        </div>
        {mode === "register" && (
          <label>
            邀请码
            <input
              aria-label="邀请码"
              required
              maxLength={256}
              autoComplete="off"
              spellCheck={false}
              value={invite}
              onChange={(event) => setInvite(event.target.value)}
              placeholder="填写管理员提供的邀请码"
            />
          </label>
        )}
        <label>
          用户名
          <input
            required
            minLength={2}
            maxLength={64}
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="输入用户名"
          />
        </label>
        <label>
          密码
          <input
            required
            minLength={10}
            maxLength={128}
            type="password"
            autoComplete={
              mode === "register" ? "new-password" : "current-password"
            }
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="至少 10 位字符"
          />
        </label>
        <ErrorMessage
          error={error || challenge.error}
          retry={challenge.error ? () => challenge.refetch() : undefined}
        />
        {ui.loginOpen && challenge.data?.enabled && challenge.data.site_key && (
          <AuthChallenge
            key={`${mode}-${challengeAttempt}`}
            siteKey={challenge.data.site_key}
            action={mode}
            onToken={setToken}
          />
        )}
        <button
          disabled={
            busy ||
            challenge.isPending ||
            challenge.isError ||
            (challenge.data?.enabled && !token)
          }
          className="button primary"
        >
          {busy ? <Spinner /> : <LockKeyhole size={16} />}{" "}
          {mode === "register" ? "创建账号" : "登录"}
          <ArrowRight size={16} />
        </button>
        <p className="form-footnote">
          FigPrism 采用邀请制。访客可自由浏览、取色与下载。
        </p>
      </form>
    </Modal>
  );
}
export function IngestModal() {
  const ui = useUI();
  const query = useQueryClient();
  const [tab, setTab] = useState<"link" | "pdf">("link");
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [domain, setDomain] = useState("");
  const [venue, setVenue] = useState("Preprint");
  const [board, setBoard] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState("");
  const [drag, setDrag] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const domains =
    useQuery({
      queryKey: ["domains"],
      queryFn: () => api<Domain[]>("/domains"),
    }).data || [];
  const boards =
    useQuery({
      queryKey: ["boards"],
      queryFn: () => api<Board[]>("/collections"),
      enabled: ui.ingestOpen,
    }).data || [];
  useEffect(() => {
    if (!input || tab !== "link") return;
    const timer = setTimeout(() => {
      api<{ title?: string; arxiv_id?: string }>(
        "/ingest/preview?input=" + encodeURIComponent(input),
      )
        .then((p) => setPreview(p.title || p.arxiv_id || "链接已识别"))
        .catch(() => setPreview(""));
    }, 700);
    return () => clearTimeout(timer);
  }, [input, tab]);
  async function chooseFile(f: File) {
    setError(null);
    if (f.size > 50 * 1024 * 1024) {
      setError(new Error("文件不能超过 50MB"));
      return;
    }
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      setError(new Error("请选择 PDF 文件"));
      return;
    }
    setFile(f);
    try {
      const digest = await crypto.subtle.digest(
        "SHA-256",
        await f.arrayBuffer(),
      );
      const sha256 = Array.from(new Uint8Array(digest))
        .map((x) => x.toString(16).padStart(2, "0"))
        .join("");
      const res = await post<{ paper: { title: string } | null }>(
        "/ingest/check",
        { sha256 },
      );
      setPreview(
        res.paper
          ? "已入库：" + res.paper.title
          : "PDF 就绪 · 将自动检测论文信息",
      );
    } catch {
      setPreview("PDF 就绪");
    }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (tab === "link") {
        await post("/ingest/link", {
          input,
          domains: domain ? [domain] : [],
          venue,
          collection_id: board || null,
        });
      } else {
        if (!file) throw new Error("请先选择 PDF");
        const body = new FormData();
        body.append("file", file);
        body.append("domains", domain);
        body.append("venue", venue);
        body.append("collection_id", board);
        await api("/ingest/pdf", { method: "POST", body });
      }
      useUI.setState({ ingestOpen: false });
      query.invalidateQueries({ queryKey: ["jobs"] });
      ui.notify("论文已加入处理队列，图表将逐张入库");
      setFile(null);
      setInput("");
      setPreview("");
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open={ui.ingestOpen}
      onOpenChange={(ingestOpen) => useUI.setState({ ingestOpen })}
      title="添加一篇论文"
      description="把感兴趣的工作，变成随时可用的绘图灵感。"
    >
      <div className="tab-row">
        <button
          className={tab === "link" ? "active" : ""}
          onClick={() => setTab("link")}
        >
          <Link2 size={16} />
          论文链接
        </button>
        <button
          className={tab === "pdf" ? "active" : ""}
          onClick={() => setTab("pdf")}
        >
          <FileText size={16} />
          本地 PDF
        </button>
      </div>
      <form className="form" onSubmit={submit}>
        {tab === "link" ? (
          <label>
            论文链接或 arXiv 编号
            <input
              required
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="arxiv.org/abs/… 或 2501.00663"
            />
            <small>支持 arXiv、Hugging Face Papers、OpenReview</small>
          </label>
        ) : (
          <div
            className={`dropzone ${drag ? "dragging" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              if (e.dataTransfer.files[0])
                void chooseFile(e.dataTransfer.files[0]);
            }}
          >
            <UploadCloud size={32} />
            <strong>{file ? file.name : "拖放论文 PDF 到这里"}</strong>
            <span>
              或{" "}
              <button
                type="button"
                className="text-button"
                onClick={() => fileInput.current?.click()}
              >
                选择文件
              </button>{" "}
              · 最大 50MB
            </span>
            <input
              ref={fileInput}
              hidden
              type="file"
              accept="application/pdf"
              onChange={(e) => {
                if (e.target.files?.[0]) void chooseFile(e.target.files[0]);
              }}
            />
          </div>
        )}
        {preview && (
          <p className="preview-note">
            <Check size={15} />
            {preview}
          </p>
        )}
        <div className="form-two">
          <label>
            研究领域
            <select value={domain} onChange={(e) => setDomain(e.target.value)}>
              <option value="">自动识别</option>
              {domains.map((d) => (
                <option key={d.slug} value={d.slug}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            会议标记
            <input
              value={venue}
              onChange={(e) => setVenue(e.target.value)}
              placeholder="如 ICLR 2026"
              maxLength={80}
            />
          </label>
        </div>
        <label>
          解析后自动收藏
          <select value={board} onChange={(e) => setBoard(e.target.value)}>
            <option value="">暂不添加到看板</option>
            {boards.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>
        <ErrorMessage error={error} />
        <button className="button primary" disabled={busy}>
          {busy ? <Spinner /> : <ArrowRight size={16} />}开始拆解论文
        </button>
      </form>
    </Modal>
  );
}
