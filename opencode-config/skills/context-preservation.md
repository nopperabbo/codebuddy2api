# Context Preservation

Panduan untuk menjaga context antar sesi agar AI tidak pernah kehilangan informasi penting tentang project.

---

## Enforcement: MCP Server `context-keeper`

**Jika MCP server `context-keeper` tersedia, WAJIB gunakan tools-nya:**

| Kapan | Tool | Deskripsi |
|-------|------|-----------|
| Awal sesi | `context_read` | Baca + auto-prune file. PANGGIL SEBELUM kerja apapun. |
| Setelah task selesai | `context_update` | Update section tertentu (Stack, Current Status, dll) |
| Sebelum sesi berakhir | `context_checkpoint` | Validasi, prune, archive jika perlu |

**Jika MCP tidak tersedia, gunakan IRON RULE:**
> Setiap kali TodoWrite dipanggil untuk mark items `completed`, WAJIB juga update `.opencode-context.md` di response yang SAMA.

---

## Prinsip Utama

1. **Baca dulu, kerja kemudian** — Selalu baca `.opencode-context.md` di awal sesi sebelum mulai kerja
2. **Tulis ringkas** — Hanya fakta penting, format bullet point, hindari narasi panjang
3. **Update inkremental** — Tambah/ubah saat ada keputusan, jangan tulis ulang seluruh file
4. **User adalah pemilik** — User boleh edit manual kapan saja

---

## Flow Setiap Sesi (OTOMATIS)

**Context file adalah PER-PROJECT** — setiap project root punya `.opencode-context.md` sendiri. Bukan file global.

```
1. Awal sesi → Cek apakah .opencode-context.md ada di root project
2. Jika TIDAK ada → BUAT OTOMATIS (jangan tanya user, langsung buat dengan template)
   - Auto-detect stack dari package.json, Cargo.toml, go.mod, requirements.txt, dll
   - Isi ## Stack dengan hasil deteksi
3. Jika SUDAH ada → Baca, lalu PRUNE dulu sebelum lanjut kerja:
   a. Hapus semua task [x] (sudah selesai) dari ## Current Status
   b. Hapus notes di ## Important Notes yang sudah tidak relevan
   c. Ringkas keputusan arsitektur lama yang sudah obvious jadi 1 baris
   d. Target: file tetap ≤ 40 baris setelah prune
4. Jika setelah prune masih > 50 baris → AUTO-ARCHIVE:
   - Pindahkan entries lama ke .opencode-context-archive.md
   - Di file utama tambah: "> Archived entries: see .opencode-context-archive.md"
   - Archive file = referensi history, tidak ada batas ukuran
5. Selama sesi → Update file saat ada:
   - Keputusan arsitektur baru
   - Stack/dependency baru ditambahkan
   - Task selesai (mark [x])
   - Bug penting ditemukan & di-fix
   - Konvensi baru disepakati
6. Akhir sesi → Pastikan status terkini tercatat
```

> **PENTING:** User tidak perlu jalankan `opencode-jce context init` manual.
> AI WAJIB buat file ini otomatis di awal sesi jika belum ada.
> AI WAJIB prune di awal sesi agar file tidak membengkak.

---

## Kapan HARUS Update Context File

| Event | Contoh | Action |
|-------|--------|--------|
| Keputusan arsitektur | "Kita pakai JWT untuk auth" | Tambah di ## Architecture Decisions |
| Dependency baru | "Install Redis untuk caching" | Update ## Stack |
| Task selesai | "Auth controller done" | Checklist [x] di ## Current Status |
| Konvensi baru | "Semua API return {success,data,error}" | Tambah di ## Conventions |
| Bug kritis di-fix | "Race condition di payment" | Tambah di ## Important Notes |

---

## Kapan TIDAK PERLU Update

- Perubahan kecil (typo fix, rename variable)
- Hal yang sudah jelas dari kode (import statements)
- Informasi sementara yang tidak relevan sesi berikutnya
- Detail implementasi yang bisa dibaca dari source code

---

## Format File .opencode-context.md

```markdown
# Project Context
> Auto-maintained by AI. You can edit this file freely.
> Last updated: YYYY-MM-DD

## Stack
- [bahasa/framework utama]
- [database]
- [tools penting]

## Architecture Decisions
- [keputusan 1]: [alasan singkat]
- [keputusan 2]: [alasan singkat]

## Conventions
- [aturan 1]
- [aturan 2]

## Current Status
- [x] [task selesai]
- [x] [task selesai]
- [ ] [task sedang dikerjakan] ← IN PROGRESS
- [ ] [task belum mulai]

## Important Notes
- [hal penting yang harus diingat]
```

---

## Rules Penulisan (Hemat Token)

1. **Maksimal 40 baris** (target) / **50 baris** (hard limit sebelum archive)
2. **Bullet point only** — Tidak perlu paragraf
3. **Tidak ada duplikasi** — Jangan tulis yang sudah ada
4. **Gunakan simbol:**
   - `[x]` = selesai (akan di-prune sesi berikutnya)
   - `[ ]` = belum
   - `←` = sedang dikerjakan
   - `⚠️` = perlu perhatian
5. **Tanggal di header** — Agar tahu kapan terakhir update
6. **Prune setiap awal sesi** — Hapus [x] tasks, notes lama, ringkas decisions

## Auto-Archive (.opencode-context-archive.md)

Jika setelah prune file masih > 50 baris:

```markdown
# Context Archive — [Project Name]
> Historical decisions and notes. Reference only.

## Archived: 2025-05-02
- [keputusan lama yang dipindahkan]
- [notes lama yang dipindahkan]

## Archived: 2025-04-28
- [entries lebih lama]
```

Rules archive:
- Grouped by tanggal archive
- Tidak ada batas ukuran
- AI boleh baca archive jika perlu context historis
- User boleh hapus archive kapan saja

---

## Integrasi dengan Memory MCP

Jika MCP Memory server aktif, gunakan untuk:
- **Fakta permanen** (API keys location, deployment URL) → simpan di Memory
- **Status project yang berubah** (current task, progress) → simpan di .opencode-context.md

Pembagian:
| Jenis Info | Simpan Di |
|-----------|-----------|
| Stack & arsitektur | .opencode-context.md |
| Status & progress | .opencode-context.md |
| Credentials location | Memory MCP |
| User preferences | Memory MCP |
| Deployment info | Memory MCP |

---

## Contoh Lengkap

```markdown
# Project Context
> Auto-maintained by AI. You can edit this file freely.
> Last updated: 2025-01-15

## Stack
- Laravel 11, PHP 8.3
- PostgreSQL 16, Redis 7
- Frontend: Blade + Livewire 3 + Tailwind CSS 3.4
- Queue: Laravel Horizon
- Deploy: Docker + AWS ECS

## Architecture Decisions
- Auth: JWT + refresh token (access 15min, refresh 7d)
- API: RESTful, versioned /api/v1/, rate limited 60/min
- File storage: S3 with signed URLs
- Cache: Redis with 5min TTL default

## Conventions
- All endpoints return: { success: bool, data: any, error: string|null }
- Migrations: YYYY_MM_DD_HHMMSS_verb_noun (e.g. create_users_table)
- Tests: Feature tests for endpoints, Unit tests for services
- Commits: feat|fix|refactor(scope): description

## Current Status
- [x] User authentication (JWT + refresh)
- [x] Product CRUD + image upload
- [x] Category management
- [ ] Shopping cart ← IN PROGRESS
- [ ] Checkout + Stripe payment
- [ ] Order management
- [ ] Email notifications

## Important Notes
- Products table has soft deletes enabled
- User model uses HasApiTokens trait (Sanctum removed, custom JWT)
- Redis connection pool max 10 in production
- ⚠️ Migration 2025_01_10 has breaking change on products.price (int→decimal)
```

---

## v2 Features

### Multi-Session Awareness
- Session metadata stored as HTML comment (invisible in rendered markdown)
- Session counter incremented on each `context_read`
- Staleness detection: warns if >7 days or >5 sessions without update
- Use `context_history` tool to check health metrics

### Context Enrichment
- `context_read` now includes auto-detected project state:
  - Git branch, uncommitted changes, last commit
  - Dependency list from package.json
- This data is in the RESPONSE only (not written to file)
- Provides immediate context without manual exploration

### Semantic Intelligence
- Fuzzy deduplication: entries with >60% word overlap are merged
- Resolved note detection: entries containing "fixed", "resolved", "completed" etc. are auto-pruned
- Runs automatically during `context_read`

### Cross-Project Context
- Define related projects in `## Related Projects` section:
  ```
  ## Related Projects
  - ../shared-lib: "Shared utilities used by this service"
  - ../api-gateway: "Routes traffic to this service"
  ```
- Use `context_query_related` tool to read their contexts
- Summaries included in `context_read` response automatically

### Compliance
- Staleness warnings escalate based on sessions without update
- `opencode-jce context audit` CLI command for manual compliance check
- Content hash enables optimistic concurrency detection
