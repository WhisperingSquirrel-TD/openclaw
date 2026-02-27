import type { OpenClawConfig } from "../../config/config.js";
import { createSubsystemLogger } from "../../logging/subsystem.js";
import type { OutboundChannel } from "./targets.js";

const log = createSubsystemLogger("outbound/rate-limiter");

export type RateLimitOverflowBehavior = "queue" | "drop";

export type RateLimitConfig = {
  maxMessagesPerMinute?: number;
  maxMessagesPerHour?: number;
  rateLimitOverflow?: RateLimitOverflowBehavior;
};

type BucketKey = string;

const buckets = new Map<BucketKey, number[]>();

function bucketKey(channel: string, accountId?: string): BucketKey {
  return accountId ? `${channel}:${accountId}` : channel;
}

function pruneExpired(timestamps: number[], windowMs: number, now: number): number[] {
  const cutoff = now - windowMs;
  let i = 0;
  while (i < timestamps.length && timestamps[i]! < cutoff) {
    i++;
  }
  return i > 0 ? timestamps.slice(i) : timestamps;
}

const ONE_MINUTE_MS = 60_000;
const ONE_HOUR_MS = 3_600_000;

export type RateLimitResult = {
  allowed: boolean;
  reason?: string;
};

export function checkRateLimit(params: {
  channel: string;
  accountId?: string;
  maxPerMinute?: number;
  maxPerHour?: number;
  now?: number;
}): RateLimitResult {
  const { channel, accountId, maxPerMinute, maxPerHour } = params;
  if (maxPerMinute === undefined && maxPerHour === undefined) {
    return { allowed: true };
  }

  const now = params.now ?? Date.now();
  const key = bucketKey(channel, accountId);
  let timestamps = buckets.get(key) ?? [];

  timestamps = pruneExpired(timestamps, ONE_HOUR_MS, now);

  if (maxPerMinute !== undefined) {
    const minuteCutoff = now - ONE_MINUTE_MS;
    const countInMinute = timestamps.filter((t) => t >= minuteCutoff).length;
    if (countInMinute >= maxPerMinute) {
      return {
        allowed: false,
        reason: `Rate limit exceeded: ${countInMinute}/${maxPerMinute} messages per minute on ${channel}${accountId ? `:${accountId}` : ""}`,
      };
    }
  }

  if (maxPerHour !== undefined) {
    if (timestamps.length >= maxPerHour) {
      return {
        allowed: false,
        reason: `Rate limit exceeded: ${timestamps.length}/${maxPerHour} messages per hour on ${channel}${accountId ? `:${accountId}` : ""}`,
      };
    }
  }

  return { allowed: true };
}

export function recordMessage(params: {
  channel: string;
  accountId?: string;
  now?: number;
}): void {
  const now = params.now ?? Date.now();
  const key = bucketKey(params.channel, params.accountId);
  let timestamps = buckets.get(key) ?? [];
  timestamps = pruneExpired(timestamps, ONE_HOUR_MS, now);
  timestamps.push(now);
  buckets.set(key, timestamps);
}

export function resolveChannelRateLimitConfig(
  cfg: OpenClawConfig,
  channel: Exclude<OutboundChannel, "none">,
  accountId?: string,
): RateLimitConfig {
  const channels = cfg.channels;
  if (!channels) {
    return {};
  }
  const resolve = (channelCfg: RateLimitConfig | undefined): RateLimitConfig => channelCfg ?? {};

  switch (channel) {
    case "telegram": {
      const tg = channels.telegram;
      if (!tg) return {};
      if (accountId && tg.accounts?.[accountId]) {
        const acct = tg.accounts[accountId]!;
        return {
          maxMessagesPerMinute: acct.maxMessagesPerMinute ?? tg.maxMessagesPerMinute,
          maxMessagesPerHour: acct.maxMessagesPerHour ?? tg.maxMessagesPerHour,
          rateLimitOverflow: acct.rateLimitOverflow ?? tg.rateLimitOverflow,
        };
      }
      return resolve(tg);
    }
    case "whatsapp": {
      const wa = channels.whatsapp;
      if (!wa) return {};
      if (accountId && wa.accounts?.[accountId]) {
        const acct = wa.accounts[accountId]!;
        return {
          maxMessagesPerMinute: acct.maxMessagesPerMinute ?? wa.maxMessagesPerMinute,
          maxMessagesPerHour: acct.maxMessagesPerHour ?? wa.maxMessagesPerHour,
          rateLimitOverflow: acct.rateLimitOverflow ?? wa.rateLimitOverflow,
        };
      }
      return resolve(wa);
    }
    case "discord": {
      const dc = channels.discord;
      if (!dc) return {};
      if (accountId && dc.accounts?.[accountId]) {
        const acct = dc.accounts[accountId]!;
        return {
          maxMessagesPerMinute: acct.maxMessagesPerMinute ?? dc.maxMessagesPerMinute,
          maxMessagesPerHour: acct.maxMessagesPerHour ?? dc.maxMessagesPerHour,
          rateLimitOverflow: acct.rateLimitOverflow ?? dc.rateLimitOverflow,
        };
      }
      return resolve(dc);
    }
    default: {
      const generic = channels[channel] as RateLimitConfig | undefined;
      return resolve(generic);
    }
  }
}

export function checkChannelRateLimit(params: {
  cfg: OpenClawConfig;
  channel: Exclude<OutboundChannel, "none">;
  accountId?: string;
  now?: number;
}): RateLimitResult & { overflow: RateLimitOverflowBehavior } {
  const limConfig = resolveChannelRateLimitConfig(params.cfg, params.channel, params.accountId);
  const overflow = limConfig.rateLimitOverflow ?? "queue";
  const result = checkRateLimit({
    channel: params.channel,
    accountId: params.accountId,
    maxPerMinute: limConfig.maxMessagesPerMinute,
    maxPerHour: limConfig.maxMessagesPerHour,
    now: params.now,
  });
  return { ...result, overflow };
}

export const __testing = {
  resetRateLimitState() {
    buckets.clear();
  },
};
