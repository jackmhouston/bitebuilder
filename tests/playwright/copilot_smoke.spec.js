const { expect, test } = require("@playwright/test");

const BITE_MESSAGE = `**[HOOK] Hook Opener (00:00:00:00–00:00:10:00)**
*A clean opener that lands the core premise.*
- Why it works: It sets the expected tone before the core claim.
`;

test("copilot end-to-end smoke: core UX and re-rendered bite card", async ({ page }) => {
  await page.addInitScript((payload) => {
    const storageKey = "bitebuilder.studio.draft.v2";
    window.localStorage.setItem(storageKey, JSON.stringify(payload));
  }, {
    messages: [
      {
        role: "assistant",
        content: BITE_MESSAGE,
      },
    ],
    transcriptSegments: [
      {
        segment_index: 0,
        tc_in: "00:00:00:00",
        tc_out: "00:00:10:00",
        speaker: "Host",
        text: "The opening segment.",
      },
    ],
  });

  await page.goto("/project/copilot");

  const pageTitle = await page.title();
  const pageHeading = await page.locator("h1").innerText();
  expect(pageTitle.includes("BiteBuilder") || pageHeading.includes("BiteBuilder") || pageHeading.includes("Copilot")).toBe(true);

  const modelSelect = await page.locator("#modelSelect").count();
  const timeoutInput = await page.locator("#timeoutInput").count();
  expect(modelSelect).toBe(0);
  expect(timeoutInput).toBe(0);

  const appShellPaddingLeft = await page.locator(".app-shell").evaluate((element) => {
    return parseFloat(getComputedStyle(element).paddingLeft);
  });
  expect(appShellPaddingLeft).toBeGreaterThanOrEqual(24);

  await page.evaluate((payload) => {
    const storageKey = "bitebuilder.studio.draft.v2";
    const currentDraft = JSON.parse(window.localStorage.getItem(storageKey) || "{}");
    const nextDraft = {
      ...currentDraft,
      messages: payload.messages,
      transcriptSegments: payload.transcriptSegments,
    };
    window.localStorage.setItem(storageKey, JSON.stringify(nextDraft));
    if (typeof window.state !== "undefined") {
      window.state = nextDraft;
      if (typeof window.renderAll === "function") {
        window.renderAll();
      } else if (typeof window.renderChat === "function") {
        window.renderChat();
      }
    }
  }, {
    messages: [
      {
        role: "assistant",
        content: BITE_MESSAGE,
      },
    ],
    transcriptSegments: [
      {
        segment_index: 0,
        tc_in: "00:00:00:00",
        tc_out: "00:00:10:00",
        speaker: "Host",
        text: "The opening segment.",
      },
    ],
  });

  const biteCard = page.locator(".bite-card");
  await expect(biteCard).toHaveCount(1);

  const borderLeftStyle = await biteCard.first().evaluate((element) => {
    return getComputedStyle(element).borderLeftStyle;
  });
  expect(borderLeftStyle).toBe("solid");
});
