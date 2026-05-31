"""
NetEase Cloud Music podcast playlist refresh script
Usage: python update_playlist.py
Fetches all programs from a DJ radio, downloads MP3 files, and updates playlist.json
"""

import json
import sys
import io
import os
import urllib.request
import urllib.error
import re
import time

# Fix encoding for Windows CMD
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

RADIO_ID = "1224027027"
API_URL = f"https://music.163.com/api/dj/program/byradio?radioId={RADIO_ID}&limit=200"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "playlist.json")
JS_OUTPUT_FILE = os.path.join(SCRIPT_DIR, "_bgm_data.js")
MP3_DIR = os.path.join(SCRIPT_DIR, "mp3")

HEADERS = {
    "Referer": "https://music.163.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

MP3_DOWNLOAD_HEADERS = {
    "Referer": "https://music.163.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "*/*",
}

# Minimum file size for a valid MP3 (10 KB)
MIN_MP3_SIZE = 10 * 1024


def sanitize_filename(name):
    """Clean song name for use as a safe filename (no illegal chars)"""
    # Remove characters illegal in Windows filenames
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Replace multiple spaces with single space
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def fetch_playlist():
    """Fetch program list from NetEase Cloud Music API"""
    req = urllib.request.Request(API_URL, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("code") != 200:
                print(f"[ERROR] API returned code={data.get('code')}, message={data.get('message')}")
                return None
            return data["programs"]
    except urllib.error.URLError as e:
        print(f"[ERROR] Network request failed: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Parse failed: {e}")
        return None


def build_playlist(programs):
    """Convert raw program data to compact format (no artist field)"""
    result = []
    for p in programs:
        song = p.get("mainSong", {})
        name = song.get("name", "")
        result.append({
            "programId": p.get("id"),
            "name": name,
            "songId": song.get("id"),
            "duration": song.get("duration", 0),
            "filename": sanitize_filename(name),
        })
    return result


def download_mp3(song_id, filename):
    """Download a single MP3 from NetEase Cloud Music outer URL.
    
    Returns True on success, False on failure.
    """
    os.makedirs(MP3_DIR, exist_ok=True)
    filepath = os.path.join(MP3_DIR, f"{filename}.mp3")

    # Skip if already downloaded and valid
    if os.path.exists(filepath) and os.path.getsize(filepath) > MIN_MP3_SIZE:
        return True

    url = f"https://music.163.com/song/media/outer/url?id={song_id}.mp3"
    req = urllib.request.Request(url, headers=MP3_DOWNLOAD_HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content_type = resp.headers.get('Content-Type', '')
            # Only save if actual audio data
            data = resp.read()
            if len(data) > MIN_MP3_SIZE:
                with open(filepath, 'wb') as f:
                    f.write(data)
                print(f"    ✓ 下载完成 ({len(data) // 1024} KB)")
                return True
            else:
                print(f"    ✗ 文件太小 ({len(data)} bytes)，可能被拒绝访问")
                # Don't save invalid file
                if os.path.exists(filepath):
                    os.remove(filepath)
                return False
    except urllib.error.HTTPError as e:
        print(f"    ✗ HTTP {e.code}: {e.reason}")
        return False
    except Exception as e:
        print(f"    ✗ 下载失败: {e}")
        return False


def cleanup_mp3(valid_filenames):
    """Remove MP3 files that are no longer in the playlist"""
    if not os.path.isdir(MP3_DIR):
        return

    valid_set = set(valid_filenames)
    for fname in os.listdir(MP3_DIR):
        if not fname.endswith('.mp3'):
            continue
        name_no_ext = fname[:-4]  # remove .mp3
        if name_no_ext not in valid_set:
            filepath = os.path.join(MP3_DIR, fname)
            os.remove(filepath)
            print(f"    🗑 清理: {fname}")


def main():
    print(f"Fetching podcast playlist (radioId={RADIO_ID}) ...")
    programs = fetch_playlist()
    if not programs:
        sys.exit(1)

    playlist = {
        "radioId": RADIO_ID,
        "count": len(programs),
        "programs": build_playlist(programs),
    }

    # Ensure mp3/ directory exists
    os.makedirs(MP3_DIR, exist_ok=True)

    # Download MP3s (skip already existing valid files)
    print(f"\nDownloading MP3s ({len(playlist['programs'])} programs) ...")
    success_count = 0
    fail_count = 0
    for i, p in enumerate(playlist["programs"]):
        fn = p["filename"]
        sid = p["songId"]
        print(f"  [{i+1}/{len(playlist['programs'])}] {fn} (songId={sid})")
        if download_mp3(sid, fn):
            success_count += 1
        else:
            fail_count += 1
        # Small delay to avoid rate limiting
        time.sleep(0.3)

    print(f"\nMP3 download: {success_count} ok, {fail_count} failed")

    # Clean up orphaned MP3s
    valid_filenames = [p["filename"] for p in playlist["programs"]]
    cleanup_mp3(valid_filenames)

    # Write playlist.json
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(playlist, f, ensure_ascii=False, indent=2)

    # Generate _bgm_data.js (no artist field)
    js_data = []
    for p in playlist["programs"]:
        js_data.append({
            "programId": p["programId"],
            "name": p["name"],
            "songId": p["songId"],
            "duration": p["duration"],
            "filename": p["filename"],
        })
    js_content = "/* Auto-generated by update_playlist.py - DO NOT EDIT */\n"
    js_content += "var __BGM_PLAYLIST__ = " + json.dumps(js_data, ensure_ascii=False) + ";\n"
    with open(JS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"\n[OK] Success! {len(programs)} programs saved to {OUTPUT_FILE}")
    print(f"     Also generated {JS_OUTPUT_FILE} ({len(js_content)} bytes)")
    print(f"  Preview (first 5):")
    for i, p in enumerate(playlist["programs"][:5]):
        print(f"    {i+1}. {p['name']} (songId={p['songId']}, file={p['filename']}.mp3)")


if __name__ == "__main__":
    main()
