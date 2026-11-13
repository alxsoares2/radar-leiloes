import os
from urllib.parse import urlsplit

import requests


class Supabase:
    def __init__(self, url, key):
        self.url = url
        self.headers = {"apikey": key}
        if not key.startswith("sb_"):
            self.headers["Authorization"] = f"Bearer {key}"

    def request(self, method, resource, **options):
        headers = {**self.headers, **options.pop("headers", {})}
        response = requests.request(method, f"{self.url}/{resource}", headers=headers, timeout=20, **options)
        if not response.ok:
            raise RuntimeError(f"Supabase respondeu HTTP {response.status_code}.")
        return response

    def read(self):
        rows = self.request("GET", "rest/v1/radar_snapshot", params={"id": "eq.main", "select": "payload"}).json()
        return rows[0]["payload"] if rows else None

    def save(self, data):
        self.request(
            "POST", "rest/v1/radar_snapshot", json={"id": "main", "payload": data},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )


def cloud_database():
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not url and not key:
        return None
    if urlsplit(url).scheme != "https" or not urlsplit(url).hostname or not key:
        raise RuntimeError("Configure SUPABASE_URL (HTTPS) e SUPABASE_SECRET_KEY.")
    return Supabase(url, key)

