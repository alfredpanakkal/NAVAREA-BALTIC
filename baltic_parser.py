#!/usr/bin/env python3
"""
baltic_parser.py — Deterministic Navigational Warning Parser for Baltic & Swedish Bulletins
Normalizes coordinate geometries into WGS84 decimal, infers issued years, classifies maritime hazard semantics,
and prepares structured JSON payloads for Supabase synchronization.
"""

import sys
import re
import json
import hashlib
from datetime import datetime, timezone

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

SOURCE_ID = "sma-baltic-subarea"
NAVAREA_ID = "Baltic"

def convert_to_decimal(degrees: str, minutes: str, direction: str) -> float:
    """Converts Degrees and Decimal Minutes into Signed Decimal Degrees (WGS84)."""
    decimal = float(degrees) + (float(minutes) / 60.0)
    if direction.upper() in ['S', 'W']:
        decimal = -decimal
    return round(decimal, 6)

def parse_coordinates(raw_text: str):
    """
    Extracts navigational coordinates from text.
    Handles varied precision:
      - 58-10.2N 011-13.3E
      - 57-35.15N 011-43.33E
      - 64-39.71N 021-16.82E
    """
    # Regex matches: DD-MM.MM[N/S] DDD-MM.MM[E/W]
    pattern = r'(\d{2,3})-(\d{2}(?:\.\d+)?)[N|S]\s+(\d{2,3})-(\d{2}(?:\.\d+)?)[E|W]'
    matches = list(re.finditer(pattern, raw_text))

    parsed_coords = []
    points = []

    for match in matches:
        full_match = match.group(0)
        # Parse latitude and longitude components
        sub = re.match(r'(\d{2,3})-(\d{2}(?:\.\d+)?)([NS])\s+(\d{2,3})-(\d{2}(?:\.\d+)?)([EW])', full_match, re.IGNORECASE)
        if sub:
            lat_deg, lat_min, lat_dir = sub.group(1), sub.group(2), sub.group(3).upper()
            lon_deg, lon_min, lon_dir = sub.group(4), sub.group(5), sub.group(6).upper()

            lat = convert_to_decimal(lat_deg, lat_min, lat_dir)
            lon = convert_to_decimal(lon_deg, lon_min, lon_dir)

            points.append([lon, lat])  # GeoJSON format: [lon, lat]
            parsed_coords.append(f"{lat_deg}-{lat_min}{lat_dir} {lon_deg}-{lon_min}{lon_dir}")

    spatial = None
    primary_lat = None
    primary_lon = None

    if points:
        if len(points) == 1:
            primary_lat = points[0][1]
            primary_lon = points[0][0]
            spatial = {"type": "Point", "coordinates": points[0]}
        elif len(points) >= 4:
            # Check for polygon or closed bounding box
            primary_lat = round(sum(p[1] for p in points) / len(points), 6)
            primary_lon = round(sum(p[0] for p in points) / len(points), 6)
            # Ensure closed polygon loop for GeoJSON specification
            closed_points = points if points[0] == points[-1] else points + [points[0]]
            spatial = {"type": "Polygon", "coordinates": [closed_points]}
        else:
            primary_lat = points[0][1]
            primary_lon = points[0][0]
            spatial = {"type": "LineString", "coordinates": points}

    return parsed_coords, primary_lat, primary_lon, spatial

def classify_hazard(raw_text: str) -> str:
    """Classifies maritime hazard category based on terminology."""
    text = raw_text.upper()
    # 1. Electronic / GNSS interference
    if any(k in text for k in ["GNSS", "DGPS", "AIS INTERFERENCE", "RADAR INTERFERENCE", "INTERFERENCE OBSERVED", "JAMMING", "SPOOFING"]):
        return "electronic"
    # 2. Military / Naval operations (explicitly avoid matching "EXERCISE CAUTION")
    military_pattern = r'\b(DETONATION|DETONATIONS|FIRING|FIRINGS|GUNNERY|MISSILE|WEAPONS?|ARMED FORCES|NAVAL EXERCISE|NAVAL EXERCISES|MILITARY EXERCISE)\b'
    if re.search(military_pattern, text):
        return "military"
    # 3. Aids to Navigation (AtoN)
    if any(k in text for k in ["LIGHT", "LIGHTS", "BUOY", "BUOYS", "RACON", "BEACON", "UNLIT", "EXTINGUISHED"]):
        return "aton"
    # 4. Subsea / Obstruction
    if any(k in text for k in ["SEISMIC", "CABLE", "PIPELINE", "ROV", "TOWING", "DREDGING", "ANCHOR", "CHAIN LOST"]):
        return "subsea"
    # 5. Drifting hazards
    if any(k in text for k in ["DRIFTING", "DERELICT", "MINE", "CONTAINER"]):
        return "drifting"
    # 6. Offshore operations
    if any(k in text for k in ["RIG", "PLATFORM", "JACK-UP"]):
        return "offshore"
    return "general"

def parse_warning(raw_block: str, reference_header: str):
    """
    Parses a single warning block and reference header into database-ready structures.
    Header format example:
      'SWEDISH NAV WARN 168/26 [Skagerrak]'
      'BALTIC SEA NAV WARN 026/25 [Western Baltic, Central Baltic]'
    """
    # 1. Extract warning ID and sub-areas
    header_clean = reference_header.strip()
    area_match = re.search(r'\[(.*?)\]', header_clean)
    sub_areas_text = area_match.group(1) if area_match else ""
    header_no_area = re.sub(r'\s*\[.*?\]', '', header_clean).strip()

    # Form standardized warning_id:
    # "SWEDISH NAV WARN 168/26" -> "SWEDISH 168/26"
    # "BALTIC SEA NAV WARN 026/25" -> "BALTIC 026/25"
    if "BALTIC SEA NAV WARN" in header_no_area:
        num = header_no_area.split("BALTIC SEA NAV WARN")[-1].strip()
        warning_id = f"BALTIC {num}"
    elif "SWEDISH NAV WARN" in header_no_area:
        num = header_no_area.split("SWEDISH NAV WARN")[-1].strip()
        warning_id = f"SWEDISH {num}"
    else:
        warning_id = header_no_area

    # 2. Extract lines & determine title
    lines = [line.strip() for line in raw_block.split('\n') if line.strip()]

    # Check for issued date line (e.g. 080056 UTC OCT)
    date_pattern = r'(\d{6}\s+UTC\s+[A-Z]{3})'
    issued_text = None
    title = ""

    for line in lines:
        d_match = re.search(date_pattern, line)
        if d_match and not issued_text:
            issued_text = d_match.group(1)
        elif not title and not d_match:
            title = line

    # Infer year from warning_id (e.g. 168/26 -> 2026, 026/25 -> 2025)
    yr_match = re.search(r'/(\d{2})$', warning_id)
    if yr_match and issued_text and not re.search(r'\b20\d{2}\b', issued_text):
        full_year = f"20{yr_match.group(1)}"
        issued_text = f"{issued_text} {full_year}"

    # 3. Parse coordinates
    coords_text, lat, lon, spatial = parse_coordinates(raw_block)

    # 4. Classify hazard
    hazard = classify_hazard(raw_block)

    # 5. Checksum calculation
    checksum = hashlib.sha256(raw_block.encode('utf-8')).hexdigest()

    raw_message = {
        "warning_id": warning_id,
        "source_id": SOURCE_ID,
        "subject_header": header_clean,
        "full_raw_text": raw_block,
        "received_timestamp": datetime.now(timezone.utc).isoformat(),
        "checksum_sha256": checksum
    }

    nav_warning = {
        "warning_id": warning_id,
        "source_id": SOURCE_ID,
        "navarea": NAVAREA_ID,
        "title": title or header_no_area,
        "issued_text": issued_text,
        "coordinates": ", ".join(coords_text) if coords_text else None,
        "latitude": lat,
        "longitude": lon,
        "category": hazard,
        "status": "active",
        "raw_text": raw_block
    }

    return raw_message, nav_warning, spatial

def main(input_filename="navarea_baltic_warnings.txt", output_filename="parsed_warnings.json"):
    print("=" * 60)
    print("🧭 Sjofartsverket Baltic Navigational Warnings Parser")
    print("=" * 60)
    try:
        with open(input_filename, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: {input_filename} not found.")
        return

    # Match blocks delimited by --- HEADER ---
    pattern = r'--- (.*?) ---\n(.*?)(?=\n--- |$)'
    matches = re.findall(pattern, content, re.DOTALL)

    parsed_data = {
        "raw_messages": [],
        "nav_warnings": [],
        "spatial_features": []
    }

    for header, block in matches:
        raw_msg, nav_warn, spatial = parse_warning(block.strip(), header.strip())
        parsed_data["raw_messages"].append(raw_msg)
        parsed_data["nav_warnings"].append(nav_warn)
        if spatial:
            parsed_data["spatial_features"].append({
                "warning_id": nav_warn["warning_id"],
                "category": nav_warn["category"],
                "geometry": spatial
            })

    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Successfully parsed {len(matches)} warnings into '{output_filename}'.")
    print(f"   • {len(parsed_data['raw_messages'])} audit records prepared for 'public.raw_messages'")
    print(f"   • {len(parsed_data['nav_warnings'])} active warnings prepared for 'public.nav_warnings'")
    print(f"   • {len(parsed_data['spatial_features'])} GeoJSON geometries generated")

if __name__ == "__main__":
    main()
