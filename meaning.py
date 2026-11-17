"""Search by meaning for the finder agents (garage-week PoC). Optional, off by default.

The finder's other tools match words. This one ranks the titles of the files and the text of the
elements that have an id by how close they are in meaning to a query, so "sign in" finds "Log on
to the console". It uses a small static embedding model that runs on this machine
(model2vec, minishlab/potion-base-8M, about 30 MB): no content leaves it. The model is fetched
from the Hugging Face Hub the first time; after that it is read from disk and the network is not
asked. REFHEAL_SEMANTIC_MODEL may name a folder that holds a model, for a machine without internet.

    REFHEAL_SEMANTIC=1        turns the tool on
    pip install model2vec     must be installed; without it the tool is not offered and the
                              finder works as before

Measured on 17 Nov 2026 on the harder set of synonymeval.py (ten links whose target moved to
another file under another name), without a model call: the right target among the first three
for 2 of 10 by word match and for 8 of 10 by this ranking. Closeness in meaning is not proof: for
"Two-factor authentication" it put "Password policy" first. The finder reads what it finds, the
reviewer checks the answer, and nothing found this way is applied without the usual checks.
"""
import os
import threading

MODEL_NAME = os.environ.get("REFHEAL_SEMANTIC_MODEL", "minishlab/potion-base-8M")
ENABLED = os.environ.get("REFHEAL_SEMANTIC") == "1"
TEXT_CHARS = 400   # of an element's text; the start says what it is about

_lock = threading.Lock()
_model = None
_why_not = None


def _load():
    """The embedding model, or None when it cannot be loaded (the reason is kept in why_not())."""
    global _model, _why_not
    with _lock:
        if _model is None and _why_not is None:
            try:
                from model2vec import StaticModel
                _model = StaticModel.from_pretrained(_on_disk(MODEL_NAME) or MODEL_NAME)
            except Exception as exc:  # not installed, or no model on disk and no network
                _why_not = " ".join(str(exc).split())[:200] or exc.__class__.__name__
        return _model


def _on_disk(name):
    """The folder of a model that was downloaded before, so that loading it asks the network
    nothing. None when it is not there yet: the first load then fetches it from the Hugging Face Hub."""
    if os.path.isdir(name):
        return name
    cache = os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface"), "hub")
    snapshots = os.path.join(cache, "models--" + name.replace("/", "--"), "snapshots")
    if not os.path.isdir(snapshots):
        return None
    folders = sorted(os.path.join(snapshots, entry) for entry in os.listdir(snapshots))
    return next((folder for folder in reversed(folders) if os.path.exists(os.path.join(folder, "model.safetensors"))), None)


def why_not():
    return _why_not


def available():
    return ENABLED and _load() is not None


def _unit(matrix):
    import numpy
    norms = numpy.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def index_of(repo):
    """(pieces, unit vectors) for a repository, built once and kept on it."""
    with _lock:
        cached = getattr(repo, "_meaning_index", None)
    if cached is not None:
        return cached
    pieces = []
    for path, entry in repo.files.items():
        if entry["title"]:
            pieces.append({"kind": "file", "path": path, "topic_id": "", "id": "", "tag": entry["tag"], "text": entry["title"]})
        for (topic_id, element_id), value in entry["elements"].items():
            text = " ".join(value["content"].split())[:TEXT_CHARS]
            if text:
                pieces.append({"kind": "element", "path": path, "topic_id": topic_id or "", "id": element_id,
                               "tag": value["tag"], "text": text})
    vectors = _unit(_load().encode([piece["text"] for piece in pieces])) if pieces else None
    with _lock:
        repo._meaning_index = (pieces, vectors)
    return repo._meaning_index


def search(repo, query, tag="", limit=8):
    """The pieces closest in meaning to the query, closest first: [{kind, path, topic_id, id, tag, text}]."""
    pieces, vectors = index_of(repo)
    if not pieces or not (query or "").strip():
        return []
    import numpy
    wanted = _unit(_load().encode([query]))[0]
    # numpy on macOS reports overflow and division warnings from this product that are not real
    # (the vectors are unit length and finite); they would fill the log of the agents.
    with numpy.errstate(all="ignore"):
        closeness = vectors @ wanted
    order = numpy.argsort(-numpy.nan_to_num(closeness, nan=-1.0))
    found = []
    for position in order:
        piece = pieces[int(position)]
        if tag and (piece["kind"] != "element" or piece["tag"] != tag):
            continue
        found.append(dict(piece, text=piece["text"][:160]))
        if len(found) == limit:
            break
    return found
