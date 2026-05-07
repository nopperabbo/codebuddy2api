#!/usr/bin/env python3
import asyncio
import sys
import os
import json
import time
import random
import subprocess
from pathlib import Path
from urllib.parse import urlparse

# ─── Config ───────────────────────────────────────────────────────
CODEBUDDY_BASE = "https://www.codebuddy.ai"
APIKEYS_FILE = Path("/root/enowx/apikeys.txt") # Ganti path Apikeys
RESULTS_FILE = Path("/root/enowx/cb_results_bavixz.json") # Ganti Result 
PROXIES_FILE = Path("/root/enowx/proxies.txt") # Ganti Path Proxy
PROFILES_DIR = Path("/root/enowx/profiles")
PROFILES_DIR.mkdir(exist_ok=True)

MAX_THREADS = 5  # <-- UBAH ANGKA INI UNTUK MENGATUR JUMLAH THREAD BERSAMAAN

DISPLAY = os.environ.get("DISPLAY", ":99")
os.environ["DISPLAY"] = DISPLAY


# ─── Helpers ──────────────────────────────────────────────────────
def load_proxies():
    if PROXIES_FILE.exists():
        lines = [l.strip() for l in open(PROXIES_FILE) if l.strip() and not l.startswith('#')]
        return lines
    return []

PROXIES = load_proxies()

def get_proxy():
    if PROXIES:
        p = random.choice(PROXIES)
        parsed = urlparse(p)
        return {
            "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
            "username": parsed.username or "",
            "password": parsed.password or "",
        }
    return None


def start_xvfb():
    r = subprocess.run(["pgrep", "-f", f"Xvfb {DISPLAY}"], capture_output=True)
    if r.returncode == 0:
        return None  # already running
    proc = subprocess.Popen(
        ["Xvfb", DISPLAY, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(1)
    return proc


def load_accounts(filepath: str, start=1, end=None):
    accounts = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('|', 1)
            if len(parts) == 2:
                accounts.append((parts[0].strip(), parts[1].strip()))
    end = end or len(accounts)
    return accounts[start-1:end]


# ─── Main Logic ───────────────────────────────────────────────────
async def register_one(email: str, password: str) -> dict:
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth
    stealth = Stealth()
    
    result = {"email": email, "status": "unknown", "api_key": None, "error": None}
    print(f"\n{'='*60}")
    print(f"[*] {email}")
    
    profile_dir = PROFILES_DIR / email.split('@')[0]
    profile_dir.mkdir(exist_ok=True)
    
    proxy = None  # no proxy - direct Keycloak + Google OAuth works fine
    if proxy:
        print(f"  [proxy] {proxy['server']}")
    
    try:
        async with async_playwright() as p:
            # Launch with persistent context = more realistic
            browser = await p.chromium.launch(
                headless=False,  # HEADED on Xvfb — avoids headless detection
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--window-size=1920,1080",
                ]
            )
            
            context_opts = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "locale": "en-US",
                "timezone_id": "Asia/Singapore",
                "color_scheme": "light",
                "java_script_enabled": True,
                "storage_state": str(profile_dir / "state.json") if (profile_dir / "state.json").exists() else None,
            }
            if proxy:
                context_opts["proxy"] = proxy
            
            context = await browser.new_context(**context_opts)
            page = await context.new_page()
            
            # Apply stealth
            await stealth.apply_stealth_async(page)
            
            # Extra: remove webdriver flag
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                delete navigator.__proto__.webdriver;
                // Chrome runtime
                window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
                // Permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                // Plugin count
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
            """)
            
            page.set_default_timeout(45000)
            
            # ── Step 1: Go DIRECTLY to Keycloak auth (bypass SPA iframe block) ──
            KEYCLOAK_AUTH = f"{CODEBUDDY_BASE}/auth/realms/copilot/protocol/openid-connect/auth?client_id=console&redirect_uri=https%3A%2F%2Fwww.codebuddy.ai%2Flogin%2Fselect%3Fredirect_uri%3Dhttps%253A%252F%252Fwww.codebuddy.ai%252Fhome&response_type=code&scope=openid"
            print(f"  [1] Loading Keycloak auth page...")
            await page.goto(KEYCLOAK_AUTH, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3)
            
            # ── Step 2: Get Google href and navigate directly ──
            print(f"  [2] Getting Google OAuth URL...")
            google_href = await page.evaluate('''() => {
                const el = document.querySelector('#social-google') || document.querySelector('a[href*="broker/google"]');
                return el ? el.getAttribute('href') : null;
            }''')
            
            if not google_href:
                await page.screenshot(path=str(profile_dir / "debug_login.png"))
                result["status"] = "no_google_btn"
                result["error"] = f"Google link not found on Keycloak. URL: {page.url[:80]}"
                await browser.close()
                return result
            
            # Make absolute URL and navigate
            if google_href.startswith('/'):
                google_href = f"{CODEBUDDY_BASE}{google_href}"
            
            await page.goto(google_href, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)  # wait for Google page to fully load
            
            await asyncio.sleep(3)
            
            # ── Step 3: Google OAuth ──
            print(f"  [3] Google OAuth flow...")
            auth_ok = await do_google_oauth(page, email, password)
            
            if auth_ok == "banned":
                result["status"] = "banned"; result["error"] = "Redirected to /banned"
                await browser.close(); return result
            elif auth_ok == "challenge":
                result["status"] = "challenge"; result["error"] = "Google challenge"
                await browser.close(); return result
            elif auth_ok is not True:
                print(f"  [!] OAuth failed: {auth_ok}")
                result["status"] = "oauth_fail"; result["error"] = f"OAuth: {auth_ok}, URL: {page.url[:60]}"
                await browser.close(); return result
            
            print(f"  [4] Logged in! URL: {page.url[:60]}")
            
            # Save state for future reuse
            try:
                await context.storage_state(path=str(profile_dir / "state.json"))
            except:
                pass
            
            # ── Step 4: Get API key ──
            # Check if we got it during registration (early key)
            api_key = await page.evaluate("() => window.__earlyApiKey || null")
            
            if not api_key:
                # Try creating key from current page
                api_key = await page.evaluate("""async () => {
                    try {
                        const resp = await fetch('/console/api/client/v1/api-keys', {
                            method: 'POST', credentials: 'include',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                name: 'enowx-' + Date.now(),
                                expire_in_days: -1,
                                user_enterprise_id: 'personal-edition-user-id'
                            })
                        });
                        const data = await resp.json();
                        if (data.code === 0 && data.data && data.data.key) return data.data.key;
                        return null;
                    } catch(e) { return null; }
                }""")
            
            if not api_key:
                # Fallback: navigate to profile/keys
                api_key = await get_api_key(page)
            
            if api_key:
                print(f"  ✅ API Key: {api_key[:25]}...")
                result["status"] = "success"
                result["api_key"] = api_key
                with open(APIKEYS_FILE, "a") as f:
                    f.write(f"{email}|{api_key}\n")
                
                # Auto-add to enowxai
                try:
                    import urllib.request
                    data = json.dumps({"email": email, "provider": "codebuddy", "credentials": {"api_key": api_key}}).encode()
                    req = urllib.request.Request(
                        "http://localhost:1431/api/accounts/add-manual",
                        data=data, headers={"Content-Type": "application/json"}, method="POST"
                    )
                    resp = urllib.request.urlopen(req, timeout=15)
                    enowx_r = json.loads(resp.read())
                    if enowx_r.get("success"):
                        print(f"  ✅ Added to enowxai!")
                    else:
                        print(f"  ⚠ enowx: {enowx_r.get('error', '')[:60]}")
                except Exception as ex:
                    print(f"  ⚠ enowx add failed: {str(ex)[:60]}")
            else:
                result["status"] = "no_key"
                result["error"] = "Logged in but API key creation failed"
                await page.screenshot(path=str(profile_dir / "debug_nokey.png"))
            
            await browser.close()
    
    except Exception as e:
        err = str(e)[:200]
        print(f"  ❌ Error: {err}")
        result["status"] = "error"
        result["error"] = err
    
    return result


async def click_google(page) -> bool:
    
    # Wait for page to fully render
    for attempt in range(8):
        # Try iframe approach
        frames = page.frames
        for frame in frames:
            try:
                google_btn = await frame.query_selector('#social-google')
                if google_btn and await google_btn.is_visible():
                    # Click checkbox first if exists
                    checkbox = await frame.query_selector('div.checkmark, input[type="checkbox"]')
                    if checkbox and await checkbox.is_visible():
                        await checkbox.click()
                        await asyncio.sleep(1)
                    await google_btn.click()
                    return True
                
                # Alt: any link with google in href
                google_link = await frame.query_selector('a[href*="google"]')
                if google_link and await google_link.is_visible():
                    checkbox = await frame.query_selector('div.checkmark, input[type="checkbox"]')
                    if checkbox and await checkbox.is_visible():
                        await checkbox.click()
                        await asyncio.sleep(1)
                    await google_link.click()
                    return True
            except:
                continue
        
        # Direct page (no iframe)
        try:
            for sel in ['#social-google', 'a[href*="google"]', 'button:has-text("Google")',
                       '[data-provider="google"]', 'a:has-text("Google")']:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    return True
        except:
            pass
        
        await asyncio.sleep(3)
    
    return False


async def do_google_oauth(page, email: str, password: str):
    
    start = time.time()
    last_step = ""
    
    while time.time() - start < 120:
        try:
            url = page.url
        except:
            await asyncio.sleep(1)
            continue
        
        elapsed = int(time.time() - start)
        
        # Success: on codebuddy, not login/banned
        is_on_cb = url.startswith("https://www.codebuddy.ai") or url.startswith("https://codebuddy.ai")
        if is_on_cb:
            if "/banned" in url:
                return "banned"
            if not any(x in url for x in ["/login", "/register", "auth/realms"]):
                return True
            # Register page = still need to complete
            if "/register/user/complete" in url:
                print(f"    [region] Completing registration via API...")
                
                # Step 1: POST /console/login/account with Singapore region
                reg_result = await page.evaluate("""async () => {
                    try {
                        // Set region (Singapore)
                        const r1 = await fetch('/console/login/account', {
                            method: 'POST', credentials: 'include',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                attributes: {
                                    countryCode: ["65"],
                                    countryFullName: ["Singapore"],
                                    countryName: ["SG"]
                                }
                            })
                        });
                        const d1 = await r1.json();
                        if (d1.code !== 0) return 'login_account_fail:' + JSON.stringify(d1);
                        
                        // Step 2: Get userId from /console/accounts
                        const r2 = await fetch('/console/accounts', {credentials: 'include'});
                        const d2 = await r2.json();
                        let userId = null;
                        if (d2.code === 0 && d2.data && d2.data.accounts && d2.data.accounts.length > 0) {
                            userId = d2.data.accounts[0].uid;
                        }
                        if (!userId) return 'no_userId:' + JSON.stringify(d2).substring(0, 200);
                        
                        // Step 3: Register overseas
                        const r3 = await fetch('/auth/realms/copilot/overseas/user/register?userId=' + userId, {
                            credentials: 'include',
                            headers: {'x-requested-with': 'XMLHttpRequest'}
                        });
                        const d3 = await r3.json();
                        if (d3.code !== 200) return 'register_fail:' + JSON.stringify(d3);
                        
                        // Step 4: Activate free trial
                        await fetch('/billing/ide/trial', {
                            method: 'POST', credentials: 'include',
                            headers: {'Content-Type': 'application/json'}
                        });
                        
                        // Step 5: Create API key RIGHT HERE before navigating away
                        const keyResp = await fetch('/console/api/client/v1/api-keys', {
                            method: 'POST', credentials: 'include',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({name: 'enowx-' + Date.now(), expire_in_days: -1, user_enterprise_id: 'personal-edition-user-id'})
                        });
                        const keyData = await keyResp.json();
                        const apiKey = (keyData.code === 0 && keyData.data && keyData.data.key) ? keyData.data.key : null;
                        
                        return 'success:' + userId + (apiKey ? ':KEY:' + apiKey : ':NOKEY');
                    } catch(e) {
                        return 'error:' + String(e);
                    }
                }""")
                print(f"    [region] Result: {reg_result}")
                
                # Extract API key if obtained during registration
                if reg_result and ':KEY:' in str(reg_result):
                    early_key = str(reg_result).split(':KEY:')[1]
                    if early_key and not early_key.startswith('NOKEY'):
                        # Got key during register! Return immediately as success
                        print(f"    [key] Got early key: {early_key[:25]}...")
                        await page.evaluate(f"window.__earlyApiKey = '{early_key}';")
                        return True  # Don't navigate to /home — it triggers ban
                
                await asyncio.sleep(2)
                
                # Only navigate to home if no key was obtained (risky — may get banned)
                try:
                    await page.goto("https://www.codebuddy.ai/home", wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(2)
                except:
                    pass
                continue
        
        # Google auth pages
        if "accounts.google.com" in url:
          try:
            # Email
            email_input = await page.query_selector('#identifierId')
            email_vis = email_input and await email_input.is_visible() if email_input else False
            pw_input = await page.query_selector('input[name="Passwd"]')
            if not pw_input:
                pw_input = await page.query_selector('input[type="password"]')
            pw_vis = pw_input and await pw_input.is_visible() if pw_input else False
            
            if int(time.time() - start) % 15 == 0:
                print(f"    [{elapsed}s] email_vis={email_vis} pw_vis={pw_vis} step={last_step}")
            
            if email_vis and last_step != "email":
                print(f"    [email] Typing {email}...")
                await email_input.click()
                await email_input.fill("")
                await email_input.type(email, delay=random.randint(40, 80))
                await asyncio.sleep(0.5)
                next_btn = await page.query_selector('#identifierNext')
                if next_btn:
                    await next_btn.click()
                last_step = "email"
                await asyncio.sleep(4)
                continue
            
            # Password (re-query since page may have navigated)
            if not pw_vis:
                pw_input = await page.query_selector('input[name="Passwd"]')
                if not pw_input:
                    pw_input = await page.query_selector('input[type="password"]')
                pw_vis = pw_input and await pw_input.is_visible() if pw_input else False
            if pw_vis and last_step != "password":
                print(f"    [password] Typing...")
                await pw_input.click()
                await pw_input.fill("")
                await pw_input.type(password, delay=random.randint(40, 80))
                await asyncio.sleep(0.5)
                next_btn = await page.query_selector('#passwordNext')
                if next_btn:
                    await next_btn.click()
                else:
                    await pw_input.press("Enter")
                last_step = "password"
                await asyncio.sleep(4)
                continue
            
            # Consent / TOS / speedbump / workspace TOS / OAuth approval
            needs_consent = any(x in url for x in ["/speedbump", "consent", "/signin/oauth"])
            is_picker = "oauthchooseaccount" in url or "accountchooser" in url
            if is_picker:
                print(f"    [picker] Selecting account...")
                await page.evaluate(f"""() => {{
                    // Try clicking by data-identifier
                    const els = document.querySelectorAll('[data-identifier="{email}"], [data-email="{email}"]');
                    for (const el of els) {{ if (el.offsetParent) {{ el.click(); return; }} }}
                    // Try clicking by text match
                    for (const el of document.querySelectorAll('li, div[role="link"], div[tabindex]')) {{
                        if (el.offsetParent === null) continue;
                        if ((el.textContent||'').includes('{email}')) {{ el.click(); return; }}
                    }}
                    // Fallback: click first account-looking element
                    const first = document.querySelector('li[data-identifier], div[data-identifier], ul li');
                    if (first) first.click();
                }}""")
                await asyncio.sleep(3)
                continue
            if needs_consent:
                # Allow retrying consent (TOS → consent can be 2 pages)
                print(f"    [consent] Accepting ({url.split('/')[-1][:30]})...")
                await accept_consent(page)
                await asyncio.sleep(4)
                continue
            
            # Challenge detection
            body_text = await page.text_content("body") or ""
            body_lower = body_text.lower()
            if any(x in body_lower for x in ["captcha", "unusual traffic", "verify it's you", "try again later"]):
                print(f"    [!] Challenge detected")
                return "challenge"
            
            # Check for "challenge" path
            if "/challenge/" in url:
                return "challenge"
          except Exception:
            await asyncio.sleep(1)
            continue
        
        await asyncio.sleep(2)
    
    # Timeout - check if we're on codebuddy anyway
    try:
        u = page.url
        if (u.startswith("https://www.codebuddy.ai") or u.startswith("https://codebuddy.ai")) and "/login" not in u and "/banned" not in u:
            return True
    except:
        pass
    
    return False


async def accept_consent(page):
    """Click Allow/Continue/Accept buttons"""
    await page.evaluate("""() => {
        const keywords = ['allow', 'continue', 'accept', 'i agree', 'lanjutkan', 'izinkan', 'setuju'];
        for (const btn of document.querySelectorAll('button, input[type="submit"], div[role="button"], span[role="button"]')) {
            if (btn.offsetParent === null) continue;
            const txt = (btn.value || btn.textContent || btn.innerText || '').toLowerCase().trim();
            if (keywords.some(k => txt.includes(k))) {
                btn.click();
                return true;
            }
        }
        // Last resort: last visible button
        const buttons = [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null);
        if (buttons.length > 0) buttons[buttons.length - 1].click();
        return false;
    }""")


async def select_region(page):
    """Handle CodeBuddy region selection on /register/user/complete"""
    try:
        # Approach 1: Click any visible input/select to open dropdown
        await page.evaluate("""() => {
            // Click all visible inputs (one might be the location dropdown)
            for (const el of document.querySelectorAll('input, div[class*="select"], div[class*="dropdown"], div[class*="t-input"]')) {
                if (el.offsetParent !== null) { el.click(); break; }
            }
        }""")
        await asyncio.sleep(2)
        
        # Approach 2: Type "Singapore" into any visible input
        inputs = await page.query_selector_all('input')
        for inp in inputs:
            if await inp.is_visible():
                await inp.click()
                await inp.fill("Singapore")
                await asyncio.sleep(1)
                # Press Enter or click dropdown option
                await inp.press("ArrowDown")
                await asyncio.sleep(0.5)
                await inp.press("Enter")
                await asyncio.sleep(1)
                break
        
        # Approach 3: Click any option/item with "Singapore" text
        await page.evaluate("""() => {
            for (const el of document.querySelectorAll('div, li, span, option, a')) {
                if (el.offsetParent === null) continue;
                const txt = (el.textContent || '').trim();
                if (txt.toLowerCase().includes('singapore') && txt.length < 30) {
                    el.click(); return;
                }
            }
        }""")
        await asyncio.sleep(1)
        
        # Click submit/continue button
        await page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button, div[role="button"], input[type="submit"]')) {
                if (btn.offsetParent === null) continue;
                const txt = (btn.textContent || '').toLowerCase();
                if (['submit', 'continue', 'next', 'confirm', 'ok', 'done', 'start'].some(k => txt.includes(k))) {
                    btn.click(); return;
                }
            }
            // Fallback: click last visible button
            const btns = [...document.querySelectorAll('button')].filter(b => b.offsetParent);
            if (btns.length) btns[btns.length-1].click();
        }""")
    except:
        pass


async def get_api_key(page) -> str | None:
    """Navigate to /profile/keys and create an API key"""
    try:
        print(f"  [5] Going to /profile/keys...")
        await page.goto(f"{CODEBUDDY_BASE}/profile/keys", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        
        if "/login" in page.url or "/banned" in page.url:
            print(f"    Redirected: {page.url[:60]}")
            return None
        
        # Create API key via fetch
        result = await page.evaluate("""async () => {
            try {
                const resp = await fetch('/console/api/client/v1/api-keys', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        name: 'enowx-' + Date.now(),
                        expire_in_days: -1,
                        user_enterprise_id: 'personal-edition-user-id'
                    })
                });
                const data = await resp.json();
                return {status: resp.status, data};
            } catch (e) {
                return {status: 0, error: String(e)};
            }
        }""")
        
        if result.get("status") == 200:
            data = result.get("data", {})
            if data.get("code") == 0:
                key = data.get("data", {}).get("key", "")
                if key:
                    return key
        
        print(f"    API response: {json.dumps(result)[:150]}")
        return None
    except Exception as e:
        print(f"    Error getting key: {e}")
        return None


# ─── Main ─────────────────────────────────────────────────────────
async def main():
    filepath = "/root/enowx/bavixz.txt" # Ganti Path akun
    start_idx = 1
    end_idx = None
    
    args = sys.argv[1:]
    if "--file" in args:
        filepath = args[args.index("--file") + 1]
    if "--start" in args:
        start_idx = int(args[args.index("--start") + 1])
    if "--end" in args:
        end_idx = int(args[args.index("--end") + 1])
    
    accounts = load_accounts(filepath, start_idx, end_idx)
    print(f"Loaded {len(accounts)} accounts (#{start_idx}-{start_idx+len(accounts)-1})")
    print(f"Output: {APIKEYS_FILE}")
    print(f"Proxies: {len(PROXIES)}")
    print(f"Threads: {MAX_THREADS} concurrency")
    
    # Start Xvfb
    xvfb = start_xvfb()
    
    results = []
    success = 0
    failed = 0
    
    # Batasan jumlah akun yang diproses bersamaan (Concurrency Limit)
    sem = asyncio.Semaphore(MAX_THREADS)

    async def process_account(i, email, password):
        nonlocal success, failed
        async with sem:
            print(f"\n[{i+1}/{len(accounts)}] Menjalankan: {email}")
            r = await register_one(email, password)
            results.append(r)
            
            if r["status"] == "success":
                success += 1
            else:
                failed += 1
            
            # Safe JSON append (ignore if write collision happens between threads)
            try:
                with open(RESULTS_FILE, "w") as f:
                    json.dump(results, f, indent=2)
            except Exception:
                pass
            
            # Delay acak sebelum selesai agar server tidak curiga
            await asyncio.sleep(random.uniform(2, 5))

    tasks = []
    for i, (email, password) in enumerate(accounts):
        tasks.append(asyncio.create_task(process_account(i, email, password)))
        # Jeda kecil tiap mau spawn task baru, menghindari spike CPU
        await asyncio.sleep(1.5)
        
    if tasks:
        # Tunggu semua concurrent proses selesai
        await asyncio.gather(*tasks)
    
    if xvfb:
        xvfb.terminate()
    
    print(f"\n{'='*60}")
    print(f"DONE! ✅ {success} success, ❌ {failed} failed")
    print(f"Keys: {APIKEYS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
