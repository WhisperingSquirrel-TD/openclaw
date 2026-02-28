import crypto from "node:crypto";

const TOTP_DIGITS = 6;
const TOTP_STEP_SECONDS = 30;
const BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

export function generateTotpSecret(bytes = 20): string {
  const buf = crypto.randomBytes(bytes);
  return base32Encode(buf);
}

export function base32Encode(buffer: Buffer): string {
  let bits = "";
  for (const byte of buffer) {
    bits += byte.toString(2).padStart(8, "0");
  }
  let result = "";
  for (let i = 0; i < bits.length; i += 5) {
    const chunk = bits.slice(i, i + 5).padEnd(5, "0");
    result += BASE32_ALPHABET[parseInt(chunk, 2)];
  }
  return result;
}

export function base32Decode(encoded: string): Buffer {
  const cleaned = encoded.replace(/[\s=]/g, "").toUpperCase();
  let bits = "";
  for (const char of cleaned) {
    const idx = BASE32_ALPHABET.indexOf(char);
    if (idx === -1) {
      throw new Error(`Invalid base32 character: ${char}`);
    }
    bits += idx.toString(2).padStart(5, "0");
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(parseInt(bits.slice(i, i + 8), 2));
  }
  return Buffer.from(bytes);
}

function hmacSha1(key: Buffer, message: Buffer): Buffer {
  return crypto.createHmac("sha1", key).update(message).digest();
}

function dynamicTruncate(hmacResult: Buffer): number {
  const offset = hmacResult[hmacResult.length - 1]! & 0x0f;
  const code =
    ((hmacResult[offset]! & 0x7f) << 24) |
    ((hmacResult[offset + 1]! & 0xff) << 16) |
    ((hmacResult[offset + 2]! & 0xff) << 8) |
    (hmacResult[offset + 3]! & 0xff);
  return code % 10 ** TOTP_DIGITS;
}

export function generateTotpCode(secret: string, timeMs?: number): string {
  const time = timeMs ?? Date.now();
  const counter = Math.floor(time / 1000 / TOTP_STEP_SECONDS);
  const counterBuf = Buffer.alloc(8);
  counterBuf.writeBigUInt64BE(BigInt(counter));
  const key = base32Decode(secret);
  const hmac = hmacSha1(key, counterBuf);
  const code = dynamicTruncate(hmac);
  return code.toString().padStart(TOTP_DIGITS, "0");
}

export function verifyTotpCode(
  secret: string,
  code: string,
  opts?: { window?: number; timeMs?: number },
): boolean {
  const window = opts?.window ?? 1;
  const time = opts?.timeMs ?? Date.now();
  const trimmed = code.trim();
  if (trimmed.length !== TOTP_DIGITS || !/^\d+$/.test(trimmed)) {
    return false;
  }
  for (let i = -window; i <= window; i++) {
    const offsetTime = time + i * TOTP_STEP_SECONDS * 1000;
    const expected = generateTotpCode(secret, offsetTime);
    if (crypto.timingSafeEqual(Buffer.from(trimmed), Buffer.from(expected))) {
      return true;
    }
  }
  return false;
}

export function generateTotpUri(
  secret: string,
  accountName: string,
  issuer = "OpenClaw",
): string {
  const encodedAccount = encodeURIComponent(accountName);
  const encodedIssuer = encodeURIComponent(issuer);
  return `otpauth://totp/${encodedIssuer}:${encodedAccount}?secret=${secret}&issuer=${encodedIssuer}&algorithm=SHA1&digits=${TOTP_DIGITS}&period=${TOTP_STEP_SECONDS}`;
}
