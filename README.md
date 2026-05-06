# CodeBuddy2API

Akses AI model premium (Claude, GPT-5, Gemini) **gratis** lewat akun CodeBuddy.
Project ini bikin server lokal yang bisa dipake di app AI manapun.

---

## Apa Ini?

CodeBuddy2API = "jembatan" antara akun CodeBuddy kamu dan aplikasi AI lain.

```
Kamu punya akun CodeBuddy (gratis)
        ↓
CodeBuddy2API jalan di komputer kamu
        ↓
Bisa dipake di: OpenCode, ChatBox, LobeChat, dll
```

---

## Yang Dibutuhkan (Install Dulu)

Sebelum mulai, pastikan ini sudah terinstall di komputer kamu:

| Software | Cara Cek | Cara Install |
|----------|----------|--------------|
| **Python 3.10+** | Buka terminal, ketik: `python3 --version` | [python.org/downloads](https://www.python.org/downloads/) |
| **Git** | `git --version` | [git-scm.com](https://git-scm.com/downloads) |
| **Node.js 18+** *(opsional)* | `node --version` | [nodejs.org](https://nodejs.org/) |

> **Cara buka terminal:**
> - **Mac:** Tekan `Cmd + Space`, ketik "Terminal", Enter
> - **Windows:** Tekan `Win + R`, ketik "cmd", Enter
> - **Linux:** Tekan `Ctrl + Alt + T`

---

## Cara Install (3 Menit)

### Langkah 1: Download Project

Buka terminal, copy-paste perintah ini satu per satu:

```bash
git clone https://github.com/nopperabbo/codebuddy2api.git
```

```bash
cd codebuddy2api
```

### Langkah 2: Jalankan Setup

```bash
bash setup.sh
```

Script ini bakal:
- Install semua yang dibutuhkan secara otomatis
- Nanya beberapa pertanyaan (tinggal jawab)
- Kasih tau langkah selanjutnya

> **Kalau ada error**, baca pesan error-nya — biasanya kasih tau apa yang kurang.

### Langkah 3: Set Password

Setelah setup selesai, buka file `.env`:

```bash
nano .env
```

Cari baris `CODEBUDDY_PASSWORD=` dan isi password bebas (ini buat akses API nanti):

```
CODEBUDDY_PASSWORD=rahasia123
```

Simpan: tekan `Ctrl + X`, lalu `Y`, lalu `Enter`.

### Langkah 4: Jalankan Server

```bash
source venv/bin/activate
python web.py
```

Kalau berhasil, akan muncul pesan bahwa server jalan di `http://127.0.0.1:8003`.

### Langkah 5: Tambah Akun CodeBuddy

1. Buka browser (Chrome/Firefox)
2. Pergi ke: `http://127.0.0.1:8003`
3. Masukkan password yang kamu set tadi
4. Klik tab **"Credential Management"**
5. Klik **"Start Authentication"**
6. Login pake akun CodeBuddy kamu
7. Selesai! Credential tersimpan otomatis

> Belum punya akun CodeBuddy? Daftar gratis di [codebuddy.ai](https://www.codebuddy.ai)

---

## Cara Pake

Setelah server jalan, kamu bisa pake di app AI manapun dengan setting:

| Setting | Isi dengan |
|---------|-----------|
| **Base URL** | `http://127.0.0.1:8003/codebuddy/v1` |
| **API Key** | Password yang kamu set di `.env` |
| **Model** | `auto-chat` |

### Model yang Bisa Dipake

| Model | Cocok untuk |
|-------|-------------|
| `auto-chat` | Sehari-hari (recommended) |
| `auto-smart` | Tugas yang butuh mikir banyak |
| `auto-fast` | Jawaban cepat |
| `claude-opus-4.6` | Coding dan analisis kompleks |
| `gpt-5.5` | General purpose |
| `gemini-2.5-pro` | Dokumen panjang |

---

## Cara Matikan Server

Di terminal yang lagi jalan server-nya, tekan `Ctrl + C`.

---

## Cara Jalankan Lagi (Besok/Lusa)

Setiap mau pake lagi:

```bash
cd codebuddy2api
source venv/bin/activate
python web.py
```

---

## OpenCode AI Config (Opsional - Untuk Developer)

Repo ini juga include config untuk **OpenCode** — AI coding assistant yang bisa pake semua model di atas langsung dari terminal.

**Apa itu OpenCode?**
Kayak ChatGPT tapi di terminal, bisa langsung edit code, baca file, jalankan command. Cocok buat developer.

**Cara install:**
Waktu jalankan `bash setup.sh`, jawab `y` pas ditanya "Install OpenCode config?"

**Yang perlu diinstall tambahan:**
- Node.js 18+ (wajib)
- Bun: `curl -fsSL https://bun.sh/install | bash`
- OpenCode: `npm install -g opencode`

Setelah install, jalankan `opencode` di terminal.

Detail lengkap: lihat [opencode-config/README.md](opencode-config/README.md)

---

## Troubleshooting (Kalau Ada Masalah)

### "python3 not found"
Python belum terinstall. Download dari [python.org](https://www.python.org/downloads/).

### "git not found"
Git belum terinstall. Download dari [git-scm.com](https://git-scm.com/downloads).

### "No valid credentials"
Belum tambah akun CodeBuddy. Buka `http://127.0.0.1:8003` dan ikuti Langkah 5.

### "Invalid password"
Password di app client kamu ga sama dengan yang di file `.env`.

### Server ga bisa diakses dari HP
Ganti `CODEBUDDY_HOST=0.0.0.0` di file `.env`, restart server.

### Port 8003 sudah dipakai
Ganti `CODEBUDDY_PORT=8005` (atau angka lain) di file `.env`.

---

## Akses dari HP (Satu WiFi)

1. Edit `.env`: ganti `CODEBUDDY_HOST=0.0.0.0`
2. Restart server
3. Cek IP komputer: `ifconfig` (Mac) atau `ipconfig` (Windows)
4. Di HP, pake: `http://IP_KOMPUTER:8003/codebuddy/v1`

---

## Docker (Untuk yang Sudah Familiar)

```bash
docker-compose up -d
```

---

## License

MIT
