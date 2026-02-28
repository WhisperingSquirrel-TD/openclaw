import { createSubsystemLogger } from "../../logging/subsystem.js";

const log = createSubsystemLogger("totp/session");

type ApprovalWindow = {
  expiresAt: number;
  approvedActions: Set<string>;
  channel: string;
  accountId?: string;
};

let activeWindow: ApprovalWindow | null = null;

type PendingResolver = {
  resolve: (approved: boolean) => void;
  action: string;
  timer: ReturnType<typeof setTimeout>;
  settled: boolean;
};

const pendingResolvers: PendingResolver[] = [];

function settleResolver(entry: PendingResolver, approved: boolean): void {
  if (entry.settled) {
    return;
  }
  entry.settled = true;
  clearTimeout(entry.timer);
  entry.resolve(approved);
}

function drainAllResolvers(approved: boolean): void {
  for (const entry of pendingResolvers) {
    settleResolver(entry, approved);
  }
  pendingResolvers.length = 0;
}

export function startApprovalWindow(params: {
  durationMinutes: number;
  actions?: string[];
  channel?: string;
  accountId?: string;
}): { expiresAt: number } {
  const durationMs = params.durationMinutes * 60 * 1000;
  const expiresAt = Date.now() + durationMs;

  activeWindow = {
    expiresAt,
    approvedActions: new Set(params.actions ?? ["message.send"]),
    channel: params.channel ?? "all",
    accountId: params.accountId,
  };

  log.info("TOTP approval window opened", {
    durationMinutes: params.durationMinutes,
    expiresAt: new Date(expiresAt).toISOString(),
    actions: Array.from(activeWindow.approvedActions),
  });

  const remaining: PendingResolver[] = [];
  for (const entry of pendingResolvers) {
    if (activeWindow.approvedActions.has(entry.action)) {
      settleResolver(entry, true);
    } else {
      remaining.push(entry);
    }
  }
  pendingResolvers.length = 0;
  pendingResolvers.push(...remaining);

  return { expiresAt };
}

export function isApprovalWindowActive(): boolean {
  if (!activeWindow) {
    return false;
  }
  if (Date.now() >= activeWindow.expiresAt) {
    log.info("TOTP approval window expired");
    activeWindow = null;
    return false;
  }
  return true;
}

export function isActionApproved(action: string): boolean {
  if (!isApprovalWindowActive()) {
    return false;
  }
  return activeWindow!.approvedActions.has(action);
}

export function getRemainingSeconds(): number {
  if (!isApprovalWindowActive()) {
    return 0;
  }
  return Math.max(0, Math.ceil((activeWindow!.expiresAt - Date.now()) / 1000));
}

export function closeApprovalWindow(): void {
  if (activeWindow) {
    log.info("TOTP approval window closed manually");
    activeWindow = null;
  }
  drainAllResolvers(false);
}

export function waitForApprovalWindow(
  action: string,
  timeoutMs: number,
): Promise<boolean> {
  if (isActionApproved(action)) {
    return Promise.resolve(true);
  }

  return new Promise<boolean>((resolve) => {
    const entry: PendingResolver = {
      resolve,
      action,
      settled: false,
      timer: null as unknown as ReturnType<typeof setTimeout>,
    };

    entry.timer = setTimeout(() => {
      settleResolver(entry, false);
      const idx = pendingResolvers.indexOf(entry);
      if (idx !== -1) {
        pendingResolvers.splice(idx, 1);
      }
    }, timeoutMs);

    pendingResolvers.push(entry);
  });
}

export function getWindowStatus(): {
  active: boolean;
  remainingSeconds: number;
  actions: string[];
} | null {
  if (!isApprovalWindowActive()) {
    return null;
  }
  return {
    active: true,
    remainingSeconds: getRemainingSeconds(),
    actions: Array.from(activeWindow!.approvedActions),
  };
}
