#!/usr/bin/env python3
"""Build the TV-matching corpus under services/backend/tests/fixtures/thediscdb/
from the TheDiscDB data repo (github.com/TheDiscDb/data, MIT).

The corpus is real disc layouts: for each selected series, every release and
disc with its MakeMKV title list (index, playlist file, duration, size) and the
community's episode placement (season, episode, name). Tests use the title
durations as the scan, the placement as the oracle, and the TMDb season
summary as the provider's season list. Nothing else from the repo is kept.

Usage:
    uv run python -I devtools/thediscdb-fixture.py            # download main, rebuild
    uv run python -I devtools/thediscdb-fixture.py --tarball data.tar.gz

The manifest records the upstream commit the tarball came from, so the corpus
can be regenerated and diffed. Add a series to SERIES to extend it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

TARBALL_URL = "https://codeload.github.com/TheDiscDb/data/tar.gz/refs/heads/main"
COMMIT_URL = "https://api.github.com/repos/TheDiscDb/data/commits/main"
OUT_DIR = Path(__file__).resolve().parent.parent / "services" / "backend" / "tests" / "fixtures" / "thediscdb"

# Series directory name in the repo -> fixture slug, and why it is here.
SERIES: dict[str, tuple[str, str]] = {
    "All Creatures Great & Small (2020)": (
        "all-creatures-great-and-small",
        "Two late seasons only (5, 6); playlists in reverse episode order; varied runtimes.",
    ),
    "Breaking Bad (2008)": ("breaking-bad", "Clean reference: five seasons, in order, distinct runtimes."),
    "Star Trek Deep Space Nine (1993)": (
        "star-trek-deep-space-nine",
        "DVD, seven seasons, runtimes identical within a season: runtime alone cannot place a title.",
    ),
    "Supernatural (2005)": ("supernatural", "Fourteen seasons on disc (2 to 15): beyond the ten-season scan cap."),
    "Doctor Who (2005)": (
        "doctor-who-2005",
        "Specials (season 0), three releases of the same episodes (Blu-ray and UHD), shuffled playlists.",
    ),
    "Futurama (1999)": (
        "futurama",
        "One volume whose playlists are shuffled against episode order with uniform runtimes.",
    ),
    "Sherlock (2010)": ("sherlock", "Ninety-minute episodes: a TV disc that looks like a movie."),
    "The Simpsons (1989)": (
        "the-simpsons",
        "Deep seasons: 38 TMDb seasons, so a wrong season guess has many candidates.",
    ),
    "Doctor Who (1963)": (
        "doctor-who-1963",
        "Deep seasons: 26 TMDb seasons of classic serials with uneven episode counts.",
    ),
}

_DISC_RE = re.compile(r"^data-main/data/series/([^/]+)/([^/]+)/(disc\d+)\.json$")
_TNUM = re.compile(r"_t(\d+)\.mkv$", re.IGNORECASE)


def duration_s(text: str) -> int | None:
    parts = text.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() != "" else None
    except TypeError, ValueError:
        return None


def _title(entry: dict[str, Any]) -> dict[str, Any]:
    item = entry.get("Item") if isinstance(entry.get("Item"), dict) else {}
    m = _TNUM.search(str(entry.get("Comment") or ""))
    return {
        "index": entry.get("Index"),
        "makemkv_title": int(m.group(1)) if m else None,
        "source_file": entry.get("SourceFile"),
        "duration_s": duration_s(str(entry.get("Duration") or "")),
        "size": entry.get("Size"),
        "item": {
            "type": item.get("Type"),
            "title": item.get("Title"),
            "season": _int(item.get("Season")),
            "episode": _int(item.get("Episode")),
        },
    }


def _disc(obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": obj.get("Index"),
        "slug": obj.get("Slug"),
        "name": obj.get("Name"),
        "format": obj.get("Format"),
        "content_hash": obj.get("ContentHash"),
        "titles": [_title(t) for t in obj.get("Titles") or [] if isinstance(t, dict)],
    }


def _series(meta: dict[str, Any], tmdb: dict[str, Any], releases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ext = tmdb.get("external_ids") if isinstance(tmdb.get("external_ids"), dict) else {}
    ids = meta.get("ExternalIds") if isinstance(meta.get("ExternalIds"), dict) else {}
    return {
        "title": meta.get("Title"),
        "year": meta.get("Year"),
        "external_ids": {
            "tmdb": ids.get("Tmdb") or (str(tmdb["id"]) if tmdb.get("id") else None),
            "imdb": ids.get("Imdb") or ext.get("imdb_id"),
            "tvdb": str(ext["tvdb_id"]) if ext.get("tvdb_id") else None,
        },
        "tmdb": {
            "number_of_seasons": tmdb.get("number_of_seasons"),
            "number_of_episodes": tmdb.get("number_of_episodes"),
            "episode_run_time": tmdb.get("episode_run_time") or [],
            "seasons": [
                {
                    "season_number": s.get("season_number"),
                    "episode_count": s.get("episode_count"),
                    "name": s.get("name"),
                }
                for s in tmdb.get("seasons") or []
                if isinstance(s, dict)
            ],
        },
        "releases": [
            {
                "slug": slug,
                "title": rel["release"].get("Title"),
                "year": rel["release"].get("Year"),
                "discs": sorted(rel["discs"], key=lambda d: (d["index"] is None, d["index"])),
            }
            for slug, rel in sorted(releases.items())
        ],
    }


def build(tarball: Path, out_dir: Path, *, commit: str | None) -> dict[str, Any]:
    wanted = set(SERIES)
    meta: dict[str, dict[str, Any]] = {}
    tmdb: dict[str, dict[str, Any]] = {}
    releases: dict[str, dict[str, dict[str, Any]]] = {}
    with tarfile.open(tarball, "r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            parts = member.name.split("/")
            if len(parts) < 5 or parts[1] != "data" or parts[2] != "series" or parts[3] not in wanted:
                continue
            fh = tar.extractfile(member)
            if fh is None:
                continue
            obj = json.load(fh)
            if not isinstance(obj, dict):
                continue
            series = parts[3]
            if len(parts) == 5 and parts[4] == "metadata.json":
                meta[series] = obj
            elif len(parts) == 5 and parts[4] == "tmdb.json":
                tmdb[series] = obj
            elif len(parts) == 6 and parts[5] == "release.json":
                releases.setdefault(series, {}).setdefault(parts[4], {"release": {}, "discs": []})["release"] = obj
            elif _DISC_RE.match(member.name):
                # Older contributions have no ContentHash; the matcher corpus
                # does not need one (the snapshot index skips those discs).
                releases.setdefault(series, {}).setdefault(parts[4], {"release": {}, "discs": []})["discs"].append(
                    _disc(obj)
                )
    missing = wanted - set(releases)
    if missing:
        raise SystemExit(f"series not found in tarball: {sorted(missing)}")

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()
    manifest: dict[str, Any] = {
        "source": "https://github.com/TheDiscDb/data (MIT)",
        "commit": commit,
        "built": dt.datetime.now(dt.UTC).date().isoformat(),
        "generator": "devtools/thediscdb-fixture.py",
        "series": {},
    }
    for name, (slug, why) in SERIES.items():
        data = _series(meta.get(name, {}), tmdb.get(name, {}), releases[name])
        (out_dir / f"{slug}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        discs = [d for r in data["releases"] for d in r["discs"]]
        manifest["series"][slug] = {
            "upstream": name,
            "why": why,
            "releases": len(data["releases"]),
            "discs": len(discs),
            # Numbered episodes only: an Episode-kind title without season and
            # episode (a feature-length opener) is not an oracle entry.
            "episodes": sum(
                1
                for d in discs
                for t in d["titles"]
                if t["item"]["type"] == "Episode"
                and t["item"]["season"] is not None
                and t["item"]["episode"] is not None
            ),
        }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def _main_commit() -> str | None:
    try:
        with urllib.request.urlopen(COMMIT_URL, timeout=30) as resp:  # noqa: S310 (fixed https URL)
            return str(json.load(resp)["sha"])
    except Exception as e:  # noqa: BLE001
        print(f"warning: could not read upstream commit: {e}", file=sys.stderr)
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tarball", type=Path, help="an already downloaded data tarball (default: download main)")
    ap.add_argument("--commit", help="upstream commit the tarball came from (default: ask GitHub for main)")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    commit = args.commit or _main_commit()
    if args.tarball:
        manifest = build(args.tarball, args.out, commit=commit)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            tarball = Path(tmp) / "data.tar.gz"
            print(f"downloading {TARBALL_URL} (about 1.5 GB)", file=sys.stderr)
            urllib.request.urlretrieve(TARBALL_URL, tarball)  # noqa: S310
            manifest = build(tarball, args.out, commit=commit)
    for slug, info in manifest["series"].items():
        print(f"{slug:32} releases {info['releases']:>2}  discs {info['discs']:>3}  episodes {info['episodes']:>4}")
    print(f"commit {manifest['commit']} -> {args.out}")


if __name__ == "__main__":
    main()
