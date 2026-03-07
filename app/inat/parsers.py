"""Parse iNaturalist API observation responses into database-ready dicts."""

import json
from .constants import ANNOTATION_LABELS, PHENOLOGY_LABELS


def parse_observation(obs: dict) -> dict:
    """Extract key fields from an iNat API observation response."""
    taxon = obs.get("taxon") or {}
    photos = obs.get("photos") or obs.get("observation_photos") or []
    photo_url = None
    if photos:
        p = photos[0]
        # Handle both observation_photos (nested) and photos (direct)
        if "photo" in p:
            p = p["photo"]
        photo_url = p.get("url", "").replace("square", "medium")

    # Location
    lat, lng = None, None
    if obs.get("geojson") and obs["geojson"].get("coordinates"):
        coords = obs["geojson"]["coordinates"]
        lng, lat = coords[0], coords[1]
    elif obs.get("location"):
        parts = obs["location"].split(",")
        if len(parts) == 2:
            lat, lng = float(parts[0].strip()), float(parts[1].strip())

    return {
        "obs_id": obs["id"],
        "observed_on": obs.get("observed_on"),
        "lat": lat,
        "lng": lng,
        "photo_url": photo_url,
        "taxon_id": taxon.get("id"),
        "taxon_name": taxon.get("name"),
        "taxon_rank": taxon.get("rank"),
        "quality_grade": obs.get("quality_grade"),
        "ids_json": json.dumps(parse_identifications(obs)),
        "comments_json": json.dumps(parse_comments(obs)),
        "annotations_json": json.dumps(parse_annotations(obs)),
    }


def parse_identifications(obs: dict) -> list[dict]:
    """Extract identifications from an observation."""
    idents = []
    for ident in obs.get("identifications", []):
        taxon = ident.get("taxon") or {}
        user = ident.get("user") or {}
        idents.append({
            "id": ident.get("id"),
            "taxon_id": taxon.get("id"),
            "taxon_name": taxon.get("name"),
            "taxon_rank": taxon.get("rank"),
            "user_login": user.get("login"),
            "user_name": user.get("name", ""),
            "user_icon": user.get("icon_url", ""),
            "current": ident.get("current", True),
            "created_at": ident.get("created_at", ""),
            "category": ident.get("category", ""),
        })
    return idents


def parse_comments(obs: dict) -> list[dict]:
    """Extract comments from an observation."""
    comments = []
    for c in obs.get("comments", []):
        user = c.get("user") or {}
        body = (c.get("body") or "").strip()
        if body:
            comments.append({
                "id": c.get("id"),
                "user_login": user.get("login"),
                "user_name": user.get("name", ""),
                "user_icon": user.get("icon_url", ""),
                "body": body,
                "created_at": c.get("created_at", ""),
            })
    return comments


def parse_annotations(obs: dict) -> list[dict]:
    """Extract annotations from an observation."""
    annotations = []
    for a in obs.get("annotations", []):
        attr_id = a.get("controlled_attribute_id")
        val_id = a.get("controlled_value_id")
        user = a.get("user") or {}
        attr_label = ANNOTATION_LABELS.get(attr_id, f"attr_{attr_id}")
        val_label = PHENOLOGY_LABELS.get(val_id, f"val_{val_id}")

        annotations.append({
            "id": a.get("uuid", a.get("id")),
            "attribute_id": attr_id,
            "attribute_label": attr_label,
            "value_id": val_id,
            "value_label": val_label,
            "user_login": user.get("login"),
            "user_name": user.get("name", ""),
            "user_icon": user.get("icon_url", ""),
        })
    return annotations
