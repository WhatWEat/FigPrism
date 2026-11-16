import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
const credentials = JSON.parse(
  readFileSync(
    path.resolve(__dirname, "../../data/qa/e2e-account.json"),
    "utf8",
  ),
);
test("guest browsing, filters and mobile layout", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "从一张好图，看见新灵感。" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "方法架构图", exact: true }).click();
  await page.getByRole("button", { name: "记忆机制", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Agent 长期/情景/图谱记忆" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "筛选钴蓝配色" }).click();
  await expect(
    page.getByRole("button", { name: "筛选钴蓝配色" }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "重置筛选", exact: true }).click();
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("textbox", { name: "搜索图表" })).toBeFocused();
  await page
    .getByRole("textbox", { name: "搜索图表" })
    .fill("nonexistent-e2e-paper");
  await expect(
    page.getByRole("heading", { name: "还没有匹配的图表" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "重置所有筛选" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../data/qa/mobile-gallery.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "登录", exact: false })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  expect(errors).toEqual([]);
});
test("member login, board lifecycle and protected admin", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "登录", exact: false })
    .first()
    .click();
  await page.getByLabel("用户名", { exact: true }).fill(credentials.username);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "登录", exact: true })
    .click();
  await expect(
    page.getByRole("banner").getByRole("button", { name: "添加论文" }),
  ).toBeVisible();
  await page
    .getByRole("banner")
    .getByRole("button", { name: "添加论文" })
    .click();
  await page.getByRole("button", { name: "本地 PDF" }).click();
  await page.locator("input[type=file]").setInputFiles({
    name: "invalid.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not a pdf"),
  });
  await expect(page.getByText("请选择 PDF 文件")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "看板", exact: true }).click();
  await page.getByRole("button", { name: "新建看板" }).click();
  await page.getByLabel("看板名称").fill("E2E 灵感看板");
  await page.getByRole("button", { name: "创建看板", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "E2E 灵感看板" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "重命名看板" }).click();
  await page.getByLabel("看板名称").fill("E2E 更新后的看板");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "保存", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "E2E 更新后的看板" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "删除看板", exact: true }).click();
  await page.getByRole("button", { name: "确认删除看板" }).click();
  await expect(
    page.getByRole("heading", { name: "E2E 更新后的看板" }),
  ).not.toBeVisible();
  await page.goto("/admin");
  await expect(
    page.getByRole("heading", { name: "需要管理员权限" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "账号菜单" }).click();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(
    page.getByRole("button", { name: "登录 FigPrism" }),
  ).toBeVisible();
});
test("real figure inspector, color export, keyboard navigation and vector download", async ({
  page,
  request,
}) => {
  const res = await request.get("/api/figures?limit=3");
  const data = await res.json();
  test.skip(!data.items?.length, "Real paper import still running");
  await page.goto("/");
  await page.getByRole("button", { name: "单图平铺流", exact: true }).click();
  await page.locator(".figure-open").first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("heading", { name: "科研配色 PALETTE" }),
  ).toBeVisible();
  const img = dialog.locator(".image-wrap img");
  await expect(img).toHaveAttribute("data-resolution", "hd", {
    timeout: 20000,
  });
  await expect(img).toBeVisible();
  await expect
    .poll(() =>
      img.evaluate(
        (el: HTMLImageElement) => el.complete && el.naturalWidth > 0,
      ),
    )
    .toBeTruthy();
  await dialog.getByRole("button", { name: "Matplotlib", exact: true }).click();
  await expect(dialog.locator(".code-box").first()).toContainText(
    "plt.rcParams",
  );
  const href = await dialog
    .getByRole("link", { name: /下载矢量 PDF/ })
    .getAttribute("href");
  expect(href).toBeTruthy();
  const raw = await request.get(href!);
  expect(raw.status()).toBe(200);
  expect((await raw.body()).subarray(0, 4).toString()).toBe("%PDF");
  await page.keyboard.press("i");
  await expect(dialog.locator(".image-stage")).toHaveClass(/picking/);
  await page.screenshot({
    path: "../data/qa/inspector-desktop.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
});

test("subfigure focus, pixel picker, crop controls and saved board context", async ({
  page,
}) => {
  const response = await page.request.post("/api/auth/login", {
    data: { username: credentials.username, password: credentials.password },
  });
  expect(response.status()).toBe(200);
  const data = await (await page.request.get("/api/figures?limit=100")).json();
  const figure = data.items.find(
    (f: { subitems: { id: string }[] }) =>
      f.subitems.length > 1 && f.subitems.some((s) => s.id === "b"),
  );
  test.skip(!figure, "Composite import still running");
  await page.goto("/");
  await page.getByRole("button", { name: "单图平铺流", exact: true }).click();
  await page
    .getByRole("button", {
      name: `查看 ${figure.fig_label} ${figure.title}`,
      exact: true,
    })
    .click();
  const dialog = page.getByRole("dialog");
  const image = dialog.locator(".image-wrap img");
  await expect(image).toHaveAttribute("data-resolution", "hd", {
    timeout: 20000,
  });
  await expect
    .poll(() =>
      image.evaluate(
        (el: HTMLImageElement) => el.complete && el.naturalWidth > 0,
      ),
    )
    .toBeTruthy();
  await dialog
    .locator(".sub-controls")
    .getByRole("button", { name: "(b)", exact: true })
    .click();
  await expect(dialog.locator(".spotlight")).toBeVisible();
  await expect(dialog.getByText("SUBFIGURE B", { exact: true })).toBeVisible();
  await page.keyboard.press("i");
  const rect = (await image.boundingBox())!;
  await page.mouse.move(rect.x + rect.width * 0.5, rect.y + rect.height * 0.5);
  await expect(dialog.locator(".loupe span")).toHaveText(/^#[0-9A-F]{6}$/);
  await page.mouse.click(rect.x + rect.width * 0.5, rect.y + rect.height * 0.5);
  await expect(page.locator(".toast[role=status]")).toContainText("已复制");
  await page.keyboard.press("i");
  await dialog.getByRole("button", { name: "框选重切" }).click();
  const preview = dialog.locator(".crop-page img");
  await expect
    .poll(() =>
      preview.evaluate(
        (el: HTMLImageElement) => el.complete && el.naturalWidth > 0,
      ),
    )
    .toBeTruthy();
  const pageRect = (await preview.boundingBox())!;
  await page.mouse.move(
    pageRect.x + pageRect.width * 0.2,
    pageRect.y + pageRect.height * 0.3,
  );
  await page.mouse.down();
  await page.mouse.move(
    pageRect.x + pageRect.width * 0.8,
    pageRect.y + pageRect.height * 0.5,
    { steps: 5 },
  );
  await page.mouse.up();
  await expect(
    dialog.getByRole("button", { name: "确认重切并刷新配色" }),
  ).toBeEnabled();
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await dialog
    .locator(".sub-controls")
    .getByRole("button", { name: "(b)", exact: true })
    .click();
  await dialog
    .getByRole("textbox", { name: "灵感笔记" })
    .fill("E2E: preserve this panel and note");
  await dialog.getByRole("button", { name: "保存至看板" }).click();
  await expect(page.locator(".toast[role=status]")).toContainText("灵感和笔记已保存");
  const boards = await (await page.request.get("/api/collections")).json();
  const board = boards.find((b: { name: string }) => b.name === "我的灵感收藏");
  expect(board).toBeTruthy();
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "看板", exact: true }).click();
  await expect(page).toHaveURL(/\/collections$/);
  await page.locator(".board-content .figure-open").first().click();
  await expect(page.getByText("SUBFIGURE B", { exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "灵感笔记" })).toHaveValue(
    "E2E: preserve this panel and note",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../data/qa/inspector-mobile.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await page.request.delete("/api/collections/" + board.id);
});
