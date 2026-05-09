---
name: Ganda Automation Rules
description: Custom engineering rules for bot creation, reverse engineering, and proxy APIs.
---

# Ganda's Automation & Bot Engineering Rules

You are assisting a highly pragmatic, "lazy but productive" system builder and automation engineer. The goal is to build fast, robust, and automated tools (bots, proxies, scrapers) with minimal overhead.

## 1. Asynchronous by Default
- **NEVER** use `requests`. Always use `httpx` with `asyncio` or `aiohttp` for networking.
- Bots must be able to handle high concurrency. Use `asyncio.gather` or `asyncio.Queue` for batch processing.
- If scraping or making API calls, implement smart concurrency with semaphores to avoid blowing up memory but keeping speed high.

## 2. Stealth & Reverse Engineering
- Assume APIs might have rate limits or fingerprinting. 
- When building scrapers, prefer `curl_cffi` (for TLS fingerprint spoofing) or `undetected-chromedriver`/Playwright Stealth over vanilla requests if hitting WAFs (Cloudflare/Akamai).
- Always include realistic headers (User-Agent, Accept, Sec-Ch-Ua) in API requests.

## 3. Data Storage & State Management
- **AVOID** saving state or harvested credentials in plain `.txt` or `.json` files when building concurrent systems. 
- Use **SQLite** (`aiosqlite` for async) for anything involving multiple accounts, harvested keys, or job queues. It prevents file corruption during concurrent writes.
- For simple config, JSON is fine, but state tracking must be in SQLite.

## 4. Self-Healing & Pragmatism
- Implement automatic failover. If a proxy or API key dies (403/429), the code MUST automatically catch it, rotate the key, and retry.
- Do not over-engineer with massive OOP patterns if a simple, functional approach works better. The user prefers code that "just works" and can be deployed quickly.
- Avoid unnecessary dependencies. Stick to the standard library where possible + core robust libraries (`httpx`, `fastapi`, `pydantic`).

## 5. Environment & Setup
- Always use `python3` and suggest using virtual environments, but keep setup commands as simple one-liners.

**Whenever the user asks to create a bot, scraper, or proxy, apply these rules implicitly without needing to be reminded.**
