"""
Bulk CodeBuddy API key harvester (concurrent).
Flow: Playwright Google OAuth → extract cookies → HTTP registration + API key creation.

Usage:
    python bulk_harvest.py [--accounts accounts.txt] [--workers 4] [--retries 2]
    python bulk_harvest.py --headed  # debug mode with visible browser
"""
import os
import sys
import json
import time
import asyncio
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List, Set
from dataclasses import dataclass, field

import httpx
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from playwright_stealth import Stealth

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

file_lock = asyncio.Lock()
rate_limit_event = asyncio.Event()
rate_limit_event.set()  # starts unblocked

CODEBUDDY_BASE = "https://www.codebuddy.ai"
CREDS_DIR = Path(__file__).parent / ".codebuddy_creds"
KEYS_FILE = Path(__file__).parent / "harvested_keys.json"
FAILED_FILE = Path(__file__).parent / "failed_accounts.txt"
STATE_FILE = Path(__file__).parent / ".harvest_state.json"

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

    async def record_failure(self, email: str):
        async with self.lock:
            self.failed += 1
            self.errors.append(email)
            self._print_progress()
            await self._save_failed(email)

    async def record_retry(self):
        async with self.lock:
            self.retried += 1

    async def record_skip(self, email: str):
        async with self.lock:
            self.skipped += 1

    def _print_progress(self):
        done = self.success + self.failed
        pct = (done / self.total * 100) if self.total > 0 else 0
        logger.info(f"[PROGRESS] {done}/{self.total} ({pct:.0f}%) | ✓ {self.success} ✗ {self.failed} ⊘ {self.skipped}")

    async def _save_failed(self, email: str):
        async with file_lock:
            with open(FAILED_FILE, 'a') as f:
                f.write(f"{email}\n")


def load_harvested_emails() -> Set[str]:
    if not KEYS_FILE.exists():
        return set()
    try:
        keys = json.loads(KEYS_FILE.read_text())
        return {item['email'] for item in keys if item.get('email')}
    except Exception:
        return set()


def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"completed": [], "failed": [], "last_index": 0}


async def save_state(stats: HarvestStats, last_index: int):
    async with file_lock:
        state = {
            "completed": [k['email'] for k in stats.keys],
            "failed": stats.errors,
            "last_index": last_index,
            "timestamp": int(time.time()),
        }
        STATE_FILE.write_text(json.dumps(state, indent=2))


def detect_rate_limit(page_content: str) -> bool:
    content_lower = page_content.lower()
    return any(signal in content_lower for signal in RATE_LIMIT_SIGNALS)


async def handle_rate_limit(worker_id: int):
    if rate_limit_event.is_set():
        rate_limit_event.clear()
        logger.warning(f"[W{worker_id}] ⚠️  RATE LIMIT DETECTED — pausing ALL workers for 5 minutes")
        await asyncio.sleep(300)
        rate_limit_event.set()
        logger.info(f"[W{worker_id}] ✓ Rate limit cooldown complete, resuming")
    else:
        logger.info(f"[W{worker_id}] Waiting for rate limit cooldown...")
        await rate_limit_event.wait()


def load_accounts(filepath: str) -> List[Tuple[str, str]]:
    accounts = []
    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Support both email:password and email\tpassword formats
            for sep in [':', '\t']:
                parts = line.split(sep, 1)
                if len(parts) == 2:
                    email, password = parts[0].strip(), parts[1].strip()
                    if email and password:
                        accounts.append((email, password))
                    break
            else:
                logger.warning(f"Line {line_num}: invalid format, skipping")
    return accounts


async def google_login(page: Page, email: str, password: str, worker_id: int = 0) -> bool:
    try:
        for _ in range(10):
            try:
                await page.wait_for_load_state('domcontentloaded', timeout=5000)
                break
            except Exception:
                await asyncio.sleep(1)

        await asyncio.sleep(2)
        logger.info(f"[{email}] Google page: {page.url[:80]}")

        # Rate limit check on page content
        try:
            body_text = await page.text_content('body') or ''
            if detect_rate_limit(body_text):
                logger.warning(f"[{email}] Rate limit detected on Google login page")
                await handle_rate_limit(worker_id)
                return False
        except Exception:
            pass

        await page.wait_for_selector('input[type="email"]', timeout=20000)
        await asyncio.sleep(1)
        email_input = page.locator('input[type="email"]')
        await email_input.click()
        await email_input.press_sequentially(email, delay=50)
        await asyncio.sleep(0.5)

        next_btn = await page.query_selector('#identifierNext') or await page.query_selector('button:has-text("Next")')
        if next_btn:
            await next_btn.click()
        else:
            await page.keyboard.press('Enter')

        await asyncio.sleep(3)

        # Rate limit check after email submit
        try:
            body_text = await page.text_content('body') or ''
            if detect_rate_limit(body_text):
                logger.warning(f"[{email}] Rate limit after email submit")
                await handle_rate_limit(worker_id)
                return False
        except Exception:
            pass

        try:
            await page.wait_for_selector('input[type="password"]', timeout=20000)
        except Exception:
            await page.wait_for_selector('input[name="Passwd"], input[name="password"]', timeout=10000)

        await asyncio.sleep(1)
        pwd_locator = page.locator('input[type="password"]')
        if await pwd_locator.count() == 0:
            pwd_locator = page.locator('input[name="Passwd"]')
        if await pwd_locator.count() == 0:
            logger.error(f"[{email}] Password input not found")
            return False

        await pwd_locator.first.click()
        await pwd_locator.first.press_sequentially(password, delay=50)
        await asyncio.sleep(0.5)

        pwd_next = await page.query_selector('#passwordNext') or await page.query_selector('button:has-text("Next")')
        if pwd_next:
            await pwd_next.click()
        else:
            await page.keyboard.press('Enter')

        await asyncio.sleep(5)

        error_el = await page.query_selector('div[aria-live="assertive"]')
        if error_el:
            text = await error_el.text_content()
            if text and ('wrong' in text.lower() or 'couldn' in text.lower()):
                logger.error(f"[{email}] Google login error: {text.strip()[:100]}")
                return False

        for _ in range(10):
            await asyncio.sleep(2)
            if 'codebuddy.ai' in page.url:
                logger.info(f"[{email}] Redirected to CodeBuddy")
                return True

            for sel in ['#submit_approve_access', 'button:has-text("Allow")', 'button:has-text("Continue")']:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        logger.info(f"[{email}] Clicking consent: {sel}")
                        await btn.click()
                        await asyncio.sleep(3)
                        break
                except Exception:
                    continue

        return True
    except Exception as e:
        if 'destroyed' in str(e).lower() or 'navigation' in str(e).lower():
            logger.info(f"[{email}] Navigation race (likely success)")
            return True
        logger.error(f"[{email}] Google login failed: {e}")
        return False


async def do_browser_login(browser: Browser, email: str, password: str, worker_id: int = 0) -> Optional[Dict[str, str]]:
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 720},
        locale='en-US',
    )

    stealth = Stealth(
        navigator_platform_override='MacIntel',
        webgl_vendor_override='Apple',
        webgl_renderer_override='Apple M1',
    )
    await stealth.apply_stealth_async(context)

    page = await context.new_page()

    try:
        # Go to CodeBuddy login page directly
        login_url = f"{CODEBUDDY_BASE}/auth/realms/copilot/protocol/openid-connect/auth?client_id=console&scope=openid%20offline_access&response_type=code&redirect_uri=https%3A%2F%2Fwww.codebuddy.ai%2Flogin%2Fselect"
        await page.goto(login_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        # Wait for page to render
        for attempt in range(15):
            await asyncio.sleep(2)
            btn_count = await page.evaluate('() => document.querySelectorAll("button, a, [role=button]").length')
            if btn_count > 0:
                logger.info(f"[{email}] Login page rendered, {btn_count} buttons")
                break

        # Switch to "Log in" tab if available
        try:
            login_tab = page.get_by_text("Log in")
            if await login_tab.count() > 0:
                await login_tab.first.click()
                await asyncio.sleep(2)
        except Exception:
            pass

        # Find and click Google button
        google_btn = None
        for pattern in ["Log in with Google", "Sign in with Google", "Sign up with Google", "Continue with Google", "Google"]:
            try:
                btn = page.get_by_role("button", name=pattern)
                if await btn.count() > 0:
                    google_btn = btn.first
                    logger.info(f"[{email}] Found: '{pattern}'")
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
            # Check if content is in iframe
            for frame in page.frames:
                if 'auth/realms' in frame.url or 'openid-connect' in frame.url:
                    logger.info(f"[{email}] Found login iframe: {frame.url[:80]}")
                    # Switch to "Log in" tab in iframe
                    try:
                        login_tab = frame.get_by_text("Log in")
                        if await login_tab.count() > 0:
                            await login_tab.first.click()
                            await asyncio.sleep(2)
                    except Exception:
                        pass

                    for pattern in ["Log in with Google", "Sign in with Google", "Google"]:
                        try:
                            btn = frame.get_by_role("button", name=pattern)
                            if await btn.count() > 0:
                                google_btn = btn.first
                                logger.info(f"[{email}] Found in iframe: '{pattern}'")
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
            await page.screenshot(path=f"/tmp/cb_no_google_{email.split('@')[0]}.png")
            return None

        await google_btn.click()
        await asyncio.sleep(3)

        # Handle Terms & Conditions
        for pattern in ["Confirm", "确认", "Agree", "Accept", "I agree"]:
            for target in [page] + [f for f in page.frames if f != page.main_frame]:
                try:
                    if hasattr(target, 'get_by_role'):
                        btn = target.get_by_role("button", name=pattern)
                        if await btn.count() > 0:
                            logger.info(f"[{email}] Confirming terms: '{pattern}'")
                            await btn.first.click()
                            await asyncio.sleep(3)
                            break
                except Exception:
                    continue

        # Wait for Google OAuth page
        google_page = None
        for _ in range(15):
            await asyncio.sleep(2)
            for p in context.pages:
                if 'accounts.google.com' in p.url:
                    google_page = p
                    break
            if google_page:
                break

        if not google_page:
            # Check if main page navigated to Google
            if 'accounts.google.com' in page.url:
                google_page = page
            else:
                logger.error(f"[{email}] Google page not found")
                await page.screenshot(path=f"/tmp/cb_no_google_page_{email.split('@')[0]}.png")
                return None

        try:
            login_ok = await google_login(google_page, email, password, worker_id)
        except Exception as e:
            if 'destroyed' in str(e).lower():
                login_ok = True
            else:
                raise

        if not login_ok:
            return None

        for attempt in range(20):
            await asyncio.sleep(2)

            for p in context.pages:
                try:
                    purl = p.url
                    if purl.startswith('https://www.codebuddy.ai') and 'auth/realms' not in purl:
                        logger.info(f"[{email}] On CodeBuddy: {purl[:80]}")
                        break
                except Exception:
                    continue
            else:
                for p in context.pages:
                    try:
                        current_url = p.url
                        if 'accounts.google.com' not in current_url:
                            continue

                        # Handle Google Workspace Terms of Service
                        if 'workspacetermsofservice' in current_url or 'speedbump' in current_url:
                            for sel in ['button:has-text("Accept")', 'button:has-text("I understand")', 'input[type="submit"]', 'button:has-text("Agree")', 'button:has-text("Continue")']:
                                try:
                                    btn = await p.query_selector(sel)
                                    if btn and await btn.is_visible():
                                        logger.info(f"[{email}] Accepting Workspace ToS: '{sel}'")
                                        await btn.click()
                                        await asyncio.sleep(3)
                                        break
                                except Exception:
                                    continue
                            continue

                        for sel in ['#submit_approve_access', 'button:has-text("Continue")', 'button:has-text("Allow")']:
                            try:
                                btn = await p.query_selector(sel)
                                if btn and await btn.is_visible():
                                    logger.info(f"[{email}] Clicking consent '{sel}' on {current_url[:60]}")
                                    await btn.click()
                                    await asyncio.sleep(3)
                                    break
                            except Exception:
                                continue
                    except Exception:
                        continue
                continue
            break

        logger.info(f"[{email}] Waiting for CodeBuddy redirect...")
        codebuddy_page = None
        for _ in range(30):
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

        if not codebuddy_page:
            logger.error(f"[{email}] Timeout waiting for CodeBuddy redirect")
            return None

        logger.info(f"[{email}] On CodeBuddy: {codebuddy_page.url[:100]}")

        # Wait for the SPA to complete its internal login flow
        # It calls /console/login/enterprise internally and sets session cookies
        await asyncio.sleep(5)

        # If on /login/select, wait for it to redirect to /home or /register
        for _ in range(15):
            url = codebuddy_page.url
            if '/home' in url or '/register' in url or '/profile' in url:
                break
            await asyncio.sleep(2)

        await asyncio.sleep(3)
        logger.info(f"[{email}] Final page: {codebuddy_page.url[:100]}")

        # Now extract ALL cookies (including session cookies set by the SPA)
        cookies = await context.cookies()
        cookie_dict = {}
        for c in cookies:
            domain = c.get('domain', '')
            if 'codebuddy.ai' in domain or domain == '' or domain == 'www.codebuddy.ai':
                cookie_dict[c['name']] = c['value']

        logger.info(f"[{email}] Got {len(cookie_dict)} cookies: {list(cookie_dict.keys())}")
        if not cookie_dict:
            return None
        return cookie_dict

    except Exception as e:
        logger.error(f"[{email}] Browser login error: {e}")
        return None
    finally:
        await context.close()


async def http_get_access_token(cookies: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Call /console/login/enterprise to exchange session for accessToken."""
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Cookie': cookie_str,
        'Origin': 'https://www.codebuddy.ai',
        'Referer': 'https://www.codebuddy.ai/login/select',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    }

    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(
            f"{CODEBUDDY_BASE}/console/login/enterprise?state=",
            headers=headers,
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 0 and data.get('data', {}).get('accessToken'):
                return data['data']
    return None


async def http_complete_registration(cookies: Dict[str, str]) -> bool:
    """Complete registration by selecting region (Singapore)."""
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Cookie': cookie_str,
        'Origin': 'https://www.codebuddy.ai',
        'Referer': 'https://www.codebuddy.ai/register/user/complete',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    }

    async with httpx.AsyncClient(verify=False) as client:
        # Step 1: Submit region
        resp = await client.post(
            f"{CODEBUDDY_BASE}/console/login/account",
            json=REGION_PAYLOAD,
            headers=headers,
            timeout=30
        )
        logger.info(f"  Region submit: {resp.status_code} - {resp.text[:200]}")
        if resp.status_code != 200 or resp.json().get('code') != 0:
            return False

        # Step 2: Activate trial
        resp = await client.post(
            f"{CODEBUDDY_BASE}/billing/ide/trial",
            headers=headers,
            timeout=30
        )
        logger.info(f"  Trial activate: {resp.status_code} - {resp.text[:200]}")

        return True


async def http_create_api_key(cookies: Dict[str, str], email: str) -> Optional[str]:
    """Create an API key via HTTP API. Returns the full API key string."""
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Cookie': cookie_str,
        'Origin': 'https://www.codebuddy.ai',
        'Referer': 'https://www.codebuddy.ai/profile/keys',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    }

    key_name = f"{email.split('@')[0][:12]}_{int(time.time()) % 10000}"

    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(
            f"{CODEBUDDY_BASE}/console/api/client/v1/api-keys",
            json={
                "name": key_name,
                "expire_in_days": 365,
                "user_enterprise_id": "personal-edition-user-id"
            },
            headers=headers,
            timeout=30
        )

        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 0 and data.get('data', {}).get('key'):
                api_key = data['data']['key']
                logger.info(f"  API key created: {api_key[:20]}...")
                return api_key

        if resp.status_code == 400 and 'name exists' in resp.text:
            logger.info(f"  Key name exists, listing existing keys...")
            list_resp = await client.get(
                f"{CODEBUDDY_BASE}/console/api/client/v1/api-keys?page=1&page_size=10&user_enterprise_id=personal-edition-user-id",
                headers=headers,
                timeout=30
            )
            if list_resp.status_code == 200:
                list_data = list_resp.json()
                items = list_data.get('data', {}).get('items', [])
                if items:
                    logger.info(f"  Found {len(items)} existing key(s), account already set up")
                    return f"EXISTING:{items[0].get('masked_key', 'unknown')}"

        logger.error(f"  API key creation failed: {resp.status_code} - {resp.text[:300]}")
        return None


async def save_key(email: str, api_key: str):
    async with file_lock:
        keys = []
        if KEYS_FILE.exists():
            try:
                keys = json.loads(KEYS_FILE.read_text())
            except Exception:
                keys = []

        keys.append({
            "email": email,
            "api_key": api_key,
            "created_at": int(time.time()),
        })

        KEYS_FILE.write_text(json.dumps(keys, indent=2))


async def save_credential_file(email: str, api_key: str, token_data: Optional[Dict] = None):
    async with file_lock:
        CREDS_DIR.mkdir(parents=True, exist_ok=True)

        cred = {
            "bearer_token": api_key,
            "user_id": email,
            "created_at": int(time.time()),
        }
        if token_data:
            cred["access_token"] = token_data.get("accessToken", "")
            cred["refresh_token"] = token_data.get("refreshToken", "")

        safe_name = "".join(c for c in email.split('@')[0] if c.isalnum() or c in "._-")[:20]
        filepath = CREDS_DIR / f"codebuddy_{safe_name}_{int(time.time())}.json"
        filepath.write_text(json.dumps(cred, indent=2))
        return filepath.name


async def harvest_single(browser: Browser, email: str, password: str, worker_id: int = 0) -> Optional[str]:
    logger.info(f"[{email}] Step 1/5: Browser Google OAuth")
    cookies = await do_browser_login(browser, email, password, worker_id)
    if not cookies:
        logger.error(f"[{email}] FAILED at browser login")
        return None

    logger.info(f"[{email}] Step 2/5: Get access token")
    token_data = await http_get_access_token(cookies)
    if not token_data:
        logger.error(f"[{email}] FAILED to get access token")
        return None
    logger.info(f"[{email}] Got accessToken (len={len(token_data.get('accessToken', ''))})")

    logger.info(f"[{email}] Step 3/5: Complete registration")
    reg_ok = await http_complete_registration(cookies)
    if not reg_ok:
        logger.warning(f"[{email}] Registration may have failed (might already be registered)")

    logger.info(f"[{email}] Step 4/5: Create API key")
    api_key = await http_create_api_key(cookies, email)
    if not api_key:
        logger.error(f"[{email}] FAILED to create API key")
        return None

    logger.info(f"[{email}] Step 5/5: Check credits")
    credit_info = await check_credit(cookies)
    credit_str = ""
    if credit_info:
        used = credit_info.get('used', '?')
        total = credit_info.get('total', '?')
        credit_str = f" | credits: {used}/{total}"

    await save_key(email, api_key)
    cred_file = await save_credential_file(email, api_key, token_data)
    logger.info(f"[{email}] ✓ key: {api_key[:25]}...{credit_str} → {cred_file}")
    return api_key


async def harvest_worker(
    semaphore: asyncio.Semaphore,
    browser: Browser,
    email: str,
    password: str,
    stats: HarvestStats,
    retries: int,
    stagger_delay: float,
    worker_id: int,
):
    async with semaphore:
        # Stagger launch to avoid Google rate-limiting
        if stagger_delay > 0 and worker_id > 0:
            stagger = stagger_delay * (worker_id % 4)
            await asyncio.sleep(stagger)

        for attempt in range(1, retries + 1):
            await rate_limit_event.wait()

            try:
                logger.info(f"[W{worker_id}] {email} (attempt {attempt}/{retries})")
                api_key = await harvest_single(browser, email, password, worker_id)

                if api_key:
                    await stats.record_success(email, api_key)
                    return
                else:
                    if attempt < retries:
                        await stats.record_retry()
                        wait = 5 * attempt
                        logger.warning(f"[W{worker_id}] {email} failed, retrying in {wait}s...")
                        await asyncio.sleep(wait)
                    else:
                        await stats.record_failure(email)
            except Exception as e:
                logger.error(f"[W{worker_id}] {email} exception: {e}")
                if attempt < retries:
                    await stats.record_retry()
                    await asyncio.sleep(5 * attempt)
                else:
                    await stats.record_failure(email)


async def run_batch(
    accounts: List[Tuple[str, str]],
    args,
    stats: HarvestStats,
    batch_num: int,
    total_batches: int,
):
    logger.info(f"\n{'='*60}")
    logger.info(f"BATCH {batch_num}/{total_batches} — {len(accounts)} accounts")
    logger.info(f"{'='*60}")

    semaphore = asyncio.Semaphore(args.workers)

    async with async_playwright() as p:
        launch_kwargs = {
            'headless': not args.headed,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-infobars',
            ],
        }
        # Prefer real Chrome over Chromium for better Google compatibility
        try:
            browser = await p.chromium.launch(channel='chrome', **launch_kwargs)
            logger.info("Using real Chrome")
        except Exception:
            browser = await p.chromium.launch(**launch_kwargs)
            logger.info("Falling back to Chromium")

        tasks = [
            harvest_worker(
                semaphore=semaphore,
                browser=browser,
                email=email,
                password=password,
                stats=stats,
                retries=args.retries,
                stagger_delay=args.stagger,
                worker_id=i,
            )
            for i, (email, password) in enumerate(accounts)
        ]

        await asyncio.gather(*tasks)
        await browser.close()


async def auto_feed_proxy():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8003/health", timeout=5)
            if resp.status_code == 200:
                logger.info("[AUTO-FEED] codebuddy2api proxy is running, credentials will be picked up on next request")
                return True
    except Exception:
        pass
    logger.info("[AUTO-FEED] codebuddy2api proxy not running (keys saved to disk for later)")
    return False


async def check_credit(cookies: Dict[str, str]) -> Optional[Dict[str, Any]]:
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers = {
        'Accept': 'application/json',
        'Cookie': cookie_str,
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    }
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(
                f"{CODEBUDDY_BASE}/billing/ide/usage",
                headers=headers,
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    return data.get('data', {})
    except Exception:
        pass
    return None


async def main():
    parser = argparse.ArgumentParser(description='Bulk CodeBuddy API key harvester (concurrent)')
    parser.add_argument('--accounts', default='accounts.txt', help='Accounts file (email:password per line)')
    parser.add_argument('--headed', action='store_true', default=False, help='Show browser (debug mode)')
    parser.add_argument('--workers', type=int, default=4, help='Concurrent workers (default: 4)')
    parser.add_argument('--retries', type=int, default=2, help='Retries per account (default: 2)')
    parser.add_argument('--stagger', type=float, default=3.0, help='Stagger delay between worker launches (seconds)')
    parser.add_argument('--batch-size', type=int, default=50, help='Accounts per batch (default: 50)')
    parser.add_argument('--batch-cooldown', type=float, default=60.0, help='Cooldown between batches in seconds (default: 60)')
    parser.add_argument('--start', type=int, default=0, help='Start from account index N')
    parser.add_argument('--limit', type=int, default=0, help='Process only N accounts (0=all)')
    parser.add_argument('--no-skip', action='store_true', default=False, help='Process all accounts even if already harvested')
    parser.add_argument('--resume', action='store_true', default=False, help='Resume from last saved state')
    args = parser.parse_args()

    accounts_file = Path(args.accounts)
    if not accounts_file.exists():
        logger.error(f"Accounts file not found: {accounts_file}")
        sys.exit(1)

    accounts = load_accounts(str(accounts_file))
    if not accounts:
        logger.error("No valid accounts found")
        sys.exit(1)

    # Resume from state
    if args.resume:
        state = load_state()
        if state.get('last_index', 0) > 0:
            logger.info(f"Resuming from index {state['last_index']}")
            accounts = accounts[state['last_index']:]

    if args.start > 0:
        accounts = accounts[args.start:]
    if args.limit > 0:
        accounts = accounts[:args.limit]

    # Skip already-harvested
    if not args.no_skip:
        already_done = load_harvested_emails()
        if already_done:
            before = len(accounts)
            accounts = [(e, p) for e, p in accounts if e not in already_done]
            skipped = before - len(accounts)
            if skipped > 0:
                logger.info(f"Skipped {skipped} already-harvested accounts")

    if not accounts:
        logger.info("No accounts to process (all already harvested)")
        sys.exit(0)

    logger.info(f"Accounts to process: {len(accounts)}")
    logger.info(f"Workers: {args.workers} | Retries: {args.retries} | Batch: {args.batch_size}")
    logger.info(f"Mode: {'headed' if args.headed else 'headless'}")

    # Clear failed file for fresh run
    if FAILED_FILE.exists() and not args.resume:
        FAILED_FILE.unlink()

    CREDS_DIR.mkdir(parents=True, exist_ok=True)
    stats = HarvestStats(total=len(accounts))

    start_time = time.time()

    # Split into batches
    batches = [accounts[i:i + args.batch_size] for i in range(0, len(accounts), args.batch_size)]
    total_batches = len(batches)

    for batch_idx, batch in enumerate(batches, 1):
        await run_batch(batch, args, stats, batch_idx, total_batches)
        await save_state(stats, args.start + batch_idx * args.batch_size)

        if batch_idx < total_batches:
            logger.info(f"Batch {batch_idx} done. Cooling down {args.batch_cooldown}s before next batch...")
            await asyncio.sleep(args.batch_cooldown)

    elapsed = time.time() - start_time

    # Auto-feed proxy
    await auto_feed_proxy()

    # Cleanup state on full completion
    if stats.failed == 0 and STATE_FILE.exists():
        STATE_FILE.unlink()

    print(f"\n{'='*60}")
    print(f"HARVEST COMPLETE ({elapsed:.1f}s)")
    print(f"{'='*60}")
    print(f"Success: {stats.success}")
    print(f"Failed:  {stats.failed}")
    print(f"Skipped: {stats.skipped}")
    print(f"Retries: {stats.retried}")
    print(f"Speed:   {stats.success / max(elapsed, 1) * 60:.1f} keys/min")
    if stats.keys:
        print(f"\nAPI Keys:")
        for item in stats.keys:
            print(f"  {item['email']}: {item['key'][:30]}...")
    if stats.errors:
        print(f"\nFailed accounts (saved to {FAILED_FILE}):")
        for e in stats.errors:
            print(f"  {e}")
        print(f"\nRe-run failures: python bulk_harvest.py --accounts {FAILED_FILE}")
    print(f"\nKeys saved to: {KEYS_FILE}")
    print(f"Credentials saved to: {CREDS_DIR}/")


if __name__ == '__main__':
    asyncio.run(main())
