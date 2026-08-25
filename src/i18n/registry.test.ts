import { describe, expect, it } from "vitest";

Object.defineProperty(globalThis, "localStorage", {
  value: {
    getItem: () => "en",
    setItem: () => undefined,
  },
  configurable: true,
});


const { SUPPORTED_LOCALES, isSupportedLocale } = await import("../../ui/src/i18n/lib/translate.ts");

describe("ui i18n locale registry", () => {
  it("lists the current supported locales", () => {
    expect(SUPPORTED_LOCALES).toEqual(["en", "zh-CN", "zh-TW", "pt-BR"]);
  });

  it("recognizes supported locales without accepting unsupported browser locales", () => {
    expect(isSupportedLocale("zh-CN")).toBe(true);
    expect(isSupportedLocale("pt-BR")).toBe(true);
    expect(isSupportedLocale("de-DE")).toBe(false);
    expect(isSupportedLocale(null)).toBe(false);
  });
});