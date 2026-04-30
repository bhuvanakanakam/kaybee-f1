#!/usr/bin/env python3
"""
Bhuvana's Pit Wall — Live API Server
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Data sources:
  • Jolpica F1 API  (https://api.jolpi.ca/ergast)  — standings, results, schedule
  • FastF1          (https://github.com/theOehrly/Fast-F1) — pit stops, lap analysis

Run:  python3 server.py
Dashboard: http://localhost:5000
"""

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import requests
import certifi
import time
from datetime import datetime, timezone
from pathlib import Path

# ── FastF1 (optional — degrades gracefully if session load fails) ──
try:
    import fastf1
    import pandas as pd
    FF1_AVAILABLE = True
except ImportError:
    FF1_AVAILABLE = False
    print("  [warn] fastf1 not installed — pip install fastf1  (pit-stop analysis disabled)")

# ── App setup ────────────────────────────────────────────────────
app = Flask(__name__, static_folder=".")
CORS(app, origins="*")

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)
FF1_CACHE = CACHE_DIR / "fastf1"
FF1_CACHE.mkdir(exist_ok=True)

if FF1_AVAILABLE:
    fastf1.Cache.enable_cache(str(FF1_CACHE))

JOLPICA   = "https://api.jolpi.ca/ergast/f1"
_mem: dict = {}           # {key: (timestamp, data)}
CACHE_TTL  = 1800         # 30 min default
RACE_TTL   = 7200         # 2 h for results (they don't change once set)

# ── Team colour map ───────────────────────────────────────────────
_TEAM_COLORS = {
    "mercedes":       "#27F4D2",
    "ferrari":        "#E8002D",
    "mclaren":        "#FF8000",
    "red bull":       "#3671C6",
    "williams":       "#64C4FF",
    "haas":           "#B6BABD",
    "alpine":         "#0093CC",
    "audi":           "#00877C",
    "sauber":         "#00877C",
    "rb f1":          "#6692FF",
    "racing bulls":   "#6692FF",
    "visa cash":      "#6692FF",
    "alphatauri":     "#6692FF",
    "aston martin":   "#229971",
    "cadillac":       "#8A9099",
}

# Light-coloured teams whose badge text should be black
_LIGHT_TEAMS = {"mercedes", "williams", "haas"}


def team_color(name: str) -> str:
    nl = name.lower()
    for k, v in _TEAM_COLORS.items():
        if k in nl:
            return v
    return "#8a8172"


def badge_text_color(name: str) -> str:
    return "#000" if any(k in name.lower() for k in _LIGHT_TEAMS) else "#fff"


# ── HTTP helper ───────────────────────────────────────────────────
def jolpica(endpoint: str, key: str, ttl: int = CACHE_TTL):
    now = time.time()
    if key in _mem:
        ts, data = _mem[key]
        if now - ts < ttl:
            return data
    try:
        r = requests.get(
            f"{JOLPICA}/{endpoint}",
            timeout=12,
            headers={"User-Agent": "BhuvanasPitWall/2.0"},
            verify=certifi.where(),
        )
        r.raise_for_status()
        data = r.json()
        _mem[key] = (now, data)
        return data
    except Exception as exc:
        print(f"  [jolpica] {endpoint} → {exc}")
        if key in _mem:
            return _mem[key][1]   # serve stale
        return None


# ── FastF1 last-race session (background, lazy) ───────────────────
_ff1_session = None
_ff1_loaded  = False
_ff1_loading = False


def _load_ff1_session():
    global _ff1_session, _ff1_loaded, _ff1_loading
    if not FF1_AVAILABLE or _ff1_loading:
        return
    _ff1_loading = True
    try:
        year  = datetime.now(timezone.utc).year
        sched = fastf1.get_event_schedule(year, include_testing=False)
        today = datetime.now(timezone.utc).date()
        past  = sched[sched["EventDate"].dt.date < today]
        if past.empty:
            return
        last_event = past.iloc[-1]
        sess = fastf1.get_session(year, int(last_event["RoundNumber"]), "R")
        sess.load(laps=True, telemetry=False, weather=False, messages=False)
        _ff1_session = sess
        print(f"  [fastf1] loaded: {sess.event['EventName']} R{last_event['RoundNumber']}")
    except Exception as exc:
        print(f"  [fastf1] session load failed: {exc}")
    finally:
        _ff1_loaded  = True
        _ff1_loading = False


def ensure_ff1():
    """Trigger a background load if not yet done."""
    import threading
    if FF1_AVAILABLE and not _ff1_loaded and not _ff1_loading:
        threading.Thread(target=_load_ff1_session, daemon=True).start()


# ── Routes ────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/status")
def status():
    return jsonify({
        "ok":        True,
        "server":    "Bhuvana's Pit Wall API",
        "fastf1":    FF1_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/standings/drivers")
def driver_standings():
    data = jolpica("current/driverStandings.json", "wdc")
    if not data:
        return jsonify({"error": "upstream unavailable"}), 503
    lists = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists:
        return jsonify([])
    out = []
    for s in lists[0]["DriverStandings"]:
        team = s["Constructors"][0]["name"] if s["Constructors"] else ""
        code = s["Driver"].get("code") or s["Driver"]["familyName"][:3].upper()
        out.append({
            "pos":    int(s["position"]),
            "driver": f"{s['Driver']['givenName'][0]}. {s['Driver']['familyName']}",
            "full":   f"{s['Driver']['givenName']} {s['Driver']['familyName']}",
            "id":     s["Driver"]["driverId"],
            "code":   code,
            "nat":    s["Driver"]["nationality"],
            "team":   team,
            "color":  team_color(team),
            "textColor": badge_text_color(team),
            "pts":    float(s["points"]),
            "wins":   int(s["wins"]),
        })
    return jsonify(out)


@app.route("/api/standings/constructors")
def constructor_standings():
    data = jolpica("current/constructorStandings.json", "wcc")
    if not data:
        return jsonify({"error": "upstream unavailable"}), 503
    lists = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists:
        return jsonify([])
    out = []
    for s in lists[0]["ConstructorStandings"]:
        name = s["Constructor"]["name"]
        out.append({
            "pos":   int(s["position"]),
            "name":  name,
            "nat":   s["Constructor"]["nationality"],
            "color": team_color(name),
            "pts":   float(s["points"]),
            "wins":  int(s["wins"]),
        })
    return jsonify(out)


@app.route("/api/last-race")
def last_race():
    data = jolpica("current/last/results.json", "last_race", ttl=RACE_TTL)
    if not data:
        return jsonify({"error": "upstream unavailable"}), 503
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return jsonify({})
    race    = races[0]
    results = race["Results"]
    podium  = []
    for r in results[:3]:
        gap = r.get("Time", {}).get("time") or r.get("status", "")
        podium.append({
            "pos":    int(r["position"]),
            "driver": f"{r['Driver']['givenName']} {r['Driver']['familyName']}",
            "id":     r["Driver"]["driverId"],
            "team":   r["Constructor"]["name"],
            "number": r["Driver"]["permanentNumber"],
            "time":   gap,
        })
    fl = next((r for r in results if r.get("FastestLap", {}).get("rank") == "1"), None)
    return jsonify({
        "name":    race["raceName"],
        "circuit": race["Circuit"]["circuitName"],
        "date":    race["date"],
        "round":   int(race["round"]),
        "podium":  podium,
        "fastestLap": {
            "driver": f"{fl['Driver']['givenName']} {fl['Driver']['familyName']}",
            "time":   fl["FastestLap"]["Time"]["time"],
            "lap":    int(fl["FastestLap"]["lap"]),
            "speed":  fl["FastestLap"].get("AverageSpeed", {}).get("speed", ""),
        } if fl else None,
    })


@app.route("/api/next-race")
def next_race():
    data = jolpica("current/next.json", "next_race")
    if not data:
        return jsonify({"error": "upstream unavailable"}), 503
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return jsonify({})
    r = races[0]
    t = r.get("time", "13:00:00Z")
    return jsonify({
        "round":      int(r["round"]),
        "name":       r["raceName"],
        "circuit":    r["Circuit"]["circuitName"],
        "location":   f"{r['Circuit']['Location']['locality']}, {r['Circuit']['Location']['country']}",
        "country":    r["Circuit"]["Location"]["country"],
        "date":       r["date"],
        "time":       t,
        "datetime":   f"{r['date']}T{t.replace('Z', '+00:00')}",
        "qualifying": r.get("Qualifying", {}).get("date"),
        "sprint":     r.get("Sprint", {}).get("date"),
    })


@app.route("/api/schedule")
def schedule():
    data = jolpica("current.json", "schedule", ttl=86400)  # 24 h
    if not data:
        return jsonify({"error": "upstream unavailable"}), 503
    races = data["MRData"]["RaceTable"]["Races"]
    today = datetime.now(timezone.utc).date()
    out   = []
    for r in races:
        rd = datetime.strptime(r["date"], "%Y-%m-%d").date()
        out.append({
            "round":    int(r["round"]),
            "name":     r["raceName"],
            "circuit":  r["Circuit"]["circuitName"],
            "location": r["Circuit"]["Location"]["locality"],
            "country":  r["Circuit"]["Location"]["country"],
            "date":     r["date"],
            "fp1":      r.get("FirstPractice", {}).get("date"),
            "status":   "done" if rd < today else "upcoming",
        })
    return jsonify(out)


@app.route("/api/winners")
def winners():
    """P1 for every completed race this season."""
    data = jolpica("current/results.json?limit=50", "season_results", ttl=RACE_TTL)
    if not data:
        return jsonify({})
    out = {}
    for race in data["MRData"]["RaceTable"]["Races"]:
        if race["Results"]:
            w = race["Results"][0]
            out[int(race["round"])] = {
                "driver": f"{w['Driver']['givenName'][0]}. {w['Driver']['familyName']}",
                "team":   w["Constructor"]["name"],
            }
    return jsonify(out)


@app.route("/api/paddock")
def paddock():
    """Auto-generated paddock intel from Jolpica + FastF1."""
    ensure_ff1()
    intel = []

    # ── Story 1: Championship battle ─────────────────────────────
    wdc = jolpica("current/driverStandings.json", "wdc")
    if wdc:
        lists = wdc["MRData"]["StandingsTable"]["StandingsLists"]
        if lists and len(lists[0]["DriverStandings"]) >= 2:
            ds   = lists[0]["DriverStandings"]
            p1   = ds[0]
            p2   = ds[1]
            gap  = float(p1["points"]) - float(p2["points"])
            p1n  = f"{p1['Driver']['givenName']} {p1['Driver']['familyName']}"
            p2n  = f"{p2['Driver']['givenName']} {p2['Driver']['familyName']}"
            p1t  = p1["Constructors"][0]["name"] if p1["Constructors"] else ""
            intel.append({
                "kicker":   "The Story",
                "lead":     True,
                "headline": f"{p1n} leads championship · {gap:.0f} pts clear of {p2n.split()[-1]}",
                "body":     (
                    f"After {p1['wins']} win(s) this season, {p1n.split()[-1]} paces the field for "
                    f"{p1t}. {p2n.split()[-1]} is the nearest challenger at {float(p2['points']):.0f} pts "
                    f"— {gap:.0f} points behind."
                ),
            })

    # ── Story 2: Last race winner ─────────────────────────────────
    lr = jolpica("current/last/results.json", "last_race", ttl=RACE_TTL)
    if lr:
        races = lr["MRData"]["RaceTable"]["Races"]
        if races:
            race    = races[0]
            results = race["Results"]
            if results:
                w   = results[0]
                wn  = f"{w['Driver']['givenName']} {w['Driver']['familyName']}"
                wt  = w["Constructor"]["name"]
                fl  = next((r for r in results if r.get("FastestLap", {}).get("rank") == "1"), None)
                fl_txt = ""
                if fl:
                    fln    = f"{fl['Driver']['givenName'].split()[0]} {fl['Driver']['familyName']}"
                    flt    = fl["FastestLap"]["Time"]["time"]
                    fl_txt = f" Fastest lap: {fln} ({flt})."
                intel.append({
                    "kicker":   "Last Race",
                    "lead":     False,
                    "headline": f"{wn} wins the {race['raceName']}",
                    "body":     (
                        f"{wt}'s {wn.split()[-1]} took victory at {race['Circuit']['circuitName']}."
                        f"{fl_txt} Round {race['round']} of the 2026 season."
                    ),
                })

    # ── Story 3: FastF1 pit-stop analysis ────────────────────────
    if FF1_AVAILABLE and _ff1_session is not None:
        try:
            sess  = _ff1_session
            laps  = sess.laps
            pits  = laps[laps["PitOutTime"].notna() & laps["PitInTime"].notna()].copy()
            if not pits.empty:
                pits["pit_s"] = (
                    pits["PitOutTime"] - pits["PitInTime"]
                ).dt.total_seconds()
                pits = pits[(pits["pit_s"] > 1.5) & (pits["pit_s"] < 60)]
                if not pits.empty:
                    best      = pits.loc[pits["pit_s"].idxmin()]
                    pit_drv   = str(best["Driver"])
                    pit_time  = float(best["pit_s"])
                    team_avg  = (
                        pits.groupby("Team")["pit_s"].mean().sort_values()
                    )
                    fastest_t = team_avg.index[0] if not team_avg.empty else "Unknown"
                    intel.append({
                        "kicker":   "Strategy · FastF1",
                        "lead":     False,
                        "headline": f"Fastest stop: {pit_drv} · {pit_time:.2f}s | Fastest team avg: {fastest_t}",
                        "body":     (
                            f"FastF1 analysis of {sess.event['EventName']} pit data. "
                            f"{pit_drv} recorded the quickest individual stop at {pit_time:.2f}s. "
                            f"{fastest_t} had the best average across all stops — "
                            f"a key factor in the strategy battle."
                        ),
                    })
        except Exception as exc:
            print(f"  [fastf1] paddock analysis: {exc}")

    # ── Story 4: Max Watch ────────────────────────────────────────
    if wdc:
        lists = wdc["MRData"]["StandingsTable"]["StandingsLists"]
        if lists:
            ds      = lists[0]["DriverStandings"]
            p1_pts  = float(ds[0]["points"])
            max_e   = next((d for d in ds if d["Driver"]["driverId"] == "max_verstappen"), None)
            if max_e:
                gap = p1_pts - float(max_e["points"])
                pos = max_e["position"]
                msg = (
                    "The gap is closing — watch this space."
                    if gap < 30
                    else "Red Bull's power-unit deficit is the key obstacle, but Max's race craft keeps the fight alive every weekend."
                )
                intel.append({
                    "kicker":   "Max Watch",
                    "lead":     False,
                    "headline": f"Verstappen P{pos} · {gap:.0f} pts from the lead",
                    "body":     f"The four-time champion sits P{pos} with {float(max_e['points']):.0f} pts. {msg}",
                })

    # ── Fallback story if FastF1 slot empty ──────────────────────
    if len(intel) < 4 and wdc:
        lists = wdc["MRData"]["StandingsTable"]["StandingsLists"]
        if lists:
            ds    = lists[0]["DriverStandings"]
            lec_e = next((d for d in ds if d["Driver"]["driverId"] == "leclerc"), None)
            if lec_e:
                lec_pts = float(lec_e["points"])
                p1_pts  = float(ds[0]["points"])
                intel.append({
                    "kicker":   "Ferrari",
                    "lead":     False,
                    "headline": f"Leclerc P{lec_e['position']} · {lec_pts:.0f} pts for Ferrari",
                    "body":     (
                        f"Charles Leclerc holds P{lec_e['position']} ({lec_pts:.0f} pts), "
                        f"{p1_pts - lec_pts:.0f} points off the championship lead. "
                        f"A strong mid-season run could change the picture entirely."
                    ),
                })

    return jsonify(intel[:4])


# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("🏎  Bhuvana's Pit Wall — Live API Server")
    print("━" * 48)
    print("📡  API:       http://localhost:5000/api/status")
    print("🏁  Dashboard: http://localhost:5000")
    print("━" * 48)
    if FF1_AVAILABLE:
        print("  FastF1 enabled — first pit-stop load may take ~60 s")
        print(f"  Cache folder: {FF1_CACHE.resolve()}")
    else:
        print("  FastF1 not installed — run: pip install fastf1")
    print()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
