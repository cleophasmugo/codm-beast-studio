"""End-to-end smoke test for CODM Beast Studio (python playwright, real backend).

Usage:
    python frontend/e2e/smoke.py [BASE_URL] [SAMPLES_DIR] [SHOTS_DIR]

BASE_URL defaults to http://localhost:8000 (FastAPI serving frontend/dist). With the Vite
dev/preview server use http://localhost:5173 or http://localhost:4173 (both proxy /api).

Flow: upload a gameplay video + screenshot through the drop zone's file input, run
"Create My Montage", wait for the render, check the <video> plays and the download link
works; then Image Studio: Auto Enhance the screenshot, export it, Add to Montage on that
project, re-render, and check the new render. Screenshots go to SHOTS_DIR.
"""

from __future__ import annotations

import glob
import os
import sys
import time

from playwright.sync_api import Page, expect, sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BASE_URL", "http://localhost:8000")).rstrip("/")
SAMPLES = sys.argv[2] if len(sys.argv) > 2 else "samples"
SHOTS = sys.argv[3] if len(sys.argv) > 3 else "e2e-shots"
RENDER_TIMEOUT = 600_000


def chromium_path() -> str | None:
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    hits = sorted(glob.glob(f"{root}/chromium-*/chrome-linux/chrome"))
    return hits[-1] if hits else None


def shot(page: Page, name: str, full: bool = True) -> None:
    os.makedirs(SHOTS, exist_ok=True)
    page.screenshot(path=f"{SHOTS}/{name}.png", full_page=full)
    print(f"  screenshot {SHOTS}/{name}.png")


H264 = 'video/mp4; codecs="avc1.640028"'


def check_video_plays(page: Page, scope, fmt: str = "mp4_h264") -> bool:
    """Assert the <video> loads and plays. Playwright's open-source Chromium has no H.264
    decoder, so for MP4 in such a browser we assert the app's 'cannot play here' notice
    instead and return False (the file itself is checked by check_download)."""
    video = scope.locator("[data-testid=export-video]").first
    expect(video).to_be_visible(timeout=30_000)
    if fmt.startswith("mp4") and not page.evaluate(f"document.createElement('video').canPlayType('{H264}')"):
        expect(scope.locator("[data-testid=video-unsupported]")).to_be_visible(timeout=30_000)
        print("  this Chromium build cannot decode H.264: app shows the download fallback notice (expected)")
        return False
    handle = video.element_handle()
    page.wait_for_function("v => v.readyState >= 1 && v.duration > 0", arg=handle, timeout=30_000)
    duration = video.evaluate("v => v.duration")
    video.evaluate("v => { v.muted = true; return v.play(); }")
    page.wait_for_function("v => v.currentTime > 0.3", arg=handle, timeout=20_000)
    print(f"  video OK: duration={duration:.2f}s, readyState={video.evaluate('v => v.readyState')}, playing")
    assert duration > 0
    return True


def check_download(page: Page, scope) -> bytes:
    link = scope.locator("[data-testid=download-link]").first
    href = link.get_attribute("href")
    assert href, "download link has no href"
    r = page.request.get(BASE + href if href.startswith("/") else href)
    assert r.ok, f"download failed: {r.status}"
    cd = r.headers.get("content-disposition", "")
    body = r.body()
    print(f"  download OK: {href} -> {r.status}, {len(body)} bytes, {cd}")
    assert "attachment" in cd and len(body) > 1000
    return body


def main() -> int:
    exe = chromium_path()
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))

        # ------------------------------------------------------------------ 1. upload
        print("1. Upload via the dashboard drop zone")
        page.goto(BASE + "/")
        expect(page.get_by_role("heading", name="Drop your gameplay.", exact=False)).to_be_visible()
        with page.expect_response(lambda r: r.url.endswith("/api/media") and r.request.method == "POST", timeout=180_000) as resp:
            page.locator("[data-testid=upload-input]").first.set_input_files(
                [f"{SAMPLES}/sample_gameplay.mp4", f"{SAMPLES}/sample_screenshot.jpg"]
            )
        assert resp.value.ok, f"upload failed: {resp.value.status} {resp.value.text()}"
        uploaded = resp.value.json()
        video_id = next(m["id"] for m in uploaded if m["kind"] == "video")
        image_id = next(m["id"] for m in uploaded if m["kind"] == "image")
        print(f"  uploaded video={video_id} image={image_id}")
        expect(page.get_by_text("2 selected")).to_be_visible()
        expect(page.locator(f"[data-testid=pick-{video_id}]")).to_be_visible()

        # ------------------------------------------------------------------ 2. one-click montage
        print("2. Create My Montage (Beast Mode, 15s)")
        page.get_by_role("radio", name="Beast Mode").click()
        page.get_by_role("button", name="15s", exact=True).click()
        with page.expect_response(lambda r: "/api/montage/quick" in r.url) as qr:
            page.locator("[data-testid=create-montage]").click()
        assert qr.value.status == 202, qr.value.text()
        job = qr.value.json()
        project_id = job["project_id"]
        print(f"  job={job['id']} project={project_id}")
        expect(page.locator("[data-testid=job-card]").first).to_be_visible()
        page.wait_for_timeout(2500)
        shot(page, "e2e_01_dashboard_rendering")
        result = page.locator("[data-testid=job-result]")
        expect(result).to_be_visible(timeout=RENDER_TIMEOUT)
        check_video_plays(page, result)
        mp4 = check_download(page, result)
        assert mp4[4:8] == b"ftyp", "download is not an MP4 file"
        result.scroll_into_view_if_needed()
        shot(page, "e2e_02_dashboard_done")

        # ------------------------------------------------------------------ 2b. editor: WebM export
        print("2b. Project editor: switch output to WebM (VP9) and Export")
        page.goto(f"{BASE}/projects/{project_id}")
        expect(page.locator("[data-testid=clip-strip]")).to_be_visible(timeout=30_000)
        page.get_by_role("tab", name="Output").click()
        page.get_by_role("button", name="WebM (VP9)").click()
        page.get_by_role("button", name="720p", exact=True).click()
        with page.expect_response(lambda r: r.url.endswith(f"/api/projects/{project_id}/render"), timeout=60_000) as rr:
            page.locator("[data-testid=export-render]").click()
        assert rr.value.status == 202, rr.value.text()
        expect(page.get_by_text("Render finished")).to_be_visible(timeout=RENDER_TIMEOUT)
        page.wait_for_timeout(1500)
        player = page.locator("main")
        assert check_video_plays(page, player, "webm_vp9"), "WebM export did not play"
        webm = check_download(page, player)
        assert webm[:4] == b"\x1a\x45\xdf\xa3", "download is not a WebM file"
        shot(page, "e2e_02b_editor_webm")

        # ------------------------------------------------------------------ 3. image studio
        print("3. Image Studio: auto enhance + export")
        page.goto(f"{BASE}/image-studio?image={image_id}")
        expect(page.locator("[data-testid=image-preview] img").first).to_be_visible(timeout=60_000)
        page.locator("[data-testid=auto-enhance]").click()
        reasons = page.locator("[data-testid=auto-reasons]")
        expect(reasons).to_be_visible()
        expect(reasons.locator("li").first).to_be_visible(timeout=60_000)
        print("  auto reasons:", reasons.locator("li").all_inner_texts())
        page.wait_for_timeout(1000)
        shot(page, "e2e_03_image_auto_enhanced")
        page.get_by_role("tab", name="Export").click()
        page.get_by_role("button", name="JPEG (smaller)").click()
        with page.expect_response(lambda r: f"/api/images/{image_id}/render" in r.url, timeout=120_000) as rr:
            page.locator("[data-testid=export-image]").click()
        assert rr.value.ok, rr.value.text()
        rendered = rr.value.json()
        new_media = rendered["media"]["id"]
        print(f"  exported image export={rendered['export']['id']} media={new_media} {rendered['export']['width']}x{rendered['export']['height']}")
        res = page.locator("[data-testid=image-export-result]")
        expect(res).to_be_visible()
        check_download(page, res)

        # ------------------------------------------------------------------ 4. add to montage + re-render
        print("4. Add to Montage + re-render")
        page.locator("[data-testid=atm-project]").select_option(project_id)
        with page.expect_response(lambda r: "/api/images/add-to-montage" in r.url) as ar:
            page.locator("[data-testid=add-to-montage]").click()
        assert ar.value.ok, ar.value.text()
        proj = ar.value.json()
        clips = (proj.get("timeline") or {}).get("clips", [])
        assert any(c.get("media_id") == new_media and c["kind"] == "image" for c in clips), "image clip not in timeline"
        print(f"  timeline now has {len(clips)} clips including the exported image")
        expect(page.locator("[data-testid=atm-done]")).to_be_visible()
        page.locator("[data-testid=rerender]").click()
        done = page.locator("[data-testid=atm-done] [data-testid=job-result]")
        expect(done).to_be_visible(timeout=RENDER_TIMEOUT)
        assert check_video_plays(page, done, "webm_vp9"), "re-rendered montage did not play"
        check_download(page, done)
        done.scroll_into_view_if_needed()
        shot(page, "e2e_04_image_added_rerendered")

        # ------------------------------------------------------------------ 5. editor + exports pages
        print("5. Project editor and export history")
        page.goto(f"{BASE}/projects/{project_id}")
        expect(page.locator("[data-testid=clip-strip]")).to_be_visible(timeout=30_000)
        n = page.locator("[data-testid=clip-strip] li, [data-testid=clip-strip] > *").count()
        print(f"  editor shows {n} clips")
        shot(page, "e2e_05_editor")
        page.goto(f"{BASE}/exports")
        expect(page.locator("[data-testid=export-card]").first).to_be_visible()
        shot(page, "e2e_06_exports")

        mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mp = mobile.new_page()
        for path, name in [("/", "e2e_m_dashboard"), (f"/projects/{project_id}", "e2e_m_editor"), (f"/image-studio?image={image_id}", "e2e_m_image")]:
            mp.goto(BASE + path)
            mp.wait_for_timeout(2000)
            sw = mp.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)")
            assert sw <= 390, f"horizontal overflow on {path}: {sw}px"
            shot(mp, name)
        mobile.close()

        real_errors = [e for e in errors if "favicon" not in e]
        if real_errors:
            print("Console errors:", real_errors)
        browser.close()
    print(f"PASS in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
