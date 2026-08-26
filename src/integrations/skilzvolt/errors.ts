export type SkilzVoltOAuthErrorKind =
  | "discovery"
  | "registration"
  | "authorization"
  | "token_exchange"
  | "refresh"
  | "network"
  | "timeout"
  | "cancelled";

export class SkilzVoltOAuthError extends Error {
  constructor(
    message: string,
    readonly kind: SkilzVoltOAuthErrorKind,
  ) {
    super(message);
    this.name = "SkilzVoltOAuthError";
  }
}
