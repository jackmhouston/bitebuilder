const { test, expect } = require("@playwright/test");

const CHAT_MESSAGE = `Before the recommendation:

**[HOOK] Hero Cut (00:00:01:00–00:00:11:00)**
*A strong opener that references [3] and gets attention immediately.*
- Why it works: It starts with clear motion from segment [4].`;

test("renders bite recommendations as blue cards", async ({ page }) => {
  await page.addInitScript((payload) => {
    window.localStorage.setItem("bitebuilder.studio.draft.v2", JSON.stringify(payload));
  }, {
    messages: [
      {
        role: "assistant",
        content: CHAT_MESSAGE,
      },
    ],
    transcriptSegments: [
      { segment_index: 3, tc_in: "00:00:01:00", tc_out: "00:00:11:00", speaker: "Host", text: "Segment three" },
      { segment_index: 4, tc_in: "00:00:11:00", tc_out: "00:00:21:00", speaker: "Host", text: "Segment four" },
    ],
  });

  await page.goto("/project/chat");

  const card = page.locator(".bite-card");
  await expect(card).toHaveCount(1);

  const borderColor = await card.evaluate((element) => getComputedStyle(element).borderLeftColor);
  expect(borderColor).toBe("rgb(36, 88, 196)");

  await expect(page.locator(".bite-card-label")).toHaveText("HOOK");
  await expect(page.locator('.bite-card .segment-chip[data-chat-keep-index="3"]')).toHaveCount(1);
  await expect(page.locator('.bite-card .segment-chip[data-chat-keep-index="4"]')).toHaveCount(1);
});
