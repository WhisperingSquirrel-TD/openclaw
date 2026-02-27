import { loadConfig } from "../config/config.js";
import type { ChannelMode } from "./accounts.js";
import { resolveWhatsAppAccount } from "./accounts.js";

export class WatchModeBlockError extends Error {
  constructor(accountId: string) {
    super(
      `WhatsApp account "${accountId}" is in watch mode — all outbound messages are blocked. ` +
        `Set channels.whatsapp.mode (or channels.whatsapp.accounts.${accountId}.mode) to "active" to enable sending.`,
    );
    this.name = "WatchModeBlockError";
  }
}

export function resolveWhatsAppMode(accountId?: string | null): ChannelMode {
  const cfg = loadConfig();
  const account = resolveWhatsAppAccount({ cfg, accountId });
  return account.mode;
}

export function assertNotWatchMode(accountId?: string | null): void {
  const cfg = loadConfig();
  const account = resolveWhatsAppAccount({ cfg, accountId });
  if (account.mode === "watch") {
    throw new WatchModeBlockError(account.accountId);
  }
}
