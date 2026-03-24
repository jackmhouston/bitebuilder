const { test, expect } = require("@playwright/test");

const flowPages = ["/project/chat", "/project/intake", "/project/generate", "/project/export"];

test("copilot layout margin and message padding", async ({ page }) => {
  await page.goto("/project/chat");
  await expect(page.locator(".app-shell")).toBeVisible();

  const appShell = page.locator(".app-shell");
  const appPaddingLeft = await appShell.evaluate((node) => {
    return parseFloat(getComputedStyle(node).paddingLeft);
  });
  expect(appPaddingLeft).toBeGreaterThanOrEqual(24);

  const messageCount = await page.locator(".message").count();
  if (messageCount === 0) {
    await page.evaluate(() => {
      const log = document.querySelector(".chat-log");
      if (!log) return;
      const message = document.createElement("div");
      message.className = "message";
      message.innerHTML = "<div class='message-role'>assistant</div><div class='message-body'>Layout probe</div>";
      log.appendChild(message);
    });
  }

  const firstMessage = page.locator(".message").first();
  await expect(firstMessage).toHaveCount(1);
  const messagePaddingTop = await firstMessage.evaluate((node) => {
    return parseFloat(getComputedStyle(node).paddingTop);
  });
  expect(messagePaddingTop).toBeGreaterThanOrEqual(12);
});

test("chat, intake, generate, and export pages load without layout breakage", async ({ page }) => {
  for (const path of flowPages) {
    const consoleErrors = [];
    page.on("console", (entry) => {
      if (entry.type() === "error") {
        consoleErrors.push(entry.text());
      }
    });

    await page.goto(path);
    await expect(page.locator(".app-shell")).toBeVisible();
    expect(consoleErrors).toEqual([]);
  }
});
