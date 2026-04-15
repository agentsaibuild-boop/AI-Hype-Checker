"""FastAPI server for the AI Hype Checker."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import trafilatura
import scorer
import os

app = FastAPI(title="AI Hype Checker")


class TextInput(BaseModel):
    text: str


class UrlInput(BaseModel):
    url: str


@app.get("/")
async def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


@app.post("/analyze")
async def analyze(body: TextInput):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текстът е празен.")
    if len(text.split()) < 20:
        raise HTTPException(status_code=400, detail="Текстът е твърде кратък (минимум 20 думи).")
    result = scorer.analyze(text)
    return JSONResponse(content=result)


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Injected into every Playwright page — hides automation signals
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins',   {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
window.chrome = { runtime: {} };
const orig = window.navigator.permissions.query;
window.navigator.permissions.query = p =>
  p.name === 'notifications'
    ? Promise.resolve({state: Notification.permission})
    : orig(p);
"""


async def _fetch_html(url: str) -> str:
    """
    Three-attempt chain:
      1. curl_cffi  — Chrome TLS fingerprint impersonation (fastest, beats most firewalls)
      2. Playwright — real headless browser with stealth scripts (beats JS challenges)
    """
    # ── Attempt 1: curl_cffi (real Chrome TLS fingerprint) ──────────────────
    try:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession() as s:
            resp = await s.get(
                url,
                impersonate="chrome124",
                headers={"Accept-Language": "en-US,en;q=0.9"},
                follow_redirects=True,
                timeout=15,
            )
            if resp.status_code < 400:
                return resp.text
    except Exception:
        pass

    # ── Attempt 2: Playwright + stealth ─────────────────────────────────────
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=_UA,
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
        )
        await ctx.add_init_script(_STEALTH_JS)
        page = await ctx.new_page()
        await page.goto(url, wait_until="networkidle", timeout=35_000)
        html = await page.content()
        await browser.close()
        return html


@app.post("/scrape")
async def scrape(body: UrlInput):
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Невалиден URL.")

    try:
        html = await _fetch_html(url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Неуспешно зареждане: {e}")

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
        url=url,
    )
    if not text or len(text.split()) < 20:
        raise HTTPException(
            status_code=422,
            detail="Не може да се извлече текст от тази страница.",
        )
    return JSONResponse(content={"text": text})


class HtmlInput(BaseModel):
    html: str
    url: str = ""


@app.post("/extract-html")
async def extract_html(body: HtmlInput):
    if not body.html.strip():
        raise HTTPException(status_code=400, detail="HTML-ът е празен.")
    text = trafilatura.extract(
        body.html,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
        url=body.url or None,
    )
    if not text or len(text.split()) < 20:
        raise HTTPException(status_code=422, detail="Не може да се извлече текст от предоставения HTML.")
    return JSONResponse(content={"text": text})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
