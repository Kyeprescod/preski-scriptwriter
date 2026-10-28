"""Shared production record for Poppy, Clip Drop, Daily Post and the editor.

One document per video in the `jobs` collection of the Clip Drop artifact database (the storage
Poppy, Clip Drop and any Claude Code session on this account can already read and write).
This module holds only the schema, the state machine and a validator, so every agent
checks the same rules. Writes must be pinned with the document's `version` (if_version): that is
what stops Poppy and Claude Code overwriting each other.
"""
import json
import re
import sys

STATES = ["IDEA", "SCRIPTED", "AWAITING_FOOTAGE", "READY_TO_EDIT", "EDITING",
          "AWAITING_APPROVAL", "APPROVED", "SCHEDULED", "PUBLISHED", "ANALYSED", "FAILED"]

# from -> allowed next states. FAILED can return to any earlier stage via retry (see RETRY_TO).
NEXT = {
    "IDEA": ["SCRIPTED"],
    "SCRIPTED": ["AWAITING_FOOTAGE", "READY_TO_EDIT"],
    "AWAITING_FOOTAGE": ["READY_TO_EDIT"],
    "READY_TO_EDIT": ["EDITING"],
    "EDITING": ["AWAITING_APPROVAL", "FAILED"],
    "AWAITING_APPROVAL": ["APPROVED", "READY_TO_EDIT"],   # back to edit = changes requested
    "APPROVED": ["SCHEDULED"],
    "SCHEDULED": ["PUBLISHED", "FAILED"],
    "PUBLISHED": ["ANALYSED"],
    "ANALYSED": [],
    "FAILED": ["READY_TO_EDIT", "SCRIPTED", "AWAITING_FOOTAGE"],
}

FIELDS = ["job_id", "brand", "video_concept", "research_references", "script", "onscreen_hook", "caption",
          "shot_list", "asset_ids", "footage_locations", "edit_instructions", "production_status",
          "export_path", "approval_status", "postiz_status", "published_url", "analytics",
          "created_at", "updated_at"]
# extras the state machine needs; kept next to the required fields
EXTRA = ["test", "failure", "attempts", "claimed_by", "history"]

# what must be true before a job may enter a state
def prerequisites(job, to):
    miss = []
    if to == "SCRIPTED" and not job.get("script"):
        miss.append("script")
    if to in ("READY_TO_EDIT", "EDITING"):
        if not job.get("script"):
            miss.append("script")
        if not job.get("asset_ids"):
            miss.append("asset_ids")
    if to == "EDITING" and job.get("claimed_by") in (None, ""):
        miss.append("claimed_by")
    if to == "AWAITING_APPROVAL" and not job.get("export_path"):
        miss.append("export_path")
    if to == "SCHEDULED" and job.get("approval_status") != "approved":
        miss.append("approval_status=approved")
    if to == "PUBLISHED" and not job.get("published_url"):
        miss.append("published_url")
    if to == "FAILED" and not job.get("failure"):
        miss.append("failure")
    return miss


def can_move(job, to):
    cur = job.get("production_status")
    if to not in NEXT.get(cur, []):
        return False, "%s -> %s is not allowed" % (cur, to)
    miss = prerequisites(job, to)
    if miss:
        return False, "missing: " + ", ".join(miss)
    if job.get("test") and to in ("SCHEDULED", "PUBLISHED"):
        return False, "test jobs are never scheduled or published"
    return True, "ok"


def new_job(job_id, brand="Preski Fitness", concept="", **kw):
    now = kw.pop("now")
    j = {f: None for f in FIELDS}
    j.update(job_id=job_id, brand=brand, video_concept=concept, production_status="IDEA",
             research_references=[], shot_list=[], asset_ids=[], footage_locations={},
             edit_instructions={}, approval_status="none", postiz_status="none", analytics={},
             created_at=now, updated_at=now, attempts=0, history=[], test=False)
    j.update(kw)
    return j


def validate(job):
    errs = []
    if not re.fullmatch(r"job_[0-9]{8}_[a-z0-9\-]{3,40}", str(job.get("job_id", ""))):
        errs.append("job_id must look like job_YYYYMMDD_slug")
    for f in FIELDS:
        if f not in job:
            errs.append("missing field " + f)
    if job.get("production_status") not in STATES:
        errs.append("bad production_status")
    return errs


if __name__ == "__main__":
    j = json.load(open(sys.argv[1], encoding="utf-8"))
    j = j.get("data", j)
    e = validate(j)
    print("OK" if not e else "\n".join(e))
    sys.exit(1 if e else 0)
