"""Bounded, opt-in repository state. Saves never stage, commit, or push Git files.

POSIX directory descriptors and no-follow opens keep client names beneath the
configured root. A collection lock serializes compare-and-swap across processes.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

STATE_PROTOCOL = 2
STATE_DIR = "state"
MAX_BODY = 4 * 1024 * 1024
_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class StateError(ValueError):
    def __init__(self, message, status=400, code="invalid_state"):
        super().__init__(message)
        self.status, self.code = status, code

    def as_dict(self):
        return {"error": str(self), "code": self.code}


class StateConflict(StateError):
    def __init__(self, revision):
        super().__init__("State changed; load the current revision before saving", 409, "conflict")
        self.current_revision = revision

    def as_dict(self):
        return {**super().as_dict(), "current_revision": self.current_revision}


def strict_json(raw):
    def invalid(value):
        raise ValueError(f"non-finite JSON value: {value}")
    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite JSON number")
        return number
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, parse_constant=invalid, parse_float=finite, object_pairs_hook=pairs)


class StateStore:
    def __init__(self, root: Path, *, collections=()):
        self.root = Path(os.path.abspath(root))
        if not isinstance(collections, (list, tuple)) or not self.valid(*collections):
            raise StateError("state.collections must be a list of slug names")
        self.collections = frozenset(collections)
        self._flock = None
        if self.collections:
            try:
                import fcntl
            except ImportError as exc:
                raise StateError("Durable state requires a POSIX host", 501, "unsupported") from exc
            self._flock = fcntl.flock
            self._lock_ex = fcntl.LOCK_EX

    @classmethod
    def for_artifact(cls, artifact_dir, site_dir, collections):
        root = Path(os.path.abspath(artifact_dir)) / STATE_DIR
        site = Path(site_dir).resolve()
        resolved = root.resolve()
        if collections and (resolved == site or site in resolved.parents or resolved in site.parents):
            raise StateError("state/ must not overlap build.site", 403, "unsafe_path")
        return cls(root, collections=collections)

    @staticmethod
    def valid(*names):
        return all(isinstance(n, str) and _SLUG.fullmatch(n) for n in names)

    def _validate(self, collection, name=None):
        if not self.valid(collection, *([name] if name is not None else [])):
            raise StateError("bad collection or document name")
        if collection not in self.collections:
            raise StateError("collection is not enabled in state.collections", 403, "disabled")

    @contextmanager
    def _directory(self, collection):
        self._validate(collection)
        descriptors = []
        lock = None
        try:
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
            descriptors.append(fd)
            for i, part in enumerate(self.root.parts[1:]):
                if i == len(self.root.parts) - 2:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                    os.fsync(fd)
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                descriptors.append(fd)
            try:
                os.mkdir(collection, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            os.fsync(fd)
            fd = os.open(collection, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
            lock = os.open(".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                           0o600, dir_fd=fd)
            self._regular(lock)
            self._flock(lock, self._lock_ex)
            yield fd
        except OSError as exc:
            raise StateError("State storage unavailable or unsafe", 503, "storage_unavailable") from exc
        finally:
            if lock is not None:
                os.close(lock)
            for fd in reversed(descriptors):
                os.close(fd)

    @staticmethod
    def _regular(fd):
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise StateError("State files must be regular files without hardlinks", 403, "unsafe_path")

    def _read(self, fd, name):
        try:
            source = os.open(name + ".json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:
            return None
        with os.fdopen(source, "rb") as stream:
            self._regular(stream.fileno())
            raw = stream.read(MAX_BODY + 4097)
        if len(raw) > MAX_BODY + 4096:
            raise StateError("Stored document exceeds size limit", 413, "too_large")
        try:
            payload = strict_json(raw)
            if (not isinstance(payload, dict) or "document" not in payload
                    or payload.get("name") != name or not isinstance(payload.get("updated"), str)):
                raise ValueError("missing document")
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise StateError("Stored state is invalid; original bytes preserved", 500, "corrupt") from exc
        return {**payload, "revision": hashlib.sha256(raw).hexdigest(), "durable": True,
                "git_committed": False}

    def read(self, collection, name):
        self._validate(collection, name)
        with self._directory(collection) as fd:
            return self._read(fd, name)

    def list(self, collection):
        self._validate(collection)
        with self._directory(collection) as fd:
            entries = []
            for filename in sorted(os.listdir(fd)):
                if filename.endswith(".json") and self.valid(filename[:-5]):
                    doc = self._read(fd, filename[:-5])
                    entries.append({k: doc[k] for k in ("name", "updated", "revision", "durable")})
            return entries

    @staticmethod
    def _compare(current, expected_revision):
        if expected_revision is not None and not (
            isinstance(expected_revision, str) and re.fullmatch(r"[0-9a-f]{64}", expected_revision)
        ):
            raise StateError("expected_revision must be null or a revision returned by the server")
        revision = current["revision"] if current else None
        if revision != expected_revision:
            raise StateConflict(revision)

    def write(self, collection, name, document, *, expected_revision):
        self._validate(collection, name)
        try:
            encoded = json.dumps(document, allow_nan=False, ensure_ascii=False).encode("utf-8")
        except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
            raise StateError("document must be finite JSON") from exc
        if len(encoded) > MAX_BODY:
            raise StateError("document exceeds size limit", 413, "too_large")
        payload = {"name": name, "updated": datetime.now(timezone.utc).isoformat(),
                   "document": document}
        payload["updated"] = payload["updated"].replace("+00:00", "Z")
        raw = (json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()
        with self._directory(collection) as fd:
            self._compare(self._read(fd, name), expected_revision)
            temp = ".pending-" + uuid.uuid4().hex
            try:
                target = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                                 0o600, dir_fd=fd)
                with os.fdopen(target, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, name + ".json", src_dir_fd=fd, dst_dir_fd=fd)
                os.fsync(fd)
            finally:
                try:
                    os.unlink(temp, dir_fd=fd)
                except FileNotFoundError:
                    pass
        return {**payload, "revision": hashlib.sha256(raw).hexdigest(), "durable": True,
                "git_committed": False}

    def delete(self, collection, name, *, expected_revision):
        self._validate(collection, name)
        with self._directory(collection) as fd:
            current = self._read(fd, name)
            self._compare(current, expected_revision)
            if current is None:
                return False
            os.unlink(name + ".json", dir_fd=fd)
            os.fsync(fd)
            return True
