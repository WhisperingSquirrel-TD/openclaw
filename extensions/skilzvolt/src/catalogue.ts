import { createHash } from "node:crypto";
import { SkilzVoltError } from "./client.js";
import type { SkilzVoltClient } from "./client.js";
import {
  createSkillReceipt,
  parseWorkflowContract,
  type SkillReceipt,
  type WorkflowContract,
} from "./governance.js";

/**
 * Private routing metadata for one catalogue entry. Never shown to the model - only the compact
 * `- name: description [SkilzVolt]` line is. The model reaches full content later via the
 * existing generic skilzvolt tool (skills_search/skills_get), keyed by name.
 */
export type SkilzVoltCatalogueEntry = {
  skillId: string;
  workspaceId: string;
  workspaceName?: string;
  name: string;
  description: string;
  updatedAt?: string;
  currentVersionId?: string;
};

type CatalogueSnapshot =
  | {
      ok: true;
      revision?: string;
      entries: SkilzVoltCatalogueEntry[];
      lines: string[];
      fetchedAt: number;
      // Server-declared freshness window (confirmed field, 2026-08-26: top-level
      // `snapshot_expires_at`, "when applicable"). Absent when SkilzVolt doesn't send one.
      expiresAt?: number;
    }
  | { ok: false; reason: string; fetchedAt: number };

export type SkilzVoltCatalogueResult =
  | { ok: true; lines: string[] }
  | { ok: false; reason: string };

export type SkilzVoltLiveSkill = {
  entry: SkilzVoltCatalogueEntry;
  content: string;
  receipt: SkillReceipt;
  workflow: WorkflowContract;
};

// SkilzVolt's own catalogue may be large; this bounds pagination in case of a cursor loop bug on
// either side rather than hanging bootstrap indefinitely.
const MAX_PAGES = 50;
// Fallback re-fetch interval when SkilzVolt doesn't declare a snapshot_expires_at: re-fetch
// periodically rather than on every prompt build, but never serve data past this age as current
// without at least attempting a revision check. A server-declared expiry (see `expiresAt` above)
// always takes precedence over this fixed guess when present.
const CACHE_TTL_MS = 5 * 60 * 1000;

/** Parses a server-declared expiry timestamp; invalid/absent values fall back to the fixed TTL. */
function parseExpiresAt(raw: string | undefined): number | undefined {
  if (!raw) return undefined;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? undefined : ms;
}

function isSnapshotFresh(snapshot: CatalogueSnapshot): boolean {
  if (snapshot.ok && typeof snapshot.expiresAt === "number") {
    return Date.now() < snapshot.expiresAt;
  }
  return Date.now() - snapshot.fetchedAt < CACHE_TTL_MS;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function readString(
  value: Record<string, unknown> | undefined,
  keys: readonly string[],
): string | undefined {
  if (!value) return undefined;
  for (const key of keys) {
    const candidate = value[key];
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate;
    }
  }
  return undefined;
}

function readTextResult(value: unknown): Record<string, unknown> {
  const record = asRecord(value);
  if (!record) {
    throw new SkilzVoltError("SkilzVolt skill response was not a JSON object", "contract_drift");
  }
  const data = asRecord(record.data) ?? record;
  if (data.isError === true) {
    throw new SkilzVoltError("SkilzVolt reported an error reading the live skill", "protocol");
  }
  return asRecord(data.skill) ?? data;
}

function readSkillContent(record: Record<string, unknown>): string | undefined {
  const direct = readString(record, ["content", "markdown", "body", "text"]);
  if (direct) return direct;
  const chunks = record.chunks ?? record.content_chunks ?? record.contentChunks;
  if (Array.isArray(chunks)) {
    const texts = chunks
      .map((chunk) => {
        if (typeof chunk === "string") return chunk;
        const item = asRecord(chunk);
        return item ? readString(item, ["content", "markdown", "body", "text"]) : undefined;
      })
      .filter((chunk): chunk is string => Boolean(chunk));
    if (texts.length > 0) return texts.join("");
  }
  return undefined;
}

function readOptionalString(
  value: Record<string, unknown>,
  keys: readonly string[],
): string | undefined {
  for (const key of keys) {
    if (typeof value[key] === "string") return value[key] as string;
  }
  return undefined;
}

function readRequiredNumber(value: Record<string, unknown>, key: string): number {
  const number = value[key];
  if (typeof number !== "number" || !Number.isFinite(number) || number < 0) {
    throw new SkilzVoltError(`SkilzVolt response is missing valid ${key}`, "contract_drift");
  }
  return number;
}

function parseEntry(raw: unknown): SkilzVoltCatalogueEntry {
  const record = asRecord(raw);
  if (!record) {
    throw new SkilzVoltError("SkilzVolt catalogue entry was not a JSON object", "contract_drift");
  }
  // Confirmed live contract (2026-08-26): SkilzVolt puts workspace context in flat
  // home_workspace_id/home_workspace_name/home_workspace_slug fields on the entry itself, not a
  // nested `workspace` object. Keep the nested-object shape as a fallback (it's what our
  // original, unverified assumption and existing tests used) so a future schema change back
  // toward it doesn't require another emergency fix, without weakening the check below.
  const workspace = asRecord(record.workspace);
  const skillId = readString(record, ["skill_id", "skillId", "id"]);
  const name = readString(record, ["name"]);
  const workspaceId =
    readString(record, ["home_workspace_id", "homeWorkspaceId"]) ??
    readString(workspace, ["workspace_id", "workspaceId", "id"]);
  if (!skillId || !name || !workspaceId) {
    throw new SkilzVoltError(
      "SkilzVolt catalogue entry is missing a canonical skill_id, name, or workspace_id",
      "contract_drift",
    );
  }
  const workspaceName =
    readString(record, ["home_workspace_name", "homeWorkspaceName"]) ??
    readString(record, ["home_workspace_slug", "homeWorkspaceSlug"]) ??
    readString(workspace, ["name", "slug"]);
  // `source` (confirmed field, always "skilzvolt" today) is deliberately not read or validated:
  // this parser only ever runs on responses from the skilzvolt_catalogue tool call, so the field
  // carries no decision this code needs to make. Revisit if SkilzVolt ever multiplexes other
  // sources through the same tool.
  return {
    skillId,
    workspaceId,
    workspaceName,
    name,
    description: readString(record, ["description"]) ?? "",
    updatedAt: readString(record, ["updated_at", "updatedAt"]),
    currentVersionId: readString(record, ["current_version_id", "currentVersionId"]),
  };
}

function toCompactLine(entry: SkilzVoltCatalogueEntry): string {
  const description = entry.description.replace(/\s+/g, " ").trim();
  // Intentionally not deduplicated by name: duplicate names across different workspaces are
  // genuinely distinct skills, and the model disambiguates later via skills_search/skills_get.
  return `- ${entry.name}: ${description} [SkilzVolt]`;
}

/**
 * Bootstraps and caches the live SkilzVolt skill catalogue for prompt injection. On any
 * network/protocol/schema failure this reports an explicit degraded state rather than silently
 * falling back to a stale or locally-guessed catalogue.
 */
export class SkilzVoltCatalogue {
  private snapshot?: CatalogueSnapshot;

  constructor(private readonly client: SkilzVoltClient) {}

  async getLines(signal?: AbortSignal): Promise<SkilzVoltCatalogueResult> {
    const isFresh = this.snapshot ? isSnapshotFresh(this.snapshot) : false;
    if (!isFresh) {
      await this.refresh(signal);
    }
    if (!this.snapshot) {
      return { ok: false, reason: "SkilzVolt catalogue has not been fetched yet" };
    }
    return this.snapshot.ok
      ? { ok: true, lines: this.snapshot.lines }
      : { ok: false, reason: this.snapshot.reason };
  }

  /** Internal-only routing lookup by skill_id. Never exposed to the model directly. */
  findRouting(skillId: string): SkilzVoltCatalogueEntry | undefined {
    return this.snapshot?.ok
      ? this.snapshot.entries.find((entry) => entry.skillId === skillId)
      : undefined;
  }

  /** Internal-only routing metadata for the runtime intent router. */
  getEntries(): SkilzVoltCatalogueEntry[] {
    return this.snapshot?.ok ? [...this.snapshot.entries] : [];
  }

  async readCurrentSkill(
    entry: SkilzVoltCatalogueEntry,
    purpose: string,
    signal?: AbortSignal,
  ): Promise<SkilzVoltLiveSkill> {
    if (!entry.currentVersionId) {
      throw new SkilzVoltError(
        `SkilzVolt skill ${entry.name} has no current version`,
        "contract_drift",
      );
    }
    let startChar: number | undefined;
    let versionId: string | undefined = entry.currentVersionId;
    let content = "";
    let totalChars: number | undefined;
    let totalBytes: number | undefined;
    let serverHash: string | undefined;
    let resources: unknown[] = [];
    let completed = false;
    for (let page = 0; page < 1000; page += 1) {
      const args: Record<string, unknown> = {
        skill_id: entry.skillId,
        max_chars: 12000,
        include_metadata: true,
        include_resources: true,
      };
      args.version_id = versionId;
      if (startChar !== undefined) args.start_char = startChar;
      const skill = readTextResult(await this.client.callTool("skills_get", args, signal));
      const skillId = readString(skill, ["skill_id"]);
      if (!skillId || skillId !== entry.skillId) {
        throw new SkilzVoltError(
          "SkilzVolt current skill identity does not match the catalogue",
          "contract_drift",
        );
      }
      if (page === 0 && skill.version_is_current !== true) {
        throw new SkilzVoltError("SkilzVolt skill version is not current", "contract_drift");
      }
      const responseVersion = readOptionalString(skill, ["version_id"]);
      if (!responseVersion || (versionId && responseVersion !== versionId)) {
        throw new SkilzVoltError(
          "SkilzVolt response changed version during chunked read",
          "contract_drift",
        );
      }
      versionId ??= responseVersion;
      if (versionId !== entry.currentVersionId) {
        throw new SkilzVoltError(
          "SkilzVolt current skill version does not match the catalogue",
          "contract_drift",
        );
      }
      if (page === 0) {
        totalChars = readRequiredNumber(skill, "total_content_chars");
        totalBytes = readRequiredNumber(skill, "total_content_bytes");
        serverHash = readOptionalString(skill, ["content_hash", "content_sha256"]);
        if (!serverHash) {
          throw new SkilzVoltError(
            "SkilzVolt response lacks whole-version content hash",
            "contract_drift",
          );
        }
        resources = Array.isArray(skill.resources) ? skill.resources : [];
      }
      const chunkRecord = asRecord(skill.chunk);
      if (!chunkRecord) {
        throw new SkilzVoltError(
          "SkilzVolt response lacks nested chunk metadata",
          "contract_drift",
        );
      }
      const expectedStart = startChar ?? 0;
      const chunkStart = chunkRecord.start_char;
      const chunkEnd = chunkRecord.end_char;
      if (
        typeof chunkStart !== "number" ||
        typeof chunkEnd !== "number" ||
        chunkStart !== expectedStart ||
        chunkEnd < chunkStart
      ) {
        throw new SkilzVoltError("SkilzVolt chunk offsets are invalid", "contract_drift");
      }
      const chunk = readOptionalString(skill, ["content"]) ?? "";
      const chunkChars = Array.from(chunk).length;
      if (chunkEnd - chunkStart !== chunkChars) {
        throw new SkilzVoltError("SkilzVolt chunk character count is invalid", "contract_drift");
      }
      if (
        chunkRecord.content_utf8_bytes !== undefined &&
        (typeof chunkRecord.content_utf8_bytes !== "number" ||
          chunkRecord.content_utf8_bytes !== Buffer.byteLength(chunk, "utf8"))
      ) {
        throw new SkilzVoltError("SkilzVolt chunk UTF-8 byte count is invalid", "contract_drift");
      }
      content += chunk;
      const next = chunkRecord.next_start_char;
      const complete = chunkRecord.complete === true;
      if (complete) {
        completed = true;
        break;
      }
      if (typeof next !== "number" || next <= (startChar ?? 0)) {
        throw new SkilzVoltError(
          "SkilzVolt skill read did not provide a valid next_start_char",
          "contract_drift",
        );
      }
      startChar = next;
    }
    if (
      !completed ||
      !versionId ||
      totalChars === undefined ||
      totalBytes === undefined ||
      !serverHash
    ) {
      throw new SkilzVoltError(
        "SkilzVolt skill read lacks whole-version integrity metadata",
        "contract_drift",
      );
    }
    if (
      Array.from(content).length !== totalChars ||
      Buffer.byteLength(content, "utf8") !== totalBytes
    ) {
      throw new SkilzVoltError(
        "SkilzVolt skill content length does not match integrity metadata",
        "contract_drift",
      );
    }
    const computedHash = createHash("sha256").update(content, "utf8").digest("hex");
    if (computedHash !== serverHash.toLowerCase()) {
      throw new SkilzVoltError("SkilzVolt skill content hash mismatch", "contract_drift");
    }
    let workflow: WorkflowContract;
    let workflowSource: "skill-body" | "resource" = "skill-body";
    let workflowResourceId: string | undefined;
    let workflowSha256: string | undefined = computedHash;
    try {
      workflow = parseWorkflowContract(content);
    } catch (error) {
      let resourceText: string | undefined;
      for (const resource of resources) {
        const record = asRecord(resource);
        const resourceId = record ? readOptionalString(record, ["resource_id"]) : undefined;
        if (!resourceId) continue;
        const authoritativeHash = record
          ? readOptionalString(record, ["content_sha256"])
          : undefined;
        const authoritativeSize =
          record && typeof record.content_length === "number" ? record.content_length : undefined;
        if (
          !authoritativeHash ||
          !/^[a-f0-9]{64}$/i.test(authoritativeHash) ||
          authoritativeSize === undefined
        ) {
          throw new SkilzVoltError(
            "SkilzVolt workflow resource reference is missing authoritative hash or size",
            "contract_drift",
          );
        }
        const fetched = readTextResult(
          await this.client.callTool("skills_get_resource", { resource_id: resourceId }, signal),
        );
        const fetchedRecord = asRecord(fetched);
        const mismatch = (keys: string[], expected: string) =>
          keys.some((key) => {
            const value = fetchedRecord ? readOptionalString(fetchedRecord, [key]) : undefined;
            return value !== undefined && value !== expected;
          });
        if (
          mismatch(["resource_id"], resourceId) ||
          mismatch(["skill_id"], entry.skillId) ||
          mismatch(["version_id"], entry.currentVersionId ?? "")
        ) {
          throw new SkilzVoltError(
            "SkilzVolt workflow resource identity mismatch",
            "contract_drift",
          );
        }
        const text = readOptionalString(fetched, ["content", "markdown", "body", "text"]);
        if (text) {
          const responseHash = readOptionalString(fetched, ["content_sha256"]);
          const responseSize =
            fetchedRecord && typeof fetchedRecord.content_length === "number"
              ? fetchedRecord.content_length
              : undefined;
          const computedResourceHash = createHash("sha256").update(text, "utf8").digest("hex");
          if (
            !responseHash ||
            !/^[a-f0-9]{64}$/i.test(responseHash) ||
            responseSize === undefined ||
            responseHash.toLowerCase() !== authoritativeHash.toLowerCase() ||
            responseSize !== authoritativeSize ||
            computedResourceHash !== authoritativeHash.toLowerCase() ||
            Buffer.byteLength(text, "utf8") !== authoritativeSize
          ) {
            throw new SkilzVoltError(
              "SkilzVolt workflow resource integrity mismatch",
              "contract_drift",
            );
          }
          resourceText = text;
          workflowSource = "resource";
          workflowResourceId = resourceId;
          workflowSha256 = computedResourceHash;
          break;
        }
        const structured =
          (Array.isArray(fetched.requirements) ? fetched : undefined) ??
          asRecord(fetched.data) ??
          asRecord(fetched.workflow) ??
          asRecord(fetched.manifest);
        if (structured) {
          resourceText = JSON.stringify(structured);
          const responseHash = readOptionalString(fetched, ["content_sha256"]);
          const responseSize =
            fetchedRecord && typeof fetchedRecord.content_length === "number"
              ? fetchedRecord.content_length
              : undefined;
          const computedResourceHash = createHash("sha256")
            .update(resourceText, "utf8")
            .digest("hex");
          if (
            !responseHash ||
            responseSize === undefined ||
            responseHash.toLowerCase() !== authoritativeHash.toLowerCase() ||
            responseSize !== authoritativeSize ||
            computedResourceHash !== authoritativeHash.toLowerCase() ||
            Buffer.byteLength(resourceText, "utf8") !== authoritativeSize
          ) {
            throw new SkilzVoltError(
              "SkilzVolt workflow resource integrity mismatch",
              "contract_drift",
            );
          }
          workflowSource = "resource";
          workflowResourceId = resourceId;
          workflowSha256 = computedResourceHash;
          break;
        }
      }
      if (!resourceText) throw error;
      workflow = parseWorkflowContract(resourceText);
    }
    const receipt = createSkillReceipt({
      entry,
      content,
      purpose,
      workflowSource,
      resourceId: workflowResourceId,
      workflowSha256,
    });
    return { entry, content, receipt, workflow };
  }

  async refresh(signal?: AbortSignal): Promise<void> {
    const knownRevision = this.snapshot?.ok ? this.snapshot.revision : undefined;
    try {
      const entries: SkilzVoltCatalogueEntry[] = [];
      let cursor: string | undefined;
      let revision: string | undefined;
      let expiresAtRaw: string | undefined;
      let unchanged = false;
      for (let page = 0; page < MAX_PAGES; page += 1) {
        const args: Record<string, unknown> = {};
        if (cursor) {
          args.cursor = cursor;
        } else if (knownRevision) {
          args.known_revision = knownRevision;
        }
        const raw = await this.client.callTool("skills_catalogue", args, signal);
        const result = asRecord(raw);
        if (result?.isError === true) {
          throw new SkilzVoltError(
            "SkilzVolt reported an error fetching the skill catalogue",
            "protocol",
          );
        }
        const data = asRecord(result?.data) ?? result;
        if (!data) {
          throw new SkilzVoltError(
            "SkilzVolt catalogue response was not a JSON object",
            "contract_drift",
          );
        }
        revision = readString(data, ["revision", "catalogue_revision"]) ?? revision;
        expiresAtRaw =
          readString(data, ["snapshot_expires_at", "snapshotExpiresAt"]) ?? expiresAtRaw;
        if (page === 0 && data.unchanged === true) {
          unchanged = true;
          break;
        }
        const skills = data.skills;
        if (!Array.isArray(skills)) {
          throw new SkilzVoltError(
            "SkilzVolt catalogue response is missing a skills array",
            "contract_drift",
          );
        }
        for (const skill of skills) {
          entries.push(parseEntry(skill));
        }
        const nextCursor = readString(data, ["next_cursor", "nextCursor"]);
        if (!nextCursor) {
          cursor = undefined;
          break;
        }
        cursor = nextCursor;
      }

      // If the loop exhausted MAX_PAGES while a next_cursor was still pending, the catalogue is
      // larger than we bounded for. Reporting the partial list as the live catalogue would be
      // silently wrong, so this is treated as an explicit failure instead.
      if (cursor) {
        throw new SkilzVoltError(
          `SkilzVolt skill catalogue exceeded ${MAX_PAGES} pages without finishing; refusing to serve a partial catalogue as current`,
          "contract_drift",
        );
      }

      if (unchanged) {
        if (!this.snapshot?.ok) {
          throw new SkilzVoltError(
            "SkilzVolt reported the catalogue as unchanged, but no prior catalogue is cached",
            "contract_drift",
          );
        }
        this.snapshot = {
          ...this.snapshot,
          fetchedAt: Date.now(),
          expiresAt: parseExpiresAt(expiresAtRaw) ?? this.snapshot.expiresAt,
        };
        return;
      }

      this.snapshot = {
        ok: true,
        revision,
        entries,
        lines: entries.map(toCompactLine),
        fetchedAt: Date.now(),
        expiresAt: parseExpiresAt(expiresAtRaw),
      };
    } catch (error) {
      this.snapshot = {
        ok: false,
        reason:
          error instanceof SkilzVoltError
            ? error.message
            : "Failed to fetch the SkilzVolt skill catalogue",
        fetchedAt: Date.now(),
      };
    }
  }
}
