const governedRuns = new Map<string, { skillName: string }>();

export function registerGovernedRun(runId: string, skillName: string): void {
  governedRuns.set(runId, { skillName });
}

export function getGovernedRun(runId: string): { skillName: string } | undefined {
  const entry = governedRuns.get(runId);
  if (!entry) {
    return undefined;
  }
  return { skillName: entry.skillName };
}

export function clearGovernedRun(runId: string): void {
  governedRuns.delete(runId);
}
