"""Execute a CCORE document in an offline, disposable browser process."""
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ORIGIN = "https://ccore.invalid"
PAGE = ORIGIN + "/prop"
THREE = Path(__file__).with_name("three")
MODULES = {
    "build/three.module.js": "build/three.module.min.js",
    "build/three.module.min.js": "build/three.module.min.js",
    "examples/jsm/exporters/GLTFExporter.js": "examples/jsm/exporters/GLTFExporter.js",
    "examples/jsm/controls/OrbitControls.js": "examples/jsm/controls/OrbitControls.js",
    "examples/jsm/utils/BufferGeometryUtils.js": "examples/jsm/utils/BufferGeometryUtils.js",
    "examples/jsm/utils/TextureUtils.js": "examples/jsm/utils/TextureUtils.js",
    "examples/jsm/environments/RoomEnvironment.js": "examples/jsm/environments/RoomEnvironment.js",
    "examples/jsm/geometries/RoundedBoxGeometry.js": "examples/jsm/geometries/RoundedBoxGeometry.js",
    "examples/jsm/geometries/ConvexGeometry.js": "examples/jsm/geometries/ConvexGeometry.js",
    "examples/jsm/math/ConvexHull.js": "examples/jsm/math/ConvexHull.js",
}
CSP = (
    "sandbox allow-scripts allow-downloads; default-src 'none'; "
    "script-src 'unsafe-inline' https://ccore.invalid https://cdn.jsdelivr.net https://unpkg.com; "
    "style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-src 'none'; worker-src 'none'"
)


def module_path(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        return None
    if parsed.netloc == "ccore.invalid" and parsed.path.startswith("/three/"):
        relative = parsed.path.removeprefix("/three/")
    elif parsed.netloc in ("cdn.jsdelivr.net", "unpkg.com"):
        match = re.fullmatch(r"/(?:npm/)?three@0\.\d+\.\d+/(.+)", parsed.path)
        relative = match[1] if match else ""
    else:
        return None
    return MODULES.get(relative)


def launch(driver):
    return driver.chromium.launch(chromium_sandbox=True, headless=True, args=[
        "--disable-background-networking", "--disable-quic",
        "--host-resolver-rules=MAP * ~NOTFOUND",
        "--proxy-server=127.0.0.1:9", "--proxy-bypass-list=<-loopback>",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
    ])


def render(source, output):
    from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout

    html = source.read_bytes()
    errors = []
    with sync_playwright() as driver, launch(driver) as browser:
        context = browser.new_context(offline=True, service_workers="block", accept_downloads=True,
                                      viewport={"width": 960, "height": 720})
        served_document = False

        def replay(route):
            nonlocal served_document
            request = route.request
            if request.method != "GET":
                return route.abort()
            if not served_document and request.url == PAGE and request.is_navigation_request():
                served_document = True
                return route.fulfill(body=html, content_type="text/html; charset=utf-8",
                                     headers={"Content-Security-Policy": CSP})
            path = module_path(request.url)
            if path and request.resource_type == "script":
                body = (THREE / path).read_text(encoding="utf-8")
                # Add-ons work even when the generated page uses direct CDN imports
                # instead of its own import map for the package's bare specifier.
                body = re.sub(r"""(from\s*)(['"])three\2""",
                              r'\1"' + ORIGIN + '/three/build/three.module.js"', body)
                return route.fulfill(body=body, content_type="application/javascript",
                                     headers={"Access-Control-Allow-Origin": "*"})
            return route.abort()

        context.route("**/*", replay)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)[:240]) if len(errors) < 3 else None)
        try:
            page.goto(PAGE, wait_until="domcontentloaded", timeout=12000)
            export = page.get_by_role("button", name=re.compile(r"(export|download|save).*glb", re.I)).first
            export.wait_for(state="visible", timeout=10000)
            with page.expect_download(timeout=15000) as event:
                export.click(timeout=5000)
            download = event.value
            if not download.url.startswith("blob:"):
                raise ValueError("The scene did not create a local GLB.")
            download.save_as(str(output))
        except BrowserTimeout as error:
            message = "The generated scene could not export a GLB. Try another seed or simplify the description."
            if errors:
                message += " Scene error: " + errors[0]
            raise ValueError(message) from error


if __name__ == "__main__":
    if sys.argv[1:] == ["--probe"]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as driver, launch(driver) as browser:
            print("CCORE renderer ready, Chromium", browser.version)
    else:
        try:
            render(Path(sys.argv[1]), Path(sys.argv[2]))
        except Exception as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(1)
