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


async def _fetch_via_jina(url: str) -> str:
    """Jina AI Reader — връща чист текст директно, заобикаля повечето anti-bot защити."""
    import httpx
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        resp = await client.get(
            f"https://r.jina.ai/{url}",
            headers={
                "Accept": "text/plain",
                "X-No-Cache": "true",
            },
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Jina: HTTP {resp.status_code}")
        text = resp.text
        # Jina сам предупреждава когато попадне на CAPTCHA/bot challenge страница
        if "requiring CAPTCHA" in text or "Robot Challenge" in text or "Checking the site connection" in text:
            raise RuntimeError("Jina: страницата изисква CAPTCHA")
        if len(text.split()) < 20:
            raise RuntimeError("Jina: извлеченият текст е твърде кратък")
        return text


async def _fetch_html(url: str) -> str:
    """
    Three-attempt chain:
      1. Jina AI Reader — clean text extraction, bypasses most anti-bot walls (no browser needed)
      2. curl_cffi      — Chrome TLS fingerprint impersonation
      3. Playwright     — real headless browser with stealth scripts
    """
    errors = []

    # ── Attempt 1: Jina AI Reader (most reliable, no browser needed) ────────
    try:
        return await _fetch_via_jina(url)
    except Exception as e:
        errors.append(f"jina: {e}")

    # ── Attempt 2: curl_cffi (real Chrome TLS fingerprint) ──────────────────
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
            errors.append(f"curl_cffi: HTTP {resp.status_code}")
    except Exception as e:
        errors.append(f"curl_cffi: {e}")

    # ── Attempt 3: Playwright + stealth ─────────────────────────────────────
    try:
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
    except Exception as e:
        errors.append(f"playwright: {e}")

    raise RuntimeError(" | ".join(errors))


@app.post("/scrape")
async def scrape(body: UrlInput):
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Невалиден URL.")

    # ── Attempt 1: Jina returns clean text directly ──────────────────────────
    try:
        text = await _fetch_via_jina(url)
        return JSONResponse(content={"text": text})
    except Exception:
        pass

    # ── Attempts 2-3: fetch HTML, then extract with trafilatura ─────────────
    html_errors = []
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
                html = resp.text
            else:
                html_errors.append(f"curl_cffi: HTTP {resp.status_code}")
                html = None
    except Exception as e:
        html_errors.append(f"curl_cffi: {e}")
        html = None

    if html is None:
        try:
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
        except Exception as e:
            html_errors.append(f"playwright: {e}")
            html = None

    if html is None:
        raise HTTPException(status_code=422, detail=f"Неуспешно зареждане: {' | '.join(html_errors)}")

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


@app.post("/summarize")
async def summarize(body: TextInput):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текстът е празен.")

    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.lex_rank import LexRankSummarizer

    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = LexRankSummarizer()
    sentences = summarizer(parser.document, sentences_count=5)
    summary = " ".join(str(s) for s in sentences)

    if not summary.strip():
        raise HTTPException(status_code=422, detail="Не може да се генерира резюме.")

    return JSONResponse(content={"summary": summary})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
