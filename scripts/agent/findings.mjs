// Finding identity, and the contract the Reviewer's output has to satisfy.
//
// A finding needs a stable id so that round 2 can say "B1 is fixed, B3 is not"
// and mean the same B1 the first review named. The Reviewer is a fresh session
// each round and cannot be relied on to renumber consistently, so ids are
// allocated here and carried in the pull request's state, never by the model.

/** Severities, most severe first. The prefix is the id's letter. */
export const SEVERITIES = [
  { name: "blocking", prefix: "B" },
  { name: "non-blocking", prefix: "N" },
  { name: "optional", prefix: "O" },
];

const prefixBySeverity = new Map(SEVERITIES.map((s) => [s.name, s.prefix]));

/** Thrown when the Reviewer returns something that is not a review. */
export class ReviewContractError extends Error {}

/**
 * Validate the Reviewer's JSON.
 *
 * Deliberately strict. A malformed review must fail loudly rather than be
 * coerced into an empty finding list, because an empty finding list is
 * indistinguishable from "nothing wrong" and would end the loop as ready.
 */
export function parseReview(raw) {
  let doc;
  try {
    doc = typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch (cause) {
    throw new ReviewContractError(
      `Reviewer output is not JSON: ${cause.message}`,
    );
  }
  if (doc === null || typeof doc !== "object" || Array.isArray(doc)) {
    throw new ReviewContractError("Reviewer output is not a JSON object.");
  }
  if (!Array.isArray(doc.findings)) {
    throw new ReviewContractError("Reviewer output has no `findings` array.");
  }

  const findings = doc.findings.map((f, i) => {
    if (f === null || typeof f !== "object") {
      throw new ReviewContractError(`findings[${i}] is not an object.`);
    }
    if (!prefixBySeverity.has(f.severity)) {
      throw new ReviewContractError(
        `findings[${i}].severity is ${JSON.stringify(f.severity)}; ` +
          `expected one of ${SEVERITIES.map((s) => s.name).join(", ")}.`,
      );
    }
    const summary = typeof f.summary === "string" ? f.summary.trim() : "";
    if (summary === "") {
      throw new ReviewContractError(`findings[${i}].summary is empty.`);
    }
    return {
      severity: f.severity,
      file: typeof f.file === "string" ? f.file.trim() : "",
      summary,
      failure: typeof f.failure === "string" ? f.failure.trim() : "",
      fix: typeof f.fix === "string" ? f.fix.trim() : "",
    };
  });

  return {
    summary: typeof doc.summary === "string" ? doc.summary.trim() : "",
    findings,
  };
}

/**
 * The key two findings must share to be considered the same finding across
 * rounds. Severity is included on purpose: a finding the Reviewer downgrades
 * from blocking to optional is a different claim about the same code, and
 * silently reusing the id would hide that it changed.
 */
function identityKey(f) {
  return [
    f.severity,
    f.file,
    f.summary.replace(/\s+/g, " ").toLowerCase(),
  ].join(" ");
}

/**
 * Give every finding an id, reusing the id a matching finding already holds.
 *
 * `registry` maps identity key to id and is carried in state. Ids are never
 * reused for a different finding, so a reader can follow B1 across the whole
 * pull request.
 *
 * @returns {{findings: object[], registry: Record<string,string>}}
 */
export function assignIds(findings, registry = {}) {
  const next = { ...registry };
  const used = new Set(Object.values(next));

  const counters = new Map(SEVERITIES.map((s) => [s.prefix, 0]));
  for (const id of used) {
    const m = /^([BNO])(\d+)$/.exec(id);
    if (m) counters.set(m[1], Math.max(counters.get(m[1]) ?? 0, Number(m[2])));
  }

  const withIds = findings.map((f) => {
    const key = identityKey(f);
    let id = next[key];
    if (id === undefined) {
      const prefix = prefixBySeverity.get(f.severity);
      const n = (counters.get(prefix) ?? 0) + 1;
      counters.set(prefix, n);
      id = `${prefix}${n}`;
      next[key] = id;
      used.add(id);
    }
    return { id, ...f };
  });

  return { findings: withIds, registry: next };
}

/** Findings that stop the loop from concluding ready. */
export function blockingOf(findings) {
  return findings.filter((f) => f.severity === "blocking");
}

/** Render findings as Markdown for a pull request comment. */
export function renderFindings(findings) {
  if (findings.length === 0) return "_No findings._";
  return SEVERITIES.flatMap(({ name }) => {
    const group = findings.filter((f) => f.severity === name);
    if (group.length === 0) return [];
    const heading = name[0].toUpperCase() + name.slice(1);
    return [
      `### ${heading}`,
      "",
      ...group.flatMap((f) => [
        `**${f.id}** - ${f.summary}${f.file ? ` (\`${f.file}\`)` : ""}`,
        "",
        ...(f.failure ? [`- Failure: ${f.failure}`] : []),
        ...(f.fix ? [`- Fix: ${f.fix}`] : []),
        "",
      ]),
    ];
  }).join("\n");
}
