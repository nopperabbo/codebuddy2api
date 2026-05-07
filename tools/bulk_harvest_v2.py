"""
Bulk CodeBuddy API key harvester v2 — lightweight pipeline edition.
Architecture: Browser workers (OAuth only) → asyncio.Queue → HTTP workers (registration + key).

Usage:
    python bulk_harvest_v2.py [--accounts accounts.txt] [--browser-workers 2] [--http-workers 6]
    python bulk_harvest_v2.py --headed  # debug mode
    python bulk_harvest_v2.py --xvfb    # Linux stealth mode
"""
import os
import sys
import json
import time
import asyncio
import argparse
import logging
import subprocess
import random
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List, Set
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from playwright_stealth import Stealth

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

CODEBUDDY_BASE = "https://www.codebuddy.ai"
KEYS_FILE = Path(__file__).parent / "harvested_keys.json"
FAILED_FILE = Path(__file__).parent / "failed_accounts.txt"
STATE_FILE = Path(__file__).parent / ".harvest_state.json"
PROFILES_DIR = Path(__file__).parent / ".browser_profiles"
PROXIES_FILE = Path(__file__).parent / "proxies.txt"

REGION_PAYLOAD = {
    "attributes": {
        "countryCode": ["65"],
        "countryFullName": ["Singapore"],
        "countryName": ["SG"]
    }
}

RATE_LIMIT_SIGNALS = [
    'unusual activity', 'try again later', 'captcha', 'recaptcha',
    'verify it\'s you', 'too many attempts', 'rate limit', 'blocked',
]

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
delete navigator.__proto__.webdriver;
window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };

const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => [4, 8, 12, 16][Math.floor(Math.random() * 4)],
});
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => [4, 8, 16][Math.floor(Math.random() * 3)],
});

if (navigator.connection) {
    Object.defineProperty(navigator.connection, 'rtt', { get: () => 50 + Math.floor(Math.random() * 100) });
    Object.defineProperty(navigator.connection, 'downlink', { get: () => 5 + Math.random() * 15 });
    Object.defineProperty(navigator.connection, 'effectiveType', { get: () => '4g' });
}

const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
    const ctx = this.getContext('2d');
    if (ctx) {
        const noise = (Math.random() - 0.5) * 0.01;
        const imageData = ctx.getImageData(0, 0, Math.min(this.width, 2), Math.min(this.height, 2));
        imageData.data[0] = Math.max(0, Math.min(255, imageData.data[0] + noise * 255));
        ctx.putImageData(imageData, 0, 0);
    }
    return originalToDataURL.apply(this, arguments);
};

const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Google Inc. (NVIDIA)';
    if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Ti, OpenGL 4.5)';
    return getParameter.apply(this, arguments);
};

const originalGetChannelData = AudioBuffer.prototype.getChannelData;
AudioBuffer.prototype.getChannelData = function(channel) {
    const data = originalGetChannelData.apply(this, arguments);
    if (data.length > 0) {
        data[0] = data[0] + (Math.random() - 0.5) * 0.0001;
    }
    return data;
};
"""

BLOCKED_RESOURCE_TYPES = ['image', 'media', 'font', 'stylesheet']
BLOCKED_URL_PATTERNS = [
    'google-analytics.com', 'googletagmanager.com', 'facebook.net',
    'doubleclick.net', 'hotjar.com', '.png', '.jpg', '.jpeg', '.gif',
    '.svg', '.woff', '.woff2', '.ttf', '.ico',
]

file_lock = asyncio.Lock()
rate_limit_event = asyncio.Event()
rate_limit_event.set()

TELEGRAM_BOT_TOKEN = "8540953511:AAF709bIJV9e4dAejN4YyJ3kQu9RWCkhRgM"
TELEGRAM_CHAT_ID = "5316759602"


def gaussian_delay(mean: float = 80, std: float = 30, minimum: float = 30) -> int:
    return max(int(minimum), int(random.gauss(mean, std)))


def random_viewport() -> Dict[str, int]:
    base_w, base_h = 1280, 720
    jitter_w = random.randint(-30, 30)
    jitter_h = random.randint(-20, 20)
    return {'width': base_w + jitter_w, 'height': base_h + jitter_h}


async def human_move_and_click(page: Page, element):
    try:
        box = await element.bounding_box()
        if not box:
            await element.click()
            return

        target_x = box['x'] + box['width'] * random.uniform(0.3, 0.7)
        target_y = box['y'] + box['height'] * random.uniform(0.3, 0.7)

        start_x = random.uniform(100, 400)
        start_y = random.uniform(100, 300)

        steps = random.randint(8, 15)
        for i in range(steps):
            t = (i + 1) / steps
            t = t * t * (3 - 2 * t)
            x = start_x + (target_x - start_x) * t + random.uniform(-2, 2)
            y = start_y + (target_y - start_y) * t + random.uniform(-2, 2)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.01, 0.03))

        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.click(target_x, target_y)
    except Exception:
        await element.click()


async def human_type(page: Page, locator, text: str):
    await locator.click()
    await asyncio.sleep(random.uniform(0.2, 0.5))
    for char in text:
        await page.keyboard.press(char)
        await asyncio.sleep(gaussian_delay(70, 25, 25) / 1000)
        if random.random() < 0.03:
            await asyncio.sleep(random.uniform(0.3, 0.8))


async def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            )
    except Exception:
        pass


@dataclass
class HarvestStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    retried: int = 0
    skipped: int = 0
    keys: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def record_success(self, email: str, key: str):
        async with self.lock:
            self.success += 1
            self.keys.append({'email': email, 'key': key})
            self._print_progress()

    async def record_failure(self, email: str, reason: str = ""):
        async with self.lock:
            self.failed += 1
            self.errors.append(email)
            self._print_progress()
            await self._save_failed(email, reason)

    async def record_retry(self):
        async with self.lock:
            self.retried += 1

    def _print_progress(self):
        done = self.success + self.failed
        pct = (done / self.total * 100) if self.total > 0 else 0
        logger.info(f"[PROGRESS] {done}/{self.total} ({pct:.0f}%) | ✓ {self.success} ✗ {self.failed}")

    async def _save_failed(self, email: str, reason: str):
        async with file_lock:
            with open(FAILED_FILE, 'a') as f:
                f.write(f"{email}|{reason}\n")


def load_proxies() -> list:
    if PROXIES_FILE.exists():
        return [l.strip() for l in open(PROXIES_FILE) if l.strip() and not l.startswith('#')]
    return []


def parse_proxy(proxy_url: str) -> Optional[Dict[str, str]]:
    parsed = urlparse(proxy_url)
    if not parsed.hostname:
        return None
    return {
        "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
        "username": parsed.username or "",
        "password": parsed.password or "",
    }


def start_xvfb(display: str = ":99") -> Optional[subprocess.Popen]:
    if sys.platform != 'linux':
        return None
    r = subprocess.run(["pgrep", "-f", f"Xvfb {display}"], capture_output=True)
    if r.returncode == 0:
        return None
    try:
        proc = subprocess.Popen(
            ["Xvfb", display, "-screen", "0", "1280x720x24", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(1)
        os.environ["DISPLAY"] = display
        logger.info(f"Started Xvfb on {display}")
        return proc
    except FileNotFoundError:
        logger.warning("Xvfb not found, falling back to headless")
        return None


def load_accounts(filepath: str) -> List[Tuple[str, str]]:
    accounts = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            for sep in [':', '\t', '|']:
                parts = line.split(sep, 1)
                if len(parts) == 2:
                    email, password = parts[0].strip(), parts[1].strip()
                    if email and password:
                        accounts.append((email, password))
                    break
    return accounts


def load_harvested_emails() -> Set[str]:
    if not KEYS_FILE.exists():
        return set()
    try:
        keys = json.loads(KEYS_FILE.read_text())
        return {item['email'] for item in keys if item.get('email')}
    except Exception:
        return set()


def detect_rate_limit(page_content: str) -> bool:
    content_lower = page_content.lower()
    return any(signal in content_lower for signal in RATE_LIMIT_SIGNALS)


async def handle_rate_limit(worker_id: int):
    if rate_limit_event.is_set():
        rate_limit_event.clear()
        logger.warning(f"[W{worker_id}] RATE LIMIT — pausing all workers 5 min")
        await asyncio.sleep(300)
        rate_limit_event.set()
        logger.info(f"[W{worker_id}] Rate limit cooldown done")
    else:
        await rate_limit_event.wait()


async def block_resources(route):
    req = route.request
    if req.resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return
    url_lower = req.url.lower()
    if any(pattern in url_lower for pattern in BLOCKED_URL_PATTERNS):
        await route.abort()
        return
    await route.continue_()


async def google_login(page: Page, email: str, password: str, worker_id: int = 0) -> bool:
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=15000)
        await asyncio.sleep(2)

        try:
            body_text = await page.text_content('body') or ''
            if detect_rate_limit(body_text):
                await handle_rate_limit(worker_id)
                return False
        except Exception:
            pass

        url = page.url
        if 'oauthchooseaccount' in url or 'accountchooser' in url:
            logger.info(f"[{email}] Account picker, selecting...")
            await page.evaluate(f"""() => {{
                const els = document.querySelectorAll('[data-identifier="{email}"], [data-email="{email}"]');
                for (const el of els) {{ if (el.offsetParent) {{ el.click(); return; }} }}
                for (const el of document.querySelectorAll('li, div[role="link"], div[tabindex]')) {{
                    if (el.offsetParent === null) continue;
                    if ((el.textContent||'').includes('{email}')) {{ el.click(); return; }}
                }}
            }}""")
            await asyncio.sleep(3)
            if 'codebuddy.ai' in page.url:
                return True

        try:
            await page.wait_for_selector('input[type="email"]', timeout=15000)
        except Exception:
            if 'codebuddy.ai' in page.url:
                return True
            return False

        await asyncio.sleep(random.uniform(0.3, 0.8))
        email_input = page.locator('input[type="email"]')
        await human_type(page, email_input, email)
        await asyncio.sleep(random.uniform(0.2, 0.5))

        next_btn = await page.query_selector('#identifierNext')
        if next_btn:
            await human_move_and_click(page, next_btn)
        else:
            await page.keyboard.press('Enter')

        await asyncio.sleep(3)

        try:
            body_text = await page.text_content('body') or ''
            if detect_rate_limit(body_text):
                await handle_rate_limit(worker_id)
                return False
        except Exception:
            pass

        try:
            await page.wait_for_selector('input[type="password"]', timeout=15000)
        except Exception:
            try:
                await page.wait_for_selector('input[name="Passwd"]', timeout=5000)
            except Exception:
                if 'codebuddy.ai' in page.url:
                    return True
                logger.error(f"[{email}] Password field not found")
                return False

        await asyncio.sleep(random.uniform(0.3, 0.8))
        pwd_locator = page.locator('input[type="password"]')
        if await pwd_locator.count() == 0:
            pwd_locator = page.locator('input[name="Passwd"]')
        if await pwd_locator.count() == 0:
            return False

        await human_type(page, pwd_locator.first, password)
        await asyncio.sleep(random.uniform(0.2, 0.5))

        pwd_next = await page.query_selector('#passwordNext')
        if pwd_next:
            await human_move_and_click(page, pwd_next)
        else:
            await page.keyboard.press('Enter')

        await asyncio.sleep(4)

        error_el = await page.query_selector('div[aria-live="assertive"]')
        if error_el:
            text = await error_el.text_content()
            if text and ('wrong' in text.lower() or 'couldn' in text.lower()):
                logger.error(f"[{email}] Google: {text.strip()[:80]}")
                return False

        for _ in range(12):
            await asyncio.sleep(2)
            url = page.url

            if 'codebuddy.ai' in url:
                return True

            if '/challenge/' in url:
                logger.warning(f"[{email}] Google challenge detected")
                return False

            if 'oauthchooseaccount' in url or 'accountchooser' in url:
                await page.evaluate(f"""() => {{
                    const els = document.querySelectorAll('[data-identifier="{email}"], [data-email="{email}"]');
                    for (const el of els) {{ if (el.offsetParent) {{ el.click(); return; }} }}
                    for (const el of document.querySelectorAll('li, div[role="link"]')) {{
                        if (el.offsetParent === null) continue;
                        if ((el.textContent||'').includes('{email}')) {{ el.click(); return; }}
                    }}
                }}""")
                await asyncio.sleep(3)
                continue

            if any(x in url for x in ['/speedbump', 'consent', '/signin/oauth', 'workspacetermsofservice']):
                await page.evaluate("""() => {
                    const kw = ['allow', 'continue', 'accept', 'i agree', 'i understand', 'confirm'];
                    for (const btn of document.querySelectorAll('button, input[type="submit"], div[role="button"]')) {
                        if (btn.offsetParent === null) continue;
                        const txt = (btn.value || btn.textContent || '').toLowerCase().trim();
                        if (kw.some(k => txt.includes(k))) { btn.click(); return; }
                    }
                    const buttons = [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null);
                    if (buttons.length > 0) buttons[buttons.length - 1].click();
                }""")
                await asyncio.sleep(3)
                continue

            for sel in ['#submit_approve_access', 'button:has-text("Allow")', 'button:has-text("Continue")']:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(3)
                        break
                except Exception:
                    continue

        return 'codebuddy.ai' in page.url

    except Exception as e:
        if 'destroyed' in str(e).lower() or 'navigation' in str(e).lower():
            return True
        logger.error(f"[{email}] OAuth error: {str(e)[:100]}")
        return False


async def browser_get_cookies(
    browser: Browser, email: str, password: str, worker_id: int = 0, proxy: Optional[Dict] = None
) -> Optional[Dict[str, str]]:
    profile_dir = PROFILES_DIR / email.split('@')[0]
    profile_dir.mkdir(parents=True, exist_ok=True)
    state_path = profile_dir / "state.json"

    context_opts: Dict[str, Any] = {
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'viewport': random_viewport(),
        'locale': 'en-US',
        'timezone_id': 'Asia/Singapore',
        'color_scheme': 'light',
    }

    if state_path.exists():
        try:
            context_opts['storage_state'] = str(state_path)
        except Exception:
            pass

    if proxy:
        context_opts['proxy'] = proxy

    context = await browser.new_context(**context_opts)

    stealth = Stealth(
        navigator_platform_override='Win32',
        webgl_vendor_override='Google Inc. (NVIDIA)',
        webgl_renderer_override='ANGLE (NVIDIA, NVIDIA GeForce RTX 3060)',
    )
    await stealth.apply_stealth_async(context)

    page = await context.new_page()
    await page.add_init_script(STEALTH_INIT_SCRIPT)
    await page.route("**/*", block_resources)

    try:
        login_url = f"{CODEBUDDY_BASE}/auth/realms/copilot/protocol/openid-connect/auth?client_id=console&scope=openid%20offline_access&response_type=code&redirect_uri=https%3A%2F%2Fwww.codebuddy.ai%2Flogin%2Fselect"
        await page.goto(login_url, wait_until='domcontentloaded', timeout=20000)
        await asyncio.sleep(2)

        for _ in range(10):
            btn_count = await page.evaluate('() => document.querySelectorAll("button, a, [role=button]").length')
            if btn_count > 0:
                break
            await asyncio.sleep(1)

        try:
            login_tab = page.get_by_text("Log in")
            if await login_tab.count() > 0:
                await login_tab.first.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        google_btn = None
        for pattern in ["Log in with Google", "Sign in with Google", "Sign up with Google", "Continue with Google", "Google"]:
            try:
                btn = page.get_by_role("button", name=pattern)
                if await btn.count() > 0:
                    google_btn = btn.first
                    break
            except Exception:
                continue

        if not google_btn:
            for pattern in ["Log in with Google", "Google"]:
                try:
                    btn = page.get_by_text(pattern)
                    if await btn.count() > 0:
                        google_btn = btn.first
                        break
                except Exception:
                    continue

        if not google_btn:
            for frame in page.frames:
                if 'auth/realms' in frame.url or 'openid-connect' in frame.url:
                    try:
                        lt = frame.get_by_text("Log in")
                        if await lt.count() > 0:
                            await lt.first.click()
                            await asyncio.sleep(1)
                    except Exception:
                        pass
                    for pattern in ["Log in with Google", "Sign in with Google", "Google"]:
                        try:
                            btn = frame.get_by_role("button", name=pattern)
                            if await btn.count() > 0:
                                google_btn = btn.first
                                break
                        except Exception:
                            continue
                    if not google_btn:
                        for pattern in ["Log in with Google", "Google"]:
                            try:
                                btn = frame.get_by_text(pattern)
                                if await btn.count() > 0:
                                    google_btn = btn.first
                                    break
                            except Exception:
                                continue
                    break

        if not google_btn:
            logger.error(f"[{email}] No Google button found")
            return None

        await google_btn.click()
        await asyncio.sleep(2)

        for pattern in ["Confirm", "Agree", "Accept", "I agree"]:
            for target in [page] + [f for f in page.frames if f != page.main_frame]:
                try:
                    if hasattr(target, 'get_by_role'):
                        btn = target.get_by_role("button", name=pattern)
                        if await btn.count() > 0:
                            await btn.first.click()
                            await asyncio.sleep(2)
                            break
                except Exception:
                    continue

        google_page = None
        for _ in range(10):
            await asyncio.sleep(1)
            for p in context.pages:
                if 'accounts.google.com' in p.url:
                    google_page = p
                    break
            if google_page:
                break

        if not google_page:
            if 'accounts.google.com' in page.url:
                google_page = page
            else:
                logger.error(f"[{email}] Google page not found after click")
                return None

        login_ok = await google_login(google_page, email, password, worker_id)
        if not login_ok:
            return None

        codebuddy_page = None
        for _ in range(20):
            await asyncio.sleep(2)
            for p in context.pages:
                try:
                    if p.url.startswith('https://www.codebuddy.ai') and 'auth/realms' not in p.url:
                        codebuddy_page = p
                        break
                except Exception:
                    continue

            if codebuddy_page:
                break

            for p in context.pages:
                try:
                    purl = p.url
                    if 'accounts.google.com' not in purl:
                        continue
                    if any(x in purl for x in ['workspacetermsofservice', 'speedbump', 'consent', '/signin/oauth']):
                        await p.evaluate("""() => {
                            const kw = ['allow', 'continue', 'accept', 'i agree', 'i understand'];
                            for (const btn of document.querySelectorAll('button, input[type="submit"], div[role="button"]')) {
                                if (btn.offsetParent === null) continue;
                                const txt = (btn.value || btn.textContent || '').toLowerCase().trim();
                                if (kw.some(k => txt.includes(k))) { btn.click(); return; }
                            }
                        }""")
                        await asyncio.sleep(3)
                except Exception:
                    continue

        if not codebuddy_page:
            logger.error(f"[{email}] Timeout waiting for CodeBuddy")
            return None

        await asyncio.sleep(3)

        for _ in range(10):
            url = codebuddy_page.url
            if '/home' in url or '/register' in url or '/profile' in url:
                break
            await asyncio.sleep(1)

        try:
            await context.storage_state(path=str(state_path))
        except Exception:
            pass

        cookies = await context.cookies()
        cookie_dict = {}
        for c in cookies:
            domain = c.get('domain', '')
            if 'codebuddy.ai' in domain or domain == '' or domain == 'www.codebuddy.ai':
                cookie_dict[c['name']] = c['value']

        if not cookie_dict:
            logger.error(f"[{email}] No cookies extracted")
            return None

        logger.info(f"[{email}] Got {len(cookie_dict)} cookies")
        return cookie_dict

    except Exception as e:
        logger.error(f"[{email}] Browser error: {str(e)[:120]}")
        return None
    finally:
        await context.close()


def build_headers(cookies: Dict[str, str], referer: str = "") -> Dict[str, str]:
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Cookie': cookie_str,
        'Origin': 'https://www.codebuddy.ai',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    }
    if referer:
        headers['Referer'] = referer
    return headers


async def http_complete_and_get_key(cookies: Dict[str, str], email: str) -> Optional[str]:
    headers = build_headers(cookies, f"{CODEBUDDY_BASE}/login/select")

    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        resp = await client.post(
            f"{CODEBUDDY_BASE}/console/login/enterprise?state=",
            headers=headers,
        )
        if resp.status_code != 200:
            logger.error(f"[{email}] Enterprise login failed: {resp.status_code}")
            return None
        data = resp.json()
        if data.get('code') != 0:
            logger.error(f"[{email}] Enterprise login error: {data}")
            return None

        headers = build_headers(cookies, f"{CODEBUDDY_BASE}/register/user/complete")

        resp = await client.post(
            f"{CODEBUDDY_BASE}/console/login/account",
            json=REGION_PAYLOAD,
            headers=headers,
        )
        if resp.status_code == 200 and resp.json().get('code') == 0:
            logger.info(f"[{email}] Region set: Singapore")
        else:
            logger.info(f"[{email}] Region already set or failed (continuing)")

        await client.post(f"{CODEBUDDY_BASE}/billing/ide/trial", headers=headers)

        key_name = f"{email.split('@')[0][:12]}_{int(time.time()) % 10000}"
        headers = build_headers(cookies, f"{CODEBUDDY_BASE}/profile/keys")

        resp = await client.post(
            f"{CODEBUDDY_BASE}/console/api/client/v1/api-keys",
            json={"name": key_name, "expire_in_days": 365, "user_enterprise_id": "personal-edition-user-id"},
            headers=headers,
        )

        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 0 and data.get('data', {}).get('key'):
                return data['data']['key']

        if resp.status_code == 400 and 'name exists' in resp.text:
            list_resp = await client.get(
                f"{CODEBUDDY_BASE}/console/api/client/v1/api-keys?page=1&page_size=10&user_enterprise_id=personal-edition-user-id",
                headers=headers,
            )
            if list_resp.status_code == 200:
                items = list_resp.json().get('data', {}).get('items', [])
                if items:
                    return f"EXISTING:{items[0].get('masked_key', 'unknown')}"

        logger.error(f"[{email}] Key creation failed: {resp.status_code} {resp.text[:150]}")
        return None


async def save_key(email: str, api_key: str):
    async with file_lock:
        keys = []
        if KEYS_FILE.exists():
            try:
                keys = json.loads(KEYS_FILE.read_text())
            except Exception:
                keys = []
        keys.append({"email": email, "api_key": api_key, "created_at": int(time.time())})
        KEYS_FILE.write_text(json.dumps(keys, indent=2))


async def save_state(stats: HarvestStats, last_index: int):
    async with file_lock:
        state = {
            "completed": [k['email'] for k in stats.keys],
            "failed": stats.errors,
            "last_index": last_index,
            "timestamp": int(time.time()),
        }
        STATE_FILE.write_text(json.dumps(state, indent=2))


async def try_cookie_first(email: str) -> Optional[Dict[str, str]]:
    profile_dir = PROFILES_DIR / email.split('@')[0]
    state_path = profile_dir / "state.json"

    if not state_path.exists():
        return None

    try:
        state = json.loads(state_path.read_text())
    except Exception:
        return None

    cookies_list = state.get('cookies', [])
    if not cookies_list:
        return None

    cookie_dict = {}
    for c in cookies_list:
        domain = c.get('domain', '')
        if 'codebuddy.ai' in domain or domain == '' or domain == 'www.codebuddy.ai':
            cookie_dict[c['name']] = c['value']

    if not cookie_dict:
        return None

    headers = build_headers(cookie_dict, f"{CODEBUDDY_BASE}/home")
    try:
        async with httpx.AsyncClient(verify=False, timeout=15) as client:
            resp = await client.get(f"{CODEBUDDY_BASE}/billing/ide/usage", headers=headers)
            if resp.status_code == 200 and resp.json().get('code') == 0:
                logger.info(f"[{email}] Saved cookies still valid, skipping browser")
                return cookie_dict
    except Exception:
        pass

    return None


async def check_key_health(api_key: str) -> bool:
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            resp = await client.get(f"{CODEBUDDY_BASE}/billing/ide/usage", headers=headers)
            return resp.status_code == 200
    except Exception:
        return False


async def browser_worker(
    worker_id: int,
    browser: Browser,
    input_queue: asyncio.Queue,
    cookie_queue: asyncio.Queue,
    stats: HarvestStats,
    retries: int,
    proxies: List[str],
    stagger: float,
):
    if stagger > 0 and worker_id > 0:
        await asyncio.sleep(stagger * worker_id)

    while True:
        try:
            item = input_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        email, password = item
        await rate_limit_event.wait()

        cached_cookies = await try_cookie_first(email)
        if cached_cookies:
            await cookie_queue.put((email, cached_cookies))
            input_queue.task_done()
            continue

        success = False
        for attempt in range(1, retries + 1):
            proxy = parse_proxy(random.choice(proxies)) if proxies else None
            logger.info(f"[BW{worker_id}] {email} (attempt {attempt}/{retries})")

            try:
                cookies = await browser_get_cookies(browser, email, password, worker_id, proxy)
                if cookies:
                    await cookie_queue.put((email, cookies))
                    success = True
                    break
                else:
                    if attempt < retries:
                        await stats.record_retry()
                        await asyncio.sleep(3 * attempt)
            except Exception as e:
                logger.error(f"[BW{worker_id}] {email} error: {str(e)[:80]}")
                if attempt < retries:
                    await stats.record_retry()
                    await asyncio.sleep(3 * attempt)

        if not success:
            await stats.record_failure(email, "browser_login_failed")

        input_queue.task_done()
        await asyncio.sleep(random.uniform(1, 3))


async def http_worker(
    worker_id: int,
    cookie_queue: asyncio.Queue,
    stats: HarvestStats,
    done_event: asyncio.Event,
):
    while True:
        try:
            email, cookies = await asyncio.wait_for(cookie_queue.get(), timeout=5)
        except asyncio.TimeoutError:
            if done_event.is_set() and cookie_queue.empty():
                break
            continue

        logger.info(f"[HW{worker_id}] {email} → creating key via HTTP")

        try:
            api_key = await http_complete_and_get_key(cookies, email)
            if api_key:
                await save_key(email, api_key)
                await stats.record_success(email, api_key)
                logger.info(f"[HW{worker_id}] {email} ✓ {api_key[:25]}...")
            else:
                await stats.record_failure(email, "key_creation_failed")
        except Exception as e:
            logger.error(f"[HW{worker_id}] {email} HTTP error: {str(e)[:80]}")
            await stats.record_failure(email, f"http_error:{str(e)[:50]}")

        cookie_queue.task_done()


def get_memory_usage_mb() -> float:
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / (1024 * 1024) if sys.platform == 'linux' else usage.ru_maxrss / (1024 * 1024)
    except Exception:
        return 0


async def adaptive_concurrency_monitor(input_queue: asyncio.Queue, max_ram_mb: float = 4096):
    while not input_queue.empty():
        ram = get_memory_usage_mb()
        if ram > max_ram_mb * 0.85:
            if rate_limit_event.is_set():
                logger.warning(f"RAM {ram:.0f}MB > {max_ram_mb * 0.85:.0f}MB threshold — throttling")
                rate_limit_event.clear()
                await asyncio.sleep(30)
                rate_limit_event.set()
        await asyncio.sleep(10)


async def main():
    parser = argparse.ArgumentParser(description='CodeBuddy harvester v2 — lightweight pipeline')
    parser.add_argument('--accounts', default='accounts.txt', help='Accounts file (email:password per line)')
    parser.add_argument('--browser-workers', type=int, default=2, help='Browser workers for OAuth (default: 2, keep low!)')
    parser.add_argument('--http-workers', type=int, default=6, help='HTTP workers for key creation (default: 6, lightweight)')
    parser.add_argument('--retries', type=int, default=2, help='Retries per account (default: 2)')
    parser.add_argument('--stagger', type=float, default=3.0, help='Stagger between browser workers (seconds)')
    parser.add_argument('--headed', action='store_true', default=False, help='Show browser (debug)')
    parser.add_argument('--xvfb', action='store_true', default=False, help='Xvfb headed mode (Linux stealth)')
    parser.add_argument('--proxy', action='store_true', default=False, help='Enable proxy rotation from proxies.txt')
    parser.add_argument('--start', type=int, default=0, help='Start from account index N')
    parser.add_argument('--limit', type=int, default=0, help='Process only N accounts (0=all)')
    parser.add_argument('--no-skip', action='store_true', default=False, help='Process all even if already harvested')
    parser.add_argument('--resume', action='store_true', default=False, help='Resume from last state')
    parser.add_argument('--max-ram', type=int, default=4096, help='Max RAM in MB before throttling (default: 4096)')
    parser.add_argument('--auto-retry', action='store_true', default=False, help='Auto-retry failed accounts after completion')
    args = parser.parse_args()

    accounts_file = Path(args.accounts)
    if not accounts_file.exists():
        logger.error(f"Accounts file not found: {accounts_file}")
        sys.exit(1)

    accounts = load_accounts(str(accounts_file))
    if not accounts:
        logger.error("No valid accounts found")
        sys.exit(1)

    if args.resume and STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            idx = state.get('last_index', 0)
            if idx > 0:
                accounts = accounts[idx:]
                logger.info(f"Resuming from index {idx}")
        except Exception:
            pass

    if args.start > 0:
        accounts = accounts[args.start:]
    if args.limit > 0:
        accounts = accounts[:args.limit]

    if not args.no_skip:
        already_done = load_harvested_emails()
        if already_done:
            before = len(accounts)
            accounts = [(e, p) for e, p in accounts if e not in already_done]
            skipped = before - len(accounts)
            if skipped > 0:
                logger.info(f"Skipped {skipped} already-harvested accounts")

    if not accounts:
        logger.info("Nothing to process")
        sys.exit(0)

    xvfb_proc = start_xvfb() if args.xvfb else None
    proxies = load_proxies() if args.proxy else []

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    if FAILED_FILE.exists() and not args.resume:
        FAILED_FILE.unlink()

    use_headed = args.headed or args.xvfb
    logger.info(f"Accounts: {len(accounts)} | Browser workers: {args.browser_workers} | HTTP workers: {args.http_workers}")
    logger.info(f"Mode: {'xvfb-headed' if args.xvfb else ('headed' if args.headed else 'headless')} | Proxy: {'on' if proxies else 'off'}")

    stats = HarvestStats(total=len(accounts))
    start_time = time.time()

    input_queue: asyncio.Queue = asyncio.Queue()
    cookie_queue: asyncio.Queue = asyncio.Queue()
    browser_done = asyncio.Event()

    for acc in accounts:
        await input_queue.put(acc)

    async with async_playwright() as p:
        launch_kwargs = {
            'headless': not use_headed,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-infobars',
                '--disable-gpu',
                '--window-size=1280,720',
            ],
        }
        try:
            browser = await p.chromium.launch(channel='chrome', **launch_kwargs)
            logger.info("Using Chrome")
        except Exception:
            browser = await p.chromium.launch(**launch_kwargs)
            logger.info("Using Chromium")

        http_tasks = [
            asyncio.create_task(http_worker(i, cookie_queue, stats, browser_done))
            for i in range(args.http_workers)
        ]

        browser_tasks = [
            asyncio.create_task(browser_worker(
                i, browser, input_queue, cookie_queue, stats, args.retries, proxies, args.stagger
            ))
            for i in range(args.browser_workers)
        ]

        monitor_task = asyncio.create_task(adaptive_concurrency_monitor(input_queue, args.max_ram))

        await asyncio.gather(*browser_tasks)
        browser_done.set()
        monitor_task.cancel()

        await cookie_queue.join()
        for t in http_tasks:
            t.cancel()

        await browser.close()

    elapsed = time.time() - start_time

    if xvfb_proc:
        xvfb_proc.terminate()

    await save_state(stats, args.start + len(accounts))

    if stats.failed == 0 and STATE_FILE.exists():
        STATE_FILE.unlink()

    summary = (
        f"HARVEST v2 COMPLETE ({elapsed:.1f}s)\n"
        f"✓ {stats.success} | ✗ {stats.failed} | ↻ {stats.retried}\n"
        f"Speed: {stats.success / max(elapsed, 1) * 60:.1f} keys/min"
    )

    print(f"\n{'='*60}")
    print(summary)
    print(f"{'='*60}")
    if stats.keys:
        print(f"\nKeys:")
        for item in stats.keys:
            print(f"  {item['email']}: {item['key'][:30]}...")
    if stats.errors:
        print(f"\nFailed ({FAILED_FILE}):")
        for e in stats.errors[:10]:
            print(f"  {e}")
        if len(stats.errors) > 10:
            print(f"  ... and {len(stats.errors) - 10} more")
    print(f"\nKeys: {KEYS_FILE}")

    await send_telegram(f"🤖 <b>CodeBuddy Harvest</b>\n\n{summary}")

    if args.auto_retry and stats.errors and FAILED_FILE.exists():
        logger.info(f"\n--- AUTO-RETRY: {len(stats.errors)} failed accounts in 60s ---")
        await asyncio.sleep(60)
        retry_accounts = load_accounts(str(FAILED_FILE))
        if retry_accounts:
            logger.info(f"Retrying {len(retry_accounts)} accounts...")
            retry_stats = HarvestStats(total=len(retry_accounts))
            retry_input: asyncio.Queue = asyncio.Queue()
            retry_cookies: asyncio.Queue = asyncio.Queue()
            retry_done = asyncio.Event()

            for acc in retry_accounts:
                await retry_input.put(acc)

            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(channel='chrome', headless=not use_headed, args=launch_kwargs['args'])
                except Exception:
                    browser = await p.chromium.launch(headless=not use_headed, args=launch_kwargs['args'])

                r_http = [asyncio.create_task(http_worker(i, retry_cookies, retry_stats, retry_done)) for i in range(args.http_workers)]
                r_browser = [asyncio.create_task(browser_worker(i, browser, retry_input, retry_cookies, retry_stats, args.retries, proxies, args.stagger)) for i in range(args.browser_workers)]

                await asyncio.gather(*r_browser)
                retry_done.set()
                await retry_cookies.join()
                for t in r_http:
                    t.cancel()
                await browser.close()

            retry_summary = f"↻ RETRY: ✓ {retry_stats.success} | ✗ {retry_stats.failed}"
            print(f"\n{retry_summary}")
            await send_telegram(f"↻ <b>Auto-Retry</b>\n{retry_summary}")


if __name__ == '__main__':
    asyncio.run(main())
