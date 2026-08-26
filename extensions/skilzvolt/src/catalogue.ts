import { SkilzVoltError } from "./client.js";
import type { SkilzVoltClient } from "./client.js";

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
    }
  | { ok: false; reason: string; fetchedAt: number };

export type SkilzVoltCatalogueResult =
  | { ok: true; lines: string[] }
  | { ok: false; reason: string };

// SkilzVolt's own catalogue may be large; this bounds pagination in case of a cursor loop bug on
// either side rather than hanging bootstrap indefinitely.
const MAX_PAGES = 50;
// Re-fetch periodically rather than on every prompt build, but never serve data past this age as
// current without at least attempting a revision check.
const CACHE_TTL_MS = 5 * 60 * 1000;

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

function parseEntry(raw: unknown): SkilzVoltCatalogueEntry {
  const record = asRecord(raw);
  if (!record) {
    throw new SkilzVoltError("SkilzVolt catalogue entry was not a JSON object", "contract_drift");
  }
  const workspace = asRecord(record.workspace);
  const skillId = readString(record, ["skill_id", "skillId", "id"]);
  const name = readString(record, ["name"]);
  const workspaceId = readString(workspace, ["workspace_id", "workspaceId", "id"]);
  if (!skillId || !name || !workspaceId) {
    throw new SkilzVoltError(
      "SkilzVolt catalogue entry is missing a canonical skill_id, name, or workspace_id",
      "contract_drift",
    );
  }
  return {
    skillId,
    workspaceId,
    workspaceName: readString(workspace, ["name", "slug"]),
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
    const isFresh = this.snapshot && Date.now() - this.snapshot.fetchedAt < CACHE_TTL_MS;
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

  async refresh(signal?: AbortSignal): Promise<void> {
    const knownRevision = this.snapshot?.ok ? this.snapshot.revision : undefined;
    try {
      const entries: SkilzVoltCatalogueEntry[] = [];
      let cursor: string | undefined;
      let revision: string | undefined;
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
        this.snapshot = { ...this.snapshot, fetchedAt: Date.now() };
        return;
      }

      this.snapshot = {
        ok: true,
        revision,
        entries,
        lines: entries.map(toCompactLine),
        fetchedAt: Date.now(),
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
