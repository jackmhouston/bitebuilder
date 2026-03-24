const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "tests/playwright",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8000",
    headless: Boolean(process.env.CI),
  },
  webServer: {
    command: "python webapp.py",
    url: "http://127.0.0.1:8000/project/chat",
    reuseExistingServer: !process.env.CI,
  },
});
