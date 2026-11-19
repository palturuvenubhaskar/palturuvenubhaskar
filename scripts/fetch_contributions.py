#!/usr/bin/env python3
"""
Scrape real daily contribution counts from GitHub's public, unauthenticated
contributions fragment and write data/contributions.json with the raw days plus
derived stats (current streak, longest streak, best day, monthly totals).

No token, no auth, no GraphQL -- just the public HTML GitHub already serves.
Run by .github/workflows/readme-cards.yml before render_readme_cards.py.
"""

import datetime
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

USERNAME = os.environ.get("GH_PROFILE_USER", "palturuvenubhaskar")
URL = f"https://github.com/users/{USERNAME}/contributions"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "contributions.json")


def fetch_days():
    resp = requests.get(URL, headers={"User-Agent": "profile-readme-bot/1.0"}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    cells = soup.select("td.ContributionCalendar-day")
    if not cells:
        print("no calendar cells found -- github markup may have changed", file=sys.stderr)
        sys.exit(1)

    days = []
    for td in cells:
        day = td.get("data-date")
        if not day:
            continue
        tip = soup.find("tool-tip", attrs={"for": td.get("id")}) if td.get("id") else None
        text = tip.get_text(strip=True) if tip else ""
        if re.search(r"no contributions", text, re.I):
            count = 0
        else:
            m = re.match(r"(\d+)", text)
            count = int(m.group(1)) if m else 0
        days.append({"date": day, "count": count, "level": int(td.get("data-level") or 0)})

    days.sort(key=lambda d: d["date"])
    return days


def current_streak(days):
    idx = len(days) - 1
    if days[idx]["count"] == 0:  # today isn't over yet
        idx -= 1
    end, run = idx, 0
    while idx >= 0 and days[idx]["count"] > 0:
        run += 1
        idx -= 1
    return (run, days[idx + 1]["date"], days[end]["date"]) if run else (0, None, None)


def longest_streak(days):
    best = run = 0
    start = end = None
    run_start = 0
    for i, d in enumerate(days):
        if d["count"] > 0:
            if run == 0:
                run_start = i
            run += 1
            if run > best:
                best, start, end = run, days[run_start]["date"], days[i]["date"]
        else:
            run = 0
    return best, start, end


def build(days):
    total = sum(d["count"] for d in days)
    active = sum(1 for d in days if d["count"] > 0)
    best = max(days, key=lambda d: d["count"])
    cs, cs0, cs1 = current_streak(days)
    ls, ls0, ls1 = longest_streak(days)

    monthly = {}
    for d in days:
        monthly[d["date"][:7]] = monthly.get(d["date"][:7], 0) + d["count"]

    return {
        "username": USERNAME,
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "range": {"start": days[0]["date"], "end": days[-1]["date"]},
        "total_contributions": total,
        "active_days": active,
        "avg_per_active_day": round(total / active, 1) if active else 0,
        "current_streak": {"length": cs, "start": cs0, "end": cs1},
        "longest_streak": {"length": ls, "start": ls0, "end": ls1},
        "best_day": {"date": best["date"], "count": best["count"]},
        "monthly": [{"month": k, "total": v} for k, v in sorted(monthly.items())],
        "days": days,
    }


if __name__ == "__main__":
    data = build(fetch_days())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(
        f"wrote {OUT}: {data['total_contributions']} contributions, "
        f"streak {data['current_streak']['length']} (best {data['longest_streak']['length']})"
    )
