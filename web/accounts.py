"""Studia accounts for the hosted mode: users, invites, sessions and login throttling."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from core.log import redact

ITERATIONS = 600_000  # PBKDF2-SHA256, OWASP 2023; scrypt is missing from LibreSSL builds
USERNAME = re.compile(r"^[\w.\-]{2,32}$")
USERNAME_RULE = "用户名需 2–32 位，只能包含字母、数字、汉字、下划线、点或减号"
# No list separators or quoting: "a,b@x.com" would reach several mailboxes from one To header.
EMAIL = re.compile(r"^[^@\s,;<>\"()\[\]\\]+@[^@\s,;<>\"()\[\]\\]+\.[^@\s,;<>\"()\[\]\\]+$")
MIN_PASSWORD = 8
NO_PASSWORD = "!"  # sentinel for OAuth-only accounts; never matches check_password
SESSION_TTL = 7 * 86400
INVITE_TTL = 7 * 86400
RESET_TTL = 30 * 60
ISSUE_REPORT_STATUSES = ("open", "resolved", "ignored")
ISSUE_REPORT_SOURCES = ("auto", "manual")
MAX_REPORT_REPORTERS = 50


class AccountError(Exception):
    pass


def hash_password(password, salt=None, iterations=None):
    salt = salt or secrets.token_bytes(16)
    iterations = iterations or ITERATIONS
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256$%d$%s$%s" % (iterations, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def check_password(password, stored):
    if not stored or stored == NO_PASSWORD:
        return False
    try:
        _, iterations, salt, digest = stored.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def _oauth_username(username, external_id, provider="linuxdo"):
    """Turn an external OAuth handle into a valid Studia username."""
    cleaned = re.sub(r"[^\w.\-]", "_", (username or "").strip()).strip("_")
    if len(cleaned) < 2:
        cleaned = "%s_%s" % (provider, re.sub(r"[^\w.\-]", "", str(external_id)))
    if len(cleaned) < 2:
        cleaned = "%s_%s" % (provider, secrets.token_hex(3))
    return cleaned[:32]


# Verifying against a dummy hash keeps unknown usernames as slow as wrong passwords.
_DUMMY = hash_password(secrets.token_urlsafe(16))


def _validate(username, password):
    if not USERNAME.fullmatch(username or ""):
        raise AccountError(USERNAME_RULE)
    if len(password or "") < MIN_PASSWORD:
        raise AccountError("密码至少 %d 位" % MIN_PASSWORD)


class Accounts:
    """Users, invites and sessions in one SQLite file (mode 600) inside the data directory."""

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, password TEXT NOT NULL,
            role TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0, created REAL, last_login REAL);
        CREATE TABLE IF NOT EXISTS invites (
            code TEXT PRIMARY KEY, created REAL, created_by TEXT, expires REAL, used_by TEXT);
        CREATE TABLE IF NOT EXISTS sessions (
            key TEXT PRIMARY KEY, uid TEXT NOT NULL, csrf TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS resets (key TEXT PRIMARY KEY, uid TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS oauth_accounts (
            provider TEXT NOT NULL, external_id TEXT NOT NULL, uid TEXT NOT NULL,
            username TEXT, name TEXT, trust_level INTEGER, created REAL,
            PRIMARY KEY (provider, external_id), UNIQUE (provider, uid));
        CREATE TABLE IF NOT EXISTS issue_reports (
            id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL UNIQUE,
            platform TEXT NOT NULL,
            course_id TEXT NOT NULL,
            course_name TEXT NOT NULL,
            course_type TEXT NOT NULL DEFAULT '',
            course_kind TEXT NOT NULL DEFAULT '',
            job_kind TEXT NOT NULL,
            headline TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            source TEXT NOT NULL DEFAULT 'manual',
            report_count INTEGER NOT NULL DEFAULT 1,
            reporters_json TEXT NOT NULL DEFAULT '[]',
            payload_json TEXT NOT NULL,
            created REAL NOT NULL,
            updated REAL NOT NULL);
    """

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / "studia.db"
        # Create the file 600 first: SQLite gives its journal the same mode as the database.
        os.close(os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600))
        # ponytail: one connection behind one lock; fine for a handful of users, use a pool if it ever isn't.
        self.db = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(self.SCHEMA)
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(users)")}
            if "max_jobs" not in columns:
                # A per-user override of the site's parallel-job limit; NULL means the default.
                self.db.execute("ALTER TABLE users ADD COLUMN max_jobs INTEGER")
            if "email" not in columns:
                # Verified by a mailed code; needed to change a password and to reset a forgotten one.
                self.db.execute("ALTER TABLE users ADD COLUMN email TEXT")
            self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email ON users (email COLLATE NOCASE)")
            report_cols = {row[1] for row in self.db.execute("PRAGMA table_info(issue_reports)")}
            if "source" not in report_cols:
                self.db.execute("ALTER TABLE issue_reports ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
        self._import_json()

    def _import_json(self):
        """One-time move from the accounts.json used before the database."""
        legacy = self.directory / "accounts.json"
        if not legacy.exists():
            return
        data = json.loads(legacy.read_text(encoding="utf-8"))
        with self.transaction():
            for uid, u in (data.get("users") or {}).items():
                self.db.execute("INSERT OR IGNORE INTO users (id, username, password, role, disabled, created, last_login) "
                                "VALUES (?,?,?,?,?,?,?)",
                                (uid, u["username"], u["password"], u["role"], int(bool(u.get("disabled"))),
                                 u.get("created"), u.get("last_login")))
            for code, i in (data.get("invites") or {}).items():
                self.db.execute("INSERT OR IGNORE INTO invites VALUES (?,?,?,?,?)",
                                (code, i.get("created"), i.get("created_by"), i.get("expires"), i.get("used_by")))
        legacy.replace(legacy.with_name("accounts.json.migrated"))

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.db.execute("COMMIT")

    def _one(self, sql, *args):
        with self.lock:
            return self.db.execute(sql, args).fetchone()

    @staticmethod
    def _oauth_public(row):
        if row is None:
            return None
        return {"id": row["external_id"], "username": row["username"] or "", "name": row["name"] or "",
                "trust_level": row["trust_level"]}

    @staticmethod
    def public(row, oauth=None):
        return {"id": row["id"], "username": row["username"], "role": row["role"], "disabled": bool(row["disabled"]),
                "created": row["created"], "last_login": row["last_login"], "max_jobs": row["max_jobs"],
                "email": row["email"], "has_password": bool(row["password"] and row["password"] != NO_PASSWORD),
                "linuxdo": oauth}

    # ------------------------------------------------------------ site settings and limits

    def setting(self, key, default=None):
        row = self._one("SELECT value FROM settings WHERE key = ?", key)
        return json.loads(row["value"]) if row else default

    def set_setting(self, key, value):
        with self.transaction():
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))

    def set_job_limit(self, uid, limit):
        """A user's own parallel-job limit; None returns them to the site default."""
        with self.transaction():
            if self.db.execute("UPDATE users SET max_jobs = ? WHERE id = ?", (limit, uid)).rowcount == 0:
                raise AccountError("用户不存在")

    # ------------------------------------------------------------ users

    def create_user(self, username, password, role="user"):
        _validate(username, password)
        uid = secrets.token_hex(8)
        try:
            with self.transaction():
                self.db.execute("INSERT INTO users (id, username, password, role, created) VALUES (?,?,?,?,?)",
                                (uid, username, hash_password(password), role, time.time()))
        except sqlite3.IntegrityError:
            raise AccountError("用户名已被使用")
        return uid

    def setup_admin(self, username, password):
        """Create the first administrator; refused once any administrator exists."""
        _validate(username, password)
        uid = secrets.token_hex(8)
        with self.transaction():
            if self.db.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone():
                raise AccountError("管理员已经设置过了，请直接登录")
            self.db.execute("INSERT INTO users (id, username, password, role, created) VALUES (?,?,?,'admin',?)",
                            (uid, username, hash_password(password), time.time()))
        return uid

    def user(self, uid):
        with self.lock:
            row = self.db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
            if row is None:
                return None
            oauth = self.db.execute("SELECT * FROM oauth_accounts WHERE uid = ? AND provider = 'linuxdo'", (uid,)).fetchone()
        return self.public(row, self._oauth_public(oauth))

    def users(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM users ORDER BY created").fetchall()
            links = {r["uid"]: self._oauth_public(r)
                     for r in self.db.execute("SELECT * FROM oauth_accounts WHERE provider = 'linuxdo'").fetchall()}
        return [self.public(row, links.get(row["id"])) for row in rows]

    def find(self, login):
        """A user by username or bound email (登录 and 忘记密码 take either)."""
        if not login:
            return None
        with self.lock:
            row = self.db.execute("SELECT * FROM users WHERE username = ? OR email = ? COLLATE NOCASE", (login, login)).fetchone()
            if row is None:
                return None
            oauth = self.db.execute("SELECT * FROM oauth_accounts WHERE uid = ? AND provider = 'linuxdo'", (row["id"],)).fetchone()
        return self.public(row, self._oauth_public(oauth))

    def has_admin(self):
        return self._one("SELECT 1 FROM users WHERE role = 'admin'") is not None

    def authenticate(self, login, password):
        row = self._one("SELECT * FROM users WHERE username = ? OR email = ? COLLATE NOCASE", login, login) if login else None
        stored = row["password"] if (row is not None and row["password"] != NO_PASSWORD) else _DUMMY
        if not check_password(password or "", stored) or row is None or row["password"] == NO_PASSWORD:
            return None
        if row["disabled"]:
            raise AccountError("这个账号已被停用，请联系管理员")
        with self.transaction():
            self.db.execute("UPDATE users SET last_login = ? WHERE id = ?", (time.time(), row["id"]))
        return self.user(row["id"])

    def password_ok(self, uid, password):
        row = self._one("SELECT password FROM users WHERE id = ?", uid)
        stored = row["password"] if (row is not None and row["password"] != NO_PASSWORD) else _DUMMY
        return check_password(password or "", stored) and row is not None and row["password"] != NO_PASSWORD

    def touch(self, uid, every=60):
        """Record activity: last_login is shown as "last seen", so a 7-day cookie or a fresh
        registration counts too, not only typing the password. Written at most once a minute."""
        now = time.time()
        with self.transaction():
            self.db.execute("UPDATE users SET last_login = ? WHERE id = ? AND (last_login IS NULL OR last_login < ?)",
                            (now, uid, now - every))

    def set_password(self, uid, password):
        if len(password or "") < MIN_PASSWORD:
            raise AccountError("密码至少 %d 位" % MIN_PASSWORD)
        hashed = hash_password(password)
        with self.transaction():
            if self.db.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, uid)).rowcount == 0:
                raise AccountError("用户不存在")
            self.db.execute("DELETE FROM resets WHERE uid = ?", (uid,))  # a link mailed earlier must not undo this

    def set_username(self, uid, username):
        if not USERNAME.fullmatch(username or ""):
            raise AccountError(USERNAME_RULE)
        try:
            with self.transaction():
                if self.db.execute("UPDATE users SET username = ? WHERE id = ?", (username, uid)).rowcount == 0:
                    raise AccountError("用户不存在")
        except sqlite3.IntegrityError:
            raise AccountError("用户名已被使用") from None

    def email_taken(self, email, uid):
        return self._one("SELECT 1 FROM users WHERE email = ? COLLATE NOCASE AND id != ?", email, uid) is not None

    def set_email(self, uid, email):
        try:
            with self.transaction():
                self.db.execute("UPDATE users SET email = ? WHERE id = ?", (email, uid))
        except sqlite3.IntegrityError:
            raise AccountError("这个邮箱已经绑定了其他账号") from None

    def create_reset(self, uid, ttl=RESET_TTL):
        """Token for a mailed password link. Single use, kept hashed like sessions (so links outlive a restart);
        only the newest link of a user works."""
        token = secrets.token_urlsafe(32)
        with self.transaction():
            self.db.execute("DELETE FROM resets WHERE uid = ? OR expires < ?", (uid, time.time()))
            self.db.execute("INSERT INTO resets VALUES (?,?,?)", (Sessions._key(token), uid, time.time() + ttl))
        return token

    def reset_password(self, token, password):
        """Set the password a mailed link was sent for; returns that user's id."""
        if len(password or "") < MIN_PASSWORD:
            raise AccountError("密码至少 %d 位" % MIN_PASSWORD)
        hashed = hash_password(password)  # slow on purpose: outside the lock
        with self.transaction():
            row = self.db.execute("SELECT uid FROM resets WHERE key = ? AND expires >= ?",
                                  (Sessions._key(token or ""), time.time())).fetchone()
            if row is None:
                raise AccountError("链接无效或已过期，请重新发送")
            self.db.execute("DELETE FROM resets WHERE uid = ?", (row["uid"],))
            self.db.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, row["uid"]))
        return row["uid"]

    def set_disabled(self, uid, disabled):
        with self.transaction():
            row = self.db.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()
            if row is None:
                raise AccountError("用户不存在")
            admins = self.db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND disabled = 0").fetchone()[0]
            if disabled and row["role"] == "admin" and admins <= 1:
                raise AccountError("不能停用最后一个管理员")
            self.db.execute("UPDATE users SET disabled = ? WHERE id = ?", (int(bool(disabled)), uid))

    # ------------------------------------------------------------ invites

    def create_invite(self, created_by, ttl=INVITE_TTL):
        code = "-".join(secrets.token_hex(2).upper() for _ in range(3))
        with self.transaction():
            self.db.execute("INSERT INTO invites VALUES (?,?,?,?,NULL)", (code, time.time(), created_by, time.time() + ttl))
        return code

    def invites(self):
        now = time.time()
        with self.lock:
            rows = self.db.execute("SELECT * FROM invites ORDER BY created DESC").fetchall()
        return [{"code": r["code"], "created": r["created"], "expires": r["expires"], "used_by": r["used_by"],
                 "state": "used" if r["used_by"] else "expired" if r["expires"] < now else "open"} for r in rows]

    def revoke_invite(self, code):
        with self.transaction():
            if self.db.execute("DELETE FROM invites WHERE code = ?", (code,)).rowcount == 0:
                raise AccountError("邀请码不存在")

    def register(self, code, username, password, *, invite=True, email=None):
        """A new account. invite: the site wants an unused invite code, which this uses up. email: one already
        proven by a mailed code, bound from the start."""
        _validate(username, password)
        code = (code or "").strip().upper()
        uid = secrets.token_hex(8)
        hashed = hash_password(password)  # slow on purpose: not while holding the database lock
        with self.transaction():
            if invite:
                row = self.db.execute("SELECT * FROM invites WHERE code = ?", (code,)).fetchone()
                if row is None or row["used_by"] or row["expires"] < time.time():
                    raise AccountError("邀请码无效或已过期")
            try:
                self.db.execute("INSERT INTO users (id, username, password, role, created, email) VALUES (?,?,?,'user',?,?)",
                                (uid, username, hashed, time.time(), email))
            except sqlite3.IntegrityError as exc:
                raise AccountError("这个邮箱已经注册过了" if "email" in str(exc) else "用户名已被使用") from None
            if invite:
                self.db.execute("UPDATE invites SET used_by = ? WHERE code = ?", (uid, code))
        return uid

    # ------------------------------------------------------------ OAuth accounts

    def login_oauth(self, provider, external_id, *, username="", name="", trust_level=None):
        """Sign in via an OAuth identity, creating a passwordless user on first visit. Returns (uid, created)."""
        external_id = str(external_id or "").strip()
        if not external_id:
            raise AccountError("第三方账号标识无效")
        level = trust_level if isinstance(trust_level, int) and not isinstance(trust_level, bool) else None
        uname, display = str(username or "").strip()[:64], str(name or "").strip()[:64]
        now = time.time()
        with self.transaction():
            link = self.db.execute("SELECT uid FROM oauth_accounts WHERE provider = ? AND external_id = ?",
                                   (provider, external_id)).fetchone()
            if link is not None:
                row = self.db.execute("SELECT id, disabled FROM users WHERE id = ?", (link["uid"],)).fetchone()
                if row is not None:
                    if row["disabled"]:
                        raise AccountError("这个账号已被停用，请联系管理员")
                    self.db.execute("UPDATE oauth_accounts SET username = ?, name = ?, trust_level = ? "
                                    "WHERE provider = ? AND external_id = ?",
                                    (uname, display, level, provider, external_id))
                    self.db.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, row["id"]))
                    return row["id"], False
                self.db.execute("DELETE FROM oauth_accounts WHERE provider = ? AND external_id = ?",
                                (provider, external_id))
            base = _oauth_username(uname, external_id, provider)
            uid = secrets.token_hex(8)
            candidates = [base] + ["%s_%d" % (base[:27], n) for n in range(2, 20)] + [
                "%s_%s" % (base[:25], secrets.token_hex(3)) for _ in range(10)
            ]
            inserted = False
            for candidate in candidates:
                try:
                    self.db.execute(
                        "INSERT INTO users (id, username, password, role, created, last_login) VALUES (?,?,?,'user',?,?)",
                        (uid, candidate, NO_PASSWORD, now, now),
                    )
                    inserted = True
                    break
                except sqlite3.IntegrityError:
                    continue
            if not inserted:
                raise AccountError("无法分配用户名，请稍后重试")
            self.db.execute(
                "INSERT INTO oauth_accounts (provider, external_id, uid, username, name, trust_level, created) "
                "VALUES (?,?,?,?,?,?,?)",
                (provider, external_id, uid, uname, display, level, now),
            )
            return uid, True

    def bind_oauth(self, uid, provider, external_id, *, username="", name="", trust_level=None):
        """Link an external OAuth identity to an existing Studia account."""
        external_id = str(external_id or "").strip()
        if not external_id:
            raise AccountError("第三方账号标识无效")
        level = trust_level if isinstance(trust_level, int) and not isinstance(trust_level, bool) else None
        uname, display = str(username or "").strip()[:64], str(name or "").strip()[:64]
        with self.transaction():
            if self.db.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone() is None:
                raise AccountError("用户不存在")
            existing = self.db.execute("SELECT uid FROM oauth_accounts WHERE provider = ? AND external_id = ?",
                                       (provider, external_id)).fetchone()
            if existing is not None:
                if existing["uid"] != uid:
                    raise AccountError("这个 Linux DO 账号已经绑定了其他 Studia 账号")
                self.db.execute("UPDATE oauth_accounts SET username = ?, name = ?, trust_level = ? "
                                "WHERE provider = ? AND external_id = ?",
                                (uname, display, level, provider, external_id))
                return
            if self.db.execute("SELECT 1 FROM oauth_accounts WHERE provider = ? AND uid = ?", (provider, uid)).fetchone():
                raise AccountError("当前账号已经绑定了其他 Linux DO 账号，请先解绑")
            self.db.execute(
                "INSERT INTO oauth_accounts (provider, external_id, uid, username, name, trust_level, created) "
                "VALUES (?,?,?,?,?,?,?)",
                (provider, external_id, uid, uname, display, level, time.time()),
            )

    def unbind_oauth(self, uid, provider):
        """Remove an OAuth link; refused when the account has no password to fall back on."""
        with self.transaction():
            row = self.db.execute("SELECT password FROM users WHERE id = ?", (uid,)).fetchone()
            if row is None:
                raise AccountError("用户不存在")
            if not row["password"] or row["password"] == NO_PASSWORD:
                raise AccountError("当前账号没有设置密码，不能解绑 Linux DO")
            if self.db.execute("DELETE FROM oauth_accounts WHERE provider = ? AND uid = ?", (provider, uid)).rowcount == 0:
                raise AccountError("当前账号尚未绑定 Linux DO")

    # ------------------------------------------------------------ course adaptation reports

    @staticmethod
    def _clean_note(note):
        if not isinstance(note, str):
            return ""
        text = " ".join(note.split()).strip()
        return redact(text)[:500]

    @staticmethod
    def _parse_json(raw, default):
        try:
            value = json.loads(raw) if raw else default
            return value if isinstance(value, type(default)) else default
        except (ValueError, TypeError):
            return default

    @classmethod
    def _report_public(cls, row):
        reporters = cls._parse_json(row["reporters_json"], [])
        payload = cls._parse_json(row["payload_json"], {})
        distinct_uids = {entry.get("uid") or entry.get("username") for entry in reporters if isinstance(entry, dict)}
        manual_uids = {
            entry.get("uid") or entry.get("username")
            for entry in reporters
            if isinstance(entry, dict) and (entry.get("source") or "manual") == "manual"
        }
        public_reporters = [
            {
                "username": str(entry.get("username") or "成员"),
                "at": entry.get("at"),
                "note": str(entry.get("note") or ""),
                "source": str(entry.get("source") or "manual"),
            }
            for entry in reporters if isinstance(entry, dict)
        ]
        raw_source = row["source"] if "source" in row.keys() else None
        source = raw_source if raw_source in ISSUE_REPORT_SOURCES else ("manual" if manual_uids else "auto")
        return {
            "id": row["id"],
            "fingerprint": row["fingerprint"],
            "platform": row["platform"],
            "course_id": row["course_id"],
            "course_name": row["course_name"],
            "course_type": row["course_type"],
            "course_kind": row["course_kind"],
            "job_kind": row["job_kind"],
            "headline": row["headline"],
            "status": row["status"],
            "source": source,
            "manual_count": len(manual_uids),
            "report_count": int(row["report_count"] or 1),
            "reporter_count": max(1, len(distinct_uids)),
            "reporters": public_reporters,
            "payload": payload,
            "created": row["created"],
            "updated": row["updated"],
        }

    def submit_issue_report(self, check, *, uid, username, note="", source="manual"):
        """Upsert a sanitized course adaptation report grouped by its problem fingerprint."""
        if not isinstance(check, dict) or not check.get("fingerprint"):
            raise AccountError("上报内容无效")
        source = source if source in ISSUE_REPORT_SOURCES else "manual"
        fingerprint = str(check["fingerprint"])[:64]
        platform = str(check.get("platform") or "")[:32]
        course_id = str(check.get("course_id") or "")[:128]
        course_name = str(check.get("course_name") or "未知课程")[:160]
        course_type = str(check.get("course_type") or "")[:80]
        course_kind = str(check.get("course_kind") or "")[:40]
        job_kind = str(check.get("job_kind") or "")[:32]
        job_id = str(check.get("job_id") or "")[:32]
        headline = str(check.get("headline") or "检测到未完成或跳过的课程内容")[:200]
        clean_note = self._clean_note(note) if source == "manual" else ""
        now = time.time()
        payload_json = json.dumps(check, ensure_ascii=False)
        entry = {
            "uid": str(uid or ""),
            "username": str(username or "成员")[:64],
            "job_id": job_id,
            "at": now,
            "note": clean_note,
            "source": source,
        }

        with self.transaction():
            existing = self.db.execute(
                "SELECT * FROM issue_reports WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
            if existing is None:
                report_id = secrets.token_hex(8)
                self.db.execute(
                    "INSERT INTO issue_reports (id, fingerprint, platform, course_id, course_name, "
                    "course_type, course_kind, job_kind, headline, status, source, report_count, "
                    "reporters_json, payload_json, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        report_id, fingerprint, platform, course_id, course_name, course_type,
                        course_kind, job_kind, headline, "open", source, 1,
                        json.dumps([entry], ensure_ascii=False), payload_json, now, now,
                    ),
                )
                return {
                    "id": report_id,
                    "fingerprint": fingerprint,
                    "already_reported": False,
                    "report_count": 1,
                    "reporter_count": 1,
                    "status": "open",
                    "source": source,
                }

            reporters = [r for r in self._parse_json(existing["reporters_json"], []) if isinstance(r, dict)]
            dup = next(
                (r for r in reporters
                 if r.get("uid") == entry["uid"] and ((job_id and r.get("job_id") == job_id)
                                                      or (not job_id and now - float(r.get("at") or 0) < 60))),
                None,
            )
            report_count = int(existing["report_count"] or 1)
            status = existing["status"]
            row_source = existing["source"] if existing["source"] in ISSUE_REPORT_SOURCES else "manual"
            if dup is not None:
                dup_source = dup.get("source") or "manual"
                if source == "manual" and dup_source == "auto":
                    dup["source"] = "manual"
                    dup["at"] = now
                    if clean_note:
                        dup["note"] = clean_note
                    reporters.remove(dup)
                    reporters.insert(0, dup)
                    row_source = "manual"
                    if status == "resolved":
                        status = "open"
                    already_reported = False
                else:
                    if source == "manual" and clean_note:
                        dup["note"] = clean_note
                        dup["at"] = now
                    already_reported = True
            else:
                report_count += 1
                already_reported = False
                if status == "resolved":
                    status = "open"
                if source == "manual":
                    row_source = "manual"
                    reporters.insert(0, entry)
                    del reporters[MAX_REPORT_REPORTERS:]
                else:
                    # Keep at most one auto-detected row per user so retries increment hit counts without flooding.
                    prior_auto = next(
                        (r for r in reporters if r.get("uid") == entry["uid"] and r.get("source") == "auto"),
                        None,
                    )
                    if prior_auto is not None:
                        reporters.remove(prior_auto)
                    reporters.insert(0, entry)
                    del reporters[MAX_REPORT_REPORTERS:]
            distinct_uids = {r.get("uid") or r.get("username") for r in reporters}
            self.db.execute(
                "UPDATE issue_reports SET course_name = ?, course_type = ?, course_kind = ?, "
                "headline = ?, status = ?, source = ?, report_count = ?, reporters_json = ?, payload_json = ?, updated = ? "
                "WHERE id = ?",
                (
                    course_name, course_type, course_kind, headline, status, row_source, report_count,
                    json.dumps(reporters, ensure_ascii=False), payload_json, now, existing["id"],
                ),
            )
            return {
                "id": existing["id"],
                "fingerprint": fingerprint,
                "already_reported": already_reported,
                "report_count": report_count,
                "reporter_count": max(1, len(distinct_uids)),
                "status": status,
                "source": row_source,
            }

    def issue_reports(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM issue_reports ORDER BY updated DESC").fetchall()
        items = [self._report_public(row) for row in rows]
        rank = {"open": 0, "resolved": 1, "ignored": 2}
        items.sort(key=lambda r: (
            rank.get(r["status"], 3),
            -r["reporter_count"],
            0 if r["source"] == "manual" else 1,
            -r["report_count"],
            -float(r["updated"] or 0),
        ))
        return items

    def set_issue_report_status(self, report_id, status):
        if status not in ISSUE_REPORT_STATUSES:
            raise AccountError("上报状态只能是待处理、已处理或已忽略")
        with self.transaction():
            updated = self.db.execute(
                "UPDATE issue_reports SET status = ?, updated = ? WHERE id = ?",
                (status, time.time(), str(report_id or "")),
            ).rowcount
            if updated == 0:
                raise AccountError("这条上报记录不存在")

    def delete_issue_report(self, report_id):
        with self.transaction():
            deleted = self.db.execute(
                "DELETE FROM issue_reports WHERE id = ?", (str(report_id or ""),)
            ).rowcount
            if deleted == 0:
                raise AccountError("这条上报记录不存在")


class Sessions:
    """Sessions stored in the accounts database, keyed by the SHA-256 of the cookie value,
    so a restart (or a container update) does not sign everyone out."""

    def __init__(self, accounts, ttl=SESSION_TTL):
        self.accounts = accounts
        self.ttl = ttl

    @staticmethod
    def _key(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, uid):
        token = secrets.token_urlsafe(32)
        with self.accounts.transaction():
            self.accounts.db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            self.accounts.db.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                                     (self._key(token), uid, secrets.token_urlsafe(24), time.time() + self.ttl))
        return token

    def get(self, token):
        if not token:
            return None
        row = self.accounts._one("SELECT uid, csrf, expires FROM sessions WHERE key = ?", self._key(token))
        if row is None or row["expires"] < time.time():
            return None
        return {"uid": row["uid"], "csrf": row["csrf"], "expires": row["expires"]}

    def drop(self, token):
        with self.accounts.transaction():
            self.accounts.db.execute("DELETE FROM sessions WHERE key = ?", (self._key(token or ""),))

    def drop_user(self, uid):
        with self.accounts.transaction():
            self.accounts.db.execute("DELETE FROM sessions WHERE uid = ?", (uid,))


class Throttle:
    """Lock a key (IP or username) after repeated failures within a window."""

    def __init__(self, limit=5, window=900):
        self.limit, self.window = limit, window
        self.failures = {}
        self.lock = threading.Lock()

    def blocked(self, *keys):
        now = time.time()
        with self.lock:
            for key in keys:
                recent = [t for t in self.failures.get(key, []) if now - t < self.window]
                self.failures[key] = recent
                if len(recent) >= self.limit:
                    return int(self.window - (now - recent[0])) + 1
        return 0

    def take(self, *keys):
        """Check and count one attempt in one step: concurrent guesses can't all slip in before any is counted.
        Returns the seconds to wait (nothing counted) or 0; a success should clear() the keys afterwards."""
        now = time.time()
        with self.lock:
            for key in keys:
                recent = [t for t in self.failures.get(key, []) if now - t < self.window]
                self.failures[key] = recent
                if len(recent) >= self.limit:
                    return int(self.window - (now - recent[0])) + 1
            for key in keys:
                self.failures[key].append(now)
        return 0

    def fail(self, *keys):
        with self.lock:
            for key in keys:
                self.failures.setdefault(key, []).append(time.time())

    def clear(self, *keys):
        with self.lock:
            for key in keys:
                self.failures.pop(key, None)
