import type { OpenClawConfig } from "../../config/config.js";
import { loadConfig } from "../../config/config.js";
import { logInfo } from "../../logger.js";
import { logVerbose } from "../../globals.js";
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

function resolveWatchActionsConfig(cfg: OpenClawConfig): WatchActionsConfig {
  const whatsapp = cfg.channels?.whatsapp as Record<string, unknown> | undefined;
  const watchActions = whatsapp?.watchActions as Record<string, unknown> | undefined;

  return {
    enabled: watchActions?.enabled === true,
    activeHoursStart: typeof watchActions?.activeHoursStart === "number" ? watchActions.activeHoursStart : 8,
    activeHoursEnd: typeof watchActions?.activeHoursEnd === "number" ? watchActions.activeHoursEnd : 22,
    intervalMinutes: typeof watchActions?.intervalMinutes === "number" ? watchActions.intervalMinutes : 60,
    model: typeof watchActions?.model === "string" ? watchActions.model : undefined,
  };
}

function resolveWhatsAppAccountIds(cfg: OpenClawConfig): string[] {
  const whatsapp = cfg.channels?.whatsapp;
  if (!whatsapp) return [];

  const accounts = (whatsapp as Record<string, unknown>).accounts as
    | Record<string, unknown>
    | undefined;
  if (accounts && typeof accounts === "object") {
    return Object.keys(accounts);
  }

  return ["default"];
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

async function runScan(): Promise<void> {
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

    const now = Date.now();
    const intervalMs = config.intervalMinutes * 60 * 1000;
    if (now - lastScanTime < intervalMs) {
      logVerbose("watch-action-scheduler: too soon since last scan, skipping");
      return;
    }

    lastScanTime = now;
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

const TICK_INTERVAL_MS = 15 * 60 * 1000;

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
    `watch-action-scheduler: starting (active ${config.activeHoursStart}:00-${config.activeHoursEnd}:00, every ${config.intervalMinutes}min)`,
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
}
