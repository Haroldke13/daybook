#!/usr/bin/env python3
"""Dated Notepad — a local server backing a date-organised notebook.

Notes are stored as plain UTF-8 files, one per day, named YYYY-MM-DD.md
in ~/Documents/DatedNotepad. Plain files on purpose: greppable, portable,
and readable without this app.

Also extracts #tags from note bodies and writes combined .md/.txt exports
into ~/Documents/DatedNotepad/exports.
"""

import argparse
import datetime as dt
import json
import mimetypes
import re
import secrets
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
NOTES_DIR = Path.home() / "Documents" / "DatedNotepad"
EXPORT_DIR = NOTES_DIR / "exports"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_BODY = 8 * 1024 * 1024  # 8 MB per day's note is plenty

# --- #tag extraction --------------------------------------------------
# A tag is #word. It must not be an ATX heading marker ("# Foo", "## Bar"),
# must not live inside a code span or fence, must not be the fragment of a
# URL, and must contain at least one letter (so "#3" stays a plain number).
TAG_RE = re.compile(r"(?<![0-9A-Za-z_#&/\\])#([A-Za-z0-9_/-]*[A-Za-z][A-Za-z0-9_/-]*)")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?=\s|$)")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
# Bounded on both sides: the original r"(`+)[^\n]*?\1" backtracks
# catastrophically on a line of many backticks, hanging every endpoint
# that parses notes. This form is linear.
CODE_SPAN_RE = re.compile(r"`{1,3}[^`\n]{0,400}`{1,3}")
MAX_TAG = 48


def extract_tags(text: str):
    """Return the lower-cased tags used in a note, in first-seen order."""
    tags, seen, fence = [], set(), None
    for line in (text or "").splitlines():
        m = FENCE_RE.match(line)
        if fence is not None:
            # inside a fenced block: only a matching fence can close it
            if m and m.group(1)[0] == fence:
                fence = None
            continue
        if m:
            fence = m.group(1)[0]
            continue
        line = HEADING_RE.sub("", line)          # drop the heading marker only
        line = CODE_SPAN_RE.sub(" ", line)       # drop `inline code`
        for raw in TAG_RE.findall(line):
            tag = raw.rstrip("-/_").lower()[:MAX_TAG]
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tags


def note_path(day: str) -> Path:
    if not DATE_RE.match(day):
        raise ValueError("bad date")
    dt.date.fromisoformat(day)  # rejects 2026-13-45
    p = (NOTES_DIR / f"{day}.md").resolve()
    if p.parent != NOTES_DIR.resolve():
        raise ValueError("escapes notes dir")
    return p


def list_notes():
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in NOTES_DIR.glob("????-??-??.md"):
        day = p.stem
        if not DATE_RE.match(day):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        stripped = text.strip()
        out.append({
            "date": day,
            "tags": extract_tags(text),
            "chars": len(text),
            "words": len(stripped.split()) if stripped else 0,
            "empty": not stripped,
            "preview": " ".join(stripped.split())[:120],
            "mtime": int(p.stat().st_mtime),
        })
    out.sort(key=lambda n: n["date"], reverse=True)
    return out


def tag_cloud(notes):
    counts = {}
    for n in notes:
        for t in n["tags"]:
            counts[t] = counts.get(t, 0) + 1
    return [{"tag": t, "count": c}
            for t, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def build_export(days, fmt: str):
    """Combine whole days into one document. Returns (text, words)."""
    md = fmt != "txt"
    first, last = days[0][0], days[-1][0]
    words = sum(len(t.split()) for _, t in days)
    span = first if first == last else f"{first} \u2192 {last}"
    head = f"Dated Notepad \u2014 {span}"
    tally = f"{len(days)} note{'' if len(days) == 1 else 's'} \u00b7 {words} words"
    parts = [f"# {head}", f"_{tally}_"] if md else [head, tally, "=" * len(head)]
    for day, text in days:
        parts.append(f"## {day}" if md else f"{day}\n{'-' * len(day)}")
        parts.append(text.strip())
    return "\n\n".join(parts).rstrip() + "\n", words


class Handler(BaseHTTPRequestHandler):
    server_version = "dated-notepad/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if self.server.verbose:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _deny_host(self):
        return self._send(421, b"bad host", "text/plain; charset=utf-8")

    def _host_ok(self) -> bool:
        """Reject requests whose Host is not loopback.

        Without this a malicious site can re-point its own hostname at
        127.0.0.1 (DNS rebinding) and reach this server from the browser.
        The token still gates access; this is defence in depth.
        """
        h = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return h in ("127.0.0.1", "localhost", "::1", "")

    def _authed(self, qs):
        tok = (qs.get("t") or [None])[0]
        # compare_digest raises TypeError on non-ASCII str, which would kill the
        # request thread before auth is even decided. Compare as bytes.
        if tok:
            try:
                if secrets.compare_digest(tok.encode("utf-8", "surrogatepass"),
                                          self.server.token.encode("utf-8")):
                    return True
            except (TypeError, UnicodeError):
                pass
        return self.server.token in self.headers.get("Referer", "")

    def do_GET(self):
        if not self._host_ok():
            return self._deny_host()
        parsed = urlparse(self.path)
        path, qs = unquote(parsed.path), parse_qs(parsed.query)

        if path.startswith("/static/"):
            return self.static(path[len("/static/"):])

        if not self._authed(qs):
            return self._send(403, b"forbidden", "text/plain; charset=utf-8")

        if path == "/":
            return self.static("index.html")

        if path == "/api/notes":
            notes = list_notes()
            return self._json(200, {
                "today": dt.date.today().isoformat(),
                "dir": str(NOTES_DIR),
                "exportDir": str(EXPORT_DIR),
                "notes": notes,
                "tags": tag_cloud(notes),
            })

        if path == "/api/note":
            day = (qs.get("date") or [""])[0]
            try:
                p = note_path(day)
            except ValueError:
                return self._json(400, {"error": "bad date"})
            text = p.read_text(encoding="utf-8") if p.exists() else ""
            return self._json(200, {"date": day, "text": text, "exists": p.exists()})

        if path == "/api/search":
            term = (qs.get("q") or [""])[0].lower().strip()
            hits = []
            if term:
                for n in list_notes():
                    try:
                        text = note_path(n["date"]).read_text(encoding="utf-8")
                    except (OSError, ValueError):
                        continue
                    low = text.lower()
                    if term in low:
                        i = low.index(term)
                        s = max(0, i - 45)
                        hits.append({
                            "date": n["date"],
                            "snippet": ("…" if s else "") +
                                       " ".join(text[s:i + 110].split()),
                        })
            return self._json(200, {"hits": hits})

        return self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if not self._host_ok():
            return self._deny_host()
        parsed = urlparse(self.path)
        path, qs = unquote(parsed.path), parse_qs(parsed.query)
        if not self._authed(qs):
            return self._send(403, b"forbidden", "text/plain; charset=utf-8")
        if path == "/api/export":
            return self.export()
        if path != "/api/note":
            return self._send(404, b"not found", "text/plain; charset=utf-8")

        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "bad Content-Length"})
        # A negative length passes a naive "> cap" test and then
        # rfile.read(-1) drains the socket to EOF, defeating the cap.
        if n < 0 or n > MAX_BODY:
            return self._json(413, {"error": "bad or oversized body"})
        if n > MAX_BODY:
            return self._json(413, {"error": "note too large"})
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
            p = note_path(payload["date"])
            text = payload.get("text", "")
            if not isinstance(text, str):
                raise ValueError("text must be a string")
        except (ValueError, KeyError, TypeError) as e:
            return self._json(400, {"error": str(e)})

        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        if text.strip():
            tmp = p.with_suffix(".md.tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(p)          # atomic: never a half-written note
        elif p.exists():
            p.unlink()              # emptied note = deleted day
        return self._json(200, {"ok": True, "saved": p.name, "chars": len(text)})

    def export(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "bad Content-Length"})
        # A negative length passes a naive "> cap" test and then
        # rfile.read(-1) drains the socket to EOF, defeating the cap.
        if n < 0 or n > MAX_BODY:
            return self._json(413, {"error": "bad or oversized body"})
        if n > MAX_BODY:
            return self._json(413, {"error": "request too large"})
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("body must be an object")
            fmt = "txt" if payload.get("format") == "txt" else "md"
            everything = bool(payload.get("all"))
            start = "" if everything else (payload.get("from") or "")
            end = "" if everything else (payload.get("to") or "")
            for d in (start, end):
                if d:
                    if not DATE_RE.match(d):
                        raise ValueError("bad date")
                    dt.date.fromisoformat(d)
            if start and end and start > end:
                start, end = end, start
        except (ValueError, KeyError, TypeError) as e:
            return self._json(400, {"error": str(e)})

        days = []
        for note in sorted(list_notes(), key=lambda x: x["date"]):
            day = note["date"]
            if (start and day < start) or (end and day > end):
                continue
            try:
                text = note_path(day).read_text(encoding="utf-8")
            except (OSError, ValueError):
                continue
            if text.strip():
                days.append((day, text))
        if not days:
            return self._json(400, {"error": "no notes in that range"})

        text, words = build_export(days, fmt)
        stamp = "all" if everything else f"{days[0][0]}_to_{days[-1][0]}"
        out = EXPORT_DIR / f"notes-{stamp}.{fmt}"
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            tmp = out.with_name(out.name + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(out)            # atomic, like a note save
        except OSError as e:
            return self._json(500, {"error": f"could not write export: {e}"})
        return self._json(200, {
            "ok": True, "path": str(out), "days": len(days),
            "words": words, "chars": len(text),
        })

    def static(self, rel):
        target = (STATIC_DIR / rel).resolve()
        # startswith() on the raw string also matches sibling directories
        # whose name merely begins with "static". Compare path components.
        if not target.is_relative_to(STATIC_DIR.resolve()) or not target.is_file():
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        return self._send(200, target.read_bytes(), ctype)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--token", default=None)
    ap.add_argument("--print-url", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    port = args.port
    if not port:
        s = socket.socket(); s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]; s.close()
    token = args.token or secrets.token_urlsafe(18)

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    httpd.token = token
    httpd.verbose = args.verbose

    url = f"http://127.0.0.1:{port}/?t={token}"
    print(url if args.print_url else f"Dated Notepad at {url}\nNotes in {NOTES_DIR}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
