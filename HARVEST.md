# CodeBuddy API Key Harvester v2

Otomatis harvest API key dari akun Google ke CodeBuddy. Ringan, cepat, anti-detect.

```
accounts.txt (email:password)
        ↓
  [Browser Worker x2]  ← Google OAuth (berat, tapi cuma 2)
        ↓
   asyncio.Queue
        ↓
  [HTTP Worker x6]     ← Register + Create Key (ringan)
        ↓
  harvested_keys.json
        ↓
  Telegram notif ✅
```

---

## Install

```bash
git clone https://github.com/nopperabbo/codebuddy2api.git
cd codebuddy2api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

---

## Siapkan Akun

Buat file `accounts.txt`, satu akun per baris:

```
email1@gmail.com:password1
email2@gmail.com:password2
email3@gmail.com|password3
```

Separator: `:` atau `|` atau tab.

---

## Cara Jalankan

**Standard (laptop/PC biasa, 8GB RAM):**
```bash
python bulk_harvest_v2.py
```

**Debug (lihat browser):**
```bash
python bulk_harvest_v2.py --headed --browser-workers 1
```

**Server/VPS (lebih agresif):**
```bash
python bulk_harvest_v2.py --browser-workers 4 --http-workers 10 --auto-retry
```

**Linux VPS full stealth:**
```bash
python bulk_harvest_v2.py --xvfb --proxy --browser-workers 4 --auto-retry
```

---

## Semua Options

| Flag | Default | Keterangan |
|------|---------|------------|
| `--accounts FILE` | accounts.txt | File akun Google |
| `--browser-workers N` | 2 | Jumlah browser worker (berat, keep low di laptop) |
| `--http-workers N` | 6 | Jumlah HTTP worker (ringan, bisa banyak) |
| `--retries N` | 2 | Retry per akun kalo gagal |
| `--stagger N` | 3.0 | Jeda antar browser worker (detik) |
| `--headed` | off | Tampilkan browser (debug) |
| `--xvfb` | off | Headed mode di Linux tanpa monitor |
| `--proxy` | off | Rotasi proxy dari `proxies.txt` |
| `--max-ram N` | 4096 | Auto-throttle kalo RAM lewat ini (MB) |
| `--auto-retry` | off | Otomatis retry akun gagal setelah selesai |
| `--resume` | off | Lanjut dari posisi terakhir |
| `--no-skip` | off | Proses ulang akun yang udah berhasil |
| `--start N` | 0 | Mulai dari akun ke-N |
| `--limit N` | 0 | Proses N akun aja (0 = semua) |

---

## Proxy (Opsional)

Buat file `proxies.txt`:

```
http://user:pass@ip:port
socks5://user:pass@ip:port
```

Jalankan dengan flag `--proxy`.

---

## Output

| File | Isi |
|------|-----|
| `harvested_keys.json` | API keys yang berhasil |
| `failed_accounts.txt` | Akun yang gagal (bisa di-retry) |
| `.browser_profiles/` | Saved browser state (biar run berikutnya lebih cepat) |
| `.harvest_state.json` | State buat `--resume` |

---

## Fitur

- **Pipeline architecture** — browser cuma buat OAuth, sisanya HTTP. Hemat RAM 50%+
- **Anti-detect** — canvas/WebGL/audio fingerprint noise, human-like mouse & typing
- **Cookie-first** — kalo udah pernah login, skip browser langsung HTTP
- **Rate limit handling** — auto-pause semua worker 5 menit kalo kena limit
- **Adaptive RAM** — auto-throttle kalo RAM kepake banyak
- **Auto-retry** — akun gagal otomatis di-retry setelah batch selesai
- **Resume** — kalo mati di tengah, lanjut dari posisi terakhir
- **Skip duplicates** — akun yang udah berhasil otomatis di-skip
- **Telegram notif** — dapet notif setiap batch selesai
- **Proxy rotation** — beda proxy tiap akun

---

## Tips

| Situasi | Solusi |
|---------|--------|
| RAM terbatas (8GB) | `--browser-workers 1 --http-workers 8` |
| Kena rate limit | Otomatis pause 5 menit, gak perlu restart |
| Run kedua kali | Akun berhasil otomatis di-skip |
| Mati di tengah jalan | `--resume` buat lanjut |
| Retry yang gagal aja | `python bulk_harvest_v2.py --accounts failed_accounts.txt` |
| Mau cepet di VPS | `--browser-workers 4 --http-workers 12 --xvfb` |

---

## Troubleshooting

**"No module named playwright"**
```bash
source venv/bin/activate
pip install playwright playwright-stealth
playwright install chromium
```

**"No Google button found"**
CodeBuddy mungkin ganti UI. Jalankan `--headed` buat debug manual.

**"Rate limit detected"**
Normal. Script auto-pause 5 menit. Kalo sering kena, kurangin `--browser-workers`.

**"Timeout waiting for CodeBuddy"**
Koneksi lambat atau Google challenge. Coba lagi atau pake `--proxy`.
