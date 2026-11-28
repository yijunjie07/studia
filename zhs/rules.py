"""Declarative course, resource and assessment rules for Zhihuishu (智慧树).

Single source of truth shared by study runners, unit grids, API scoring and post-task checks:
- ZHS_ASSESSMENT_RULES: which score items Studia can automate vs manual-only (见面课, 掌握度).
- ZHS_AI_RESOURCE_RULES: (resourcesType, resourcesDistributeType) -> action ("play_video" | "complete" | "unsupported").
- ZHS_COURSE_RULES: course kind ("shared" | "ai") -> study/review runner dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- 考核分项能力表

@dataclass(frozen=True)
class AssessmentItemRule:
    key: str
    api_field: str
    label: str
    auto: bool
    feature: str = ""


# 按智慧树成绩分析页的顺序排列。
ZHS_ASSESSMENT_RULES = (
    AssessmentItemRule("progress", "progressScoreShare", "学习", True),
    AssessmentItemRule("habit", "learnedHabitScoreShare", "习惯", True, feature="review"),
    AssessmentItemRule("interactive", "learnedInteractiveScoreShare", "互动", True, feature="qa"),
    AssessmentItemRule("knowledge", "learnedKnowledgeScoreShare", "掌握度", False),
    AssessmentItemRule("test", "examScoreShare", "测试", True),
    AssessmentItemRule("meet", "meetCourseScoreShare", "见面课", False),
    AssessmentItemRule("final", "finalExamScoreShare", "期末", True),
)


def assessment_schema():
    """Serializable schema of Zhihuishu assessment items and whether Studia covers each."""
    return [{"key": r.key, "label": r.label, "auto": r.auto} for r in ZHS_ASSESSMENT_RULES]


def uncovered_assessment_shares(shares):
    """Return positive-weight assessment items that Studia cannot earn automatically."""
    if not isinstance(shares, dict):
        return []
    uncovered = []
    for rule in ZHS_ASSESSMENT_RULES:
        if rule.auto:
            continue
        weight = shares.get(rule.key)
        if isinstance(weight, (int, float)) and not isinstance(weight, bool) and weight > 0:
            uncovered.append({"key": rule.key, "label": rule.label, "share": weight})
    return uncovered


# ---------------------------------------------------------------- 智慧课程资源规则表

@dataclass(frozen=True)
class ZhsAiResourceRule:
    action: str          # "play_video" | "complete" | "unsupported"
    unit_kind: str       # "video" | "doc" | "unsupported"
    label: str = ""
    known: bool = True


_AI_VIDEO = ZhsAiResourceRule(action="play_video", unit_kind="video", label="智慧课程视频")
_AI_DOC = ZhsAiResourceRule(action="complete", unit_kind="doc", label="智慧课程文档")

ZHS_AI_FALLBACK_RULE = ZhsAiResourceRule(
    action="complete",
    unit_kind="doc",
    label="未登记资源类型（尝试直接完成）",
    known=False,
)

# (resourcesType, resourcesDistributeType) -> rule
ZHS_AI_RESOURCE_RULES = {
    (1, 3): _AI_VIDEO,
    (2, 2): _AI_VIDEO,
    (3, 1): _AI_DOC,
}


def ai_resource_pair(detail, item):
    detail = detail if isinstance(detail, dict) else {}
    item = item if isinstance(item, dict) else {}
    return (
        _to_int(detail.get("resourcesType", item.get("resourcesType"))),
        _to_int(detail.get("resourcesDistributeType", item.get("resourcesDistributeType"))),
    )


def resolve_zhs_ai_rule(detail, item) -> ZhsAiResourceRule:
    """Resolve one 智慧课程 resource's (resourcesType, resourcesDistributeType) pair to a rule."""
    return ZHS_AI_RESOURCE_RULES.get(ai_resource_pair(detail, item), ZHS_AI_FALLBACK_RULE)


# ---------------------------------------------------------------- 课型分发注册表

@dataclass(frozen=True)
class ZhsCourseRule:
    kind: str
    label: str
    study_method: str
    review_method: Optional[str] = None


ZHS_COURSE_RULES = {
    "shared": ZhsCourseRule("shared", "共享课", "study_shared", "review_shared"),
    "ai": ZhsCourseRule("ai", "智慧课程", "study_ai", None),
}


def resolve_zhs_course_rule(kind) -> Optional[ZhsCourseRule]:
    """Look up the study/review runner dispatch rule for a Zhihuishu course kind."""
    return ZHS_COURSE_RULES.get(str(kind or ""))
