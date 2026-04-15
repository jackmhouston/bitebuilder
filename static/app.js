const STORAGE_KEY = "bitebuilder.studio.draft.v2";
const WORKFLOW_OPERATION_SNAPSHOTS = ["received", "validating", "prompting", "generating", "finalizing"];

function createEmptyPlan() {
  return {
    opening_segment_index: null,
    must_include_segment_indexes: [],
    generation_directive: "",
    narrative_arc: "",
    speaker_balance: "",
    rationale: "",
    source_segment_indexes: [],
  };
}

function createSourcePair(seed = {}) {
  return {
    id: seed.id || `source-${Math.random().toString(36).slice(2, 10)}`,
    transcriptText: seed.transcriptText || "",
    xmlText: seed.xmlText || "",
    transcriptName: seed.transcriptName || "",
    xmlName: seed.xmlName || "",
  };
}

function normalizeSourcePairs(sourcePairs = [], fallback = {}) {
  const rawPairs = Array.isArray(sourcePairs) ? sourcePairs : [];
  const normalized = rawPairs.map((pair) => createSourcePair(pair));
  if (!normalized.length && (fallback.transcriptText || fallback.xmlText || fallback.transcriptName || fallback.xmlName)) {
    normalized.push(createSourcePair({
      transcriptText: fallback.transcriptText,
      xmlText: fallback.xmlText,
      transcriptName: fallback.transcriptName,
      xmlName: fallback.xmlName,
    }));
  }
  return normalized.length ? normalized : [createSourcePair()];
}

function syncLegacyFieldsFromSources(pairs) {
  const firstComplete = (pairs || []).find((pair) => pair.transcriptText && pair.xmlText) || (pairs || [])[0] || createSourcePair();
  const completeCount = (pairs || []).filter((pair) => pair.transcriptText && pair.xmlText).length;
  return {
    transcriptText: firstComplete.transcriptText || "",
    xmlText: firstComplete.xmlText || "",
    transcriptName: completeCount > 1 ? `${completeCount} sources loaded` : (firstComplete.transcriptName || ""),
    xmlName: completeCount > 1 ? `${completeCount} XMLs loaded` : (firstComplete.xmlName || ""),
  };
}

function createDefaultState() {
  return {
    projectTitle: "Untitled project",
    projectNotes: "",
    sourcePairs: [createSourcePair()],
    transcriptText: "",
    xmlText: "",
    transcriptName: "",
    xmlName: "",
    brief: "",
    projectContext: "",
    model: "",
    thinkingMode: "auto",
    options: 3,
    timeout: 180,
    variantName: "v1",
    speakerBalance: "balanced",
    messages: [],
    transcriptSegments: [],
    candidateShortlist: [],
    pinnedSegmentIndexes: [],
    bannedSegmentIndexes: [],
    requiredSegmentIndexes: [],
    lockedSegmentIndexes: [],
    forcedOpenSegmentIndex: null,
    manualAssemblyIndexes: [],
    focusedSegmentIndex: null,
    suggestedPlan: createEmptyPlan(),
    acceptedPlan: createEmptyPlan(),
    runHistory: [],
    compareLeftRunId: "",
    compareRightRunId: "",
    currentJob: null,
    currentJobStatus: "",
    currentJobLogs: [],
    lastError: null,
    lastOperation: null,
    lastGeneration: null,
  };
}

function loadState() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
    const savedRunHistory = Array.isArray(saved.runHistory) ? saved.runHistory : [];
    const savedLastGeneration = saved.lastGeneration || savedRunHistory[0] || null;
    const sourcePairs = normalizeSourcePairs(saved.sourcePairs, saved);
    return {
      ...createDefaultState(),
      ...saved,
      ...syncLegacyFieldsFromSources(sourcePairs),
      sourcePairs,
      messages: Array.isArray(saved.messages) ? saved.messages : [],
      transcriptSegments: Array.isArray(saved.transcriptSegments) ? saved.transcriptSegments : [],
      candidateShortlist: Array.isArray(saved.candidateShortlist) ? saved.candidateShortlist : [],
      pinnedSegmentIndexes: Array.isArray(saved.pinnedSegmentIndexes) ? saved.pinnedSegmentIndexes : [],
      bannedSegmentIndexes: Array.isArray(saved.bannedSegmentIndexes) ? saved.bannedSegmentIndexes : [],
      requiredSegmentIndexes: Array.isArray(saved.requiredSegmentIndexes) ? saved.requiredSegmentIndexes : [],
      lockedSegmentIndexes: Array.isArray(saved.lockedSegmentIndexes) ? saved.lockedSegmentIndexes : [],
      manualAssemblyIndexes: Array.isArray(saved.manualAssemblyIndexes) ? saved.manualAssemblyIndexes : [],
      suggestedPlan: normalizePlan(saved.suggestedPlan),
      acceptedPlan: normalizePlan(saved.acceptedPlan),
      runHistory: savedRunHistory,
      currentJob: null,
      currentJobStatus: "",
      currentJobLogs: [],
      lastGeneration: savedLastGeneration,
    };
  } catch (_error) {
    return createDefaultState();
  }
}

let state = loadState();
let modelInventory = [];
let modelLookupState = "idle";
let modelLookupMessage = "";

const pageKey = document.body.dataset.page || "";
const pageStatus = document.querySelector("[data-page-status]");
const pageStatusMessage = pageStatus ? pageStatus.querySelector("[data-page-message]") : null;
const pageErrorContainer = pageStatus ? pageStatus.querySelector("[data-page-error]") : null;
const pageSnapshotContainer = pageStatus ? pageStatus.querySelector("[data-page-snapshot]") : null;
const stepLinks = Array.from(document.querySelectorAll("[data-step-link]"));
const optionsInput = document.getElementById("optionsInput");
const briefInput = document.getElementById("briefInput");
const contextInput = document.getElementById("contextInput");
const projectTitleInput = document.getElementById("projectTitleInput");
const projectNotesInput = document.getElementById("projectNotesInput");
const variantNameInput = document.getElementById("variantNameInput");
const speakerBalanceSelect = document.getElementById("speakerBalanceSelect");
const transcriptFileInput = document.getElementById("transcriptFile");
const xmlFileInput = document.getElementById("xmlFile");
const sourceList = document.getElementById("sourceList");
const addSourceButton = document.getElementById("addSourceButton");
const projectFileInput = document.getElementById("projectFileInput");
const loadSolarDemoButton = document.getElementById("loadSolarDemoButton");
const saveProjectButton = document.getElementById("saveProjectButton");
const transcriptPreview = document.getElementById("transcriptPreview");
const xmlPreview = document.getElementById("xmlPreview");
const startFreshButton = document.getElementById("startFreshButton");
const startOverButton = document.getElementById("startOverButton");
const continueFromIntakeButton = document.getElementById("continueFromIntakeButton");
const continueFromBriefButton = document.getElementById("continueFromBriefButton");
const continueFromChatButton = document.getElementById("continueFromChatButton");
const chatLog = document.getElementById("chatLog");
const chatInput = document.getElementById("chatInput");
const chatButton = document.getElementById("chatButton");
const clearChatButton = document.getElementById("clearChatButton");
const suggestedPlanPanel = document.getElementById("suggestedPlan");
const acceptedPlanPanel = document.getElementById("acceptedPlan");
const acceptedPlanSummary = document.getElementById("acceptedPlanSummary");
const generateButton = document.getElementById("generateButton");
const results = document.getElementById("results");
const transcriptBrowser = document.getElementById("transcriptBrowser");
const transcriptSearchInput = document.getElementById("transcriptSearchInput");
const manualLane = document.getElementById("manualLane");
const manualXmlButton = document.getElementById("manualXmlButton");
const shortlistList = document.getElementById("shortlistList");
const previewShortlistButton = document.getElementById("previewShortlistButton");
const selectedBites = document.getElementById("selectedBites");
const rerunSameFilesButton = document.getElementById("rerunSameFilesButton");
const openFolderButton = document.getElementById("openFolderButton");
const compareLeftSelect = document.getElementById("compareLeftSelect");
const compareRightSelect = document.getElementById("compareRightSelect");
const comparePanel = document.getElementById("comparePanel");
const logsPanel = document.getElementById("logsPanel");
const logsRunSelect = document.getElementById("logsRunSelect");
const jobLog = document.getElementById("jobLog");

function persistState() {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function commitState(patch, { clearGeneration = false, clearError = false } = {}) {
  const normalizedPatch = normalizeStatePatch(patch);
  state = {
    ...state,
    ...normalizedPatch,
    messages: Array.isArray(normalizedPatch.messages) ? normalizedPatch.messages : state.messages,
  };
  if (!normalizedPatch.sourcePairs && Array.isArray(state.sourcePairs)) {
    Object.assign(state, syncLegacyFieldsFromSources(state.sourcePairs));
  }

  if (clearGeneration) {
    state.lastGeneration = null;
  }
  if (clearError) {
    state.lastError = null;
    state.lastOperation = null;
  }

  persistState();
  renderAll();
}

function setStatus(message) {
  if (pageStatusMessage) {
    pageStatusMessage.textContent = message || "";
    return;
  }
  if (pageStatus) {
    pageStatus.textContent = message;
  }
}

function clearInlineError() {
  if (!pageErrorContainer) {
    return;
  }
  pageErrorContainer.innerHTML = "";
  pageStatus?.classList.remove("status-error");
  if (pageStatusMessage) {
    pageStatusMessage.classList.remove("status-error");
  }
  [briefInput, contextInput, projectNotesInput].forEach((element) => {
    element?.classList.remove("input-error");
  });
  [transcriptFileInput, xmlFileInput].forEach((element) => {
    element?.classList.remove("input-error");
  });
}

function operationStageFromMessage(message) {
  const text = String(message || "").toLowerCase();
  if (text.includes("parsing transcript") || text.includes("parsing premiere xml") || text.includes("resolving local model")) {
    return "validating";
  }
  if (text.includes("summarizing editorial direction") || text.includes("running generation attempt")) {
    return "prompting";
  }
  if (text.includes("writing output files")) {
    return "finalizing";
  }
  if (text.includes("selection complete") || text.includes("selection")) {
    return "generating";
  }
  return "generating";
}

function operationStageFromErrorStage(stage) {
  if (stage === "transcript" || stage === "premiere_xml") {
    return "validating";
  }
  if (stage === "selection" || stage === "output") {
    return "generating";
  }
  if (stage === "model" || stage === "brief") {
    return "prompting";
  }
  return operationStageFromMessage("");
}

function formatSnapshotHtml(snapshot = {}) {
  if (!pageSnapshotContainer) {
    return "";
  }
  const current = snapshot.stage || "received";
  const messages = snapshot.log
    ? `<div class="snapshot-line"><strong>Snapshot:</strong><span>${snapshot.log}</span></div>`
    : "";
  return `
    <div class="operation-snapshot">
      <div class="snapshot-line">
        ${WORKFLOW_OPERATION_SNAPSHOTS.map((item) => `<span class="snapshot-chip${item === current ? " is-active" : ""}">${item}</span>`).join("")}
      </div>
      ${messages}
    </div>
  `;
}

function commitOperationSnapshot(message, operation = "generation") {
  const stage = operationStageFromMessage(message);
  state = { ...state, lastOperation: { ...(state.lastOperation || {}), operation, stage, message } };
  persistState();
  if (pageSnapshotContainer) {
    pageSnapshotContainer.innerHTML = formatSnapshotHtml(state.lastOperation);
  }
}

function clearOperationSnapshot() {
  if (pageSnapshotContainer) {
    pageSnapshotContainer.innerHTML = "";
  }
}

function fixErrorAction(error) {
  const stage = (error && error.stage) || "";
  if (stage === "transcript") {
    return "/project/intake";
  }
  if (stage === "premiere_xml") {
    return "/project/intake";
  }
  if (stage === "brief") {
    return "/project/brief";
  }
  if (stage === "model") {
    return "/project/chat";
  }
  if (stage === "selection" || stage === "output") {
    return "/project/generate";
  }
  return "/";
}

function updateFieldErrors(error) {
  if (!error || !error.stage) {
    return;
  }
  if (error.stage === "transcript") {
    transcriptFileInput?.classList.add("input-error");
  }
  if (error.stage === "premiere_xml") {
    xmlFileInput?.classList.add("input-error");
  }
  if (error.stage === "brief") {
    briefInput?.classList.add("input-error");
  }
}

function showError(error, operation) {
  if (!error) {
    return;
  }
  clearInlineError();
  state.lastError = error;
  state.lastOperation = {
    ...(state.lastOperation || {}),
    operation,
    stage: (error.stage && operationStageFromErrorStage(error.stage))
      || state.lastOperation?.stage
      || operationStageFromMessage(error.message),
    message: error.message || "Operation failed.",
  };
  persistState();

  if (pageErrorContainer) {
    const canFix = error.stage || operation;
    const fixHref = canFix ? fixErrorAction(error) : "#";
    const retryLabel = operation === "preview" ? "Try again (Preview)" : "Try again (Generate)";
    const fixLabel = canFix ? "Fix inputs" : "Open relevant step";
    pageErrorContainer.innerHTML = `
      <h3>Error: ${escapeHtml(error.code || "operation_failed")}</h3>
      <p>${escapeHtml(error.message || "An operation did not complete.")}</p>
      <p><strong>Expected format:</strong> ${escapeHtml(error.expected_input_format || "Review inputs and retry.")}</p>
      <p><strong>Next action:</strong> ${escapeHtml(error.next_action || "Retry after updates.")}</p>
      <div class="actions">
        <a class="button button-secondary" href="${fixHref}">${fixLabel}</a>
        <button class="button" type="button" data-recover-action="retry">${escapeHtml(retryLabel)}</button>
      </div>
    `;
    pageStatus?.classList.add("status-error");
  }
  if (error.stage) {
    updateFieldErrors(error);
  }
  setStatus(`${error.message}`);
  renderOperationSnapshot();
  renderStepLinks();
}

function sanitizeFilename(value, fallback = "project") {
  return String(value || fallback)
    .trim()
    .replace(/[^a-z0-9._-]+/gi, "-")
    .replace(/^-+|-+$/g, "") || fallback;
}

function uniqueNumbers(values) {
  return Array.from(new Set((values || []).map((value) => Number(value)).filter((value) => Number.isInteger(value) && value >= 0)));
}

function normalizePlan(plan = {}) {
  const normalized = {
    ...createEmptyPlan(),
    ...(plan || {}),
  };
  const openingValue = normalized.opening_segment_index;
  const parsedOpening = openingValue == null || openingValue === ""
    ? null
    : Number(openingValue);
  normalized.opening_segment_index = Number.isInteger(parsedOpening)
    && parsedOpening >= 0
    ? parsedOpening
    : null;
  normalized.must_include_segment_indexes = uniqueNumbers(normalized.must_include_segment_indexes);
  normalized.source_segment_indexes = uniqueNumbers(normalized.source_segment_indexes);
  normalized.generation_directive = String(normalized.generation_directive || "").trim();
  normalized.narrative_arc = String(normalized.narrative_arc || "").trim();
  normalized.speaker_balance = String(normalized.speaker_balance || "").trim();
  normalized.rationale = String(normalized.rationale || "").trim();
  return normalized;
}

function planHasContent(plan) {
  const normalized = normalizePlan(plan);
  return (
    Number.isInteger(normalized.opening_segment_index)
    || normalized.must_include_segment_indexes.length > 0
    || Boolean(normalized.generation_directive)
    || Boolean(normalized.narrative_arc)
    || Boolean(normalized.speaker_balance)
    || Boolean(normalized.rationale)
  );
}

function normalizeStatePatch(patch = {}) {
  const next = { ...patch };
  if ("sourcePairs" in next) {
    next.sourcePairs = normalizeSourcePairs(next.sourcePairs, next);
    Object.assign(next, syncLegacyFieldsFromSources(next.sourcePairs));
  }
  if ("pinnedSegmentIndexes" in next) {
    next.pinnedSegmentIndexes = uniqueNumbers(next.pinnedSegmentIndexes);
  }
  if ("bannedSegmentIndexes" in next) {
    next.bannedSegmentIndexes = uniqueNumbers(next.bannedSegmentIndexes);
  }
  if ("requiredSegmentIndexes" in next) {
    next.requiredSegmentIndexes = uniqueNumbers(next.requiredSegmentIndexes);
  }
  if ("lockedSegmentIndexes" in next) {
    next.lockedSegmentIndexes = uniqueNumbers(next.lockedSegmentIndexes);
  }
  if ("manualAssemblyIndexes" in next) {
    next.manualAssemblyIndexes = uniqueNumbers(next.manualAssemblyIndexes);
  }
  if ("transcriptSegments" in next && !Array.isArray(next.transcriptSegments)) {
    next.transcriptSegments = [];
  }
  if ("candidateShortlist" in next && !Array.isArray(next.candidateShortlist)) {
    next.candidateShortlist = [];
  }
  if ("runHistory" in next && !Array.isArray(next.runHistory)) {
    next.runHistory = [];
  }
  if ("currentJobLogs" in next && !Array.isArray(next.currentJobLogs)) {
    next.currentJobLogs = [];
  }
  if ("suggestedPlan" in next) {
    next.suggestedPlan = normalizePlan(next.suggestedPlan);
  }
  if ("acceptedPlan" in next) {
    next.acceptedPlan = normalizePlan(next.acceptedPlan);
  }
  return next;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function truncate(text, maxLength = 1600) {
  if (!text) {
    return "";
  }
  return text.length > maxLength ? `${text.slice(0, maxLength)}\n\n[...]` : text;
}

function compactText(text, fallback) {
  if (!text || !text.trim()) {
    return fallback;
  }
  const normalized = text.trim().replace(/\s+/g, " ");
  return normalized.length > 220 ? `${normalized.slice(0, 220)}...` : normalized;
}

function countTranscriptSegments(transcriptText) {
  return (transcriptText.match(/\d{2}:\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2}:\d{2}/g) || []).length;
}

function findSegment(index) {
  return (state.transcriptSegments || []).find((segment) => Number(segment.segment_index) === Number(index)) || null;
}

function findCandidate(index) {
  return (state.candidateShortlist || []).find((candidate) => Number(candidate.segment_index) === Number(index)) || null;
}

function segmentStates(index) {
  const accepted = normalizePlan(state.acceptedPlan);
  return {
    isOpening: accepted.opening_segment_index === index || state.forcedOpenSegmentIndex === index,
    isRequired: accepted.must_include_segment_indexes.includes(index) || state.requiredSegmentIndexes.includes(index),
    isPinned: state.pinnedSegmentIndexes.includes(index),
    isLocked: state.lockedSegmentIndexes.includes(index),
    isManual: state.manualAssemblyIndexes.includes(index),
    isBanned: state.bannedSegmentIndexes.includes(index),
    isShortlisted: (state.candidateShortlist || []).some((candidate) => Number(candidate.segment_index) === Number(index)),
  };
}

function isKeptState(states) {
  return Boolean(states.isOpening || states.isRequired || states.isPinned || states.isLocked || states.isManual);
}

function segmentCardTone(index) {
  const states = segmentStates(index);
  if (states.isBanned) {
    return "is-banned";
  }
  if (isKeptState(states)) {
    return "is-kept";
  }
  return "";
}

function renderStateBadges(index) {
  const states = segmentStates(index);
  const badges = [];
  if (states.isOpening) {
    badges.push('<span class="segment-chip is-static is-opening">Opening</span>');
  }
  if (states.isRequired) {
    badges.push('<span class="segment-chip is-static is-kept">Must use</span>');
  }
  if (states.isPinned) {
    badges.push('<span class="segment-chip is-static is-kept">Keep</span>');
  }
  if (states.isLocked) {
    badges.push('<span class="segment-chip is-static is-kept">Locked</span>');
  }
  if (states.isManual) {
    badges.push('<span class="segment-chip is-static is-kept">Lane</span>');
  }
  if (states.isShortlisted) {
    badges.push('<span class="segment-chip is-static">Candidate</span>');
  }
  if (states.isBanned) {
    badges.push('<span class="segment-chip is-static is-banned">Skip</span>');
  }
  return badges.join("");
}

function renderWithSegmentChips(source) {
  const normalized = String(source || "");
  const parts = [];
  const regex = /\[(\d+)\]/g;
  let cursor = 0;
  let match = regex.exec(normalized);

  while (match) {
    const index = Number(match[1]);
    const textChunk = normalized.slice(cursor, match.index);
    if (textChunk) {
      parts.push(`<span class="message-body-text">${escapeHtml(textChunk).replace(/\n/g, "<br>")}</span>`);
    }
    const states = segmentStates(index);
    const classes = ["segment-chip"];
    if (states.isOpening) {
      classes.push("is-opening");
    } else if (states.isBanned) {
      classes.push("is-banned");
    } else if (isKeptState(states)) {
      classes.push("is-kept");
    }
    parts.push(
      `<button class="${classes.join(" ")}" type="button" data-chat-keep-index="${index}" title="Keep this segment for generate">[${index}]</button>`,
    );
    cursor = match.index + match[0].length;
    match = regex.exec(normalized);
  }

  const remainder = normalized.slice(cursor);
  if (remainder) {
    parts.push(`<span class="message-body-text">${escapeHtml(remainder).replace(/\n/g, "<br>")}</span>`);
  }

  if (!parts.length) {
    return escapeHtml(normalized).replace(/\n/g, "<br>");
  }

  return parts.join("");
}

function renderBiteCardSection(label, titleText, timecodeRange, quoteLine, whyLine) {
  const pieces = [];
  pieces.push(
    [
      '<div class="bite-card">',
      '  <div class="bite-card-header">',
      `    <span class="bite-card-label">${escapeHtml(label)}</span>`,
      `    <span class="bite-card-title">${escapeHtml(titleText)}</span>`,
      `    <span class="bite-card-timecode">${escapeHtml(timecodeRange)}</span>`,
      "  </div>",
    ].join("\n"),
  );

  if (quoteLine) {
    pieces.push(`<div class="bite-card-quote"><em>${renderWithSegmentChips(quoteLine)}</em></div>`);
  }

  if (whyLine) {
    pieces.push(`<div class="bite-card-why"><strong>Why it works:</strong> ${renderWithSegmentChips(whyLine)}</div>`);
  }

  pieces.push("</div>");
  return pieces.join("\n");
}

function renderChatMessageContent(content) {
  const source = String(content || "");
  const blockPattern = /^\*\*\[(.+?)\](.*)\((\d{2}:\d{2}:\d{2}[:;]\d{2}[\u2013-]\d{2}:\d{2}:\d{2}[:;]\d{2})\)\*\*$/;
  const quotePattern = /^\*(.+)\*$/;
  const whyPattern = /^\s*[-*]\s*Why it works:\s*(.+)$/i;

  const lines = source.split("\n");
  const parts = [];
  const proseLines = [];

  const flushProse = () => {
    if (!proseLines.length) {
      return;
    }
    parts.push(renderWithSegmentChips(proseLines.join("\n")));
    proseLines.length = 0;
  };

  for (let i = 0; i < lines.length; i += 1) {
    const rawLine = lines[i];
    const line = rawLine.trimEnd();
    const match = line.match(blockPattern);

    if (match) {
      flushProse();

      const label = (match[1] || "").trim();
      const titleText = (match[2] || "").trim();
      const timecodeRange = match[3] || "";

      let quoteLine = "";
      let whyLine = "";

      const nextLine = lines[i + 1];
      if (nextLine && quotePattern.test(nextLine.trim()) && !nextLine.trimStart().startsWith("**")) {
        const matchedQuote = nextLine.trim().match(quotePattern);
        if (matchedQuote) {
          quoteLine = matchedQuote[1];
          i += 1;
        }
      }

      const potentialWhyLine = lines[i + 1];
      if (potentialWhyLine) {
        const matchedWhy = potentialWhyLine.match(whyPattern);
        if (matchedWhy) {
          whyLine = matchedWhy[1];
          i += 1;
        }
      }

      parts.push(renderBiteCardSection(label, titleText, timecodeRange, quoteLine, whyLine));
      continue;
    }

    proseLines.push(rawLine);
  }

  flushProse();

  if (!parts.length) {
    return renderWithSegmentChips(source);
  }

  return parts.join("");
}

function segmentLabel(index) {
  const segment = findSegment(index);
  if (!segment) {
    return `Segment ${index}`;
  }
  return `${segment.tc_in} ${segment.speaker}: ${compactText(segment.text, "")}`;
}

function formatSeconds(value) {
  const amount = Number(value || 0);
  return Number.isFinite(amount) ? `${amount.toFixed(1)}s` : "0.0s";
}

function rawDurationSeconds(value) {
  const amount = Number(value || 0);
  return Number.isFinite(amount) ? amount : 0;
}

function getSegmentDuration(index) {
  const segment = findSegment(index);
  if (!segment) {
    return 0;
  }
  const duration = Number(segment.duration_seconds);
  return Number.isFinite(duration) ? duration : 0;
}

function speakerBalanceLabel(value) {
  if (value === "ceo") {
    return "More CEO";
  }
  if (value === "worker") {
    return "More worker";
  }
  if (value === "balanced") {
    return "Balanced";
  }
  return value || "";
}

function formatPlanInline(plan) {
  const normalized = normalizePlan(plan);
  const parts = [];
  if (Number.isInteger(normalized.opening_segment_index)) {
    parts.push(`open [${normalized.opening_segment_index}]`);
  }
  if (normalized.must_include_segment_indexes.length) {
    parts.push(`must include ${normalized.must_include_segment_indexes.map((value) => `[${value}]`).join(", ")}`);
  }
  if (normalized.narrative_arc) {
    parts.push(normalized.narrative_arc);
  }
  if (normalized.generation_directive) {
    parts.push(compactText(normalized.generation_directive, "Directive"));
  }
  return parts.join(" | ") || "None";
}

function buildPreviewCutFromSegment(index, purpose = "", reason = "") {
  const segment = findSegment(index);
  if (!segment) {
    return null;
  }
  const candidate = findCandidate(index);
  return {
    segment_index: index,
    tc_in: segment.tc_in,
    tc_out: segment.tc_out,
    speaker: segment.speaker,
    text: segment.text,
    duration_seconds: candidate?.duration_seconds || getSegmentDuration(index),
    purpose: purpose || (candidate?.roles || [])[0] || "",
    reasons: [
      ...(candidate?.reasons || []),
      ...(reason ? [reason] : []),
    ].filter(Boolean),
  };
}

function derivePreviewCuts() {
  const activeFile = getActiveGeneration()?.files?.[0];
  if (activeFile?.selected_cuts?.length) {
    return {
      source: `Last run | ${formatSeconds(activeFile.actual_duration_seconds)} | ${activeFile.cut_count} cuts`,
      cuts: activeFile.selected_cuts.map((cut) => ({
        ...cut,
        duration_seconds: rawDurationSeconds(cut.duration_seconds || getSegmentDuration(cut.segment_index)),
      })),
    };
  }

  if (state.manualAssemblyIndexes.length) {
    return {
      source: "Manual lane",
      cuts: state.manualAssemblyIndexes
        .map((index, order) => buildPreviewCutFromSegment(index, `Manual ${order + 1}`, "manual lane"))
        .filter(Boolean),
    };
  }

  const accepted = normalizePlan(state.acceptedPlan);
  const orderedIndexes = [];
  const addIndex = (index) => {
    if (Number.isInteger(index) && index >= 0 && !orderedIndexes.includes(index) && !state.bannedSegmentIndexes.includes(index)) {
      orderedIndexes.push(index);
    }
  };

  addIndex(accepted.opening_segment_index);
  accepted.must_include_segment_indexes.forEach(addIndex);
  state.requiredSegmentIndexes.forEach(addIndex);
  state.lockedSegmentIndexes.forEach(addIndex);
  state.pinnedSegmentIndexes.forEach(addIndex);

  let runningDuration = orderedIndexes.reduce((sum, index) => sum + getSegmentDuration(index), 0);
  for (const candidate of state.candidateShortlist || []) {
    if (orderedIndexes.length >= 6 || runningDuration >= 60) {
      break;
    }
    if (orderedIndexes.includes(candidate.segment_index) || state.bannedSegmentIndexes.includes(candidate.segment_index)) {
      continue;
    }
    orderedIndexes.push(candidate.segment_index);
    runningDuration += rawDurationSeconds(candidate.duration_seconds);
  }

  const cuts = orderedIndexes
    .map((index) => {
      const candidate = findCandidate(index);
      const states = segmentStates(index);
      let purpose = "";
      let reason = "";
      if (states.isOpening) {
        purpose = "Opening";
        reason = "kept opening";
      } else if (states.isRequired) {
        purpose = "Must use";
        reason = "accepted must-use";
      } else if (states.isLocked) {
        purpose = "Locked";
        reason = "locked from prior run";
      } else if (states.isPinned) {
        purpose = "Keep";
        reason = "kept from transcript";
      } else if (candidate?.roles?.length) {
        purpose = candidate.roles[0];
        reason = (candidate.reasons || [])[0] || "candidate";
      }
      return buildPreviewCutFromSegment(index, purpose, reason);
    })
    .filter(Boolean);

  return {
    source: cuts.length ? (state.candidateShortlist.length ? "Kept plan + candidates" : "Kept plan") : "",
    cuts,
  };
}

function buildTimelineLabels(totalDuration) {
  const safeTotal = Math.max(rawDurationSeconds(totalDuration), 1);
  const step = safeTotal / 4;
  return [0, 1, 2, 3, 4].map((value) => formatSeconds(step * value));
}

function renderTimelineHtml(cuts, { emptyText = "No cut preview yet.", source = "" } = {}) {
  const items = (cuts || []).filter(Boolean);
  if (!items.length) {
    return `<div class="result-card"><strong>${escapeHtml(emptyText)}</strong></div>`;
  }

  const totalDuration = items.reduce((sum, cut) => sum + rawDurationSeconds(cut.duration_seconds || getSegmentDuration(cut.segment_index)), 0);
  const ruler = buildTimelineLabels(totalDuration);
  const blocks = items.map((cut, position) => {
    const index = Number(cut.segment_index);
    const indexLabel = Number.isInteger(index) ? `[${index}]` : "";
    const states = segmentStates(index);
    const classes = ["timeline-block"];
    if (states.isOpening || /^opening$/i.test(cut.purpose || "")) {
      classes.push("is-opening");
    } else if (states.isBanned) {
      classes.push("is-banned");
    } else if (isKeptState(states)) {
      classes.push("is-kept");
    }
    const actualDuration = rawDurationSeconds(cut.duration_seconds || getSegmentDuration(index));
    const visualDuration = Math.max(actualDuration, 4);
    return `
      <article class="${classes.join(" ")}" style="flex: ${visualDuration} 1 0">
        <strong>${position + 1}. ${escapeHtml(indexLabel)}</strong>
        <span>${escapeHtml(cut.purpose || "Cut")}</span>
        <span>${escapeHtml(cut.tc_in)} - ${escapeHtml(cut.tc_out)}</span>
        <span>${formatSeconds(actualDuration)}</span>
      </article>
    `;
  }).join("");

  const list = items.map((cut, position) => {
    const index = Number(cut.segment_index);
    return `
      <div class="timeline-item">
        <div class="timeline-item-head">
          <strong>${position + 1}. ${escapeHtml(cut.tc_in)} - ${escapeHtml(cut.tc_out)}</strong>
          <span>${escapeHtml(cut.speaker || "")} | ${formatSeconds(cut.duration_seconds || getSegmentDuration(index))}</span>
        </div>
        <div class="cut-badges">${renderStateBadges(index)}</div>
        <div class="timeline-item-body">${escapeHtml(cut.text || cut.dialogue_summary || "")}</div>
        ${(cut.reasons || []).length ? `<div class="result-meta">${escapeHtml(cut.reasons.join(", "))}</div>` : ""}
      </div>
    `;
  }).join("");

  return `
    <div class="result-card">
      <div class="timeline-shell">
        <div class="timeline-summary">
          ${source ? `<span>${escapeHtml(source)}</span>` : ""}
          <span>${formatSeconds(totalDuration)} total</span>
          <span>${items.length} cut${items.length === 1 ? "" : "s"}</span>
        </div>
        <div class="timeline-ruler">
          ${ruler.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}
        </div>
        <div class="timeline-track">${blocks}</div>
        <div class="timeline-list">${list}</div>
      </div>
    </div>
  `;
}

function renderPlanHtml(plan, emptyText, actionButtons = "", variant = "default") {
  const normalized = normalizePlan(plan);
  if (!planHasContent(normalized)) {
    return `<div class="result-card"><strong>${escapeHtml(emptyText)}</strong></div>`;
  }

  const body = [];
  if (Number.isInteger(normalized.opening_segment_index)) {
    body.push(`
      <div class="result-meta">Opening</div>
      <div class="timeline-note-row">
        <span class="segment-chip is-static is-opening">[${normalized.opening_segment_index}]</span>
        <span>${escapeHtml(segmentLabel(normalized.opening_segment_index))}</span>
      </div>
    `);
  }
  if (normalized.must_include_segment_indexes.length) {
    body.push(`
      <div class="result-meta">Must include</div>
      <div class="plan-list">
        ${normalized.must_include_segment_indexes.map((index) => `
          <div class="timeline-note-row">
            <span class="segment-chip is-static is-kept">[${index}]</span>
            <span>${escapeHtml(segmentLabel(index))}</span>
          </div>
        `).join("")}
      </div>
    `);
  }
  if (normalized.narrative_arc) {
    body.push(`
      <div class="result-meta">Narrative arc</div>
      <div>${escapeHtml(normalized.narrative_arc)}</div>
    `);
  }
  if (normalized.generation_directive) {
    body.push(`
      <div class="result-meta">Directive</div>
      <div>${escapeHtml(normalized.generation_directive)}</div>
    `);
  }
  if (normalized.speaker_balance) {
    body.push(`
      <div class="result-meta">Speaker balance</div>
      <div>${escapeHtml(speakerBalanceLabel(normalized.speaker_balance))}</div>
    `);
  }
  if (normalized.rationale) {
    body.push(`
      <div class="result-meta">Why</div>
      <div>${escapeHtml(normalized.rationale)}</div>
    `);
  }

  return `
    <article class="result-card plan-card ${variant === "accepted" ? "is-accepted" : ""}">
      ${body.join("")}
      ${actionButtons}
    </article>
  `;
}

function pushRunHistory(runPayload) {
  if (!runPayload || !runPayload.run_id) {
    return;
  }
  const nextHistory = (state.runHistory || []).filter((item) => item.run_id !== runPayload.run_id);
  nextHistory.unshift(runPayload);
  commitState({
    runHistory: nextHistory.slice(0, 20),
    lastGeneration: runPayload,
    compareLeftRunId: runPayload.run_id,
    compareRightRunId: state.compareRightRunId || (nextHistory[1]?.run_id || ""),
  });
}

async function refreshTranscriptSegments() {
  if (!isFilesReady()) {
    commitState({ transcriptSegments: [], candidateShortlist: [], manualAssemblyIndexes: [] }, { clearGeneration: true });
    return;
  }
  try {
    const response = await fetch("/api/parse-transcript", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_pairs: normalizeSourcePairs(state.sourcePairs)
          .filter((pair) => pair.transcriptText || pair.xmlText)
          .map((pair) => ({
            transcript_text: pair.transcriptText,
            xml_text: pair.xmlText,
            transcript_name: pair.transcriptName,
            xml_name: pair.xmlName,
          })),
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw (payload && payload.error) ? payload.error : { message: "Could not parse transcript." };
    }
    commitState({ transcriptSegments: payload.segments || [] }, { clearGeneration: false });
  } catch (error) {
    showError({
      code: "TRANSCRIPT-PARSE",
      message: error.message || "Could not parse transcript.",
      stage: "transcript",
      expected_input_format: "Timecoded transcript blocks as HH:MM:SS:FF - HH:MM:SS:FF.",
      next_action: "Fix the transcript and retry parsing.",
    }, "validate");
  }
}

function exportProjectState() {
  const payload = {
    version: 1,
    exported_at: new Date().toISOString(),
    state,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${sanitizeFilename(state.projectTitle || state.transcriptName || "bitebuilder")}.bitebuilder-project.json`;
  link.click();
  URL.revokeObjectURL(url);
}

async function loadProjectState(file) {
  if (!file) {
    return;
  }
  const text = await file.text();
  const payload = JSON.parse(text);
  const loaded = normalizeStatePatch(payload.state || {});
  state = {
    ...createDefaultState(),
    ...loaded,
    messages: Array.isArray(loaded.messages) ? loaded.messages : [],
  };
  persistState();
  renderAll();
  setStatus(`Loaded ${file.name}.`);
}

function toggleIndex(listKey, index) {
  const next = new Set(state[listKey] || []);
  if (next.has(index)) {
    next.delete(index);
  } else {
    next.add(index);
  }
  commitState({ [listKey]: Array.from(next) }, { clearGeneration: true });
}

function addManualSegment(index) {
  if ((state.manualAssemblyIndexes || []).includes(index)) {
    setFocusedSegment(index);
    return;
  }
  commitState({
    manualAssemblyIndexes: [...state.manualAssemblyIndexes, index],
    focusedSegmentIndex: index,
  }, { clearGeneration: false });
}

function removeManualSegment(index) {
  const nextIndexes = state.manualAssemblyIndexes.filter((value) => value !== index);
  commitState({
    manualAssemblyIndexes: nextIndexes,
    focusedSegmentIndex: state.focusedSegmentIndex === index ? (nextIndexes.at(-1) ?? null) : state.focusedSegmentIndex,
  }, { clearGeneration: false });
}

function moveManualSegment(index, delta) {
  const items = [...state.manualAssemblyIndexes];
  const position = items.indexOf(index);
  if (position < 0) {
    return;
  }
  const nextPosition = position + delta;
  if (nextPosition < 0 || nextPosition >= items.length) {
    return;
  }
  const [item] = items.splice(position, 1);
  items.splice(nextPosition, 0, item);
  commitState({ manualAssemblyIndexes: items }, { clearGeneration: false });
}

function setFocusedSegment(index) {
  if (!Number.isInteger(index)) {
    return;
  }
  commitState({ focusedSegmentIndex: index }, { clearGeneration: false });
}

function isFocusedSegment(index) {
  return Number.isInteger(state.focusedSegmentIndex) && Number(state.focusedSegmentIndex) === Number(index);
}

function focusedLaneLabel(index) {
  const lanePosition = (state.manualAssemblyIndexes || []).indexOf(index);
  return lanePosition >= 0 ? `Selected #${lanePosition + 1}` : "Not in lane";
}

function updateBindings(key, value) {
  document.querySelectorAll(`[data-bind="${key}"]`).forEach((node) => {
    node.textContent = value;
  });
}

function syncInputValue(element, value) {
  if (!element) {
    return;
  }
  const nextValue = value == null ? "" : String(value);
  if (document.activeElement !== element && element.value !== nextValue) {
    element.value = nextValue;
  }
}

function updateSourcePair(sourceId, patch) {
  const nextPairs = normalizeSourcePairs(state.sourcePairs).map((pair) => (
    pair.id === sourceId ? { ...pair, ...patch } : pair
  ));
  commitState({
    sourcePairs: nextPairs,
    messages: [],
    suggestedPlan: createEmptyPlan(),
    acceptedPlan: createEmptyPlan(),
    candidateShortlist: [],
    manualAssemblyIndexes: [],
    pinnedSegmentIndexes: [],
    bannedSegmentIndexes: [],
    requiredSegmentIndexes: [],
    lockedSegmentIndexes: [],
    forcedOpenSegmentIndex: null,
    focusedSegmentIndex: null,
    lastError: null,
  }, { clearGeneration: true, clearError: true });
}

function addSourcePair() {
  commitState({ sourcePairs: [...normalizeSourcePairs(state.sourcePairs), createSourcePair()] }, { clearGeneration: false });
}

function removeSourcePair(sourceId) {
  const remaining = normalizeSourcePairs(state.sourcePairs).filter((pair) => pair.id !== sourceId);
  commitState({ sourcePairs: remaining.length ? remaining : [createSourcePair()] }, { clearGeneration: true, clearError: true });
  void refreshTranscriptSegments();
}

function renderSourceList() {
  if (!sourceList) {
    return;
  }
  const pairs = normalizeSourcePairs(state.sourcePairs);
  sourceList.innerHTML = pairs.map((pair, index) => {
    const loadedTranscript = pair.transcriptName || "No transcript loaded";
    const loadedXml = pair.xmlName || "No XML loaded";
    return `
      <article class="result-card source-card">
        <div class="result-card-head">
          <strong>Source ${index + 1}</strong>
          <div class="result-links">
            <button class="button button-secondary" type="button" data-remove-source="${pair.id}" ${pairs.length === 1 ? "disabled" : ""}>Remove</button>
          </div>
        </div>
        <label>
          <span>Transcript</span>
          <input type="file" accept=".txt,.md,.text" data-source-file="transcript" data-source-id="${pair.id}">
          <div class="result-meta">${escapeHtml(loadedTranscript)}</div>
        </label>
        <label>
          <span>Premiere XML</span>
          <input type="file" accept=".xml,.fcpxml,.txt" data-source-file="xml" data-source-id="${pair.id}">
          <div class="result-meta">${escapeHtml(loadedXml)}</div>
        </label>
      </article>
    `;
  }).join("");
}

async function loadSolarDemoWorkspace() {
  if (!loadSolarDemoButton) {
    return;
  }
  loadSolarDemoButton.disabled = true;
  setStatus("Loading solar demo sources...");
  try {
    const response = await fetch("/api/demo/solar-workspace");
    const payload = await response.json();
    if (!response.ok) {
      throw payload;
    }
    commitState({
      projectTitle: payload.project_title || "Solar innovation story",
      variantName: payload.variant_name || "solar-v1",
      brief: payload.brief || "",
      projectContext: payload.project_context || "",
      projectNotes: payload.project_notes || "",
      sourcePairs: (payload.source_pairs || []).map((pair) => createSourcePair({
        transcriptText: pair.transcript_text,
        xmlText: pair.xml_text,
        transcriptName: pair.transcript_name,
        xmlName: pair.xml_name,
      })),
      messages: [],
      suggestedPlan: createEmptyPlan(),
      acceptedPlan: createEmptyPlan(),
      candidateShortlist: [],
      manualAssemblyIndexes: [],
      pinnedSegmentIndexes: [],
      bannedSegmentIndexes: [],
      requiredSegmentIndexes: [],
      lockedSegmentIndexes: [],
      forcedOpenSegmentIndex: null,
      focusedSegmentIndex: null,
      lastError: null,
    }, { clearGeneration: true, clearError: true });
    await refreshTranscriptSegments();
    setStatus("Solar demo sources loaded.");
  } catch (error) {
    const details = error.error || error;
    showError({
      code: details.code || "SOLAR-DEMO-FAILED",
      message: details.message || "Could not load solar demo sources.",
      stage: details.stage || "file",
      expected_input_format: details.expected_input_format || "Mounted demo files or manual file selection.",
      next_action: details.next_action || "Reconnect the source volume or choose files manually.",
    }, "workspace");
  } finally {
    loadSolarDemoButton.disabled = false;
  }
}

function setLinkEnabled(element, enabled) {
  if (!element) {
    return;
  }
  element.classList.toggle("is-disabled", !enabled);
  element.setAttribute("aria-disabled", enabled ? "false" : "true");
}

function isFilesReady() {
  return normalizeSourcePairs(state.sourcePairs).some((pair) => pair.transcriptText && pair.xmlText);
}

function isBriefReady() {
  return Boolean(state.brief.trim());
}

function isModelReady() {
  return Boolean((state.model || "").trim());
}

function isGenerateReady() {
  return isFilesReady() && isBriefReady() && isModelReady();
}

function getActiveGeneration() {
  return state.lastGeneration || state.runHistory[0] || null;
}

function hasGeneration() {
  return Boolean(getActiveGeneration() && getActiveGeneration().run_id);
}

function stepRule(stepKey) {
  switch (stepKey) {
    case "intake":
      return { enabled: true, message: "" };
    case "brief":
      return { enabled: isFilesReady(), message: "Load the transcript and the Premiere XML first." };
    case "chat":
      return { enabled: isFilesReady() && isBriefReady(), message: "Load the files and write the brief first." };
    case "generate":
      return { enabled: isGenerateReady(), message: "Check local models and choose one first." };
    case "export":
      return { enabled: hasGeneration(), message: "Generate XML first." };
    default:
      return { enabled: true, message: "" };
  }
}

function renderPageStatus() {
  renderOperationSnapshot();
  if (!pageStatus) {
    return;
  }

  switch (pageKey) {
    case "intake":
      setStatus(isFilesReady() ? "Files ready." : "Load the transcript and the Premiere XML.");
      break;
    case "brief":
      if (!isFilesReady()) {
        setStatus("Load the files first.");
      } else if (isBriefReady()) {
        setStatus("Brief saved.");
      } else {
        setStatus("Write the brief.");
      }
      break;
    case "chat":
      if (!isFilesReady()) {
        setStatus("Load the files first.");
      } else if (!isBriefReady()) {
        setStatus("Write the brief first.");
      } else if (!isModelReady()) {
        setStatus("Check local models.");
      } else {
        setStatus("Chat ready.");
      }
      break;
    case "generate":
      if (state.currentJob) {
        setStatus(state.currentJobLogs.at(-1)?.message || "Generating...");
      } else if (!isFilesReady()) {
        setStatus("Load the files first.");
      } else if (!isBriefReady()) {
        setStatus("Write the brief first.");
      } else if (!isModelReady()) {
        setStatus("Go back to Chat and choose a model.");
      } else {
        setStatus("Ready to generate.");
      }
      break;
    case "export":
      if (state.currentJob) {
        setStatus(state.currentJobLogs.at(-1)?.message || "Generating...");
      } else if (!hasGeneration()) {
        setStatus("No run yet.");
      } else {
        setStatus(`${getActiveGeneration().files.length} file(s) ready.`);
      }
      break;
    case "workspace":
      if (state.currentJob) {
        setStatus(state.currentJobLogs.at(-1)?.message || "Generating...");
      } else if (!isFilesReady()) {
        setStatus("Load the transcript and Premiere XML.");
      } else if (!isBriefReady()) {
        setStatus("Write the brief, then start pulling bites into the lane.");
      } else {
        setStatus("Workspace ready. Search, select, reorder, then generate.");
      }
      break;
    default:
      break;
  }
}

function renderOperationSnapshot() {
  if (!pageSnapshotContainer) {
    return;
  }
  if (state.lastOperation && state.lastOperation.message) {
    pageSnapshotContainer.innerHTML = formatSnapshotHtml({
      stage: state.lastOperation.stage || "received",
      log: state.lastOperation.message || "",
    });
    return;
  }
  if (state.currentJob && state.currentJobStatus) {
    pageSnapshotContainer.innerHTML = formatSnapshotHtml({
      stage: "generating",
      log: state.currentJobStatus,
    });
    return;
  }
  pageSnapshotContainer.innerHTML = "";
}

function renderStepLinks() {
  stepLinks.forEach((link) => {
    const rule = stepRule(link.dataset.stepLink || "");
    const isCurrent = link.dataset.stepLink === pageKey;
    setLinkEnabled(link, isCurrent || rule.enabled);
  });
}

function renderStateSnapshot() {
  updateBindings("projectTitle", state.projectTitle || "Untitled project");
  updateBindings("transcriptName", state.transcriptName || "No transcript loaded");
  updateBindings("xmlName", state.xmlName || "No XML loaded");
  updateBindings("segmentCount", String(countTranscriptSegments(state.transcriptText)));
  updateBindings("briefPreview", compactText(state.brief, "No brief yet."));
  updateBindings("contextPreview", compactText(state.projectContext, "No project context yet."));
  updateBindings("notesPreview", compactText(state.projectNotes, "No notes yet."));
  updateBindings("messageCount", String(state.messages.length));
  updateBindings("modelName", state.model || "Not selected");
  updateBindings("thinkingSummary", state.thinkingMode || "auto");
  updateBindings("timeoutSummary", `${Number(state.timeout || 180)}s`);
  updateBindings("optionsSummary", String(Number(state.options || 3)));
  updateBindings("variantSummary", state.variantName || "v1");
  updateBindings("speakerBalanceSummary", state.speakerBalance || "balanced");

  syncInputValue(projectTitleInput, state.projectTitle);
  syncInputValue(projectNotesInput, state.projectNotes);
  syncInputValue(briefInput, state.brief);
  syncInputValue(contextInput, state.projectContext);
  syncInputValue(optionsInput, state.options);
  syncInputValue(variantNameInput, state.variantName);
  syncInputValue(speakerBalanceSelect, state.speakerBalance);
}

function renderIntake() {
  if (transcriptPreview) {
    transcriptPreview.textContent = state.transcriptText
      ? truncate(state.transcriptText)
      : "No transcript loaded.";
  }
  if (xmlPreview) {
    xmlPreview.textContent = state.xmlText
      ? truncate(state.xmlText)
      : "No XML loaded.";
  }
  setLinkEnabled(continueFromIntakeButton, isFilesReady());
}

function renderBrief() {
  setLinkEnabled(continueFromBriefButton, isFilesReady() && isBriefReady());
}

function renderChat() {
  if (chatLog) {
    const shouldStick = (chatLog.scrollTop + chatLog.clientHeight) >= (chatLog.scrollHeight - 40);
    if (!state.messages.length) {
      chatLog.innerHTML = '<div class="chat-empty">No chat yet.</div>';
    } else {
      chatLog.innerHTML = state.messages
        .map((message) => `
          <article class="message ${message.role}">
            <span class="message-role">${escapeHtml(message.role)}</span>
            <div class="message-body">${renderChatMessageContent(message.content)}</div>
          </article>
        `)
        .join("");
      if (shouldStick) {
        chatLog.scrollTop = chatLog.scrollHeight;
      }
    }
  }

  setLinkEnabled(continueFromChatButton, isGenerateReady());
  if (chatButton) {
    chatButton.disabled = !isGenerateReady();
  }
  renderSuggestedPlan();
  renderAcceptedPlan();
}

function renderGenerate() {
  if (generateButton) {
    generateButton.disabled = !isGenerateReady();
  }
  if (previewShortlistButton) {
    previewShortlistButton.disabled = !isFilesReady();
  }
  if (manualXmlButton) {
    manualXmlButton.disabled = !state.manualAssemblyIndexes.length;
  }
  renderAcceptedPlanSummary();
  const previewTimeline = document.getElementById("timelinePreview");
  if (previewTimeline) {
    const preview = derivePreviewCuts();
    previewTimeline.innerHTML = renderTimelineHtml(preview.cuts, {
      emptyText: "No preview yet. Keep a few transcript lines or refresh candidates.",
      source: preview.source,
    });
  }
}

function renderResults(payload) {
  if (!results) {
    return;
  }

  if (!payload) {
    results.innerHTML = '<div class="result-card"><strong>No run.</strong></div>';
    return;
  }

  const sourceLine = payload.source
    ? `Source: ${payload.source.source_name} | ${payload.source.width}x${payload.source.height} | ${payload.source.actual_fps.toFixed(3)}fps`
    : "";
  const targetLine = payload.target_duration_range
    ? `Target: ${payload.target_duration_range[0]}-${payload.target_duration_range[1]}s | Thinking: ${payload.thinking_mode}`
    : `Thinking: ${payload.thinking_mode}`;
  const retryHtml = payload.used_retry
    ? `<div class="result-card"><strong>LLM validation recovery</strong><div class="result-meta">One correction retry was used before write.</div>`
      + `${(payload.selection_retry?.errors || []).length ? `<div class="result-meta">${escapeHtml((payload.selection_retry.errors || []).join(" | "))}</div>` : ""}`
      + `</div>`
    : "";
  const warningHtml = payload.validation_errors && payload.validation_errors.length
    ? `<div class="result-card"><strong>Warnings</strong><div class="result-meta">${payload.validation_errors.map(escapeHtml).join("<br>")}</div></div>`
    : "";
  const acceptedPlanText = formatPlanInline(state.acceptedPlan);
  const traceHtml = `
    <div class="result-card">
      <strong>Why this cut</strong>
      <div class="result-meta">Chat direction</div>
      <div>${escapeHtml(state.messages.filter((message) => message.role === "user").slice(-3).map((message) => message.content).join(" | ") || "No chat direction")}</div>
      <div class="result-meta">Accepted decisions</div>
      <div>${escapeHtml(acceptedPlanText)}</div>
    </div>
  `;
  const fileHtml = payload.files && payload.files.length
    ? payload.files.map((file) => `
        <div class="result-card">
          <div class="result-card-head">
            <strong>${escapeHtml(file.name)}</strong>
            <span>${file.cut_count} cuts | ${Number(file.actual_duration_seconds).toFixed(1)}s</span>
          </div>
          <div class="result-meta">${escapeHtml(file.description || "No description")}</div>
          ${renderTimelineHtml(file.selected_cuts || [], {
            emptyText: "No cut preview available.",
            source: `${Number(file.actual_duration_seconds).toFixed(1)}s actual | ${Number(file.estimated_duration_seconds || 0).toFixed(1)}s estimated`,
          })}
          ${(file.selected_cuts || []).map((cut) => `
            <div class="cut-row">
              <div class="timeline-item-head">
                <strong>${escapeHtml(cut.tc_in)} - ${escapeHtml(cut.tc_out)}</strong>
                <span>${escapeHtml(cut.speaker || "")} | ${escapeHtml(cut.purpose || "")}</span>
              </div>
              <div class="cut-badges">${renderStateBadges(Number(cut.segment_index))}</div>
              <div>${escapeHtml(cut.text || cut.dialogue_summary || "")}</div>
              <div class="result-meta">${escapeHtml((cut.reasons || []).join(", ") || "No selection note")}</div>
              ${cut.segment_index != null ? `<div class="result-links"><button class="button button-secondary" type="button" data-lock-cut="${cut.segment_index}">${state.lockedSegmentIndexes.includes(Number(cut.segment_index)) ? "Unlock bite" : "Lock this bite"}</button></div>` : ""}
            </div>
          `).join("")}
          <div class="result-links">
            <a href="${file.download_url}">Download ${escapeHtml(file.filename)}</a>
          </div>
        </div>
      `).join("")
    : '<div class="result-card"><strong>No XML files were written.</strong></div>';

  results.innerHTML = `
    <div class="result-card">
      <strong>Run</strong>
      <div class="result-meta">${escapeHtml(state.projectTitle || "Untitled project")}</div>
      <div class="result-meta">${escapeHtml(payload.saved_dir)}</div>
      <div class="result-meta">${escapeHtml(sourceLine)}</div>
      <div class="result-meta">${escapeHtml(targetLine)}</div>
      <div class="result-links">
        <a href="${payload.debug_download_url}">Download raw response</a>
        <a href="/project/logs">Open logs</a>
      </div>
    </div>
    ${retryHtml}
    ${warningHtml}
    ${traceHtml}
    ${fileHtml}
  `;
}

function renderSuggestedPlan() {
  if (!suggestedPlanPanel) {
    return;
  }
  const actions = planHasContent(state.suggestedPlan)
    ? `
      <div class="actions">
        <button class="button button-secondary" type="button" data-plan-action="accept-opening">Keep opening</button>
        <button class="button button-secondary" type="button" data-plan-action="accept-includes">Keep selects</button>
        <button class="button" type="button" data-plan-action="accept-all">Keep all</button>
      </div>
    `
    : "";
  suggestedPlanPanel.innerHTML = renderPlanHtml(state.suggestedPlan, "No suggestion yet.", actions, "suggested");
}

function renderAcceptedPlan() {
  if (!acceptedPlanPanel) {
    return;
  }
  const actions = planHasContent(state.acceptedPlan)
    ? `
      <div class="actions">
        <button class="button button-secondary" type="button" data-plan-action="clear-accepted">Clear accepted</button>
      </div>
    `
    : "";
  acceptedPlanPanel.innerHTML = renderPlanHtml(state.acceptedPlan, "No accepted edit decisions yet.", actions, "accepted");
}

function renderAcceptedPlanSummary() {
  if (!acceptedPlanSummary) {
    return;
  }
  const actions = planHasContent(state.acceptedPlan)
    ? `
      <div class="result-links">
        <a href="/project/chat">Back to chat</a>
      </div>
    `
    : "";
  acceptedPlanSummary.innerHTML = renderPlanHtml(
    state.acceptedPlan,
    "No accepted edit decisions.",
    actions,
    "accepted",
  );
}

function renderTranscriptBrowser() {
  if (!transcriptBrowser) {
    return;
  }
  const filterValue = (transcriptSearchInput?.value || "").trim().toLowerCase();
  const segments = (state.transcriptSegments || []).filter((segment) => {
    if (!filterValue) {
      return true;
    }
    return [
      segment.text,
      segment.speaker,
      segment.tc_in,
      segment.tc_out,
    ].join(" ").toLowerCase().includes(filterValue);
  });

  if (!segments.length) {
    transcriptBrowser.innerHTML = '<div class="result-card"><strong>No transcript segments.</strong></div>';
    return;
  }

  transcriptBrowser.innerHTML = segments.map((segment) => {
    const index = Number(segment.segment_index);
    const isPinned = state.pinnedSegmentIndexes.includes(index);
    const isBanned = state.bannedSegmentIndexes.includes(index);
    const isRequired = state.requiredSegmentIndexes.includes(index);
    const isManual = state.manualAssemblyIndexes.includes(index);
    const isForcedOpen = Number.isInteger(state.forcedOpenSegmentIndex) && state.forcedOpenSegmentIndex === index;
    const isFocused = isFocusedSegment(index);
    const tone = `${segmentCardTone(index)}${isFocused ? " is-focused" : ""}`.trim();
    const laneMeta = isManual ? `<span class="selection-pill">${escapeHtml(focusedLaneLabel(index))}</span>` : "";
    return `
      <article class="result-card transcript-card ${tone}" data-focus-segment="${index}">
        <div class="result-card-head">
          <strong>[${index}] ${escapeHtml(segment.tc_in)} - ${escapeHtml(segment.tc_out)}</strong>
          <div class="segment-badges">${laneMeta}${renderStateBadges(index)}</div>
        </div>
        <div class="result-meta">${escapeHtml(segment.speaker)} | ${formatSeconds(segment.duration_seconds)}</div>
        <div class="result-meta">${escapeHtml(segment.text)}</div>
        <div class="result-links">
          <button class="button button-secondary" type="button" data-segment-action="pin" data-segment-index="${index}">${isPinned ? "Unkeep" : "Keep"}</button>
          <button class="button button-secondary" type="button" data-segment-action="ban" data-segment-index="${index}">${isBanned ? "Unskip" : "Skip"}</button>
          <button class="button button-secondary" type="button" data-segment-action="require" data-segment-index="${index}">${isRequired ? "Clear must use" : "Must use"}</button>
          <button class="button button-secondary" type="button" data-segment-action="open" data-segment-index="${index}">${isForcedOpen ? "Clear first" : "Use first"}</button>
          <button class="button button-secondary" type="button" data-segment-action="add" data-segment-index="${index}">${isManual ? "In lane" : "Add to lane"}</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderManualLane() {
  if (!manualLane) {
    return;
  }
  if (!state.manualAssemblyIndexes.length) {
    manualLane.innerHTML = '<div class="result-card"><strong>No manual bites yet.</strong></div>';
    if (manualXmlButton) {
      manualXmlButton.disabled = true;
    }
    return;
  }
  manualLane.innerHTML = state.manualAssemblyIndexes.map((index) => {
    const segment = findSegment(index);
    if (!segment) {
      return "";
    }
    const lanePosition = state.manualAssemblyIndexes.indexOf(index);
    const focusedClass = isFocusedSegment(index) ? " is-focused" : "";
    return `
      <article class="result-card is-kept${focusedClass}" data-focus-segment="${index}">
        <div class="result-card-head">
          <strong>${lanePosition + 1}. ${escapeHtml(segment.tc_in)} - ${escapeHtml(segment.tc_out)}</strong>
          <div class="segment-badges"><span class="selection-pill">Selected #${lanePosition + 1}</span>${renderStateBadges(index)}</div>
        </div>
        <div class="result-meta">${escapeHtml(segment.speaker)} | ${formatSeconds(segment.duration_seconds)}</div>
        <div class="result-meta">${escapeHtml(segment.text)}</div>
        <div class="result-links">
          <button class="button button-secondary" type="button" data-manual-move="${index}" data-manual-delta="-1">Up</button>
          <button class="button button-secondary" type="button" data-manual-move="${index}" data-manual-delta="1">Down</button>
          <button class="button button-secondary" type="button" data-manual-remove="${index}">Remove</button>
        </div>
      </article>
    `;
  }).join("");
  if (manualXmlButton) {
    manualXmlButton.disabled = false;
  }
}

function renderShortlist() {
  if (!shortlistList) {
    return;
  }
  const candidates = state.candidateShortlist || [];
  if (!candidates.length) {
    shortlistList.innerHTML = '<div class="result-card"><strong>No shortlist preview yet.</strong></div>';
    return;
  }
  shortlistList.innerHTML = candidates.map((candidate) => {
    const index = Number(candidate.segment_index);
    const focusedClass = isFocusedSegment(index) ? " is-focused" : "";
    const laneMeta = state.manualAssemblyIndexes.includes(index)
      ? `<span class="selection-pill">${escapeHtml(focusedLaneLabel(index))}</span>`
      : "";
    return `
    <article class="result-card ${segmentCardTone(index)}${focusedClass}" data-focus-segment="${index}">
      <div class="result-card-head">
        <strong>[${candidate.segment_index}] ${escapeHtml(candidate.tc_in)} - ${escapeHtml(candidate.tc_out)}</strong>
        <div class="segment-badges">${laneMeta}${renderStateBadges(index)}</div>
      </div>
      <div class="result-meta">${escapeHtml(candidate.speaker)} | ${formatSeconds(candidate.duration_seconds)} | score ${Number(candidate.score || 0).toFixed(1)}</div>
      <div class="result-meta">${escapeHtml((candidate.roles || []).join(", "))}</div>
      <div class="result-meta">${escapeHtml((candidate.reasons || []).join(", "))}</div>
      <div class="result-meta">${escapeHtml(candidate.text || "")}</div>
      <div class="result-links">
        <button class="button button-secondary" type="button" data-segment-action="pin" data-segment-index="${candidate.segment_index}">${state.pinnedSegmentIndexes.includes(index) ? "Unkeep" : "Keep"}</button>
        <button class="button button-secondary" type="button" data-segment-action="open" data-segment-index="${candidate.segment_index}">${state.forcedOpenSegmentIndex === index ? "Clear first" : "Use first"}</button>
        <button class="button button-secondary" type="button" data-segment-action="add" data-segment-index="${candidate.segment_index}">${state.manualAssemblyIndexes.includes(index) ? "In lane" : "Add to lane"}</button>
      </div>
    </article>
  `;
  }).join("");
}

function renderSelectedBites() {
  if (!selectedBites) {
    return;
  }
  const activeFile = getActiveGeneration()?.files?.[0];
  const preview = derivePreviewCuts();
  const cuts = activeFile?.selected_cuts?.length ? activeFile.selected_cuts : preview.cuts;
  const title = activeFile?.selected_cuts?.length ? "Current order" : "Working order";
  const meta = activeFile?.selected_cuts?.length
    ? `${formatSeconds(activeFile.actual_duration_seconds)} | ${activeFile.cut_count} cuts`
    : preview.source || "No kept cut yet.";

  if (!cuts.length) {
    selectedBites.innerHTML = '<div class="result-card"><strong>No selected bites yet.</strong></div>';
    return;
  }
  selectedBites.innerHTML = `
    <article class="result-card">
      <strong>${escapeHtml(title)}</strong>
      <div class="result-meta">${escapeHtml(meta)}</div>
      ${cuts.map((cut, position) => {
        const segmentIndex = Number(cut.segment_index);
        const focusClass = isFocusedSegment(segmentIndex) ? " is-focused" : "";
        return `
        <div class="cut-row${focusClass}" data-focus-segment="${segmentIndex}">
          <div class="timeline-item-head">
            <strong>${position + 1}. ${escapeHtml(cut.tc_in)} - ${escapeHtml(cut.tc_out)}</strong>
            <span>${escapeHtml(cut.speaker || "")} | ${escapeHtml(cut.purpose || "") || "Cut"}</span>
          </div>
          <div class="cut-badges"><span class="selection-pill">Selected #${position + 1}</span>${renderStateBadges(segmentIndex)}</div>
          <div>${escapeHtml(cut.text || cut.dialogue_summary || "")}</div>
        </div>
      `;
      }).join("")}
    </article>
  `;
}

function renderCompare() {
  if (!comparePanel || !compareLeftSelect || !compareRightSelect) {
    return;
  }
  const runs = state.runHistory || [];
  const options = runs.map((run) => `<option value="${escapeHtml(run.run_id)}">${escapeHtml(run.run_id)} | ${escapeHtml(run.files?.[0]?.name || "run")}</option>`).join("");
  compareLeftSelect.innerHTML = `<option value="">Select run</option>${options}`;
  compareRightSelect.innerHTML = `<option value="">Select run</option>${options}`;
  syncInputValue(compareLeftSelect, state.compareLeftRunId);
  syncInputValue(compareRightSelect, state.compareRightRunId);

  const left = runs.find((run) => run.run_id === state.compareLeftRunId);
  const right = runs.find((run) => run.run_id === state.compareRightRunId);
  if (!left || !right) {
    comparePanel.innerHTML = '<div class="result-card"><strong>Select two runs to compare.</strong></div>';
    return;
  }
  const leftCuts = (left.files?.[0]?.selected_cuts || []).map((cut) => cut.tc_in);
  const rightCuts = (right.files?.[0]?.selected_cuts || []).map((cut) => cut.tc_in);
  const onlyLeft = leftCuts.filter((value) => !rightCuts.includes(value));
  const onlyRight = rightCuts.filter((value) => !leftCuts.includes(value));
  comparePanel.innerHTML = `
    <div class="result-card">
      <strong>Compare</strong>
      <div class="result-meta">Left: ${escapeHtml(left.files?.[0]?.name || left.run_id)} | ${formatSeconds(left.files?.[0]?.actual_duration_seconds)}</div>
      <div class="result-meta">Right: ${escapeHtml(right.files?.[0]?.name || right.run_id)} | ${formatSeconds(right.files?.[0]?.actual_duration_seconds)}</div>
      <div class="result-meta">Only in left: ${escapeHtml(onlyLeft.join(", ") || "none")}</div>
      <div class="result-meta">Only in right: ${escapeHtml(onlyRight.join(", ") || "none")}</div>
    </div>
  `;
}

async function renderLogsPage() {
  if (!logsPanel || !logsRunSelect) {
    return;
  }
  const runs = state.runHistory || [];
  const options = runs.map((run) => `<option value="${escapeHtml(run.run_id)}">${escapeHtml(run.run_id)}</option>`).join("");
  logsRunSelect.innerHTML = `<option value="">Select run</option>${options}`;
  const targetRunId = logsRunSelect.value || getActiveGeneration()?.run_id || state.compareLeftRunId;
  syncInputValue(logsRunSelect, targetRunId);
  if (!targetRunId) {
    logsPanel.innerHTML = '<div class="result-card"><strong>No run selected.</strong></div>';
    return;
  }

  try {
    const response = await fetch(`/api/session-log/${encodeURIComponent(targetRunId)}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not load session log.");
    }
    const attempts = payload.generation_log?.attempts || [];
    logsPanel.innerHTML = `
      <div class="result-card">
        <strong>${escapeHtml(targetRunId)}</strong>
        <div class="result-meta">${escapeHtml(payload.saved_dir || "")}</div>
      </div>
      <div class="result-card">
        <strong>Editorial direction</strong>
        <div class="result-meta">${escapeHtml(payload.editorial_direction || "None")}</div>
      </div>
      <div class="result-card">
        <strong>Prompt</strong>
        <pre>${escapeHtml(payload.prompt_text || "")}</pre>
      </div>
      ${attempts.map((attempt) => `
        <div class="result-card">
          <strong>Attempt ${attempt.attempt}</strong>
          <div class="result-meta">${escapeHtml((attempt.errors || []).join(" | ") || "No errors")}</div>
          <pre>${escapeHtml(attempt.raw_text || "")}</pre>
        </div>
      `).join("")}
    `;
  } catch (error) {
    logsPanel.innerHTML = `<div class="result-card"><strong>${escapeHtml(error.message)}</strong></div>`;
  }
}

function renderJobLog() {
  if (!jobLog) {
    return;
  }
  const logs = state.currentJobLogs || [];
  if (!logs.length) {
    jobLog.innerHTML = '<div class="result-card"><strong>No job running.</strong></div>';
    return;
  }
  jobLog.innerHTML = logs.map((entry) => `
    <div class="result-card">
      <strong>${escapeHtml(entry.timestamp || "")}</strong>
      <div class="result-meta">${escapeHtml(entry.message || "")}</div>
    </div>
  `).join("");
}

function renderAll() {
  renderStateSnapshot();
  renderStepLinks();
  renderPageStatus();
  if (state.lastError) {
    showError(state.lastError, state.lastOperation?.operation || null);
  } else {
    clearInlineError();
  }
  renderIntake();
  renderBrief();
  renderChat();
  renderGenerate();
  renderSourceList();
  renderResults(getActiveGeneration());
  renderTranscriptBrowser();
  renderManualLane();
  renderShortlist();
  renderSelectedBites();
  renderCompare();
  renderJobLog();
  void renderLogsPage();
}

async function fetchModels() {
  try {
    const response = await fetch("/api/models");
    const payload = await response.json();
    modelInventory = Array.isArray(payload.models) ? payload.models : [];

    const patch = {};
    const currentModel = String(state.model || "").toLowerCase();
    const shouldReplaceModel = !state.model || ["resume-matcher", "embed", "nomic-embed"].some((bad) => currentModel.includes(bad));
    if (shouldReplaceModel && modelInventory.length) {
      patch.model = payload.default_model || "";
    }
    if (!state.thinkingMode) {
      patch.thinkingMode = payload.default_thinking_mode || "auto";
    }

    modelLookupState = modelInventory.length ? "success" : "empty";
    modelLookupMessage = modelInventory.length
      ? `${modelInventory.length} model(s) found.`
      : "No local models found.";

    if (Object.keys(patch).length) {
      state = { ...state, ...patch };
      persistState();
    }

    renderAll();
  } catch (error) {
    modelLookupState = "error";
    modelLookupMessage = `Model lookup failed: ${error.message}`;
    setStatus(modelLookupMessage);
  }
}

async function loadFile(file, kind, sourceId = null) {
  if (!file) {
    return;
  }

  const text = await file.text();
  if (sourceId) {
    if (kind === "transcript") {
      updateSourcePair(sourceId, {
        transcriptText: text,
        transcriptName: file.name,
      });
    } else {
      updateSourcePair(sourceId, {
        xmlText: text,
        xmlName: file.name,
      });
    }
    await refreshTranscriptSegments();
    return;
  }

  if (kind === "transcript") {
    commitState({
      sourcePairs: [createSourcePair({ transcriptText: text, transcriptName: file.name, xmlText: state.xmlText, xmlName: state.xmlName })],
      messages: [],
      suggestedPlan: createEmptyPlan(),
      acceptedPlan: createEmptyPlan(),
      candidateShortlist: [],
      manualAssemblyIndexes: [],
      pinnedSegmentIndexes: [],
      bannedSegmentIndexes: [],
      requiredSegmentIndexes: [],
      lockedSegmentIndexes: [],
      forcedOpenSegmentIndex: null,
      lastError: null,
    }, { clearGeneration: true });
    await refreshTranscriptSegments();
  } else {
    commitState({
      sourcePairs: [createSourcePair({ transcriptText: state.transcriptText, transcriptName: state.transcriptName, xmlText: text, xmlName: file.name })],
      candidateShortlist: [],
      lastError: null,
    }, { clearGeneration: true });
    await refreshTranscriptSegments();
  }
}

function buildPayload() {
  const acceptedPlan = normalizePlan(state.acceptedPlan);
  const effectiveRequiredIndexes = uniqueNumbers([
    ...state.requiredSegmentIndexes,
    ...state.lockedSegmentIndexes,
    ...acceptedPlan.must_include_segment_indexes,
  ]);
  const effectiveForcedOpen = Number.isInteger(state.forcedOpenSegmentIndex)
    ? state.forcedOpenSegmentIndex
    : acceptedPlan.opening_segment_index;
  const effectiveSpeakerBalance = (state.speakerBalance === "balanced" && acceptedPlan.speaker_balance)
    ? acceptedPlan.speaker_balance
    : state.speakerBalance;
  const completeSources = normalizeSourcePairs(state.sourcePairs).filter((pair) => pair.transcriptText && pair.xmlText);
  return {
    transcript_text: state.transcriptText,
    xml_text: state.xmlText,
    source_pairs: completeSources.map((pair) => ({
      transcript_text: pair.transcriptText,
      xml_text: pair.xmlText,
      transcript_name: pair.transcriptName,
      xml_name: pair.xmlName,
    })),
    brief: state.brief.trim(),
    project_context: state.projectContext.trim(),
    messages: state.messages,
    model: state.model,
    thinking_mode: state.thinkingMode,
    options: Number(state.options || 3),
    timeout: Number(state.timeout || 180),
    accepted_plan: acceptedPlan,
    pinned_segment_indexes: state.pinnedSegmentIndexes,
    banned_segment_indexes: state.bannedSegmentIndexes,
    required_segment_indexes: effectiveRequiredIndexes,
    locked_segment_indexes: state.lockedSegmentIndexes,
    forced_open_segment_index: effectiveForcedOpen,
    speaker_balance: effectiveSpeakerBalance,
    variant_name: state.variantName,
  };
}

async function sendChat() {
  const message = (chatInput?.value || "").trim();
  if (!message) {
    setStatus("Write a message first.");
    return;
  }
  if (!isFilesReady()) {
    setStatus("Load the files first.");
    return;
  }
  if (!isBriefReady()) {
    setStatus("Write the brief first.");
    return;
  }
  if (!isModelReady()) {
    setStatus("Check local models and choose one first.");
    return;
  }

  const nextMessages = [...state.messages, { role: "user", content: message }];
  commitState({ messages: nextMessages });
  chatInput.value = "";
  chatButton.disabled = true;
  setStatus("Waiting for response...");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...buildPayload(),
        messages: nextMessages,
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw payload;
    }

    commitState({
      messages: [...nextMessages, { role: "assistant", content: payload.reply }],
      suggestedPlan: payload.suggested_plan || createEmptyPlan(),
    });
    state.lastOperation = null;
    state.lastError = null;
    commitState({}, { clearError: true });
    setStatus(`Reply received from ${payload.host}.`);
  } catch (error) {
    const details = error.error || {
      code: "CHAT-FAILED",
      message: error.message || "Chat failed.",
      stage: "model",
      expected_input_format: "Valid chat request with transcript, brief, and local model.",
      next_action: "Retry after checking model and input.",
    };
    commitState({ messages: [...nextMessages, { role: "assistant", content: `Chat failed: ${details.message || error.message}` }] });
    showError({
      code: details.code || "CHAT-FAILED",
      message: details.message || "Chat failed.",
      stage: details.stage || "model",
      expected_input_format: details.expected_input_format || "Valid chat request with transcript, brief, and local model.",
      next_action: details.next_action || "Retry after fixing inputs.",
    }, "chat");
    return;
  } finally {
    chatButton.disabled = !isGenerateReady();
  }
}

async function generateSequences() {
  if (!isFilesReady()) {
    setStatus("Load the files first.");
    return;
  }
  if (!isBriefReady()) {
    setStatus("Write the brief first.");
    return;
  }
  if (!isModelReady()) {
    setStatus("Check local models and choose one first.");
    return;
  }

  if (generateButton) {
    generateButton.disabled = true;
  }
  state.lastError = null;
  state.lastOperation = { operation: "generate", stage: "received", message: "Received generation request." };
  persistState();
  commitOperationSnapshot("Generation request received", "generate");
  setStatus("Starting generation...");

  try {
    const response = await fetch("/api/generate-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw payload;
    }
    commitState({
      currentJob: payload.job_id,
      currentJobStatus: payload.status,
      currentJobLogs: [{ timestamp: new Date().toISOString(), message: "Queued generation job." }],
    });
    await pollGenerationJob(payload.job_id);
  } catch (error) {
    const details = error.error || error;
    showError({
      code: details.code || "GENERATE-REQUEST-FAILED",
      message: details.message || "Generation failed.",
      stage: details.stage || "model",
      expected_input_format: details.expected_input_format || "Valid transcript, XML, brief and model settings.",
      next_action: details.next_action || "Fix inputs and retry.",
    }, "generate");
    commitState({
      currentJob: null,
      currentJobStatus: "",
      currentJobLogs: [],
    });
  } finally {
    if (generateButton) {
      generateButton.disabled = !isGenerateReady();
    }
  }
}

async function pollGenerationJob(jobId) {
  let isComplete = false;
  while (!isComplete) {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
    const payload = await response.json();
    if (!response.ok) {
      throw payload;
    }
    const operationMessage = payload.logs?.at(-1)?.message;
    commitState({
      currentJob: jobId,
      currentJobStatus: payload.status,
      currentJobLogs: payload.logs || [],
      lastError: null,
    });
    commitOperationSnapshot(operationMessage || payload.status, "generate");
    if (payload.status === "completed") {
      pushRunHistory(payload.result);
      commitState({
        currentJob: null,
        currentJobStatus: "completed",
      });
      window.location.assign("/project/export");
      return;
    }
    if (payload.status === "error") {
      throw payload;
    }
    if (payload.status === "partial") {
      state.lastOperation = { operation: "generate", stage: "selection", message: payload.error?.message || "Selection failed. Retry when ready." };
      state.lastError = payload.error;
      persistState();
      commitState({
        currentJob: null,
        currentJobStatus: "partial",
        currentJobLogs: payload.logs || [],
      });
      renderAll();
      return;
    }
    setStatus(payload.logs?.at(-1)?.message || "Generating...");
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    isComplete = false;
  }
}

async function previewShortlist() {
  if (!isFilesReady()) {
    setStatus("Load the files first.");
    return;
  }
  setStatus("Previewing candidate shortlist...");
  try {
    const response = await fetch("/api/preview-shortlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw payload;
    }
    commitState({ candidateShortlist: payload.candidates || [] }, { clearGeneration: false });
    state.lastOperation = { operation: "preview", stage: "completed", message: "Preview completed." };
    state.lastError = null;
    persistState();
    clearInlineError();
    setStatus(`Previewed ${payload.count || 0} candidates.`);
  } catch (error) {
    const details = error.error || error;
    showError({
      code: details.code || "PREVIEW-FAILED",
      message: details.message || "Could not preview shortlist.",
      stage: details.stage || "transcript",
      expected_input_format: details.expected_input_format || "Valid files, brief, and optional model constraints.",
      next_action: details.next_action || "Fix inputs and retry preview.",
    }, "preview");
  }
}

async function writeManualXml() {
  if (!state.manualAssemblyIndexes.length) {
    setStatus("Add some bites to the manual lane first.");
    return;
  }
  try {
    const response = await fetch("/api/render-xml", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...buildPayload(),
        name: `${state.variantName || "manual"}-manual`,
        cuts: state.manualAssemblyIndexes.map((segmentIndex) => ({ segment_index: segmentIndex })),
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw payload;
    }
    pushRunHistory(payload);
    window.location.assign("/project/export");
  } catch (error) {
    const details = error.error || error;
    showError({
      code: details.code || "MANUAL-RENDER-FAILED",
      message: details.message || "Could not render manual XML.",
      stage: details.stage || "transcript",
      expected_input_format: details.expected_input_format || "Valid manual lane and XML/transcript content.",
      next_action: details.next_action || "Fix inputs and retry.",
    }, "generate");
  }
}

async function openCurrentOutputFolder() {
  const run = getActiveGeneration();
  if (!run) {
    setStatus("No run yet.");
    return;
  }
  try {
    const response = await fetch("/api/open-output-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: run.run_id, saved_dir: run.saved_dir }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw payload.error || { message: "Could not open folder." };
    }
    setStatus(payload.message || "Opened output folder.");
  } catch (error) {
    const details = error;
    showError({
      code: details.code || "OPEN-FOLDER-FAILED",
      message: details.message || "Could not open folder.",
      stage: "output",
      expected_input_format: "A completed run with an available output folder.",
      next_action: "Retry opening the output folder from Download.",
    }, "generate");
  }
}

function applyQuickRerun(instruction) {
  const suffix = sanitizeFilename(instruction, "rerun");
  const nextVariantBase = (state.variantName || "v")
    .replace(new RegExp(`(?:-${escapeRegExp(suffix)})+$`), "")
    .replace(/-+$/g, "") || "v";
  const message = { role: "user", content: `Quick rerun: ${instruction}. Keep the same files.` };
  commitState({
    messages: [...state.messages, message],
    variantName: `${nextVariantBase}-${suffix}`,
  }, { clearGeneration: true });
  void generateSequences();
}

function acceptSuggestedPlan(mode) {
  const suggested = normalizePlan(state.suggestedPlan);
  if (!planHasContent(suggested)) {
    setStatus("No suggested plan yet.");
    return;
  }

  const nextAccepted = normalizePlan(state.acceptedPlan);

  if (mode === "accept-opening" && Number.isInteger(suggested.opening_segment_index)) {
    nextAccepted.opening_segment_index = suggested.opening_segment_index;
  }

  if (mode === "accept-includes") {
    nextAccepted.must_include_segment_indexes = uniqueNumbers([
      ...nextAccepted.must_include_segment_indexes,
      ...suggested.must_include_segment_indexes,
    ]);
  }

  if (mode === "accept-direction") {
    nextAccepted.generation_directive = suggested.generation_directive || nextAccepted.generation_directive;
    nextAccepted.narrative_arc = suggested.narrative_arc || nextAccepted.narrative_arc;
    nextAccepted.speaker_balance = suggested.speaker_balance || nextAccepted.speaker_balance;
    nextAccepted.rationale = suggested.rationale || nextAccepted.rationale;
  }

  if (mode === "accept-all") {
    if (Number.isInteger(suggested.opening_segment_index)) {
      nextAccepted.opening_segment_index = suggested.opening_segment_index;
    }
    nextAccepted.must_include_segment_indexes = uniqueNumbers([
      ...nextAccepted.must_include_segment_indexes,
      ...suggested.must_include_segment_indexes,
    ]);
    nextAccepted.source_segment_indexes = uniqueNumbers([
      ...nextAccepted.source_segment_indexes,
      ...suggested.source_segment_indexes,
    ]);
    nextAccepted.generation_directive = suggested.generation_directive || nextAccepted.generation_directive;
    nextAccepted.narrative_arc = suggested.narrative_arc || nextAccepted.narrative_arc;
    nextAccepted.speaker_balance = suggested.speaker_balance || nextAccepted.speaker_balance;
    nextAccepted.rationale = suggested.rationale || nextAccepted.rationale;
  }

  commitState({ acceptedPlan: nextAccepted }, { clearGeneration: true });
  setStatus("Accepted edit decisions updated.");
}

function toggleAcceptedSegment(index) {
  if (!Number.isInteger(index) || index < 0) {
    return;
  }
  const accepted = normalizePlan(state.acceptedPlan);
  const nextIncludes = new Set(accepted.must_include_segment_indexes);
  if (nextIncludes.has(index)) {
    nextIncludes.delete(index);
  } else {
    nextIncludes.add(index);
  }
  commitState({
    acceptedPlan: {
      ...accepted,
      must_include_segment_indexes: Array.from(nextIncludes),
    },
  }, { clearGeneration: true });
  setStatus(nextIncludes.has(index) ? `Kept [${index}] for generate.` : `Removed [${index}] from kept selections.`);
}

function resetDraft(redirectPath = null) {
  state = createDefaultState();
  modelInventory = [];
  persistState();
  renderAll();
  setStatus("Draft reset.");

  if (redirectPath) {
    window.location.assign(redirectPath);
  }
}

function bindPersistentFields() {
  if (projectTitleInput) {
    projectTitleInput.addEventListener("input", (event) => {
      commitState({ projectTitle: event.target.value }, { clearGeneration: false });
      if (state.lastError) {
        commitState({ lastError: null }, { clearError: true });
      }
    });
  }
  if (projectNotesInput) {
    projectNotesInput.addEventListener("input", (event) => {
      commitState({ projectNotes: event.target.value }, { clearGeneration: false });
      if (state.lastError) {
        commitState({ lastError: null }, { clearError: true });
      }
    });
  }
  if (briefInput) {
    briefInput.addEventListener("input", (event) => {
      commitState({ brief: event.target.value }, { clearGeneration: true, clearError: true });
    });
  }
  if (contextInput) {
    contextInput.addEventListener("input", (event) => {
      commitState({ projectContext: event.target.value }, { clearGeneration: true, clearError: true });
    });
  }
  if (optionsInput) {
    optionsInput.addEventListener("input", (event) => {
      commitState({ options: Number(event.target.value || 3) }, { clearGeneration: true, clearError: true });
    });
  }
  if (variantNameInput) {
    variantNameInput.addEventListener("input", (event) => {
      commitState({ variantName: event.target.value }, { clearGeneration: false });
    });
  }
  if (speakerBalanceSelect) {
    speakerBalanceSelect.addEventListener("change", (event) => {
      commitState({ speakerBalance: event.target.value }, { clearGeneration: true, clearError: true });
    });
  }
}

function retryLastOperation() {
  if (!state.lastOperation?.operation) {
    return;
  }
  if (state.lastOperation.operation === "preview") {
    void previewShortlist();
    return;
  }
  if (state.lastOperation.operation === "generate") {
    void generateSequences();
    return;
  }
  if (state.lastOperation.operation === "chat") {
    const lastUserMessage = (state.messages || [])
      .slice()
      .reverse()
      .find((message) => message.role === "user");
    if (chatInput && lastUserMessage?.content) {
      chatInput.value = lastUserMessage.content;
    }
    void sendChat();
  }
}

function bindNavigationGuards() {
  if (continueFromIntakeButton) {
    continueFromIntakeButton.addEventListener("click", (event) => {
      if (!isFilesReady()) {
        event.preventDefault();
        setStatus("Load the transcript and the Premiere XML first.");
      }
    });
  }

  if (continueFromBriefButton) {
    continueFromBriefButton.addEventListener("click", (event) => {
      if (!isFilesReady()) {
        event.preventDefault();
        setStatus("Load the files first.");
      } else if (!isBriefReady()) {
        event.preventDefault();
        setStatus("Write the brief first.");
      }
    });
  }

  if (continueFromChatButton) {
    continueFromChatButton.addEventListener("click", (event) => {
      if (!isGenerateReady()) {
        event.preventDefault();
        setStatus("Check local models and choose one first.");
      }
    });
  }

  stepLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      const rule = stepRule(link.dataset.stepLink || "");
      const isCurrent = link.dataset.stepLink === pageKey;
      if (!isCurrent && !rule.enabled) {
        event.preventDefault();
        setStatus(rule.message);
      }
    });
  });
}

function bindEvents() {
  bindPersistentFields();
  bindNavigationGuards();

  if (transcriptFileInput) {
    transcriptFileInput.addEventListener("change", async (event) => {
      await loadFile(event.target.files[0], "transcript");
    });
  }

  if (sourceList) {
    sourceList.addEventListener("change", async (event) => {
      const input = event.target.closest("[data-source-file]");
      if (!input) {
        return;
      }
      await loadFile(input.files[0], input.dataset.sourceFile, input.dataset.sourceId);
    });
  }

  if (addSourceButton) {
    addSourceButton.addEventListener("click", () => addSourcePair());
  }

  if (xmlFileInput) {
    xmlFileInput.addEventListener("change", async (event) => {
      await loadFile(event.target.files[0], "xml");
    });
  }

  if (projectFileInput) {
    projectFileInput.addEventListener("change", async (event) => {
      await loadProjectState(event.target.files[0]);
    });
  }

  if (saveProjectButton) {
    saveProjectButton.addEventListener("click", exportProjectState);
  }

  if (loadSolarDemoButton) {
    loadSolarDemoButton.addEventListener("click", () => {
      void loadSolarDemoWorkspace();
    });
  }

  if (startFreshButton) {
    startFreshButton.addEventListener("click", () => resetDraft());
  }

  if (startOverButton) {
    startOverButton.addEventListener("click", () => resetDraft("/"));
  }

  if (chatButton) {
    chatButton.addEventListener("click", sendChat);
  }

  if (chatInput) {
    chatInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
        return;
      }
      event.preventDefault();
      if (chatButton && !chatButton.disabled) {
        sendChat();
      }
    });
  }

  if (clearChatButton) {
    clearChatButton.addEventListener("click", () => {
      commitState({ messages: [], suggestedPlan: createEmptyPlan() });
      setStatus("Chat cleared.");
    });
  }

  document.querySelectorAll("[data-chat-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      if (chatInput) {
        chatInput.value = button.dataset.chatPrompt || "";
        chatInput.focus();
      }
    });
  });

  if (generateButton) {
    generateButton.addEventListener("click", generateSequences);
  }

  if (previewShortlistButton) {
    previewShortlistButton.addEventListener("click", previewShortlist);
  }

  if (manualXmlButton) {
    manualXmlButton.addEventListener("click", writeManualXml);
  }

  if (rerunSameFilesButton) {
    rerunSameFilesButton.addEventListener("click", generateSequences);
  }

  if (openFolderButton) {
    openFolderButton.addEventListener("click", openCurrentOutputFolder);
  }

  document.querySelectorAll("[data-rerun-style]").forEach((button) => {
    button.addEventListener("click", () => applyQuickRerun(button.dataset.rerunStyle || "make it sharper"));
  });

  if (compareLeftSelect) {
    compareLeftSelect.addEventListener("change", (event) => {
      commitState({ compareLeftRunId: event.target.value }, { clearGeneration: false });
    });
  }

  if (compareRightSelect) {
    compareRightSelect.addEventListener("change", (event) => {
      commitState({ compareRightRunId: event.target.value }, { clearGeneration: false });
    });
  }

  if (logsRunSelect) {
    logsRunSelect.addEventListener("change", () => {
      void renderLogsPage();
    });
  }

  if (transcriptSearchInput) {
    transcriptSearchInput.addEventListener("input", renderTranscriptBrowser);
  }

  document.addEventListener("click", (event) => {
    const focusSegment = event.target.closest("[data-focus-segment]");
    if (focusSegment) {
      setFocusedSegment(Number(focusSegment.dataset.focusSegment));
    }

    const recoverAction = event.target.closest("[data-recover-action]");
    if (recoverAction) {
      const action = recoverAction.dataset.recoverAction;
      if (action === "retry") {
        event.preventDefault();
        commitState({ lastError: null }, { clearError: true });
        clearInlineError();
        retryLastOperation();
      }
      return;
    }

    const segmentButton = event.target.closest("[data-segment-action]");
    if (segmentButton) {
      const index = Number(segmentButton.dataset.segmentIndex);
      const action = segmentButton.dataset.segmentAction;
      if (action === "add") {
        addManualSegment(index);
      }
      if (action === "pin") {
        toggleIndex("pinnedSegmentIndexes", index);
      }
      if (action === "ban") {
        toggleIndex("bannedSegmentIndexes", index);
      }
      if (action === "require") {
        toggleIndex("requiredSegmentIndexes", index);
      }
      if (action === "lock") {
        toggleIndex("lockedSegmentIndexes", index);
      }
      if (action === "open") {
        commitState({
          forcedOpenSegmentIndex: state.forcedOpenSegmentIndex === index ? null : index,
        }, { clearGeneration: true });
      }
    }

    const manualMove = event.target.closest("[data-manual-move]");
    if (manualMove) {
      moveManualSegment(Number(manualMove.dataset.manualMove), Number(manualMove.dataset.manualDelta || 0));
    }

    const manualRemove = event.target.closest("[data-manual-remove]");
    if (manualRemove) {
      removeManualSegment(Number(manualRemove.dataset.manualRemove));
    }

    const lockCut = event.target.closest("[data-lock-cut]");
    if (lockCut) {
      toggleIndex("lockedSegmentIndexes", Number(lockCut.dataset.lockCut));
    }

    const planAction = event.target.closest("[data-plan-action]");
    if (planAction) {
      const action = planAction.dataset.planAction;
      if (action === "clear-accepted") {
        commitState({ acceptedPlan: createEmptyPlan() }, { clearGeneration: true });
        setStatus("Accepted edit decisions cleared.");
      } else {
        acceptSuggestedPlan(action);
      }
    }

    const removeSource = event.target.closest("[data-remove-source]");
    if (removeSource) {
      removeSourcePair(removeSource.dataset.removeSource);
      return;
    }

    const chatKeep = event.target.closest("[data-chat-keep-index]");
    if (chatKeep) {
      toggleAcceptedSegment(Number(chatKeep.dataset.chatKeepIndex));
    }
  });
}

bindEvents();
void fetchModels();
if (
  state.transcriptText
  && (
    !state.transcriptSegments.length
    || !state.transcriptSegments.some((segment) => rawDurationSeconds(segment.duration_seconds) > 0)
  )
) {
  void refreshTranscriptSegments();
}
renderAll();
