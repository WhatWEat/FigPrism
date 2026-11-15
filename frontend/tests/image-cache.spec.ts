import { test, expect } from "@playwright/test";

test("reopening a figure reuses its decoded HD image", async ({ page, request }) => {
  const feed = await (await request.get("/api/figures/feed?limit=1")).json();
  const group = feed.items[0];
  test.skip(!group, "Needs a real paper");
  await page.addInitScript(() => {
    const counts: Record<string, number> = {};
    (window as any).__imageDecodes = counts;
    const decode = HTMLImageElement.prototype.decode;
    HTMLImageElement.prototype.decode = function () {
      const path = new URL(this.src, window.location.href).pathname;
      counts[path] = (counts[path] || 0) + 1;
      return decode.call(this);
    };
  });
  await page.goto("/");
  await page.getByRole("textbox", { name: "搜索图表" }).fill(group.paper.title);
  const card = page.locator(`.paper-deck[data-paper-id="${group.paper.id}"] .deck-hero`);
  await card.click();
  const hd = page.locator('.inspector-modal img[src*="/api/assets/hd/"]');
  await expect(hd).toBeVisible({ timeout: 30000 });
  const actual = await hd.getAttribute("src");
  const path = new URL(actual!, "http://localhost").pathname;
  const before = await page.evaluate((p) => (window as any).__imageDecodes[p] || 0, path);
  expect(before).toBeGreaterThan(0);
  await page.keyboard.press("Escape");
  await card.click();
  await expect(page.locator(`.inspector-modal img[src="${actual}"]`)).toBeVisible();
  const after = await page.evaluate((p) => (window as any).__imageDecodes[p] || 0, path);
  expect(after).toBe(before);
});
