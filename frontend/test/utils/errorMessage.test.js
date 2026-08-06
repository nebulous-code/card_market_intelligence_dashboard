import { describe, it, expect } from "vitest";

import {
  errorMessage,
  isNotFound,
  normalizeError,
} from "../../src/utils/errorMessage.js";

/** Shape of a real axios rejection, trimmed to what the code reads. */
const axiosError = (status, { data, headers, code } = {}) => ({
  code,
  response: status === undefined ? undefined : { status, data, headers },
});

describe("normalizeError", () => {
  it("treats a timeout as the server waking up, not a fault", () => {
    // The API sleeps on Render's free tier; a first visit routinely
    // exceeds the 15s axios timeout while the instance spins up.
    const result = normalizeError({ code: "ECONNABORTED" });
    expect(result.kind).toBe("timeout");
    expect(result.status).toBeNull();
    expect(result.message).toMatch(/waking up/);
  });

  it("treats ETIMEDOUT the same way", () => {
    expect(normalizeError({ code: "ETIMEDOUT" }).kind).toBe("timeout");
  });

  it("reports a request that never landed as offline", () => {
    const result = normalizeError(new Error("Network Error"));
    expect(result.kind).toBe("offline");
    expect(result.status).toBeNull();
    expect(result.message).toMatch(/Could not reach the server/);
  });

  it("classifies 404", () => {
    const result = normalizeError(axiosError(404));
    expect(result.kind).toBe("notFound");
    expect(result.status).toBe(404);
  });

  it("classifies 500 and above as a server problem", () => {
    expect(normalizeError(axiosError(500)).kind).toBe("server");
    expect(normalizeError(axiosError(503)).kind).toBe("server");
  });

  it("falls back for an unrecognised status", () => {
    const result = normalizeError(axiosError(418), "Custom fallback.");
    expect(result.kind).toBe("unknown");
    expect(result.message).toBe("Custom fallback.");
  });

  it("uses its own default fallback when none is supplied", () => {
    expect(normalizeError(axiosError(418)).message).toBe("Something went wrong.");
  });

  it("handles a response with no status field", () => {
    expect(normalizeError({ response: {} }).status).toBeNull();
  });
});

describe("server-supplied detail", () => {
  it("prefers the API's message on a 413", () => {
    // The upload guard explains which limit was hit and by how much --
    // strictly better than anything generic written here.
    const err = axiosError(413, { data: { detail: "File is larger than the 5 MB limit." } });
    expect(normalizeError(err).message).toBe("File is larger than the 5 MB limit.");
  });

  it("falls back to generic copy when 413 carries no detail", () => {
    expect(normalizeError(axiosError(413)).message).toMatch(/too large/);
  });

  it("prefers the API's message on a 422", () => {
    const err = axiosError(422, { data: { detail: "That workbook could not be opened." } });
    expect(normalizeError(err).message).toBe("That workbook could not be opened.");
  });

  it("ignores a structured 422 detail rather than stringifying it", () => {
    // Upload validation failures return an object that drives the
    // annotated-workbook panel. Flattening it here would produce
    // "[object Object]" on screen and hide the real handling.
    const err = axiosError(422, { data: { detail: { total_rows: 3, error_rows: [] } } });
    expect(normalizeError(err).message).toMatch(/couldn't be validated/);
  });

  it("ignores a blank detail string", () => {
    const err = axiosError(413, { data: { detail: "   " } });
    expect(normalizeError(err).message).toMatch(/too large/);
  });
});

describe("rate limiting", () => {
  it("reads Retry-After and puts the wait in the message", () => {
    const err = axiosError(429, { headers: { "retry-after": "45" } });
    const result = normalizeError(err);
    expect(result.kind).toBe("rateLimited");
    expect(result.retryAfter).toBe(45);
    expect(result.message).toBe("Too many requests. Try again in 45 seconds.");
  });

  it("says minutes rather than making the reader divide by sixty", () => {
    // The default rate-limit window reports 600, and "600 seconds" is
    // a number a person has to do arithmetic on.
    const err = axiosError(429, { headers: { "retry-after": "600" } });
    expect(normalizeError(err).message).toBe("Too many requests. Try again in 10 minutes.");
  });

  it("uses the singular for exactly one minute", () => {
    const err = axiosError(429, { headers: { "retry-after": "60" } });
    expect(normalizeError(err).message).toBe("Too many requests. Try again in 1 minute.");
  });

  it("rounds a partial minute up", () => {
    const err = axiosError(429, { headers: { "retry-after": "90" } });
    expect(normalizeError(err).message).toBe("Too many requests. Try again in 2 minutes.");
  });

  it("falls back to the server's sentence when the header is not exposed", () => {
    // Retry-After is invisible to cross-origin JS unless the API lists
    // it in expose_headers. If that is ever misconfigured the server's
    // own wording still carries the wait time, so use it rather than
    // dropping all the way to "in a moment".
    const err = axiosError(429, {
      data: { detail: "Too many uploads from this address. Try again in 600 seconds." },
    });
    const result = normalizeError(err);
    expect(result.retryAfter).toBeNull();
    expect(result.message).toBe(
      "Too many uploads from this address. Try again in 600 seconds.",
    );
  });

  it("degrades to generic copy with neither header nor detail", () => {
    const result = normalizeError(axiosError(429));
    expect(result.retryAfter).toBeNull();
    expect(result.message).toBe("Too many requests. Try again in a moment.");
  });

  it("ignores an unparseable Retry-After", () => {
    const err = axiosError(429, { headers: { "retry-after": "Wed, 21 Oct 2026 07:28:00 GMT" } });
    expect(normalizeError(err).retryAfter).toBeNull();
  });

  it("ignores a non-positive Retry-After", () => {
    const err = axiosError(429, { headers: { "retry-after": "0" } });
    expect(normalizeError(err).retryAfter).toBeNull();
  });

  it("rounds a fractional Retry-After up", () => {
    const err = axiosError(429, { headers: { "retry-after": "2.4" } });
    expect(normalizeError(err).retryAfter).toBe(3);
  });
});

describe("errorMessage", () => {
  it("returns the bare reason with no lead", () => {
    expect(errorMessage(axiosError(404))).toBe("We couldn't find that.");
  });

  it("prefixes the lead so the user gets context plus reason", () => {
    const result = errorMessage(new Error("boom"), "Could not load sets.");
    expect(result).toBe(
      "Could not load sets. Could not reach the server. Check your connection and try again.",
    );
  });

  it("does not repeat the lead when it was used as the fallback", () => {
    // An unrecognised status falls back to the lead itself; printing it
    // twice would read as a stutter.
    expect(errorMessage(axiosError(418), "Could not load sets.")).toBe(
      "Could not load sets.",
    );
  });
});

describe("isNotFound", () => {
  it("is true only for 404", () => {
    expect(isNotFound(axiosError(404))).toBe(true);
    expect(isNotFound(axiosError(500))).toBe(false);
  });

  it("is false for a request that never landed", () => {
    expect(isNotFound(new Error("Network Error"))).toBe(false);
    expect(isNotFound(undefined)).toBe(false);
  });
});
