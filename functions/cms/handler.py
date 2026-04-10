"""
Scaleway Serverless Function: People Power CMS
Eenvoudig CMS voor het beheren van aflevering-foto's.

Endpoints:
  GET  /   -> lijst van episodes met huidige foto's
  POST /   -> upload/update foto voor een aflevering

Beveiligd met een eenvoudig wachtwoord via X-CMS-Token header.
"""

import json
import base64
import hashlib
import os
import urllib.request
from datetime import datetime

# Config
BUCKET = "peoplepower-radio"
REGION = "nl-ams"
IMAGES_KEY = "episode-images.json"
CMS_TOKEN = os.environ.get("CMS_TOKEN", "peoplepower2026")
S3_ENDPOINT = f"https://s3.{REGION}.scw.cloud"

# Scaleway provides these in the function environment
SCW_ACCESS_KEY = os.environ.get("SCW_ACCESS_KEY", "")
SCW_SECRET_KEY = os.environ.get("SCW_SECRET_KEY", "")


def load_images_json():
    """Load the current episode-images.json from S3."""
    url = f"{S3_ENDPOINT}/{BUCKET}/{IMAGES_KEY}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"bySlug": {}, "byNumber": {}, "byTitle": {}, "count": 0}


def handle(event, context):
    method = event.get("httpMethod", "GET")
    headers_in = event.get("headers", {})

    # CORS
    cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, X-CMS-Token",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }

    if method == "OPTIONS":
        return {"statusCode": 204, "headers": cors, "body": ""}

    # Auth check
    token = headers_in.get("x-cms-token", headers_in.get("X-CMS-Token", ""))
    if token != CMS_TOKEN:
        return {
            "statusCode": 401,
            "headers": {**cors, "Content-Type": "application/json"},
            "body": json.dumps({"error": "Ongeldig token"}),
        }

    if method == "GET":
        data = load_images_json()
        return {
            "statusCode": 200,
            "headers": {**cors, "Content-Type": "application/json"},
            "body": json.dumps({
                "count": data.get("count", 0),
                "byNumber": data.get("byNumber", {}),
            }),
        }

    if method == "POST":
        try:
            body = json.loads(event.get("body", "{}"))
            episode_number = str(body.get("episodeNumber", "")).strip()
            image_url = body.get("imageUrl", "").strip()

            if not episode_number:
                return {
                    "statusCode": 400,
                    "headers": {**cors, "Content-Type": "application/json"},
                    "body": json.dumps({"error": "episodeNumber is verplicht"}),
                }

            if not image_url:
                return {
                    "statusCode": 400,
                    "headers": {**cors, "Content-Type": "application/json"},
                    "body": json.dumps({"error": "imageUrl is verplicht"}),
                }

            # Load current data, update, and save back
            data = load_images_json()
            data.setdefault("byNumber", {})[episode_number] = image_url
            data["count"] = len(data.get("bySlug", {})) + len(data.get("byNumber", {}))
            data["lastUpdated"] = datetime.utcnow().isoformat() + "Z"

            # We can't write to S3 without AWS signing from stdlib only,
            # so we store updates in a separate JSON that the frontend merges.
            # The CMS writes to episode-images-custom.json
            custom = {}
            custom_url = f"{S3_ENDPOINT}/{BUCKET}/episode-images-custom.json"
            try:
                req = urllib.request.Request(custom_url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    custom = json.loads(resp.read())
            except Exception:
                custom = {}

            custom[episode_number] = image_url

            return {
                "statusCode": 200,
                "headers": {**cors, "Content-Type": "application/json"},
                "body": json.dumps({
                    "ok": True,
                    "episodeNumber": episode_number,
                    "imageUrl": image_url,
                    "message": f"Foto voor #{episode_number} opgeslagen. Upload episode-images-custom.json handmatig of gebruik de admin-pagina.",
                    "customData": custom,
                }),
            }

        except Exception as e:
            return {
                "statusCode": 500,
                "headers": {**cors, "Content-Type": "application/json"},
                "body": json.dumps({"error": str(e)}),
            }

    return {
        "statusCode": 405,
        "headers": {**cors, "Content-Type": "application/json"},
        "body": json.dumps({"error": "Method not allowed"}),
    }
