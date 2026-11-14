import { test, expect } from "@playwright/test";
const methodTypes = ["Teaser", "Pipeline", "Micro-Mechanism"];
const dataTypes = ["Curve", "Bar", "Scatter/Radar", "Heatmap"];

async function mixedPaper(request: any) {
  const feed = await (await request.get("/api/figures/feed?limit=100")).json();
  return (
    feed.items.find((g: any) => g.paper.title.startsWith("Titans:")) ||
    feed.items.find(
      (g: any) =>
        g.matched_figures.filter((f: any) => methodTypes.includes(f.archetype))
          .length >= 3 &&
        g.matched_figures.some((f: any) => dataTypes.includes(f.archetype)),
    )
  );
}

test("inspector preserves method/data filters in every feed layout and labels other figures", async ({
  page,
  request,
}) => {
  const group = await mixedPaper(request);
  test.skip(!group, "Needs a paper containing methods and experiment figures");
  await page.goto("/");
  await page.getByRole("textbox", { name: "搜索图表" }).fill(group.paper.title);
  await page.getByRole("button", { name: "方法架构图", exact: true }).click();
  const deck = page.locator(`.paper-deck[data-paper-id="${group.paper.id}"]`);
  await deck.locator(".deck-hero").click();
  await expect(page.locator(".sibling-label")).toContainText("方法架构图");
  await expect
    .poll(() => page.locator(".sibling-track button").count())
    .toBeGreaterThan(0);
  expect(
    await page
      .locator(".sibling-track button")
      .evaluateAll((items) =>
        items.every((i) =>
          ["Teaser", "Pipeline", "Micro-Mechanism"].includes(
            i.getAttribute("data-archetype") || "",
          ),
        ),
      ),
  ).toBeTruthy();
  const matchedCount = await page.locator(".sibling-track button").count();
  await page.getByRole("button", { name: /查看同篇全部图表/ }).click();
  await expect
    .poll(() => page.locator(".sibling-track button").count())
    .toBeGreaterThan(matchedCount);
  const other = page
    .locator('.sibling-track button[data-matched="false"]')
    .first();
  await expect(other).toContainText("其他");
  await other.click();
  await expect(page.locator(".inspector-classification")).toContainText(
    "未命中当前筛选",
  );
  await page.getByRole("button", { name: /仅看当前筛选/ }).click();
  await expect(page.locator(".sibling-track button")).toHaveCount(matchedCount);
  await expect(page.locator(".inspector-classification")).toContainText(
    "命中方法架构图",
  );
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "数据实验图", exact: true }).click();
  for (const mode of ["横排画册流", "单图平铺流"]) {
    await page.getByRole("button", { name: mode, exact: true }).click();
    const entry =
      mode === "横排画册流"
        ? page
            .locator(
              `.paper-swimlane[data-paper-id="${group.paper.id}"] .figure-open`,
            )
            .first()
        : page.locator(".flat-feed .figure-open").first();
    await entry.click();
    await expect(page.locator(".sibling-label")).toContainText("数据实验图");
    await expect
      .poll(() => page.locator(".sibling-track button").count())
      .toBeGreaterThan(0);
    expect(
      await page
        .locator(".sibling-track button")
        .evaluateAll((items) =>
          items.every((i) =>
            ["Curve", "Bar", "Scatter/Radar", "Heatmap"].includes(
              i.getAttribute("data-archetype") || "",
            ),
          ),
        ),
    ).toBeTruthy();
    await page.keyboard.press("ArrowDown");
    await expect(page.locator(".sibling-label")).toContainText("数据实验图");
    await page.keyboard.press("Escape");
  }
});

test("slow image switches keep the workspace mounted and late loads cannot overwrite the chosen figure", async ({
  page,
  request,
}) => {
  const group = await mixedPaper(request);
  test.skip(!group, "Needs a paper with multiple figures");
  const filtered = await (
    await request.get(
      `/api/papers/${group.paper.id}/figures?view=method&show_cases=false`,
    )
  ).json();
  const [first, slow, last] = filtered.items;
  test.skip(!last, "Needs three method figures");
  await page.route(`**/api/assets/hd/${slow.id}.webp*`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1200));
    await route.continue().catch(() => {});
  });
  await page.goto("/");
  await page.getByRole("textbox", { name: "搜索图表" }).fill(group.paper.title);
  await page.getByRole("button", { name: "方法架构图", exact: true }).click();
  const deck = page.locator(`.paper-deck[data-paper-id="${group.paper.id}"]`);
  await deck
    .getByRole("button", {
      name: `打开 ${first.fig_label} ${first.title}`,
      exact: true,
    })
    .click();
  const image = page.locator(".image-wrap img");
  await expect(image).toHaveAttribute("data-figure-id", first.id);
  await expect(image).toHaveAttribute("data-resolution", "hd", {
    timeout: 20000,
  });
  await page.evaluate(() => {
    (window as any).qaFrame = document.querySelector(".inspector-body");
    (window as any).qaImage = document.querySelector(".image-wrap img");
  });
  await page
    .getByRole("button", { name: `同文 ${slow.fig_label}`, exact: true })
    .click();
  await expect(page.locator(".modal-heading h2")).toHaveText(
    `${slow.fig_label} · 图表检视器`,
  );
  expect(
    await page.evaluate(
      () =>
        document.querySelector(".inspector-body") === (window as any).qaFrame &&
        document.querySelector(".image-wrap img") === (window as any).qaImage,
    ),
  ).toBeTruthy();
  await expect(page.locator(".inspector-loading")).toHaveCount(0);
  const notice = page.locator(".image-load-status");
  await expect(notice).toContainText("高清图加载中");
  const noticeBox = (await notice.boundingBox())!;
  const canvasBox = (await page.locator(".inspector-canvas").boundingBox())!;
  expect(
    Math.abs(
      noticeBox.x + noticeBox.width / 2 - canvasBox.x - canvasBox.width / 2,
    ),
  ).toBeLessThan(2);
  expect(
    await notice
      .locator("strong")
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
  ).toBeGreaterThanOrEqual(14);

  await expect(image).toBeVisible();
  expect(
    await image.evaluate((img: HTMLImageElement) => img.naturalWidth > 0),
  ).toBeTruthy();
  await page
    .getByRole("button", { name: `同文 ${last.fig_label}`, exact: true })
    .click();
  await expect(image).toHaveAttribute("data-figure-id", last.id, {
    timeout: 20000,
  });
  await expect(image).toHaveAttribute("data-resolution", "hd", {
    timeout: 20000,
  });
  await expect(notice).toHaveCount(0);
  await page.waitForTimeout(1400);
  await expect(image).toHaveAttribute("data-figure-id", last.id);
  expect(
    await page.evaluate(
      () =>
        document.querySelector(".inspector-body") === (window as any).qaFrame &&
        document.querySelector(".image-wrap img") === (window as any).qaImage,
    ),
  ).toBeTruthy();
});
