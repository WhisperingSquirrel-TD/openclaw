import crypto from "node:crypto";
import fs from "node:fs";
import fsPromises from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { resolveStateDir } from "../config/paths.js";

const ALGORITHM = "aes-256-gcm";
const KEY_LENGTH = 32;
const IV_LENGTH = 12;
const SALT_LENGTH = 16;
const TAG_LENGTH = 16;
const PBKDF2_ITERATIONS = 100_000;
const PBKDF2_DIGEST = "sha512";

const VAULT_DIRNAME = "vault";
const ENCRYPTED_SOUL_FILENAME = "SOUL.md.enc";

const PASSPHRASE_ENV = "OPENCLAW_VAULT_PASSPHRASE";

let decryptedSoulContent: string | null = null;
let shmCleanupPath: string | null = null;
let shutdownHooksRegistered = false;

function deriveKey(passphrase: string, salt: Buffer): Buffer {
  return crypto.pbkdf2Sync(passphrase, salt, PBKDF2_ITERATIONS, KEY_LENGTH, PBKDF2_DIGEST);
}

export function encryptContent(plaintext: string, passphrase: string): Buffer {
  const salt = crypto.randomBytes(SALT_LENGTH);
  const iv = crypto.randomBytes(IV_LENGTH);
  const key = deriveKey(passphrase, salt);

  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  const encrypted = Buffer.concat([cipher.update(plaintext, "utf-8"), cipher.final()]);
  const tag = cipher.getAuthTag();

  return Buffer.concat([salt, iv, tag, encrypted]);
}

export function decryptContent(data: Buffer, passphrase: string): string {
  if (data.length < SALT_LENGTH + IV_LENGTH + TAG_LENGTH) {
    throw new Error("Invalid encrypted data: too short");
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

export function resolveVaultDir(env: NodeJS.ProcessEnv = process.env): string {
  return path.join(resolveStateDir(env), VAULT_DIRNAME);
}

export function resolveEncryptedSoulPath(env: NodeJS.ProcessEnv = process.env): string {
  return path.join(resolveVaultDir(env), ENCRYPTED_SOUL_FILENAME);
}

export function resolvePassphrase(env: NodeJS.ProcessEnv = process.env): string | undefined {
  const value = env[PASSPHRASE_ENV]?.trim();
  return value || undefined;
}

export async function encryptSoulFile(
  plaintextPath: string,
  passphrase: string,
  env: NodeJS.ProcessEnv = process.env,
): Promise<string> {
  const plaintext = await fsPromises.readFile(plaintextPath, "utf-8");
  const encrypted = encryptContent(plaintext, passphrase);

  const vaultDir = resolveVaultDir(env);
  await fsPromises.mkdir(vaultDir, { recursive: true });

  const encPath = resolveEncryptedSoulPath(env);
  await fsPromises.writeFile(encPath, encrypted);

  return encPath;
}

function resolveShmDir(): string | null {
  if (os.platform() !== "linux") {
    return null;
  }
  const shmBase = "/dev/shm";
  try {
    fs.accessSync(shmBase, fs.constants.W_OK);
    const dir = path.join(shmBase, `openclaw-soul-${process.pid}`);
    return dir;
  } catch {
    return null;
  }
}

function wipeAndDelete(filePath: string): void {
  try {
    const stat = fs.statSync(filePath);
    const zeros = Buffer.alloc(stat.size, 0);
    const fd = fs.openSync(filePath, "w");
    fs.writeSync(fd, zeros);
    fs.closeSync(fd);
    fs.unlinkSync(filePath);
  } catch {
    try {
      fs.unlinkSync(filePath);
    } catch {
      // best effort
    }
  }
}

function cleanupDecryptedFiles(): void {
  if (shmCleanupPath) {
    wipeAndDelete(shmCleanupPath);
    try {
      fs.rmdirSync(path.dirname(shmCleanupPath));
    } catch {
      // best effort
    }
    shmCleanupPath = null;
  }
  decryptedSoulContent = null;
}

function registerShutdownHooks(): void {
  if (shutdownHooksRegistered) {
    return;
  }
  shutdownHooksRegistered = true;

  const handler = () => {
    cleanupDecryptedFiles();
  };

  process.on("exit", handler);
  process.on("SIGINT", () => {
    handler();
    process.exit(130);
  });
  process.on("SIGTERM", () => {
    handler();
    process.exit(143);
  });
}

export async function decryptSoulToMemory(
  passphrase: string,
  env: NodeJS.ProcessEnv = process.env,
): Promise<string> {
  const encPath = resolveEncryptedSoulPath(env);
  const data = await fsPromises.readFile(encPath);
  const content = decryptContent(data, passphrase);

  decryptedSoulContent = content;

  const shmDir = resolveShmDir();
  if (shmDir) {
    try {
      await fsPromises.mkdir(shmDir, { recursive: true, mode: 0o700 });
      const shmPath = path.join(shmDir, "SOUL.md");
      await fsPromises.writeFile(shmPath, content, { encoding: "utf-8", mode: 0o600 });
      shmCleanupPath = shmPath;
    } catch {
      // fall back to in-memory only
    }
  }

  registerShutdownHooks();
  return content;
}

export function getDecryptedSoulContent(): string | null {
  return decryptedSoulContent;
}

export async function isVaultEncrypted(env: NodeJS.ProcessEnv = process.env): Promise<boolean> {
  try {
    await fsPromises.access(resolveEncryptedSoulPath(env));
    return true;
  } catch {
    return false;
  }
}

export async function loadSoulContent(params: {
  plaintextPath: string;
  env?: NodeJS.ProcessEnv;
}): Promise<{ content: string; source: "vault" | "plaintext" } | null> {
  const env = params.env ?? process.env;
  const passphrase = resolvePassphrase(env);

  if (passphrase && (await isVaultEncrypted(env))) {
    const cached = getDecryptedSoulContent();
    if (cached !== null) {
      return { content: cached, source: "vault" };
    }
    try {
      const content = await decryptSoulToMemory(passphrase, env);
      return { content, source: "vault" };
    } catch {
      return null;
    }
  }

  try {
    const content = await fsPromises.readFile(params.plaintextPath, "utf-8");

    if (passphrase) {
      try {
        await encryptSoulFile(params.plaintextPath, passphrase, env);
        try {
          const zeros = Buffer.alloc(Buffer.byteLength(content, "utf-8"), 0);
          await fsPromises.writeFile(params.plaintextPath, zeros);
          await fsPromises.unlink(params.plaintextPath);
        } catch {
          // plaintext deletion is best-effort
        }
      } catch {
        // encryption is best-effort on first run
      }
    }

    return { content, source: "plaintext" };
  } catch {
    return null;
  }
}

export { cleanupDecryptedFiles as wipeSoulVault };
