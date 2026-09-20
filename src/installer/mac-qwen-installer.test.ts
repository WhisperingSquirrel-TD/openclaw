import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const installer = fs.readFileSync(
  path.resolve(process.cwd(), "attached_assets/install-forked-openclaw.sh"),
  "utf8",
);

describe("Mac Mini Qwen installer gate", () => {
  it("writes the exact provider contract and timeout without selecting it immediately", () => {
    expect(installer).toContain("providers_cfg['custom-mac-ollama'] = {");
    expect(installer).toContain("'baseUrl': 'http://192.168.86.46:11434/v1'");
    expect(installer).toContain("'apiKey': 'ollama-local'");
    expect(installer).toContain("'api': 'openai-completions'");
    expect(installer).toContain("'timeoutSeconds': 1800");
    expect(installer).toContain("'id': 'qwen3-coder-131k'");
    expect(installer).toContain("'reasoning': False");
    expect(installer).toContain("'input': ['text']");
    expect(installer).toContain("'contextWindow': 16384");
    expect(installer).toContain("'maxTokens': 2048");
    expect(installer).toContain("provider_timeouts['custom-mac-ollama'] = 1800");

    const providerConfig = installer.indexOf("providers_cfg['custom-mac-ollama'] = {");
    const defaultActivation = installer.indexOf('info "Default model activated:');
    expect(providerConfig).toBeGreaterThanOrEqual(0);
    expect(defaultActivation).toBeGreaterThan(providerConfig);
    expect(installer.slice(0, defaultActivation)).toContain(
      "default unchanged pending verification",
    );
  });

  it("requires all remote checks and the exact sentinel before activation", () => {
    const tagsCheck = installer.indexOf("/api/tags");
    const modelsCheck = installer.indexOf("/v1/models");
    const sentinelCheck = installer.indexOf("QWEN-LOCAL-OK");
    const activation = installer.indexOf('info "Default model activated:');

    expect(tagsCheck).toBeGreaterThanOrEqual(0);
    expect(modelsCheck).toBeGreaterThan(tagsCheck);
    expect(sentinelCheck).toBeGreaterThan(modelsCheck);
    expect(activation).toBeGreaterThan(sentinelCheck);
    expect(installer.slice(modelsCheck, activation)).toContain("OPENCLAW_CONFIG_PATH=");
    expect(installer.slice(modelsCheck, activation)).toContain(
      'OPENCLAW_STATE_DIR="$PRIMARY_STATE_DIR"',
    );
    expect(installer.slice(modelsCheck, activation)).toContain("--timeout 1800");
    expect(installer.slice(modelsCheck, activation)).toContain("stderr=${MAC_QWEN_PROBE_DETAIL}");
  });

  it("cannot fall back to the retired or unmanaged L1 launchers", () => {
    expect(installer).not.toContain("l1-start.sh");
    expect(installer).not.toContain("l1-stop.sh");
    expect(installer).not.toContain("19789");
    expect(installer).toContain('PRIMARY_GATEWAY_SERVICE="openclaw-gateway.service"');
    expect(installer).toContain('systemctl --user restart "$PRIMARY_GATEWAY_SERVICE"');
  });
});
