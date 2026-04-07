import os, time, requests
from dotenv import load_dotenv

load_dotenv()

_token_cache = {"token": None, "expires_at": 0}

def get_token() -> str:
    """Return a valid AI Core OAuth token, refreshing only if near expiry."""
    now = time.time()
    # Refresh if expired or within 5 minutes of expiry
    if _token_cache["token"] is None or now >= _token_cache["expires_at"] - 300:
        resp = requests.post(
            f"{os.environ['AICORE_AUTH_URL']}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": os.environ["AICORE_CLIENT_ID"],
                "client_secret": os.environ["AICORE_CLIENT_SECRET"],
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = now + data.get("expires_in", 43200)
    return _token_cache["token"]
