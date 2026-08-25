import type { WebInboundMessage } from "../../../../src/web/inbound/types.js";

/** Extension ingress additionally preserves Baileys' LID identity for reply mentions. */
export type WebInboundMsg = WebInboundMessage & {
  selfLid?: string | null;
};