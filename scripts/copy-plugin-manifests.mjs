#!/usr/bin/env node
/**
 * Copies openclaw.plugin.json manifests from extensions/* into dist/extensions/*.
 * tsdown compiles extension JS but does not copy static JSON assets — this
 * script fills that gap so the plugin loader can find manifests at runtime.
 */

import { copyFileSync, mkdirSync, readdirSync, existsSync } from "node:fs";
import { resolve, join } from "node:path";

const extensionsDir = resolve("extensions");
const distExtensionsDir = resolve("dist/extensions");

for (const dirent of readdirSync(extensionsDir, { withFileTypes: true })) {
  if (!dirent.isDirectory()) continue;

  const manifest = join(extensionsDir, dirent.name, "openclaw.plugin.json");
  if (!existsSync(manifest)) continue;

  const destDir = join(distExtensionsDir, dirent.name);
  const dest = join(destDir, "openclaw.plugin.json");

  mkdirSync(destDir, { recursive: true });
  copyFileSync(manifest, dest);
  console.log(`copied: extensions/${dirent.name}/openclaw.plugin.json → dist/extensions/${dirent.name}/`);
}
