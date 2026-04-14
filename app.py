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


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}

async def _fetch_html(url: str) -> str:
    """Try httpx first (fast), fall back to Playwright (bypasses anti-bot)."""
    import httpx

    try:
        async with httpx.AsyncClient(
            headers=_HEADERS, follow_redirects=True, timeout=15, http2=True,
        ) as client:
            resp = await client.get(url)
            if resp.status_code < 400:
                return resp.text
    except Exception:
        pass

    # Fallback: real headless browser
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=_HEADERS["User-Agent"],
            locale="en-US",
        )
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
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
