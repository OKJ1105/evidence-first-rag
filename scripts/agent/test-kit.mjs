// A minimal test kit over node:test and node:assert, exposing the subset of
// the vitest API these tests use. The orchestrator and its tests run on the
// Node standard library alone, so the loop needs no package installation
// before its own tests can run — in CI, in the checks manifest, or locally.

import { describe, it as nodeIt } from "node:test";
import assert from "node:assert/strict";

export { describe };

function interpolate(template, args, index) {
  let i = 0;
  return String(template).replace(/%[sdioj#%]/g, (m) => {
    if (m === "%%") return "%";
    if (m === "%#") return String(index);
    const v = args[i++];
    return m === "%j" || m === "%o" ? format(v) : String(v);
  });
}

export function it(name, fn) {
  return nodeIt(name, fn);
}

it.each = (table) => (name, fn) => {
  table.forEach((row, index) => {
    const args = Array.isArray(row) ? row : [row];
    nodeIt(interpolate(name, args, index), () => fn(...args));
  });
};

function subsetMatches(actual, expected) {
  if (
    typeof expected !== "object" ||
    expected === null ||
    typeof actual !== "object" ||
    actual === null
  ) {
    try {
      assert.deepStrictEqual(actual, expected);
      return true;
    } catch {
      return false;
    }
  }
  return Object.entries(expected).every(([k, v]) =>
    subsetMatches(actual[k], v),
  );
}

function matchers(actual, negate) {
  const check = (ok, message) => {
    if (Boolean(ok) === negate) {
      throw new assert.AssertionError({
        message: `${negate ? "not." : ""}${message}`,
        actual,
      });
    }
  };
  return {
    toBe(expected) {
      check(Object.is(actual, expected), `toBe(${format(expected)})`);
    },
    toEqual(expected) {
      let ok = true;
      try {
        assert.deepStrictEqual(actual, expected);
      } catch {
        ok = false;
      }
      check(ok, `toEqual(${format(expected)})`);
    },
    toMatchObject(expected) {
      check(subsetMatches(actual, expected), `toMatchObject(${format(expected)})`);
    },
    toContain(item) {
      check(
        typeof actual === "string"
          ? actual.includes(item)
          : Array.isArray(actual) && actual.includes(item),
        `toContain(${format(item)})`,
      );
    },
    toMatch(re) {
      const pattern = re instanceof RegExp ? re : new RegExp(escape(re));
      check(pattern.test(actual), `toMatch(${pattern})`);
    },
    toHaveLength(n) {
      check(actual?.length === n, `toHaveLength(${n})`);
    },
    toThrow(expected) {
      let threw = null;
      let raised = false;
      try {
        actual();
      } catch (err) {
        threw = err;
        raised = true;
      }
      let ok = raised;
      if (ok && expected !== undefined) {
        if (typeof expected === "function") {
          ok = threw instanceof expected;
        } else {
          const message = String(threw?.message ?? threw);
          ok =
            expected instanceof RegExp
              ? expected.test(message)
              : message.includes(String(expected));
        }
      }
      check(ok, `toThrow(${format(expected)})`);
    },
    toBeNull() {
      check(actual === null, "toBeNull()");
    },
    toBeUndefined() {
      check(actual === undefined, "toBeUndefined()");
    },
    toBeGreaterThan(n) {
      check(actual > n, `toBeGreaterThan(${n})`);
    },
    toBeLessThan(n) {
      check(actual < n, `toBeLessThan(${n})`);
    },
  };
}

function format(value) {
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return String(value);
  }
}

function escape(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function matchesThrown(threw, expected) {
  if (expected === undefined) return true;
  if (typeof expected === "function") return threw instanceof expected;
  const message = String(threw?.message ?? threw);
  return expected instanceof RegExp
    ? expected.test(message)
    : message.includes(String(expected));
}

export function expect(actual) {
  return {
    ...matchers(actual, false),
    not: matchers(actual, true),
    rejects: {
      async toThrow(expected) {
        let threw = null;
        let raised = false;
        try {
          await actual;
        } catch (err) {
          threw = err;
          raised = true;
        }
        if (!raised || !matchesThrown(threw, expected)) {
          throw new assert.AssertionError({
            message: `rejects.toThrow(${format(expected)}) — ${
              raised ? `threw ${format(String(threw?.message))}` : "the promise resolved"
            }`,
          });
        }
      },
    },
    resolves: {
      async toBeUndefined() {
        const value = await actual;
        if (value !== undefined) {
          throw new assert.AssertionError({
            message: `resolves.toBeUndefined() — resolved with ${format(value)}`,
          });
        }
      },
    },
  };
}
