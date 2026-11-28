"""Declarative learning-unit rules for ICVE MOOC / AI 优课.

Add a new entry to MOOC_UNIT_RULES when an issue report reveals a new fileType:
- action="answered": handled on the 答题 tab; hidden from the study grid, silently skipped during study.
- action="unsupported": cannot be completed automatically; shown as skipped and recorded in post-task checks.
- action="study": completed via study_record using `strategy` ("audio" | "instant" | "metadata").
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass

from core.util import get_mp3_duration, parse_duration


@dataclass(frozen=True)
class MoocUnitRule:
    action: str          # "answered" | "unsupported" | "study"
    strategy: str = ""   # "audio" | "instant" | "metadata" | "fallback"
    label: str = ""
    known: bool = True


_ANSWERED = MoocUnitRule(action="answered", label="作业/测验/考试（在答题页处理）")
_UNEXPANDABLE = MoocUnitRule(action="unsupported", label="该节点类型暂无法展开或自动完成")
_AUDIO = MoocUnitRule(action="study", strategy="audio", label="音频资源")
_INSTANT = MoocUnitRule(action="study", strategy="instant", label="即时浏览资源")
_METADATA = MoocUnitRule(action="study", strategy="metadata", label="音视频/文档资源")

EMPTY_TYPE_RULE = MoocUnitRule(action="study", strategy="metadata", label="默认资源")
FALLBACK_RULE = MoocUnitRule(
    action="study",
    strategy="fallback",
    label="未在已知学习单元类型列表中，按默认规则尝试处理",
    known=False,
)

# Keys are normalized to lowercase (Chinese names are unaffected).
MOOC_UNIT_RULES = {
    # 答题类（归答题页处理，不计入学习异常）
    "作业": _ANSWERED,
    "考试": _ANSWERED,
    "测验": _ANSWERED,
    # 明确无法展开/暂不支持的节点
    "子节点": _UNEXPANDABLE,
    "文件夹": _UNEXPANDABLE,
    # 音频（需要读取音频时长）
    "audio": _AUDIO,
    "mp3": _AUDIO,
    "音频": _AUDIO,
    # 即时浏览类（固定/随机浏览计数即可）
    "ppt": _INSTANT,
    "img": _INSTANT,
    "图文": _INSTANT,
    # 依赖 fileUrl 元数据（时长/页数）或默认计数的常规资源
    "video": _METADATA,
    "mp4": _METADATA,
    "视频": _METADATA,
    "pptx": _METADATA,
    "image": _METADATA,
    "图片": _METADATA,
    "pdf": _METADATA,
    "doc": _METADATA,
    "docx": _METADATA,
    "xls": _METADATA,
    "xlsx": _METADATA,
    "txt": _METADATA,
    "document": _METADATA,
    "文档": _METADATA,
    "swf": _METADATA,
    "link": _METADATA,
    "网页": _METADATA,
    "演示文稿": _METADATA,
    "office": _METADATA,
}


def resolve_mooc_rule(file_type) -> MoocUnitRule:
    """Resolve one MOOC node's fileType to its declarative learning rule."""
    raw = str(file_type or "").strip()
    if not raw or raw == "未知类型":
        return EMPTY_TYPE_RULE
    rule = MOOC_UNIT_RULES.get(raw) or MOOC_UNIT_RULES.get(raw.lower())
    return rule if rule is not None else FALLBACK_RULE


def types_for_action(action: str):
    return tuple(k for k, rule in MOOC_UNIT_RULES.items() if rule.action == action)


def known_file_types():
    return set(MOOC_UNIT_RULES.keys())


def compute_study_total(
    rule: MoocUnitRule,
    node: dict,
    *,
    rng=None,
    mp3_duration=get_mp3_duration,
    duration_parser=parse_duration,
) -> int:
    """Compute the platform study totalNum/studyDuration for a MOOC node according to its rule."""
    chooser = rng or random
    total_num = chooser.randint(1, 10)
    raw_content = node.get("fileUrl", "")
    course_content = None
    url_short = None
    if isinstance(raw_content, str) and raw_content.strip():
        course_content = json.loads(raw_content)
        if isinstance(course_content, dict):
            url_short = course_content.get("url")
    elif isinstance(raw_content, dict):
        course_content = raw_content
        url_short = course_content.get("url")

    if rule.strategy == "instant":
        return total_num

    if rule.strategy == "audio" and isinstance(course_content, dict) and course_content.get("ossOriUrl"):
        return int(mp3_duration(course_content.get("ossOriUrl")))

    if url_short and isinstance(course_content, dict):
        duration = course_content.get("duration")
        has_txt = course_content.get("has_txt_file")
        if duration:
            return duration_parser(duration)
        if has_txt:
            return course_content.get("page_count")
    return total_num
