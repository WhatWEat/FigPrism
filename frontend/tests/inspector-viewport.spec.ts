import { test, expect } from "@playwright/test";
const nads = "1e1f40ef094b5869a25e830e6ab35fbb";

test("first preview fits the viewport, HD keeps its frame, and zoom reaches 3200%", async ({
  page,
  request,
}) => {
  const response = await request.get(`/api/figures/${nads}`);
  test.skip(!response.ok(), "Requires the NADS regression paper");
  const figure = await response.json();
  await page.setViewportSize({ width: 1440, height: 1000 });
  let release!: () => void;
  const wait = new Promise<void>((resolve) => (release = resolve));
  await page.route(`**/api/assets/hd/${nads}.webp*`, async (route) => {
    await wait;
    await route.continue().catch(() => {});
  });
  await page.goto("/");
  await page.getByRole("textbox", { name: "搜索图表" }).fill(figure.title);
  const entry = page.getByRole("button", {
    name: `打开 ${figure.fig_label} ${figure.title}`,
    exact: true,
  });
  await entry.click();
  const image = page.locator(".image-wrap img");
  await expect(image).toHaveAttribute("data-resolution", "preview");
  await expect(page.locator(".inspector-sidebar h2")).toHaveText(figure.title);
  await expect(page.locator(".caption-text .katex").first()).toBeVisible();
  expect(await page.locator(".caption-text").innerText()).not.toContain(
    "$M_nav$",
  );
  const before = (await image.boundingBox())!;
  const canvas = (await page.locator(".canvas-scroll").boundingBox())!;
  expect(before.width).toBeGreaterThan(canvas.width * 0.8);
  expect(before.height).toBeLessThanOrEqual(canvas.height);
  release();
  await expect(image).toHaveAttribute("data-resolution", "hd", {
    timeout: 30000,
  });
  const after = (await image.boundingBox())!;
  expect(Math.abs(after.width - before.width)).toBeLessThan(2);
  expect(Math.abs(after.height - before.height)).toBeLessThan(2);
  const slider = page.getByRole("slider", { name: "缩放倍率" });
  await slider.fill("3");
  await expect(page.locator(".zoom-controls output")).toHaveText("800%");
  expect((await image.boundingBox())!.width).toBeGreaterThan(
    before.width * 7.9,
  );
  await slider.fill("5");
  await expect(page.locator(".zoom-controls output")).toHaveText("3200%");
  await page.getByRole("button", { name: "适应窗口", exact: true }).click();
  await expect(page.locator(".zoom-controls output")).toHaveText("100%");
  expect(
    Math.abs((await image.boundingBox())!.width - before.width),
  ).toBeLessThan(2);
  await page.locator(".canvas-scroll").hover();
  await page.mouse.wheel(0, -200);
  await expect
    .poll(() => page.locator(".zoom-controls output").innerText())
    .not.toBe("100%");
  await page.screenshot({ path: "../data/qa/inspector-012.png" });
});

test("uncached next metadata shows a current-detail placeholder, never the previous caption", async ({
  page,
  request,
}) => {
  const feed = await (await request.get("/api/figures/feed?limit=10")).json();
  const group = feed.items.find((g: any) => g.matched_figures.length > 1);
  test.skip(!group, "Requires multiple figures");
  const first = group.matched_figures[0];
  const next = group.matched_figures[1];
  // Feed offers navigation IDs, but the sibling metadata has not arrived yet.
  await page.route("**/api/figures/feed?*", (route) =>
    route.fulfill({
      json: { ...feed, items: [{ ...group, hero_figure_id: first.id }] },
    }),
  );
  await page.route(`**/api/papers/${group.paper.id}/figures*`, (route) =>
    route.fulfill({ json: { items: [], total: 0, matched_count: 0 } }),
  );
  let release!: () => void;
  const wait = new Promise<void>((resolve) => (release = resolve));
  await page.route(`**/api/figures/${next.id}`, async (route) => {
    await wait;
    await route.continue().catch(() => {});
  });
  await page.goto("/");
  await page.locator(".deck-hero").first().click();
  await expect(page.locator(".caption-text")).toContainText(
    first.caption.slice(0, 30),
  );
  await page.getByRole("button", { name: "下一张图表", exact: true }).click();
  await expect(page.locator(".detail-loading")).toContainText(
    "正在加载当前图表详情",
  );
  await expect(page.locator(".caption-text")).toHaveCount(0);
  release();
  await expect(page.locator(".detail-loading")).toHaveCount(0);
  await expect(page.locator(".caption-text")).toContainText(
    next.caption.slice(0, 30),
  );
});
