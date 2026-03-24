const { test, expect } = require("@playwright/test");

test("copilot siderail removes model controls", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (entry) => {
    if (entry.type() === "error") {
      consoleErrors.push(entry.text());
    }
  });

  await page.goto("/project/chat");

  const modelSelect = await page.evaluate(() => document.querySelector("#modelSelect"));
  const timeoutInput = await page.evaluate(() => document.querySelector("#timeoutInput"));
  const thinkingModeSelect = await page.evaluate(() => document.querySelector("#thinkingModeSelect"));

  expect(modelSelect).toBeNull();
  expect(timeoutInput).toBeNull();
  expect(thinkingModeSelect).toBeNull();
  await expect(page.locator("#checkModelsButton")).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});
