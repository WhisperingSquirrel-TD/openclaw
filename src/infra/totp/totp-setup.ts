import crypto from "node:crypto";
import fs from "node:fs";
import fsPromises from "node:fs/promises";
import path from "node:path";
import { resolveStateDir } from "../../config/paths.js";
import { createSubsystemLogger } from "../../logging/subsystem.js";
import { generateTotpSecret } from "./totp.js";

const log = createSubsystemLogger("totp/setup");

const TOTP_DIRNAME = "totp";
const SECRET_FILENAME = "totp-secret.enc";
const SECRET_PLAINTEXT_FILENAME = "totp-secret.txt";
const PASSPHRASE_ENV = "OPENCLAW_VAULT_PASSPHRASE";

const ALGORITHM = "aes-256-gcm";
const KEY_LENGTH = 32;
const IV_LENGTH = 12;
const SALT_LENGTH = 16;
const TAG_LENGTH = 16;
const PBKDF2_ITERATIONS = 100_000;
const PBKDF2_DIGEST = "sha512";

function resolveTotpDir(stateDir?: string): string {
  return path.join(stateDir ?? resolveStateDir(), TOTP_DIRNAME);
}

function resolvePassphrase(): string | undefined {
  const value = process.env[PASSPHRASE_ENV]?.trim();
  return value || undefined;
}

function deriveKey(passphrase: string, salt: Buffer): Buffer {
  return crypto.pbkdf2Sync(passphrase, salt, PBKDF2_ITERATIONS, KEY_LENGTH, PBKDF2_DIGEST);
}

function encryptSecret(secret: string, passphrase: string): Buffer {
  const salt = crypto.randomBytes(SALT_LENGTH);
  const iv = crypto.randomBytes(IV_LENGTH);
  const key = deriveKey(passphrase, salt);
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  const encrypted = Buffer.concat([cipher.update(secret, "utf-8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([salt, iv, tag, encrypted]);
}

function decryptSecret(data: Buffer, passphrase: string): string {
  if (data.length < SALT_LENGTH + IV_LENGTH + TAG_LENGTH) {
    throw new Error("Invalid encrypted TOTP secret: too short");
  }
  const salt = data.subarray(0, SALT_LENGTH);
  const iv = data.subarray(SALT_LENGTH, SALT_LENGTH + IV_LENGTH);
  const tag = data.subarray(SALT_LENGTH + IV_LENGTH, SALT_LENGTH + IV_LENGTH + TAG_LENGTH);
  const encrypted = data.subarray(SALT_LENGTH + IV_LENGTH + TAG_LENGTH);
  const key = deriveKey(passphrase, salt);
  const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
  decipher.setAuthTag(tag);
  const decrypted = Buffer.concat([decipher.update(encrypted), decipher.final()]);
  return decrypted.toString("utf-8");
}

export async function isTotpConfigured(stateDir?: string): Promise<boolean> {
  const dir = resolveTotpDir(stateDir);
  const encPath = path.join(dir, SECRET_FILENAME);
  const plainPath = path.join(dir, SECRET_PLAINTEXT_FILENAME);
  try {
    await fsPromises.access(encPath);
    return true;
  } catch {
    try {
      await fsPromises.access(plainPath);
      return true;
    } catch {
      return false;
    }
  }
}

export async function saveTotpSecret(secret: string, stateDir?: string): Promise<void> {
  const dir = resolveTotpDir(stateDir);
  await fsPromises.mkdir(dir, { recursive: true, mode: 0o700 });

  const passphrase = resolvePassphrase();
  if (passphrase) {
    const encrypted = encryptSecret(secret, passphrase);
    await fsPromises.writeFile(path.join(dir, SECRET_FILENAME), encrypted, { mode: 0o600 });
    log.info("TOTP secret saved (encrypted)");
  } else {
    await fsPromises.writeFile(path.join(dir, SECRET_PLAINTEXT_FILENAME), secret, {
      encoding: "utf-8",
      mode: 0o600,
    });
    log.warn("TOTP secret saved as plaintext (set OPENCLAW_VAULT_PASSPHRASE for encryption)");
  }
}

export async function loadTotpSecret(stateDir?: string): Promise<string | null> {
  const dir = resolveTotpDir(stateDir);
  const passphrase = resolvePassphrase();

  if (passphrase) {
    const encPath = path.join(dir, SECRET_FILENAME);
    try {
      const data = await fsPromises.readFile(encPath);
      return decryptSecret(data, passphrase);
    } catch {
      // fall through to plaintext
    }
  }

  const plainPath = path.join(dir, SECRET_PLAINTEXT_FILENAME);
  try {
    const content = await fsPromises.readFile(plainPath, "utf-8");
    return content.trim();
  } catch {
    return null;
  }
}

export async function setupTotp(
  accountName: string,
  stateDir?: string,
): Promise<{ secret: string; uri: string }> {
  const { generateTotpUri } = await import("./totp.js");
  const secret = generateTotpSecret();
  await saveTotpSecret(secret, stateDir);
  const uri = generateTotpUri(secret, accountName);
  log.info("TOTP setup complete", { accountName });
  return { secret, uri };
}
