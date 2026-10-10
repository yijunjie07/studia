"""Task capabilities derived from the platform's catalog type, without API calls."""


def is_attachment_task(item, category):
    """The shared platform task card labels typeId=3 as attachment homework.

    This enum is independent of categoryId and questionSettingMethod; see
    docs/research/2026-10-10-attachment-homework.md for the public source.
    Unknown types retain existing behavior instead of guessing from names.
    """
    return item.get("typeId") in (3, "3")


def task_type_label(item, category):
    """Preserve ordinary category labels while identifying attachment tasks."""
    if is_attachment_task(item, category):
        return "附件作业"
    return {1: "作业", 2: "考试", 3: "测验"}.get(category, str(category))
