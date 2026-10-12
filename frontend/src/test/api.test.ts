import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, clipOutputDuration, detailMessage, mediaUrl, type Clip } from "../api";
import { setToken } from "../lib/token";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setToken("");
});

describe("api client", () => {
  it("sends no Authorization header without a token", async () => {
    const f = mockFetch(200, []);
    await api.listProjects();
    const init = (f.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("sends a Bearer token and JSON body when a token is set", async () => {
    setToken("s3cret");
    const f = mockFetch(200, { id: "p1" });
    await api.updateProject("p1", { name: "New" });
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/projects/p1");
    expect(init.method).toBe("PATCH");
    const h = init.headers as Record<string, string>;
    expect(h.Authorization).toBe("Bearer s3cret");
    expect(h["Content-Type"]).toBe("application/json");
    expect(JSON.parse(String(init.body))).toEqual({ name: "New" });
  });

  it("appends the token to media URLs that cannot send headers", () => {
    expect(mediaUrl("/api/media/a/file")).toBe("/api/media/a/file");
    setToken("a b&c");
    expect(mediaUrl("/api/media/a/file")).toBe("/api/media/a/file?access_token=a%20b%26c");
    expect(mediaUrl("/api/media/a/frame?t=1.00")).toBe("/api/media/a/frame?t=1.00&access_token=a%20b%26c");
    expect(mediaUrl(null)).toBe("");
  });

  it("throws ApiError carrying the API's detail message", async () => {
    mockFetch(409, { detail: "This project already has a render job in progress" });
    await expect(api.render("p1", false)).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: "This project already has a render job in progress",
    });
  });

  it("formats FastAPI validation errors and status fallbacks", () => {
    expect(detailMessage({ detail: [{ loc: ["body", "media_ids"], msg: "too short" }] }, 422)).toBe("media_ids: too short");
    expect(detailMessage(null, 401)).toMatch(/access token/);
    expect(detailMessage(null, 502)).toMatch(/Server error/);
    expect(new ApiError(404, "x")).toBeInstanceOf(Error);
  });

  it("returns undefined for 204 responses", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    await expect(api.deleteExport("e1")).resolves.toBeUndefined();
  });

  it("computes clip output duration like the backend (ramps stretch time)", () => {
    const base = { id: "c", kind: "video", media_id: "m", start: 2, end: 6, duration: 0, ramp: null } as unknown as Clip;
    expect(clipOutputDuration(base)).toBe(4);
    expect(clipOutputDuration({ ...base, ramp: { at: 1, duration: 1, speed: 0.5 } })).toBe(5);
    expect(clipOutputDuration({ ...base, kind: "image", duration: 2.5 })).toBe(2.5);
  });
});
