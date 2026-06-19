# -*- coding: utf-8 -*-
"""notebook_client.py - Best-effort HTTP wrapper around the Open Notebook API.

Open Notebook is a self-hosted research tool (docker-compose-notebook.yml).
It runs at localhost:5055 by default. This module is a thin adapter: every
function returns None / [] / False on any error, never raises. The research
features in server.py degrade gracefully when the service is down.

https://github.com/lfnovo/open-notebook  (MIT)
"""
import os, sys, json
import urllib.request, urllib.error

_BASE         = os.environ.get("OPEN_NOTEBOOK_URL", "http://127.0.0.1:5055")
_PASS         = os.environ.get("OPEN_NOTEBOOK_PASSWORD", "")
_TIMEOUT      = int(os.environ.get("OPEN_NOTEBOOK_TIMEOUT", "20"))
_CHAT_TIMEOUT = int(os.environ.get("OPEN_NOTEBOOK_CHAT_TIMEOUT", "120"))

# Cached default model id for transformations (fetched once on first use)
_xform_model_id = None


def _log(*a):
    print("[notebook]", *a, file=sys.stderr)


def _hdr():
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if _PASS:
        h["Authorization"] = f"Bearer {_PASS}"
    return h


def _get(path, timeout=None):
    try:
        req = urllib.request.Request(f"{_BASE}{path}", headers=_hdr())
        with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT) as r:
            return json.loads(r.read())
    except Exception as e:
        _log("GET", path, str(e)[:120])
        return None


def _post(path, data, timeout=None):
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{_BASE}{path}", data=body, headers=_hdr(), method="POST")
        with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT) as r:
            return json.loads(r.read())
    except Exception as e:
        _log("POST", path, str(e)[:200])
        return None


# ------------------------------------------------------------------ health
def ping():
    """True iff Open Notebook is reachable. Used to gate the Research UI."""
    try:
        req = urllib.request.Request(f"{_BASE}/health", headers=_hdr())
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


# ------------------------------------------------------------------ notebooks
def ensure_notebook(name, description=""):
    """Return the notebook_id for a notebook named `name`, creating it if needed."""
    existing = _get("/api/notebooks")
    if isinstance(existing, list):
        for nb in existing:
            if nb.get("name") == name:
                return nb.get("id")
    result = _post("/api/notebooks", {"name": name, "description": description})
    if result and result.get("id"):
        return result["id"]
    return None


# ------------------------------------------------------------------ sources
def add_source_url(notebook_id, url, title=""):
    """Add a URL to a notebook for ingestion. Returns source_id or None."""
    r = _post("/api/sources/json", {
        "type": "link",
        "notebooks": [notebook_id],
        "url": url,
        "title": title or url[:80],
        "async_processing": True,
    })
    return r.get("id") if (r and r.get("id")) else None


def add_source_text(notebook_id, content, title="Research note"):
    """Add raw text to a notebook. Returns source_id or None."""
    r = _post("/api/sources/json", {
        "type": "text",
        "notebooks": [notebook_id],
        "content": content,
        "title": title,
        "async_processing": True,
    })
    return r.get("id") if (r and r.get("id")) else None


def add_source_youtube(notebook_id, url, title=""):
    """Add a YouTube URL — Open Notebook transcribes the audio automatically."""
    r = _post("/api/sources/json", {
        "type": "link",
        "notebooks": [notebook_id],
        "url": url,
        "title": title or url[:80],
        "async_processing": True,
    })
    return r.get("id") if (r and r.get("id")) else None


def add_source_file(notebook_id, file_path, title=""):
    """Upload a local file (PDF, audio, video) to a notebook via multipart POST."""
    import mimetypes
    try:
        boundary = "----HonestlyBoundary7x"
        fname = os.path.basename(file_path)
        mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        with open(file_path, "rb") as f:
            file_data = f.read()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="notebooks"\r\n\r\n{notebook_id}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="title"\r\n\r\n{title or fname}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
        hdrs = {k: v for k, v in _hdr().items() if k != "Content-Type"}
        hdrs["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        req = urllib.request.Request(
            f"{_BASE}/api/sources/json", data=body, headers=hdrs, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            r = json.loads(resp.read())
            return r.get("id") if r.get("id") else None
    except Exception as e:
        _log("add_source_file", str(e)[:200])
        return None


def list_sources(notebook_id, limit=50):
    """List sources in a notebook. Returns a list (possibly empty)."""
    r = _get(f"/api/sources?notebook_id={notebook_id}&limit={limit}")
    if isinstance(r, list):
        return r
    if isinstance(r, dict):
        return r.get("items", r.get("sources", []))
    return []


# ------------------------------------------------------------------ chat
def start_chat(notebook_id):
    """Open a new chat session for a notebook. Returns session_id or None."""
    r = _post("/api/chat/sessions", {
        "notebook_id": notebook_id,
        "title": "Property Research",
    })
    return r.get("id") if (r and r.get("id")) else None


def send_message(session_id, message, context=None):
    """Send a message to an open session. Returns the assistant reply text or None."""
    r = _post("/api/chat/execute", {
        "session_id": session_id,
        "message": message,
        "context": context or {},
    }, timeout=_CHAT_TIMEOUT)
    if not r:
        return None
    if isinstance(r.get("reply"), str) and r["reply"]:
        return r["reply"]
    if isinstance(r.get("response"), str) and r["response"]:
        return r["response"]
    messages = r.get("messages", [])
    if not isinstance(messages, list):
        messages = []
    for msg in reversed(messages):
        role = (msg.get("role") or "").lower()
        if role in ("assistant", "ai", "model", "bot"):
            content = msg.get("content") or msg.get("text") or ""
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            if content:
                return str(content)
    _log("send_message: unexpected response shape", str(r)[:300])
    return None


# ------------------------------------------------------------------ transformations
def list_transformations():
    """All available transformation objects. Each has id/name/title/description."""
    r = _get("/api/transformations")
    if isinstance(r, list):
        return r
    if isinstance(r, dict):
        return r.get("items", r.get("data", []))
    return []


def find_transformation(name_or_title):
    """Find a transformation by name or title (case-insensitive). Returns the dict or None."""
    needle = name_or_title.lower()
    for t in list_transformations():
        if needle in (t.get("name") or "").lower() or needle in (t.get("title") or "").lower():
            return t
    return None


def _get_xform_model():
    """Return the default transformation model ID (cached after first fetch)."""
    global _xform_model_id
    if _xform_model_id:
        return _xform_model_id
    r = _get("/api/models/defaults")
    if r and r.get("default_transformation_model"):
        _xform_model_id = r["default_transformation_model"]
    return _xform_model_id


def execute_transformation(text, transformation_id, model_id=None):
    """Apply a transformation to arbitrary text. Returns the output string or None.
    Uses the configured default transformation model if model_id is not given."""
    mid = model_id or _get_xform_model()
    if not mid:
        _log("execute_transformation: no model_id available")
        return None
    r = _post("/api/transformations/execute", {
        "transformation_id": transformation_id,
        "input_text": text,
        "model_id": mid,
    }, timeout=_CHAT_TIMEOUT)
    if not r:
        return None
    return r.get("output") or None


def transform_text(text, transformation_name="Dense Summary"):
    """Convenience: apply a named transformation to a text string. Returns output or None."""
    t = find_transformation(transformation_name)
    if not t:
        _log(f"transform_text: transformation '{transformation_name}' not found")
        return None
    return execute_transformation(text, t["id"])


# ------------------------------------------------------------------ episode / speaker profiles
def list_episode_profiles():
    """Return list of configured episode profiles, or []."""
    r = _get("/api/episode-profiles")
    if isinstance(r, list):
        return r
    if isinstance(r, dict):
        return r.get("items", r.get("data", []))
    return []


def list_speaker_profiles():
    """Return list of configured speaker profiles, or []."""
    r = _get("/api/speaker-profiles")
    if isinstance(r, list):
        return r
    if isinstance(r, dict):
        return r.get("items", r.get("data", []))
    return []


def find_solo_profile():
    """Return (episode_profile_name, speaker_profile_name) for the solo narrator profile.
    Falls back to first available episode profile. Returns (None, None) if none exist."""
    ep_profiles = list_episode_profiles()
    sp_profiles = list_speaker_profiles()
    if not ep_profiles:
        return None, None

    solo_ep = None
    for p in ep_profiles:
        name = (p.get("name") or "").lower()
        if "solo" in name or "narrator" in name or "single" in name:
            solo_ep = p.get("name")
            break
    if not solo_ep:
        solo_ep = ep_profiles[0].get("name")

    solo_sp = None
    for p in sp_profiles:
        name = (p.get("name") or "").lower()
        if "solo" in name or "narrator" in name or "single" in name:
            solo_sp = p.get("name")
            break
    if not solo_sp and sp_profiles:
        # Use the speaker config specified by the chosen episode profile
        for p in ep_profiles:
            if p.get("name") == solo_ep:
                solo_sp = p.get("speaker_config")
                break
    if not solo_sp and sp_profiles:
        solo_sp = sp_profiles[0].get("name")

    return solo_ep, solo_sp


# ------------------------------------------------------------------ podcasts
def generate_podcast(notebook_id, episode_name="Property Briefing",
                     briefing_suffix="", episode_profile=None, speaker_profile=None):
    """Request podcast generation using the solo narrator profile by default.
    Returns job_id or None. Episode renders in the background (1–5 minutes)."""
    if not episode_profile or not speaker_profile:
        ep, sp = find_solo_profile()
        episode_profile = episode_profile or ep
        speaker_profile = speaker_profile or sp
    if not episode_profile or not speaker_profile:
        _log("generate_podcast: no episode/speaker profile available")
        return None
    payload = {
        "episode_profile": episode_profile,
        "speaker_profile": speaker_profile,
        "episode_name": episode_name,
        "notebook_id": notebook_id,
    }
    if briefing_suffix:
        payload["briefing_suffix"] = briefing_suffix
    r = _post("/api/podcasts/generate", payload, timeout=60)
    if not r:
        return None
    return r.get("job_id") or None


def podcast_job_status(job_id):
    """Check podcast generation progress. Returns (status_str, episode_id_or_None).
    status is 'pending' / 'processing' / 'done' / 'error'."""
    r = _get(f"/api/podcasts/jobs/{job_id}")
    if not r:
        return "error", None
    status = (r.get("status") or r.get("job_status") or "pending").lower()
    if status in ("complete", "done", "completed", "finished", "success"):
        episode_id = r.get("episode_id") or r.get("id")
        return "done", episode_id
    if status in ("failed", "error"):
        return "error", None
    return "pending", None


def list_episodes():
    """All podcast episodes. Returns a list (possibly empty)."""
    r = _get("/api/podcasts/episodes")
    if isinstance(r, list):
        return r
    if isinstance(r, dict):
        return r.get("items", [])
    return []


def get_episode(episode_id):
    """One episode by id. Returns a dict or None."""
    return _get(f"/api/podcasts/episodes/{episode_id}")


def episode_audio_url(episode_id):
    """Direct audio URL for a completed episode, or None if not yet rendered."""
    ep = get_episode(episode_id)
    if not ep:
        return None
    if ep.get("audio_url"):
        return ep["audio_url"]
    status = (ep.get("job_status") or ep.get("status") or "").lower()
    if status in ("complete", "done", "completed"):
        return f"{_BASE}/api/podcasts/episodes/{episode_id}/audio"
    return None
