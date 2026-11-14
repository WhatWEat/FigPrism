import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
const credentials = JSON.parse(
  readFileSync(
    path.resolve(__dirname, "../../data/qa/e2e-account.json"),
    "utf8",
  ),
);

test("default paper deck scrubs colors, expands inline and navigates siblings", async ({
  page,
  request,
}) => {
  const feed = await (await request.get("/api/figures/feed")).json();
  const group = feed.items.find((g: any) => g.matched_figures.length >= 3);
  test.skip(!group, "Needs a paper with at least three figures");
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "图组胶片流", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".paper-deck")).toHaveCount(feed.items.length);
  const deck = page.locator(`.paper-deck[data-paper-id="${group.paper.id}"]`);
  await expect(deck).toHaveAttribute(
    "data-active-figure",
    group.hero_figure_id,
  );
  const target = group.matched_figures.find(
    (f: any) => f.id !== group.hero_figure_id && f.palette.colors.length,
  );
  const before = (await deck.locator(".deck-hero").boundingBox())!.height;
  const thumb = deck.locator(
    `.filmstrip button[data-figure-id="${target.id}"]`,
  );
  await thumb.hover();
  await expect(deck).toHaveAttribute("data-active-figure", target.id);
  await expect(deck.locator(".deck-hero-label")).toContainText(
    target.fig_label,
  );
  await expect(
    deck.locator(".deck-footer .swatches button").first(),
  ).toHaveAttribute("title", "复制 " + target.palette.colors[0].hex);
  expect(
    Math.abs((await deck.locator(".deck-hero").boundingBox())!.height - before),
  ).toBeLessThan(1);
  await thumb.click();
  await expect(
    page.getByRole("dialog").locator(".modal-heading h2"),
  ).toHaveText(`${target.fig_label} · 图表检视器`);
  const siblings = await (
    await request.get(`/api/papers/${group.paper.id}/figures`)
  ).json();
  await expect(page.locator(".sibling-track button")).toHaveCount(
    siblings.items.length,
  );
  const index = siblings.items.findIndex((f: any) => f.id === target.id);
  const direction = index < siblings.items.length - 1 ? "ArrowDown" : "ArrowUp";
  const next = siblings.items[index + (direction === "ArrowDown" ? 1 : -1)];
  await page.keyboard.press(direction);
  await expect(
    page.getByRole("dialog").locator(".modal-heading h2"),
  ).toHaveText(`${next.fig_label} · 图表检视器`);
  await page.keyboard.press("Escape");
  await deck
    .getByRole("button", { name: `展开平铺 ${group.paper.title}`, exact: true })
    .click();
  await expect(deck.locator(".deck-tile")).toHaveCount(
    group.matched_figures.length,
  );
  await deck
    .getByRole("button", { name: `收起 ${group.paper.title}`, exact: true })
    .click();
  await expect(deck.locator(".filmstrip")).toBeVisible();
});

test("three feed modes persist and filtering only returns matched figures", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "横排画册流", exact: true }).click();
  await expect(page.locator(".paper-swimlane").first()).toBeVisible();
  const track = page.locator(".swimlane-track").first();
  await track.hover();
  await page.mouse.wheel(0, 450);
  await expect
    .poll(() => track.evaluate((el) => el.scrollLeft))
    .toBeGreaterThan(0);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "横排画册流", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "单图平铺流", exact: true }).click();
  await expect(page.locator(".flat-feed .figure-card").first()).toBeVisible();
  await expect(page.locator(".paper-deck")).toHaveCount(0);
  await page.getByRole("button", { name: "图组胶片流", exact: true }).click();
  await page
    .getByRole("button", { name: "折线 / Scaling", exact: true })
    .click();
  const filtered = await (
    await request.get("/api/figures/feed?archetype=Curve")
  ).json();
  await expect(page.locator(".paper-deck")).toHaveCount(filtered.items.length);
  for (const group of filtered.items) {
    const deck = page.locator(`.paper-deck[data-paper-id="${group.paper.id}"]`);
    await expect(deck).toHaveAttribute(
      "data-active-figure",
      group.hero_figure_id,
    );
    await expect(deck.locator(".deck-hero-label")).toContainText(
      "折线 / Scaling",
    );
    await expect(deck.locator(".deck-expand")).toContainText(
      `共 ${group.matched_figures.length} 张图`,
    );
  }
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../data/qa/patch-deck-mobile.png",
    fullPage: true,
  });
});

test("warm tokens and paper blend preserve original eyedropper pixels", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "护眼纸感融合", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(
    await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
  ).toBe("rgb(237, 234, 228)");
  await page.locator(".deck-hero").first().click();
  const image = page.locator(".image-wrap img");
  await expect
    .poll(() =>
      image.evaluate(
        (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
      ),
    )
    .toBeTruthy();
  expect(
    await image.evaluate((img) => getComputedStyle(img).mixBlendMode),
  ).toBe("multiply");
  expect(
    await page
      .locator(".caption-text")
      .evaluate((el) => getComputedStyle(el).color),
  ).toBe("rgb(54, 50, 46)");
  await page.keyboard.press("i");
  const rect = (await image.boundingBox())!;
  const position = {
    x: rect.x + rect.width * 0.4,
    y: rect.y + rect.height * 0.4,
  };
  await page.evaluate(() => {
    document
      .querySelector(".image-stage")!
      .addEventListener("pointermove", (event) => {
        (window as any).qaPointer = {
          x: (event as PointerEvent).clientX,
          y: (event as PointerEvent).clientY,
        };
      });
  });
  await page.mouse.move(position.x, position.y);
  const expected = await image.evaluate((img: HTMLImageElement) => {
    const pointer = (window as any).qaPointer;
    const rect = img.getBoundingClientRect();
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(img, 0, 0);
    const px = Math.floor(
      ((pointer.x - rect.left) / rect.width) * img.naturalWidth,
    );
    const py = Math.floor(
      ((pointer.y - rect.top) / rect.height) * img.naturalHeight,
    );
    return (
      "#" +
      [...ctx.getImageData(px, py, 1, 1).data]
        .slice(0, 3)
        .map((v) => v.toString(16).padStart(2, "0"))
        .join("")
        .toUpperCase()
    );
  });
  await expect(page.locator(".loupe span")).toHaveText(expected);
  await page.getByRole("button", { name: "切换护眼纸感", exact: true }).click();
  await expect(image).not.toHaveClass(/fig-paper-blend/);
  await page.mouse.move(position.x, position.y);
  await expect(page.locator(".loupe span")).toHaveText(expected);
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(
    page.getByRole("button", { name: "护眼纸感融合", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
});

test("swimlane saves the whole matched paper atomically to a private board", async ({
  page,
}) => {
  expect(
    (
      await page.request.post("/api/auth/login", {
        data: {
          username: credentials.username,
          password: credentials.password,
        },
      })
    ).status(),
  ).toBe(200);
  const board = await (
    await page.request.post("/api/collections", {
      data: { name: "E2E paper group" },
    })
  ).json();
  try {
    await page.goto("/");
    await page.getByRole("button", { name: "横排画册流", exact: true }).click();
    const lane = page.locator(".paper-swimlane").first();
    await expect(lane).toBeVisible();
    const count = await lane.locator(".swimlane-figure").count();
    await lane
      .getByRole("button", { name: "收藏整篇好图", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText(
      `已收藏 ${count} 张图`,
    );
    const saved = await (
      await page.request.get("/api/collections/" + board.id)
    ).json();
    expect(saved.items).toHaveLength(count);
    expect(new Set(saved.items.map((f: any) => f.paper_id)).size).toBe(1);
  } finally {
    await page.request.delete("/api/collections/" + board.id);
  }
});
