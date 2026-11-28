"""Post-task adaptation check: collect sanitized findings when a job leaves items unfinished or skipped."""
from __future__ import annotations

import hashlib
import re
import time

from core.log import redact

FINDING_META = {
    "unknown_type": ("未适配资源类型", "unknown"),
    "skipped_unit": ("跳过无法处理的节点", "skipped"),
    "unverified_unit": ("提交后平台未标记完成", "unverified"),
    "resource_error": ("学习单元处理失败", "failed"),
    "activity_error": ("课程活动未完成", "failed"),
    "empty_units": ("未读取到可学习内容", "skipped"),
    "unsupported_course": ("未适配的课程类型", "unknown"),
    "paper_skipped": ("试卷暂不支持或被跳过", "skipped"),
    "paper_error": ("试卷未能完成", "failed"),
    "paper_unknown": ("交卷结果未确认", "unverified"),
    "job_error": ("任务执行异常", "failed"),
}

PLATFORM_NAMES = {"mooc": "MOOC", "zhs": "智慧树"}
MAX_FINDINGS = 30
MAX_LOGS = 25
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_text(value, limit=240):
    if value in (None, ""):
        return ""
    text = _CTRL.sub("", str(value)).strip()
    text = " ".join(text.split())
    text = redact(text)
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


def make_finding(code, *, name="", kind="", detail="", fields="", label=""):
    """Build one sanitized finding dict safe to show in the UI and store in issue reports."""
    default_label, bucket = FINDING_META.get(code, ("未完成项", "failed"))
    return {
        "code": str(code or "job_error")[:40],
        "bucket": bucket,
        "label": _clean_text(label or default_label, 60),
        "name": _clean_text(name, 120),
        "kind": _clean_text(kind, 60),
        "detail": _clean_text(detail, 240),
        "fields": _clean_text(fields, 320),
    }


def _dedupe_findings(findings):
    items = []
    seen = set()
    for raw in findings or ():
        if not isinstance(raw, dict):
            continue
        item = make_finding(
            raw.get("code", "job_error"),
            name=raw.get("name", ""),
            kind=raw.get("kind", ""),
            detail=raw.get("detail", ""),
            fields=raw.get("fields", ""),
            label=raw.get("label", ""),
        )
        key = (item["code"], item["name"], item["kind"], item["detail"])
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
        if len(items) >= MAX_FINDINGS:
            break
    return items


def _fingerprint(platform, course_kind, course_id, job_kind, items):
    sigs = sorted({(item["code"], item["kind"]) for item in items})
    basis = "|".join([
        str(platform or ""),
        str(course_kind or ""),
        str(course_id or ""),
        str(job_kind or ""),
        ",".join("%s:%s" % pair for pair in sigs),
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _headline(job_kind, counts, items):
    total = counts["total"]
    if job_kind == "answer":
        return "有 %d 份试卷未能自动完成或被跳过" % total
    if counts["unknown"] and counts["unverified"]:
        return "发现 %d 项未适配或提交后仍未完成的内容" % total
    if counts["unknown"]:
        return "发现 %d 项暂未适配的课程内容" % counts["unknown"]
    if counts["unverified"]:
        return "有 %d 项提交后平台仍未标记完成" % counts["unverified"]
    if counts["skipped"] and not counts["failed"]:
        return "有 %d 项学习内容被跳过，无法自动完成" % counts["skipped"]
    if counts["failed"] and not counts["skipped"]:
        return "有 %d 项任务环节执行失败" % counts["failed"]
    return "检测到 %d 项未能完成或被跳过的课程内容" % total


def _sanitize_logs(lines):
    if not isinstance(lines, list):
        return []
    important = []
    normal = []
    for entry in lines:
        if not isinstance(entry, dict):
            continue
        text = _clean_text(entry.get("text", ""), 260)
        if not text:
            continue
        row = {
            "time": _clean_text(entry.get("time", ""), 16),
            "level": _clean_text(entry.get("level", ""), 16),
            "text": text,
        }
        if row["level"] in ("error", "warn"):
            important.append(row)
        else:
            normal.append(row)
    picked = important[:MAX_LOGS]
    if len(picked) < MAX_LOGS:
        picked.extend(normal[: MAX_LOGS - len(picked)])
    return picked


def _sanitize_shares(shares):
    if not isinstance(shares, dict):
        return None
    clean = {}
    for key, value in list(shares.items())[:16]:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            clean[str(key)[:32]] = value
    return clean or None


def build_issue_check(job, *, findings, course_meta=None):
    """Build a compact, redacted post-task check summary, or None when everything succeeded cleanly."""
    items = _dedupe_findings(findings)
    if not items:
        return None
    meta = course_meta if isinstance(course_meta, dict) else {}
    platform = str(job.get("platform") or "")
    course_id = str(job.get("course") or "")
    course_name = _clean_text(job.get("course_name") or "未知课程", 120)
    course_type = _clean_text(meta.get("type") or "", 60)
    course_kind = _clean_text(meta.get("kind") or platform, 40)
    progress = meta.get("progress")
    if isinstance(progress, bool) or not isinstance(progress, (int, float)):
        progress = None
    job_kind = str(job.get("kind") or "")
    counts = {"failed": 0, "skipped": 0, "unverified": 0, "unknown": 0, "total": len(items)}
    for item in items:
        bucket = item.get("bucket")
        if bucket in counts:
            counts[bucket] += 1
    return {
        "fingerprint": _fingerprint(platform, course_kind, course_id, job_kind, items),
        "platform": platform,
        "platform_name": PLATFORM_NAMES.get(platform, platform or "未知平台"),
        "course_id": course_id,
        "course_name": course_name,
        "course_type": course_type,
        "course_kind": course_kind,
        "progress": progress,
        "shares": _sanitize_shares(meta.get("shares")),
        "job_id": str(job.get("id") or ""),
        "job_kind": job_kind,
        "job_title": _clean_text(job.get("title") or job_kind or "任务", 40),
        "job_state": str(job.get("state") or ""),
        "job_summary": _clean_text(job.get("summary") or "", 180),
        "headline": _headline(job_kind, counts, items),
        "counts": counts,
        "items": items,
        "logs": _sanitize_logs(job.get("lines")),
        "created_at": time.time(),
    }


def format_issue_markdown(check, *, note=""):
    """Format one issue_check payload into a clean, redacted Markdown block for copying."""
    lines = [
        "### 课程适配问题诊断",
        "- 平台：%s%s" % (check.get("platform_name") or check.get("platform") or "未知",
                        "（%s）" % check["course_type"] if check.get("course_type") else ""),
        "- 课程：%s（ID: `%s`，课型: `%s`）" % (
            check.get("course_name") or "未知课程",
            check.get("course_id") or "",
            check.get("course_kind") or "",
        ),
        "- 任务：%s · 状态：%s%s" % (
            check.get("job_title") or check.get("job_kind") or "任务",
            check.get("job_state") or "",
            "（%s）" % check["job_summary"] if check.get("job_summary") else "",
        ),
    ]
    if check.get("progress") is not None:
        lines.append("- 当前进度：%s%%" % check["progress"])
    if check.get("shares"):
        parts = ["%s=%s" % (k, v) for k, v in check["shares"].items() if v]
        if parts:
            lines.append("- 考核占比：%s" % ", ".join(parts))
    clean_note = _clean_text(note, 500)
    if clean_note:
        lines.append("- 补充说明：%s" % clean_note)
    lines.append("")
    lines.append("#### 检测到的问题（共 %d 项）" % len(check.get("items") or []))
    for idx, item in enumerate(check.get("items") or [], 1):
        head = "%d. [%s] %s" % (idx, item.get("label") or item.get("code"), item.get("name") or "未命名")
        if item.get("kind"):
            head += "（类型：`%s`）" % item["kind"]
        lines.append(head)
        if item.get("detail"):
            lines.append("   - 说明：%s" % item["detail"])
        if item.get("fields"):
            lines.append("   - 字段：`%s`" % item["fields"])
    logs = check.get("logs") or []
    if logs:
        lines.append("")
        lines.append("#### 相关日志")
        for row in logs[:15]:
            prefix = "[%s] " % row["time"] if row.get("time") else ""
            lines.append("- %s%s" % (prefix, row.get("text") or ""))
    return "\n".join(lines)


def summarize_issue_gaps(reports, *, limit=8):
    """Aggregate open adaptation reports across courses by (platform, code, kind) to surface top gaps."""
    groups = {}
    for report in reports or ():
        if not isinstance(report, dict) or report.get("status") != "open":
            continue
        platform = str(report.get("platform") or "")
        payload = report.get("payload") if isinstance(report.get("payload"), dict) else {}
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        if not items:
            continue
        course_key = (platform, str(report.get("course_id") or report.get("course_name") or ""))
        course_name = str(report.get("course_name") or "未知课程")
        updated = float(report.get("updated") or 0)
        hit_count = int(report.get("report_count") or 1)
        reporter_count = int(report.get("reporter_count") or 1)
        is_manual = (report.get("source") or "manual") == "manual"
        usernames = {
            str(u.get("username") or "").strip()
            for u in (report.get("reporters") or ())
            if isinstance(u, dict) and str(u.get("username") or "").strip()
        }

        seen_keys = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "job_error")
            kind = str(item.get("kind") or "")
            gap_key = "%s|%s|%s" % (platform, code, kind)
            if gap_key in seen_keys:
                continue
            seen_keys.add(gap_key)
            default_label, default_bucket = FINDING_META.get(code, ("未完成项", "failed"))
            bucket = str(item.get("bucket") or default_bucket)
            label = str(item.get("label") or default_label)
            group = groups.get(gap_key)
            if group is None:
                group = {
                    "key": gap_key,
                    "platform": platform,
                    "platform_name": PLATFORM_NAMES.get(platform, platform or "未知平台"),
                    "code": code,
                    "bucket": bucket,
                    "label": label,
                    "kind": kind,
                    "courses": set(),
                    "users": set(),
                    "max_reporter_count": 0,
                    "report_count": 0,
                    "hit_count": 0,
                    "manual_count": 0,
                    "auto_count": 0,
                    "latest": 0.0,
                    "sample_course": course_name,
                }
                groups[gap_key] = group
            group["courses"].add(course_key)
            group["users"].update(usernames)
            group["max_reporter_count"] = max(group["max_reporter_count"], reporter_count)
            group["report_count"] += 1
            group["hit_count"] += hit_count
            if is_manual:
                group["manual_count"] += 1
            else:
                group["auto_count"] += 1
            if updated >= group["latest"]:
                group["latest"] = updated
                group["sample_course"] = course_name

    summary = []
    for group in groups.values():
        user_count = max(len(group["users"]), group["max_reporter_count"])
        summary.append({
            "key": group["key"],
            "platform": group["platform"],
            "platform_name": group["platform_name"],
            "code": group["code"],
            "bucket": group["bucket"],
            "label": group["label"],
            "kind": group["kind"],
            "course_count": len(group["courses"]),
            "report_count": group["report_count"],
            "user_count": user_count,
            "hit_count": group["hit_count"],
            "manual_count": group["manual_count"],
            "auto_count": group["auto_count"],
            "latest": group["latest"],
            "sample_course": group["sample_course"],
        })
    summary.sort(key=lambda g: (-g["user_count"], -g["course_count"], -g["hit_count"], -g["latest"]))
    return summary[:limit] if limit else summary
