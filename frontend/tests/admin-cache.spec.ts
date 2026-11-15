import { test, expect } from "@playwright/test";

test("admin shows both cache pools, refreshes usage and fits a phone screen", async ({
  page,
}) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      json: { user: { id: 1, username: "cache-admin", role: "admin" } },
    }),
  );
  await page.route("**/api/admin/overview", (route) =>
    route.fulfill({
      json: {
        domains: [],
        users: [],
        repairs: [],
        review_count: 0,
        vision_driver: "test",
        vision_model: "test",
      },
    }),
  );
  let storage = {
    used_bytes: 1_375_000_000,
    limit_bytes: 3_000_000_000,
    normal_used_bytes: 1_250_000_000,
    normal_limit_bytes: 2_500_000_000,
    favorite_used_bytes: 125_000_000,
    favorite_limit_bytes: 500_000_000,
  };
  await page.route("**/api/admin/pipeline", (route) =>
    route.fulfill({ json: { stages: {}, storage } }),
  );
  await page.goto("/admin");
  const normal = page.getByRole("group", { name: "普通缓存" });
  const favorite = page.getByRole("group", { name: "收藏缓存" });
  await expect(normal).toContainText("1.25 GB");
  await expect(normal).toContainText("2.5 GB");
  await expect(normal.getByRole("progressbar")).toHaveAttribute("value", "50");
  await expect(favorite).toContainText("125 MB");
  await expect(favorite).toContainText("500 MB");
  await expect(favorite.getByRole("progressbar")).toHaveAttribute(
    "value",
    "25",
  );
  storage = {
    ...storage,
    used_bytes: 0,
    normal_used_bytes: 0,
    favorite_used_bytes: 0,
    favorite_limit_bytes: 0,
  };
  await expect(normal.getByRole("progressbar")).toHaveAttribute("value", "0", {
    timeout: 10000,
  });
  await expect(favorite).toContainText("0 B");
  await expect(favorite.getByRole("progressbar")).toHaveAttribute("value", "0");
  await page.setViewportSize({ width: 375, height: 812 });
  const normalBox = await normal.boundingBox();
  const favoriteBox = await favorite.boundingBox();
  expect(normalBox).not.toBeNull();
  expect(favoriteBox!.y).toBeGreaterThan(normalBox!.y);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});

test("a failed cache query displays an error instead of zero usage", async ({
  page,
}) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      json: { user: { id: 1, username: "cache-admin", role: "admin" } },
    }),
  );
  await page.route("**/api/admin/overview", (route) =>
    route.fulfill({
      json: {
        domains: [],
        users: [],
        repairs: [],
        review_count: 0,
        vision_driver: "test",
        vision_model: "test",
      },
    }),
  );
  await page.route("**/api/admin/pipeline", (route) =>
    route.fulfill({ status: 503, json: { detail: "缓存用量读取失败" } }),
  );
  await page.goto("/admin");
  await expect(page.getByText("缓存用量读取失败", { exact: true })).toBeVisible(
    { timeout: 15000 },
  );
  await expect(page.getByRole("progressbar")).toHaveCount(0);
});
