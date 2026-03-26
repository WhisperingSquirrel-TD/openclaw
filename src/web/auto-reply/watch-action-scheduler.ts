import fs from "node:fs";
import path from "node:path";
import type { OpenClawConfig } from "../../config/config.js";
import { loadConfig } from "../../config/config.js";
import { logInfo } from "../../logger.js";
import { logVerbose } from "../../globals.js";
import { resolveOAuthDir } from "../../config/paths.js";
import { scanWatchTranscript, commitCursor } from "./watch-action-scanner.js";
import { classifyActions } from "./watch-action-classifier.js";
import { notifyActions } from "./watch-action-notify.js";
import { cleanupOldActions } from "./watch-action-store.js";

type WatchActionsConfig = {
  enabled: boolean;
  activeHoursStart: number;
  activeHoursEnd: number;
  intervalMinutes: number;
  model?: string;
};

let schedulerTimer: ReturnType<typeof setInterval> | null = null;
let lastScanTime: number = 0;
let isScanning = false;

let eventDrivenDebounceTimer: ReturnType<typeof setTimeout> | null = null;
let lastEventDrivenScanTime: number = 0;
const EVENT_DRIVEN_DEBOUNCE_MS = 45_000;
const EVENT_DRIVEN_MIN_INTERVAL_MS = 2 * 60 * 1000;

function resolveWatchActionsConfig(cfg: OpenClawConfig): WatchActionsConfig {
  const whatsapp = cfg.channels?.whatsapp as Record<string, unknown> | undefined;
  const watchActions = whatsapp?.watchActions as Record<string, unknown> | undefined;

  return {
    enabled: watchActions?.enabled === true,
    activeHoursStart: typeof watchActions?.activeHoursStart === "number" ? watchActions.activeHoursStart : 8,
    activeHoursEnd: typeof watchActions?.activeHoursEnd === "number" ? watchActions.activeHoursEnd : 22,
    intervalMinutes: typeof watchActions?.intervalMinutes === "number" ? watchActions.intervalMinutes : 5,
    model: typeof watchActions?.model === "string" ? watchActions.model : undefined,
  };
}

function resolveWhatsAppAccountIds(cfg: OpenClawConfig): string[] {
  const whatsapp = cfg.channels?.whatsapp;
  if (!whatsapp) return [];

  // IDs from config (explicit accounts block)
  const accounts = (whatsapp as Record<string, unknown>).accounts as
    | Record<string, unknown>
    | undefined;
  const configIds = accounts && typeof accounts === "object" ? Object.keys(accounts) : [];

  // Also discover account IDs from transcript files on disk — catches accounts that
  // are paired but not yet reflected in the config (e.g. single-account root-level watch mode).
  const transcriptDir = path.join(resolveOAuthDir(), "whatsapp", "watch-transcripts");
  const diskIds: string[] = [];
  try {
    const files = fs.readdirSync(transcriptDir);
    for (const file of files) {
      const match = file.match(/^whatsapp-watch-(.+)\.jsonl$/);
      if (match) {
        diskIds.push(match[1]);
      }
    }
  } catch {
    // Directory doesn't exist yet — fine, nothing to scan
  }

  // Merge: config IDs first, then any disk IDs not already in the list
  const merged = [...configIds];
  for (const id of diskIds) {
    if (!merged.includes(id)) {
      merged.push(id);
    }
  }

  // Fall back to "default" only if nothing found anywhere
  return merged.length > 0 ? merged : ["default"];
}

function isWatchModeAccount(cfg: OpenClawConfig, accountId: string): boolean {
  const whatsapp = cfg.channels?.whatsapp as Record<string, unknown> | undefined;
  if (!whatsapp) return false;

  const rootMode = whatsapp.mode as string | undefined;

  const accounts = whatsapp.accounts as Record<string, Record<string, unknown>> | undefined;
  if (accounts && accountId in accounts) {
    const accountMode = accounts[accountId]?.mode as string | undefined;
    if (accountMode) return accountMode === "watch";
  }

  return rootMode === "watch";
}

function isInActiveHours(config: WatchActionsConfig): boolean {
  const now = new Date();
  const hour = now.getHours();
  return hour >= config.activeHoursStart && hour < config.activeHoursEnd;
}

async function runScan(opts: { skipIntervalThrottle?: boolean } = {}): Promise<void> {
  if (isScanning) {
    logVerbose("watch-action-scheduler: scan already in progress, skipping");
    return;
  }

  isScanning = true;
  try {
    const cfg = loadConfig();
    const config = resolveWatchActionsConfig(cfg);

    if (!config.enabled) {
      logVerbose("watch-action-scheduler: disabled in config");
      return;
    }

    if (!isInActiveHours(config)) {
      logVerbose("watch-action-scheduler: outside active hours, skipping");
      return;
    }

    if (!opts.skipIntervalThrottle) {
      const now = Date.now();
      const intervalMs = config.intervalMinutes * 60 * 1000;
      if (now - lastScanTime < intervalMs) {
        logVerbose("watch-action-scheduler: too soon since last scan, skipping");
        return;
      }
    }

    lastScanTime = Date.now();
    const accountIds = resolveWhatsAppAccountIds(cfg);

    let totalActions = 0;
    for (const accountId of accountIds) {
      if (!isWatchModeAccount(cfg, accountId)) {
        logVerbose(`watch-action-scheduler: account ${accountId} is not in watch mode, skipping`);
        continue;
      }

      const { candidates, contextMessages, newCursorOffset } = scanWatchTranscript(accountId);
      if (candidates.length === 0) {
        commitCursor(accountId, newCursorOffset);
        continue;
      }

      logInfo(`watch-action-scheduler: scanning ${candidates.length} messages for account ${accountId}`);
      try {
        const actions = await classifyActions(cfg, candidates, contextMessages);
        if (actions.length > 0) {
          await notifyActions(cfg, actions);
          totalActions += actions.length;
        }
        commitCursor(accountId, newCursorOffset);
      } catch (err) {
        logInfo(`watch-action-scheduler: scan failed for account ${accountId}, cursor NOT advanced: ${String(err)}`);
      }
    }

    if (totalActions > 0) {
      logInfo(`watch-action-scheduler: scan complete, ${totalActions} action(s) detected`);
    } else {
      logVerbose("watch-action-scheduler: scan complete, no actions detected");
    }

    cleanupOldActions(7);
  } catch (err) {
    logInfo(`watch-action-scheduler: scan failed: ${String(err)}`);
  } finally {
    isScanning = false;
  }
}

/**
 * Called from monitor.ts each time a new WhatsApp message is written to the transcript.
 * Debounces for 45 seconds (to batch quick bursts), then triggers a scan immediately
 * regardless of the intervalMinutes setting — so cards appear within ~1 minute of the message.
 * Won't fire more than once every 2 minutes via this path.
 */
export function triggerWatchActionScanDebounced(): void {
  if (eventDrivenDebounceTimer) {
    clearTimeout(eventDrivenDebounceTimer);
    eventDrivenDebounceTimer = null;
  }

  const now = Date.now();
  if (now - lastEventDrivenScanTime < EVENT_DRIVEN_MIN_INTERVAL_MS) {
    logVerbose("watch-action-scheduler: event-driven scan throttled (too recent)");
    return;
  }

  eventDrivenDebounceTimer = setTimeout(() => {
    eventDrivenDebounceTimer = null;
    lastEventDrivenScanTime = Date.now();
    logVerbose("watch-action-scheduler: event-driven scan triggered by incoming message");
    void runScan({ skipIntervalThrottle: true });
  }, EVENT_DRIVEN_DEBOUNCE_MS);
}

const TICK_INTERVAL_MS = 2 * 60 * 1000;

export function startWatchActionScheduler(): void {
  if (schedulerTimer) {
    logVerbose("watch-action-scheduler: already running");
    return;
  }

  const cfg = loadConfig();
  const config = resolveWatchActionsConfig(cfg);

  if (!config.enabled) {
    logVerbose("watch-action-scheduler: not enabled in config");
    return;
  }

  logInfo(
    `watch-action-scheduler: starting (active ${config.activeHoursStart}:00-${config.activeHoursEnd}:00, every ${config.intervalMinutes}min, event-driven debounce ${EVENT_DRIVEN_DEBOUNCE_MS / 1000}s)`,
  );

  schedulerTimer = setInterval(() => {
    void runScan();
  }, TICK_INTERVAL_MS);

  setTimeout(() => void runScan(), 30_000);
}

export function stopWatchActionScheduler(): void {
  if (schedulerTimer) {
    clearInterval(schedulerTimer);
    schedulerTimer = null;
    logInfo("watch-action-scheduler: stopped");
  }
  if (eventDrivenDebounceTimer) {
    clearTimeout(eventDrivenDebounceTimer);
    eventDrivenDebounceTimer = null;
  }
}
