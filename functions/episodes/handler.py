"""
Scaleway Serverless Function: People Power episodes
Haalt de Springcast RSS feed op, parseert hem en geeft JSON terug.

Endpoint: GET /episodes
Cache: 10 minuten via Cache-Control header
"""

import json
import re
import urllib.request
from datetime import datetime
from xml.etree import ElementTree as ET

RSS_URL = "https://app.springcast.fm/podcast-xml/17987"
CACHE_SECONDS = 600

MONTHS_NL = ["jan", "feb", "mrt", "apr", "mei", "jun",
             "jul", "aug", "sep", "okt", "nov", "dec"]


def strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_duration(s: str) -> str:
    if not s:
        return ""
    if ":" in s:
        parts = [int(p) for p in s.split(":") if p.isdigit()]
        if len(parts) == 3:
            return f"{parts[0] * 60 + parts[1]} min"
        if len(parts) == 2:
            return f"{parts[0]} min"
    try:
        sec = int(s)
        return f"{round(sec / 60)} min"
    except ValueError:
        return ""


def format_date(s: str) -> str:
    if not s:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            d = datetime.strptime(s, fmt)
            return f"{d.day} {MONTHS_NL[d.month - 1]} {d.year}"
        except ValueError:
            continue
    return ""


def extract_episodes(xml_text: str):
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []

    episodes = []
    for item in channel.findall("item"):
        title_raw = (item.findtext("title") or "").strip()
        description = strip_html(item.findtext("description") or "")
        pub_date = (item.findtext("pubDate") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip()

        enclosure = item.find("enclosure")
        audio_url = enclosure.get("url") if enclosure is not None else ""

        image_el = item.find("itunes:image", namespaces=ns)
        image_url = image_el.get("href") if image_el is not None else ""

        duration_raw = item.findtext("itunes:duration", default="", namespaces=ns)
        duration = parse_duration(duration_raw)

        # Episode nummer extraheren uit titel als die begint met "#NNN"
        episode_number = ""
        clean_title = title_raw
        m = re.match(r"^#(\d+)\s+(.*)", title_raw)
        if m:
            episode_number = m.group(1)
            clean_title = m.group(2)

        episodes.append({
            "id": guid or link,
            "number": episode_number,
            "title": clean_title,
            "description": description[:240],
            "descriptionFull": description,
            "pubDate": pub_date,
            "pubDateFormatted": format_date(pub_date),
            "audioUrl": audio_url,
            "duration": duration,
            "link": link,
            "imageUrl": image_url,
        })
    return episodes


def handle(event, context):
    """Scaleway Serverless Function entrypoint."""
    try:
        req = urllib.request.Request(
            RSS_URL,
            headers={"User-Agent": "PeoplePower-Site/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_text = resp.read().decode("utf-8")

        episodes = extract_episodes(xml_text)

        # Query params: ?full=1 includes descriptionFull field
        qs = event.get("queryStringParameters") or {}
        include_full = qs.get("full") == "1"

        if not include_full:
            # Strip descriptionFull to keep payload smaller
            for ep in episodes:
                ep.pop("descriptionFull", None)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Cache-Control": f"public, max-age={CACHE_SECONDS}, stale-while-revalidate=86400",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "count": len(episodes),
                "episodes": episodes,
            }),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }
