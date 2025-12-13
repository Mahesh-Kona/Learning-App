import os
import sys
import json
import argparse

try:
    import requests
except Exception as e:
    print("requests package is required. Install with: pip install requests")
    sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Smoke-test cards API: login, list topic cards, fetch first card")
    parser.add_argument("--base", default=os.environ.get("BASE_URL", "http://127.0.0.1:5000"), help="API base URL")
    parser.add_argument("--email", default=os.environ.get("TEST_EMAIL", "n210163@rguktn.ac.in"), help="Login email")
    parser.add_argument("--password", default=os.environ.get("TEST_PASSWORD", "pass1"), help="Login password")
    parser.add_argument("--topic", type=int, default=int(os.environ.get("TOPIC_ID", "32")), help="Topic ID to query")
    parser.add_argument("--card", type=int, default=None, help="Specific card ID to fetch (optional)")
    args = parser.parse_args()

    base = args.base.rstrip("/")

    # 1) Login to get JWT
    login_url = f"{base}/api/v1/auth/login"
    print(f"[1/3] POST {login_url}")
    r = requests.post(login_url, json={"email": args.email, "password": args.password})
    try:
        j = r.json()
    except Exception:
        print(f"Login failed (non-JSON {r.status_code}):\n{r.text}")
        sys.exit(1)

    if r.status_code != 200 or not j.get("access_token"):
        print(f"Login failed: status={r.status_code}, body={json.dumps(j, indent=2)}")
        sys.exit(1)

    token = j["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login OK. Token acquired.")

    # 2) GET cards for topic
    list_url = f"{base}/api/v1/topics/{args.topic}/cards"
    print(f"[2/3] GET {list_url}")
    r2 = requests.get(list_url, headers=headers)
    try:
        j2 = r2.json()
    except Exception:
        print(f"List cards failed (non-JSON {r2.status_code}):\n{r2.text}")
        sys.exit(1)

    if r2.status_code != 200 or not j2.get("success"):
        print(f"List cards failed: status={r2.status_code}, body={json.dumps(j2, indent=2)}")
        sys.exit(1)

    cards = j2.get("cards", [])
    print(f"Topic {args.topic} cards count: {len(cards)}")
    if cards:
        print(json.dumps(cards[:1], indent=2))

    # 3) Optionally fetch a specific card (either provided or first from list)
    card_id = args.card or (cards[0]["id"] if cards else None)
    if card_id is not None:
        get_url = f"{base}/api/v1/cards/{card_id}"
        print(f"[3/3] GET {get_url}")
        r3 = requests.get(get_url, headers=headers)
        try:
            j3 = r3.json()
        except Exception:
            print(f"Get card failed (non-JSON {r3.status_code}):\n{r3.text}")
            sys.exit(1)

        if r3.status_code != 200 or not j3.get("success"):
            print(f"Get card failed: status={r3.status_code}, body={json.dumps(j3, indent=2)}")
            sys.exit(1)

        print("Single card OK:")
        print(json.dumps(j3.get("card", {}), indent=2))

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
