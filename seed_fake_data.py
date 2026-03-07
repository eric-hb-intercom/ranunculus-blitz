"""Seed fake blitz-in-progress data for demo purposes.

Run: python3 seed_fake_data.py
Requires: the snapshot to have been run first (observations in DB).
"""

import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = "blitz.db"

# Fake participants — iNat-style logins and display names
PARTICIPANTS = [
    {"login": "buttercup_beth", "name": "Beth Allanson", "team": 1},
    {"login": "flora_finn", "name": "Finn O'Reilly", "team": 1},
    {"login": "meadow_mark", "name": "Mark Trevithick", "team": 1},
    {"login": "petal_pat", "name": "Pat Nguyen", "team": 1},
    {"login": "ranunculus_rose", "name": "Rose Whitfield", "team": 1},
    {"login": "wild_will", "name": "Will Ashby", "team": 2},
    {"login": "botany_bex", "name": "Bex Hargreaves", "team": 2},
    {"login": "daisy_dan", "name": "Dan Kowalski", "team": 2},
    {"login": "pollen_priya", "name": "Priya Sharma", "team": 2},
    {"login": "seedling_sam", "name": "Sam Cartwright", "team": 2},
    {"login": "leaf_lucy", "name": "Lucy Brennan", "team": 3},
    {"login": "stem_steve", "name": "Steve MacLeod", "team": 3},
    {"login": "root_ravi", "name": "Ravi Patel", "team": 3},
    {"login": "bud_bridget", "name": "Bridget Calloway", "team": 3},
    {"login": "flower_faye", "name": "Faye Henderson", "team": 3},
]

TEAMS = [
    {"name": "Team Buttercup", "color": "#d4a843"},
    {"name": "Team Meadow", "color": "#e6c832"},
    {"name": "Team Hedgerow", "color": "#c46a2b"},
]

# Comment templates
COMMENTS = [
    "Looks like the petals are a bit worn, but I think the reflexed sepals confirm {}.",
    "Good photo! The leaf shape is consistent with {}.",
    "I agree with {} — note the bulbous stem base.",
    "The creeping stolons are visible here, classic {}.",
    "Could also be a hybrid? But leaning towards {}.",
    "Nice find! {} for sure based on the achene shape.",
    "The habitat (damp meadow) fits {} perfectly.",
    "Check the stem — it's furrowed, which points to {}.",
    "Great observation! Added an annotation for flowering.",
    "This one's tricky but I'm fairly confident it's {}.",
    "The glossy petals and upright habit say {} to me.",
    "Lovely photo. The basal leaves clinch it — {}.",
]

TEACHING_COMMENT = "Key ID tip: look at the sepals! In R. bulbosus they're reflexed (bent back), in R. acris they're appressed (held close), and in R. repens they're spreading. This is the single most reliable feature for separating these three species."

ANNOTATION_VALUES = ["Flowering", "Fruiting", "Flower Budding"]


def main():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    # Check we have observations
    total_obs = db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    if total_obs == 0:
        print("No observations in DB! Run the snapshot first.")
        return

    print(f"Found {total_obs} observations in database")

    # Set up blitz timing — started 45 minutes ago
    now = datetime.now(timezone.utc)
    started_at = now - timedelta(minutes=45)

    # ── Create teams ──────────────────────────────────────────────────
    db.execute("DELETE FROM teams")
    for i, team in enumerate(TEAMS):
        db.execute(
            "INSERT INTO teams (team_id, name, color) VALUES (?, ?, ?)",
            (i + 1, team["name"], team["color"]),
        )
    print(f"Created {len(TEAMS)} teams")

    # ── Create participants ───────────────────────────────────────────
    db.execute("DELETE FROM participants")
    for i, p in enumerate(PARTICIPANTS):
        db.execute(
            "INSERT INTO participants (user_id, login, name, icon_url, team_id) VALUES (?, ?, ?, ?, ?)",
            (
                1000 + i,
                p["login"],
                p["name"],
                f"https://static.inaturalist.org/attachments/users/icons/{1000+i}/thumb.jpg",
                p["team"],
            ),
        )
    print(f"Created {len(PARTICIPANTS)} participants")

    # ── Mark blitz as live ────────────────────────────────────────────
    db.execute(
        "INSERT OR REPLACE INTO blitz_config (key, value) VALUES (?, ?)",
        ("started_at", started_at.isoformat()),
    )

    # ── Resolve ~48% of observations + generate events ────────────────
    all_obs = db.execute(
        "SELECT obs_id, species_group, lat, lng FROM observations"
    ).fetchall()

    random.shuffle(all_obs)
    resolve_count = int(len(all_obs) * 0.48)
    to_resolve = all_obs[:resolve_count]
    to_comment_only = all_obs[resolve_count:resolve_count + int(len(all_obs) * 0.08)]
    to_annotate_only = all_obs[resolve_count + int(len(all_obs) * 0.08):resolve_count + int(len(all_obs) * 0.12)]

    print(f"Will resolve {resolve_count} observations (~48%)")
    print(f"Will add comments-only to {len(to_comment_only)} more")
    print(f"Will add annotations-only to {len(to_annotate_only)} more")

    db.execute("DELETE FROM events")
    event_id = 0

    # Track per-participant action counts for variety
    participant_actions = {p["login"]: 0 for p in PARTICIPANTS}

    # Helper: pick a participant, weighted towards less-active ones
    def pick_participant():
        weights = [1.0 / (participant_actions[p["login"]] + 1) for p in PARTICIPANTS]
        chosen = random.choices(PARTICIPANTS, weights=weights, k=1)[0]
        participant_actions[chosen["login"]] += 1
        return chosen

    # Helper: random time during the blitz
    def random_blitz_time():
        offset_seconds = random.randint(30, int((now - started_at).total_seconds()))
        return started_at + timedelta(seconds=offset_seconds)

    # ── Resolved observations: identification + sometimes comment/annotation ──
    for obs in to_resolve:
        obs_id = obs["obs_id"]
        species = obs["species_group"]
        t = random_blitz_time()

        # Primary identification event
        actor = pick_participant()
        event_id += 1
        db.execute(
            """INSERT INTO events (event_id, event_type, actor_login, actor_name,
                actor_icon_url, actor_team_id, is_participant, obs_id, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                event_id, "identification", actor["login"], actor["name"],
                f"https://static.inaturalist.org/attachments/users/icons/{1000+PARTICIPANTS.index(actor)}/thumb.jpg",
                actor["team"], obs_id,
                json.dumps({"taxon_name": species, "taxon_rank": "species"}),
                t.isoformat(),
            ),
        )

        # ~40% also get a comment
        if random.random() < 0.4:
            commenter = pick_participant()
            comment_time = t + timedelta(seconds=random.randint(10, 300))
            event_id += 1
            body = random.choice(COMMENTS).format(species.split()[-1])
            db.execute(
                """INSERT INTO events (event_id, event_type, actor_login, actor_name,
                    actor_icon_url, actor_team_id, is_participant, obs_id, detail_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                (
                    event_id, "comment", commenter["login"], commenter["name"],
                    f"https://static.inaturalist.org/attachments/users/icons/{1000+PARTICIPANTS.index(commenter)}/thumb.jpg",
                    commenter["team"], obs_id,
                    json.dumps({"body": body}),
                    comment_time.isoformat(),
                ),
            )

        # ~25% get an annotation
        if random.random() < 0.25:
            annotator = pick_participant()
            annot_time = t + timedelta(seconds=random.randint(5, 200))
            event_id += 1
            db.execute(
                """INSERT INTO events (event_id, event_type, actor_login, actor_name,
                    actor_icon_url, actor_team_id, is_participant, obs_id, detail_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                (
                    event_id, "annotation_added", annotator["login"], annotator["name"],
                    f"https://static.inaturalist.org/attachments/users/icons/{1000+PARTICIPANTS.index(annotator)}/thumb.jpg",
                    annotator["team"], obs_id,
                    json.dumps({"value": random.choice(ANNOTATION_VALUES)}),
                    annot_time.isoformat(),
                ),
            )

        # ~8% get a taxon move (genus bounce)
        if random.random() < 0.08:
            mover = pick_participant()
            move_time = t - timedelta(seconds=random.randint(30, 600))
            event_id += 1
            db.execute(
                """INSERT INTO events (event_id, event_type, actor_login, actor_name,
                    actor_icon_url, actor_team_id, is_participant, obs_id, detail_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                (
                    event_id, "taxon_move", mover["login"], mover["name"],
                    f"https://static.inaturalist.org/attachments/users/icons/{1000+PARTICIPANTS.index(mover)}/thumb.jpg",
                    mover["team"], obs_id,
                    json.dumps({"from_taxon_name": "Ranunculus", "from_taxon_rank": "genus",
                                "to_taxon_name": species, "to_taxon_rank": "species"}),
                    move_time.isoformat(),
                ),
            )

        # Mark resolved
        db.execute(
            "UPDATE observations SET resolved = 1, quality_grade = 'research' WHERE obs_id = ?",
            (obs_id,),
        )

    # ── Comment-only observations (not resolved yet) ──────────────────
    for obs in to_comment_only:
        actor = pick_participant()
        t = random_blitz_time()
        event_id += 1
        body = random.choice(COMMENTS).format(obs["species_group"].split()[-1])
        db.execute(
            """INSERT INTO events (event_id, event_type, actor_login, actor_name,
                actor_icon_url, actor_team_id, is_participant, obs_id, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                event_id, "comment", actor["login"], actor["name"],
                f"https://static.inaturalist.org/attachments/users/icons/{1000+PARTICIPANTS.index(actor)}/thumb.jpg",
                actor["team"], obs["obs_id"],
                json.dumps({"body": body}),
                t.isoformat(),
            ),
        )

    # ── Annotation-only observations ──────────────────────────────────
    for obs in to_annotate_only:
        actor = pick_participant()
        t = random_blitz_time()
        event_id += 1
        db.execute(
            """INSERT INTO events (event_id, event_type, actor_login, actor_name,
                actor_icon_url, actor_team_id, is_participant, obs_id, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                event_id, "annotation_added", actor["login"], actor["name"],
                f"https://static.inaturalist.org/attachments/users/icons/{1000+PARTICIPANTS.index(actor)}/thumb.jpg",
                actor["team"], obs["obs_id"],
                json.dumps({"value": random.choice(ANNOTATION_VALUES)}),
                t.isoformat(),
            ),
        )

    # ── Sprinkle in some teaching comments (same text, 5+ times) ──────
    teaching_actor = random.choice(PARTICIPANTS)
    teaching_obs = random.sample(all_obs, min(8, len(all_obs)))
    for obs in teaching_obs:
        t = random_blitz_time()
        event_id += 1
        db.execute(
            """INSERT INTO events (event_id, event_type, actor_login, actor_name,
                actor_icon_url, actor_team_id, is_participant, obs_id, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                event_id, "comment", teaching_actor["login"], teaching_actor["name"],
                f"https://static.inaturalist.org/attachments/users/icons/{1000+PARTICIPANTS.index(teaching_actor)}/thumb.jpg",
                teaching_actor["team"], obs["obs_id"],
                json.dumps({"body": TEACHING_COMMENT}),
                t.isoformat(),
            ),
        )

    # ── Quality change events for a subset of resolved ────────────────
    quality_sample = random.sample(to_resolve, min(500, len(to_resolve)))
    for obs in quality_sample:
        t = random_blitz_time()
        event_id += 1
        db.execute(
            """INSERT INTO events (event_id, event_type, actor_login, actor_name,
                actor_icon_url, actor_team_id, is_participant, obs_id, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (
                event_id, "quality_change", None, None, None, None,
                obs["obs_id"],
                json.dumps({"from": "needs_id", "to": "research"}),
                t.isoformat(),
            ),
        )

    db.commit()

    # ── Summary ───────────────────────────────────────────────────────
    resolved = db.execute("SELECT COUNT(*) FROM observations WHERE resolved = 1").fetchone()[0]
    total_events = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    event_types = db.execute(
        "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
    ).fetchall()

    print(f"\nDone! Blitz state:")
    print(f"  Status: live (started {45} min ago)")
    print(f"  Observations: {resolved}/{total_obs} resolved ({100*resolved/total_obs:.1f}%)")
    print(f"  Total events: {total_events}")
    for et, count in event_types:
        print(f"    {et}: {count}")
    print(f"\n  Participants: {len(PARTICIPANTS)} across {len(TEAMS)} teams")

    # Print per-participant breakdown
    print("\n  Per-participant actions:")
    for p in sorted(PARTICIPANTS, key=lambda x: participant_actions[x["login"]], reverse=True):
        print(f"    {p['name']:20s} ({p['login']:18s}): {participant_actions[p['login']]:5d} actions")

    db.close()


if __name__ == "__main__":
    main()
