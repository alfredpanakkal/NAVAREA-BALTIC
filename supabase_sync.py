#!/usr/bin/env python3
"""
supabase_sync.py — Baltic Navigational Warnings Supabase Synchronizer
Synchronizes parsed Swedish & Baltic Sea navigational warnings into Supabase:
- public.raw_messages: Immutable audit log (insert)
- public.nav_warnings: Master active registry (upsert on warning_id, source_id)
"""

import os
import json
import sys
from supabase import create_client, Client

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

VALID_RAW_MESSAGE_COLUMNS = {
    "warning_id", "source_id", "subject_header",
    "full_raw_text", "received_timestamp", "checksum_sha256"
}

VALID_NAV_WARNING_COLUMNS = {
    "warning_id", "source_id", "navarea", "title",
    "issued_text", "coordinates", "latitude", "longitude",
    "category", "status", "raw_text"
}

def sync_to_supabase(json_file="parsed_warnings.json"):
    print("=" * 60)
    print("⚡ Supabase Maritime Synchronization Engine (Baltic)")
    print("=" * 60)

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        print("⚠️ Warning: SUPABASE_URL or SUPABASE_KEY environment variables are missing.")
        print("Skipping Supabase synchronization. (Set SUPABASE_URL & SUPABASE_KEY to enable)")
        return

    try:
        supabase: Client = create_client(url, key)
    except Exception as e:
        print(f"❌ Error initializing Supabase client: {e}")
        sys.exit(1)

    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {json_file} not found.")
        sys.exit(1)

    messages_to_insert = data.get("raw_messages", [])
    warnings_to_insert = data.get("nav_warnings", [])

    if not warnings_to_insert and not messages_to_insert:
        print("ℹ️ No warnings found in payload to sync.")
        return

    has_errors = False

    # 1. Sync raw_messages via insert
    print(f"\n[1/2] Syncing {len(messages_to_insert)} audit records to 'public.raw_messages'...")
    for msg in messages_to_insert:
        clean_msg = {k: v for k, v in msg.items() if k in VALID_RAW_MESSAGE_COLUMNS}
        try:
            supabase.table("raw_messages").insert(clean_msg).execute()
            print(f"  ✅ [raw_messages] Inserted audit record: {msg['warning_id']}")
        except Exception as e:
            # Duplicate checksum or warning_id already logged
            print(f"  ℹ️ [raw_messages] Notice for {msg['warning_id']}: {e}")

    # 2. Sync nav_warnings via upsert (on composite key warning_id, source_id)
    print(f"\n[2/2] Syncing {len(warnings_to_insert)} active warnings to 'public.nav_warnings'...")
    for warn in warnings_to_insert:
        clean_warn = {k: v for k, v in warn.items() if k in VALID_NAV_WARNING_COLUMNS}
        try:
            supabase.table("nav_warnings").upsert(clean_warn, on_conflict="warning_id,source_id").execute()
            print(f"  ✅ [nav_warnings] Upserted active record: {warn['warning_id']} ({warn.get('category')})")
        except Exception as e:
            print(f"  ❌ [nav_warnings] ERROR syncing {warn['warning_id']}: {e}")
            has_errors = True

    if has_errors:
        print("\n❌ Sync completed with errors.")
        sys.exit(1)
    else:
        print("\n🎉 Finished synchronization operation cleanly with 0 errors!")

if __name__ == "__main__":
    sync_to_supabase()
