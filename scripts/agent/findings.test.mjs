import { describe, expect, it } from "./test-kit.mjs";
import {
  ReviewContractError,
  assignIds,
  blockingOf,
  parseReview,
  renderFindings,
} from "./findings.mjs";

const ok = {
  severity: "blocking",
  summary: "Guard passes on the input it should reject",
  file: "scripts/x.mjs",
};

describe("parseReview", () => {
  it("accepts a well-formed review and trims its strings", () => {
    const r = parseReview(
      JSON.stringify({
        summary: "  two issues  ",
        findings: [{ ...ok, fix: "  add the case  " }],
      }),
    );
    expect(r.summary).toBe("two issues");
    expect(r.findings[0].fix).toBe("add the case");
  });

  it("accepts an already-parsed object", () => {
    expect(parseReview({ findings: [] }).findings).toEqual([]);
  });

  // Each of these would otherwise degrade to "no findings", which the loop
  // reads as "nothing wrong" and concludes ready on. They must throw.
  it.each([
    ["not JSON", "{oops"],
    ["a JSON array", "[]"],
    ["a JSON scalar", '"review"'],
    ["an object with no findings array", '{"summary":"fine"}'],
    ["findings holding a non-object", '{"findings":[1]}'],
  ])("rejects %s", (_label, raw) => {
    expect(() => parseReview(raw)).toThrow(ReviewContractError);
  });

  it("rejects an unknown severity rather than guessing", () => {
    expect(() =>
      parseReview({ findings: [{ ...ok, severity: "major" }] }),
    ).toThrow(/severity/);
  });

  it("rejects an empty summary, which would produce an unusable finding id", () => {
    expect(() =>
      parseReview({ findings: [{ ...ok, summary: "   " }] }),
    ).toThrow(/summary/);
  });
});

describe("assignIds", () => {
  it("numbers each severity independently, in order", () => {
    const { findings } = assignIds([
      { severity: "blocking", file: "a", summary: "one" },
      { severity: "non-blocking", file: "b", summary: "two" },
      { severity: "blocking", file: "c", summary: "three" },
      { severity: "optional", file: "d", summary: "four" },
    ]);
    expect(findings.map((f) => f.id)).toEqual(["B1", "N1", "B2", "O1"]);
  });

  it("reuses an id when the same finding comes back in a later round", () => {
    const first = assignIds([
      { severity: "blocking", file: "a", summary: "One" },
    ]);
    const second = assignIds(
      [
        { severity: "blocking", file: "a", summary: "one" }, // same, different case
        { severity: "blocking", file: "b", summary: "new" },
      ],
      first.registry,
    );
    expect(second.findings.map((f) => f.id)).toEqual(["B1", "B2"]);
  });

  it("does not reuse an id when the severity changed", () => {
    // A finding downgraded from blocking to optional is a different claim.
    // Reusing B1 would hide that the Reviewer changed its mind.
    const first = assignIds([
      { severity: "blocking", file: "a", summary: "one" },
    ]);
    const second = assignIds(
      [{ severity: "optional", file: "a", summary: "one" }],
      first.registry,
    );
    expect(second.findings[0].id).toBe("O1");
  });

  it("continues numbering past ids already in the registry", () => {
    const registry = { "blocking a old": "B3" };
    const { findings } = assignIds(
      [{ severity: "blocking", file: "a", summary: "fresh" }],
      registry,
    );
    expect(findings[0].id).toBe("B4");
  });

  it("never issues the same id to two different findings", () => {
    let registry = {};
    const ids = [];
    for (let round = 0; round < 5; round += 1) {
      const out = assignIds(
        [
          { severity: "blocking", file: "a", summary: "stable" },
          { severity: "blocking", file: `f${round}`, summary: `new ${round}` },
        ],
        registry,
      );
      registry = out.registry;
      ids.push(...out.findings.map((f) => f.id));
    }
    const distinctKeys = new Set(Object.keys(registry));
    const distinctIds = new Set(Object.values(registry));
    expect(distinctIds.size).toBe(distinctKeys.size);
    expect(ids.filter((id) => id === "B1")).toHaveLength(5); // the stable one, every round
  });
});

describe("blockingOf", () => {
  it("selects only blocking findings", () => {
    const findings = [
      { id: "B1", severity: "blocking" },
      { id: "N1", severity: "non-blocking" },
      { id: "O1", severity: "optional" },
    ];
    expect(blockingOf(findings).map((f) => f.id)).toEqual(["B1"]);
  });
});

describe("renderFindings", () => {
  it("says so explicitly when there is nothing, rather than rendering blank", () => {
    expect(renderFindings([])).toContain("No findings");
  });

  it("groups by severity, most severe first, and shows the id", () => {
    const md = renderFindings([
      {
        id: "N1",
        severity: "non-blocking",
        summary: "nit",
        file: "",
        failure: "",
        fix: "",
      },
      {
        id: "B1",
        severity: "blocking",
        summary: "bug",
        file: "a.mjs",
        failure: "x",
        fix: "y",
      },
    ]);
    expect(md.indexOf("Blocking")).toBeLessThan(md.indexOf("Non-blocking"));
    expect(md).toContain("**B1**");
    expect(md).toContain("`a.mjs`");
  });
});
