#!/usr/bin/env node
/**
 * patch-soul-dev-workflow.mjs
 *
 * Appends the 7 app-development workflow principles to the encrypted SOUL.
 * Uses the same AES-256-GCM + PBKDF2-SHA512 algorithm as soul-vault.ts.
 *
 * Called by setup-dev-workflow.sh.  Safe to run multiple times — idempotent.
 *
 * Requirements:
 *   - OPENCLAW_VAULT_PASSPHRASE set in ~/.openclaw/.env (or environment)
 *   - ~/.openclaw/vault/SOUL.md.enc must exist
 *   - Node.js 18+ (uses built-in crypto — no extra packages needed)
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

// ── Constants (must match soul-vault.ts exactly) ──────────────────────────────
const ALGORITHM = "aes-256-gcm";
const KEY_LENGTH = 32;
const IV_LENGTH = 12;
const SALT_LENGTH = 16;
const TAG_LENGTH = 16;
const PBKDF2_ITERATIONS = 100_000;
const PBKDF2_DIGEST = "sha512";

// ── Principles block to append ────────────────────────────────────────────────
const PRINCIPLES_MARKER = "## App Development Workflow";
const PRINCIPLES_BLOCK = `
## App Development Workflow

Default workflow for any app or product work:
  Plan → Init → Build → Self-test → Preview → Tom QA → Deploy

Principles:

1. Never start substantial coding before scope is written down and agreed.
   Always produce a spec (specs/<project-name>.md) before implementation begins.

2. Planning and repo creation are separate acts.
   app-plan writes the spec only. app-init creates the repo — only after spec approved.

3. Always self-test before handoff.
   Lint, typecheck, build, and test must all pass before a preview is presented.

4. Always return a preview URL before suggesting a deploy.
   Handoff must include: URL, what changed, what was tested, what Tom should check,
   and what is intentionally not done yet.

5. Deploy only after Tom explicitly approves.
   "It looks good" is not approval. A clear "deploy it" or "ship it" is required.

6. GitHub is the source of truth for all app projects.
   Telegram is the control surface. OpenClaw is the orchestrator. Vercel is the deploy target.

7. Work in scope. Build only what the current phase defines.
   Note anything out of scope for the next phase — do not build it now.
`;

// ── Helpers ───────────────────────────────────────────────────────────────────

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  const lines = fs.readFileSync(filePath, "utf-8").split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const eqIdx = trimmed.indexOf("=");
    const key = trimmed.slice(0, eqIdx).trim();
    let value = trimmed.slice(eqIdx + 1).trim();
    value = value.replace(/^["']|["']$/g, "");
    if (key && !(key in process.env)) {
      process.env[key] = value;
    }
  }
}

function deriveKey(passphrase, salt) {
  return crypto.pbkdf2Sync(passphrase, salt, PBKDF2_ITERATIONS, KEY_LENGTH, PBKDF2_DIGEST);
}

function decrypt(data, passphrase) {
  const salt = data.subarray(0, SALT_LENGTH);
  const iv = data.subarray(SALT_LENGTH, SALT_LENGTH + IV_LENGTH);
  const tag = data.subarray(SALT_LENGTH + IV_LENGTH, SALT_LENGTH + IV_LENGTH + TAG_LENGTH);
  const encrypted = data.subarray(SALT_LENGTH + IV_LENGTH + TAG_LENGTH);

  const key = deriveKey(passphrase, salt);
  const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
  decipher.setAuthTag(tag);

  return Buffer.concat([decipher.update(encrypted), decipher.final()]).toString("utf-8");
}

function encrypt(plaintext, passphrase) {
  const salt = crypto.randomBytes(SALT_LENGTH);
  const iv = crypto.randomBytes(IV_LENGTH);
  const key = deriveKey(passphrase, salt);

  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  const encrypted = Buffer.concat([cipher.update(plaintext, "utf-8"), cipher.final()]);
  const tag = cipher.getAuthTag();

  return Buffer.concat([salt, iv, tag, encrypted]);
}

function fail(msg) {
  console.error(`\nERROR: ${msg}`);
  process.exit(1);
}

// ── Main ──────────────────────────────────────────────────────────────────────

const homeDir = os.homedir();
const envFile = path.join(homeDir, ".openclaw", ".env");
loadEnvFile(envFile);

const passphrase = (process.env.OPENCLAW_VAULT_PASSPHRASE || "").trim();
if (!passphrase) {
  fail(
    "OPENCLAW_VAULT_PASSPHRASE not set.\n" +
    "  Check ~/.openclaw/.env contains: OPENCLAW_VAULT_PASSPHRASE=<your-passphrase>"
  );
}

const stateDir = process.env.OPENCLAW_STATE_DIR?.trim() || path.join(homeDir, ".openclaw");
const vaultPath = path.join(stateDir, "vault", "SOUL.md.enc");

if (!fs.existsSync(vaultPath)) {
  fail(
    `Encrypted SOUL not found at: ${vaultPath}\n` +
    "  Ensure OpenClaw has been set up and the SOUL has been encrypted at least once."
  );
}

console.log(`Reading encrypted SOUL from: ${vaultPath}`);
const encrypted = fs.readFileSync(vaultPath);

let plaintext;
try {
  plaintext = decrypt(encrypted, passphrase);
} catch (e) {
  fail(
    `Failed to decrypt SOUL: ${e.message}\n` +
    "  This usually means the passphrase is wrong. Check OPENCLAW_VAULT_PASSPHRASE."
  );
}

console.log(`Decrypted successfully (${plaintext.length} chars).`);

// Idempotency check — do not append if already present
if (plaintext.includes(PRINCIPLES_MARKER)) {
  console.log("Dev workflow principles already present in SOUL — nothing to do.");
  process.exit(0);
}

// Append principles
const updated = plaintext.trimEnd() + "\n" + PRINCIPLES_BLOCK;
console.log("Appending dev workflow principles...");

// Re-encrypt and write back atomically via temp file
const newEncrypted = encrypt(updated, passphrase);
const tmpPath = vaultPath + ".tmp";
fs.writeFileSync(tmpPath, newEncrypted, { mode: 0o600 });
fs.renameSync(tmpPath, vaultPath);

console.log(`SOUL updated and re-encrypted at: ${vaultPath}`);
console.log("Done.");
