# ⚓ HELM SCRAPER — NAVAREA Baltic Sub-Area Ingestion Engine

[![Production Portal](https://img.shields.io/badge/Production%20Portal-Helm.Warning%20Data%20Bank-0070f3?style=for-the-badge&logo=vercel)](https://helmwarning.vercel.app/)
[![Baltic Pipeline](https://img.shields.io/github/actions/workflow/status/alfredpanakkal/NAVAREA-1/baltic-sync.yml?branch=main&label=Baltic%20Pipeline&style=for-the-badge&logo=githubactions)](https://github.com/alfredpanakkal/NAVAREA-1/actions/workflows/baltic-sync.yml)
[![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Database](https://img.shields.io/badge/Database-Supabase%20PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase)](https://supabase.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

> **Automated radio navigational warning scraper, deterministic parser, coordinate normalizer, and Supabase synchronizer for the Baltic Sea and Swedish coastal waters, powering [Helm.Warning](https://helmwarning.vercel.app/).**

---

## 🌊 Overview

The Baltic Sea is designated as a specialized sub-area under NAVAREA I, coordinated by the **Swedish Maritime Administration (Sjöfartsverket / SMA)**.

This engine harvests official maritime safety broadcasts from [Sjöfartsverket VHF Navigational Warnings](https://navvarn.sjofartsverket.se/en/Navigationsvarningar/VHF), normalizes navigational positions (including polygons, multi-point hazard bounds, and variable decimal precision) into WGS84 coordinates, infers issued years, classifies maritime hazard semantics, and persists data directly into the Helm.Warning Supabase data bank.

---

## 🗺️ NAVAREA Baltic Coverage

Broadcasts originate across 15 sub-regions:
- **Skagerrak**
- **Kattegat**
- **The Sound**
- **Lake Vänern and Trollhätte Canal**
- **Western Baltic**
- **Southern Baltic**
- **South-eastern Baltic**
- **Central Baltic**
- **Lake Mälaren and Södertälje Canal**
- **Northern Baltic**
- **Sea of Åland and Archipelago Sea**
- **Sea of Bothnia**
- **The Quark**
- **Bay of Bothnia**
- **Other lakes and canals**

---

## 🏗️ Architecture Pipeline

```
                 [ Sjöfartsverket Nav Warnings Portal ]
            (https://navvarn.sjofartsverket.se/en/Navigationsvarningar/VHF)
                                   │
                                   ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │               STAGE 1: EVIDENCE ACQUISITION                     │
 │  baltic_scraper.py                                              │
 │  • Public SSR HTML extraction (no CSRF overhead)                │
 │  • Deduplicates regional broadcasts across multiple sub-areas   │
 │  • Emits verbatim text ledger (navarea_baltic_warnings.txt)     │
 └────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │               STAGE 2: DETERMINISTIC REGEX PARSER               │
 │  baltic_parser.py                                               │
 │  • Variable precision coordinate regex (\d{1,3} decimals)       │
 │  • Centroid & GeoJSON bounding box polygon computation          │
 │  • Issued year temporal inference (e.g., 168/26 ➔ 2026)         │
 │  • Hazard semantic categorization (military, aton, subsea, etc.)│
 │  • SHA-256 cryptographic bulletin auditing                      │
 │  • Emits structured payload (parsed_warnings.json)              │
 └────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │               STAGE 3: SMART DIFFERENTIAL SYNC                  │
 │  supabase_sync.py                                               │
 │  • Pre-sync Supabase state inspection                           │
 │  • SKIPS unchanged bulletins (zero redundant DB writes)         │
 │  • INSERTS new bulletins into public.raw_messages               │
 │  • UPSERTS new/revised bulletins into public.nav_warnings       │
 │  • MARKS status='cancelled' for expired/dropped bulletins       │
 │    (source_id: 'sma-baltic-subarea', navarea: 'Baltic')         │
 └────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │               STAGE 4: MARITIME PRESENTATION                    │
 │  Helm.Warning Web Portal (Next.js / MapLibre / Vercel)          │
 │  https://helmwarning.vercel.app/                                │
 └─────────────────────────────────────────────────────────────────┘
```

---

## 💾 Database Integration Contract

Fully aligned with the Helm.Warning data bank specification:
- **`source_id`**: `'sma-baltic-subarea'` (matches [`sourcesRegistry.ts`](../navwaarning%20sep2026/src/data/sourcesRegistry.ts))
- **`navarea`**: `'Baltic'` (matches [`types.ts`](../navwaarning%20sep2026/src/types.ts))

### Composite Uniqueness:
- `public.raw_messages`: `(warning_id, source_id, checksum_sha256)`
- `public.nav_warnings`: `(warning_id, source_id)`

---

## 🏷️ Hazard Classification

| Category | Keywords & Terminology | Sample Baltic Findings |
| :--- | :--- | :--- |
| `military` | `DETONATIONS`, `FIRING`, `GUNNERY`, `ARMED FORCES`, `NAVAL EXERCISES` | Lysekil detonations (`168/26`), Central Baltic exercises (`029/26`) |
| `aton` | `LIGHT`, `LIGHTS`, `BUOY`, `RACON`, `BEACON`, `UNLIT`, `EXTINGUISHED` | Donsö Svartskär unlit (`156/26`), Dalbolandet lights (`159/26`) |
| `subsea` | `PIPELINE`, `CABLE`, `SEISMIC`, `DREDGING`, `ANCHOR`, `CHAIN LOST` | Kärsön pipeline (`160/26`), Luleå lost anchor & chain (`165/26`) |
| `electronic` | `GNSS`, `DGPS`, `AIS INTERFERENCE`, `RADAR INTERFERENCE`, `JAMMING` | Baltic-wide GNSS/AIS interference alert (`026/25`) |
| `drifting` | `DRIFTING`, `DERELICT`, `MINE`, `CONTAINER` | Adrift navigation hazards |
| `general` | *(Fallback)* | General safety and advisory bulletins |

---

## ⚙️ Quickstart & Local Execution

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Environment Variables (Optional for Supabase Sync)
```bash
# PowerShell:
$env:SUPABASE_URL = "https://your-project.supabase.co"
$env:SUPABASE_KEY = "your-supabase-key"

# Bash:
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-supabase-key"
```

### 3. Run Pipeline
```bash
# Execute end-to-end pipeline in one command:
python run_pipeline.py

# Or step-by-step:
python baltic_scraper.py   # Harvests navarea_baltic_warnings.txt
python baltic_parser.py    # Normalizes & emits parsed_warnings.json
python supabase_sync.py    # Syncs to Supabase tables
```

### 4. Run Unit Test Suite
```bash
python -m unittest tests/test_baltic.py
```

---

## 🤖 Cloud Automation (GitHub Actions)

Configured via [`.github/workflows/baltic-sync.yml`](./.github/workflows/baltic-sync.yml):
- **Cron Frequency:** Every 6 hours (`0 */6 * * *`).
- **Manual Trigger:** Supported via `workflow_dispatch`.
- **Secrets Configured:** `SUPABASE_URL` and `SUPABASE_KEY`.
- **Artifacts:** Publishes verified `navarea_baltic_warnings.txt` and `parsed_warnings.json` on each run.
