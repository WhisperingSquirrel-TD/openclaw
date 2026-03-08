"use strict";

function emptyPluginConfigSchema() {
  return {
    safeParse(value) {
      if (value === undefined) {
        return { success: true, data: undefined };
      }
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        return {
          success: false,
          error: { issues: [{ path: [], message: "expected config object" }] },
        };
      }
      if (Object.keys(value).length > 0) {
        return {
          success: false,
          error: { issues: [{ path: [], message: "config must be empty" }] },
        };
      }
      return { success: true, data: value };
    },
    jsonSchema: {
      type: "object",
      additionalProperties: false,
      properties: {},
    },
  };
}

let _mod;

function getModule() {
  if (!_mod) {
    try {
      _mod = require("./index.js");
    } catch {
      _mod = require("./index.ts");
    }
  }
  return _mod;
}

const proxy = new Proxy(
  {},
  {
    get(_target, prop) {
      if (prop === "__esModule") return true;
      if (prop === "default") return proxy;
      if (prop === "emptyPluginConfigSchema") return emptyPluginConfigSchema;
      return getModule()[prop];
    },
    has(_target, prop) {
      if (prop === "__esModule" || prop === "default" || prop === "emptyPluginConfigSchema")
        return true;
      return prop in getModule();
    },
    ownKeys() {
      const keys = new Set(Object.keys(getModule()));
      keys.add("emptyPluginConfigSchema");
      keys.add("__esModule");
      keys.add("default");
      return [...keys];
    },
    getOwnPropertyDescriptor(_target, prop) {
      if (prop === "__esModule")
        return { configurable: true, enumerable: false, value: true, writable: false };
      if (prop === "default")
        return { configurable: true, enumerable: true, value: proxy, writable: false };
      if (prop === "emptyPluginConfigSchema")
        return {
          configurable: true,
          enumerable: true,
          value: emptyPluginConfigSchema,
          writable: false,
        };
      const mod = getModule();
      if (prop in mod)
        return { configurable: true, enumerable: true, value: mod[prop], writable: false };
      return undefined;
    },
  },
);

module.exports = proxy;
