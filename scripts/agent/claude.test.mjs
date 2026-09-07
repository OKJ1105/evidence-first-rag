import { describe, expect, it } from "./test-kit.mjs";
import {
  AgentError,
  runAgent,
  TOOLS,
  deniedTools,
  detail,
  extractJson,
  parseAgentOutput,
} from "./claude.mjs";

describe("the tool sets", () => {
  it("gives the Reviewer no way to edit — property 4 by construction", () => {
    expect(TOOLS.reviewer).not.toContain("Edit");
    expect(TOOLS.reviewer).not.toContain("Write");
  });

  it("gives neither role Bash", () => {
    expect(TOOLS.writer).not.toContain("Bash");
    expect(TOOLS.reviewer).not.toContain("Bash");
  });

  it("denies the escape hatches outright, not only by omission", () => {
    // The allowlist alone is not enough: a branch-supplied settings file could
    // otherwise restore them (BF4).
    for (const tool of ["Bash", "WebFetch", "WebSearch", "Task"]) {
      expect(deniedTools).toContain(tool);
    }
  });
});

describe("extractJson", () => {
  it("pulls an object out of surrounding prose", () => {
    expect(extractJson('here you go:\n{"a":1}\nhope that helps')).toBe(
      '{"a":1}',
    );
  });

  it("pulls one out of a fenced block", () => {
    expect(extractJson('```json\n{"a":[1,2]}\n```')).toBe('{"a":[1,2]}');
  });

  it("is not fooled by a brace inside a string", () => {
    expect(extractJson('{"a":"}"}')).toBe('{"a":"}"}');
  });

  it("throws rather than returning nothing when there is no object", () => {
    expect(() => extractJson("no json here")).toThrow(AgentError);
  });

  it("throws on an unclosed object rather than guessing", () => {
    expect(() => extractJson('{"a":1')).toThrow(AgentError);
  });

  // A Reviewer quotes the code it is reviewing. Taking the first fence in the
  // reply -- whatever its language -- is what killed the loop on #39 and, twice
  // on one unchanged head, on #48. Each row below is one of those replies.
  it("skips a quoted fence that carries no brace", () => {
    const reply = '```python\nraise TypeError\n```\n\n```json\n{"ok":1}\n```';
    expect(extractJson(reply)).toBe('{"ok":1}');
  });

  it("skips a quoted fence whose braces do not balance", () => {
    // This reply produced "The agent's JSON object is not closed." on #48.
    const reply = '```js\nif (a) { return b;\n```\n\n```json\n{"ok":1}\n```';
    expect(extractJson(reply)).toBe('{"ok":1}');
  });

  it("skips a quoted fence that is balanced but is not JSON", () => {
    // The dangerous one: the old parser returned "{ return b; }" and raised
    // nothing, so the Reviewer's actual verdict was discarded in silence.
    const reply = '```js\nif (a) { return b; }\n```\n\n```json\n{"ok":1}\n```';
    expect(extractJson(reply)).toBe('{"ok":1}');
  });

  it("finds the verdict behind several quoted fences", () => {
    const reply = [
      "```diff",
      "-old",
      "```",
      "```yaml",
      "on: {push}",
      "```",
      "```json",
      '{"summary":"ok","findings":[]}',
      "```",
    ].join("\n");
    expect(extractJson(reply)).toBe('{"summary":"ok","findings":[]}');
  });

  it("prefers a json fence over an object mentioned earlier in prose", () => {
    const reply = 'I considered {"draft":true} first.\n```json\n{"final":true}\n```';
    expect(extractJson(reply)).toBe('{"final":true}');
  });

  it("says what it scanned when nothing parses", () => {
    let message = "";
    try {
      extractJson("```js\nif (a) { return b; }\n```");
    } catch (error) {
      message = error.message;
    }
    // Two runs died on #48 with a message that named neither. This one does.
    expect(message.includes("1 fenced block(s) scanned")).toBe(true);
    expect(message.includes("return b")).toBe(true);
  });
});

// The loop's second live run failed with "The reviewer exited 1: (no stderr)"
// and no other evidence. `claude -p --output-format json` writes its result —
// errors included — to stdout, so reporting stderr alone discarded the only
// copy of what went wrong.

describe("detail", () => {
  it("prefers the envelope's own result over the raw streams", () => {
    const out = JSON.stringify({
      is_error: true,
      result: "Invalid API key · Please run /login",
      session_id: "s1",
    });
    expect(detail(out, "")).toBe("Invalid API key · Please run /login");
  });

  it("reports stdout when the envelope is not JSON", () => {
    expect(detail("something went wrong", "")).toContain(
      "stdout: something went wrong",
    );
  });

  it("reports both streams when both have content", () => {
    const d = detail("out here", "err here");
    expect(d).toContain("stdout: out here");
    expect(d).toContain("stderr: err here");
  });

  it("never returns an empty message", () => {
    expect(detail("", "")).toBe("(no output on either stream)");
    expect(detail(null, undefined)).toBe("(no output on either stream)");
  });

  it("truncates rather than pasting a whole transcript into a comment", () => {
    const d = detail("x".repeat(5000), "");
    expect(d.length).toBeLessThan(1700);
    expect(d).toContain("5000 chars");
  });
});

describe("is_error in the envelope", () => {
  it("is surfaced, so a zero exit is not read as success", () => {
    const out = JSON.stringify({
      is_error: true,
      result: "turn limit reached",
    });
    expect(parseAgentOutput("reviewer", out).isError).toBe(true);
  });

  it("is false for an ordinary reply", () => {
    const out = JSON.stringify({
      is_error: false,
      result: "{}",
      session_id: "s",
    });
    const parsed = parseAgentOutput("reviewer", out);
    expect(parsed.isError).toBe(false);
    expect(parsed.text).toBe("{}");
    expect(parsed.sessionId).toBe("s");
  });
});

// The prompt used to be argv. Linux caps one argument at 32 pages — 131072
// bytes — and #81 pushed the Reviewer's governing documents alone
// to 123805 bytes before any diff. Measured: spawn with a 130000-byte argument
// succeeds and 200000 throws E2BIG. On stdin there is no ceiling, so the prompt
// moved there; these assert it stays off argv.

describe("the prompt does not travel on argv", () => {
  it("is absent from the arguments and written to stdin", async () => {
    // The credential is never used here - the spawner is a fake - but
    // `runAgent` refuses to start without it, which is its own guard.
    const restore = process.env.CLAUDE_CODE_OAUTH_TOKEN;
    process.env.CLAUDE_CODE_OAUTH_TOKEN = "not-a-real-token";
    const prompt = "P".repeat(200_000);
    const seen = { args: null, wrote: "" };
    const child = {
      stdin: {
        on() {},
        end(text) {
          seen.wrote = text;
        },
      },
      stdout: { on() {} },
      stderr: { on() {} },
      kill() {},
      on(event, handler) {
        if (event === "close") queueMicrotask(() => handler(0));
      },
    };
    const result = await runAgent({
      role: "reviewer",
      prompt,
      timeoutMs: 1000,
      cwd: ".",
      spawnFn: (_cmd, args) => {
        seen.args = args;
        return child;
      },
    });

    expect(seen.wrote).toBe(prompt);
    for (const arg of seen.args) {
      expect(arg.length).toBeLessThan(131_072);
      expect(arg).not.toContain("PPPP");
    }
    expect(result.role).toBe("reviewer");

    if (restore === undefined) delete process.env.CLAUDE_CODE_OAUTH_TOKEN;
    else process.env.CLAUDE_CODE_OAUTH_TOKEN = restore;
  });
});
