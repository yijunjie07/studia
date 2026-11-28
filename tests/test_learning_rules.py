import json
import random
import unittest
from unittest.mock import Mock, patch

from mooc.main import AIMoocHandler, course_units as mooc_course_units
from mooc.rules import MOOC_UNIT_RULES, MoocUnitRule, compute_study_total, resolve_mooc_rule
from zhs.api import SCORE_SHARES, course_offers
from zhs.main import ZHSHandler, course_units as zhs_course_units
from zhs.rules import (
    ZHS_AI_RESOURCE_RULES,
    ZHS_ASSESSMENT_RULES,
    ZhsAiResourceRule,
    assessment_schema,
    resolve_zhs_ai_rule,
    resolve_zhs_course_rule,
    uncovered_assessment_shares,
)


class MoocRulesTest(unittest.TestCase):
    def test_resolve_mooc_rule_classifies_known_and_unknown_types_case_insensitively(self):
        self.assertEqual(resolve_mooc_rule("作业").action, "answered")
        self.assertEqual(resolve_mooc_rule("文件夹").action, "unsupported")
        self.assertEqual(resolve_mooc_rule("audio").strategy, "audio")
        self.assertEqual(resolve_mooc_rule("PPT").strategy, "instant")
        self.assertEqual(resolve_mooc_rule("VIDEO").strategy, "metadata")
        self.assertEqual(resolve_mooc_rule("pdf").strategy, "metadata")

        unknown = resolve_mooc_rule("vr_lab")
        self.assertEqual(unknown.action, "study")
        self.assertEqual(unknown.strategy, "fallback")
        self.assertFalse(unknown.known)

    def test_compute_study_total_handles_audio_video_doc_instant_and_fallback(self):
        rng = random.Random(0)
        audio_node = {"fileType": "audio", "fileUrl": json.dumps({"ossOriUrl": "https://x/a.mp3"})}
        self.assertEqual(
            compute_study_total(resolve_mooc_rule("audio"), audio_node, rng=rng, mp3_duration=lambda u: 125.8),
            125,
        )

        video_node = {"fileType": "video", "fileUrl": json.dumps({"url": "short", "duration": "00:02:30"})}
        self.assertEqual(compute_study_total(resolve_mooc_rule("video"), video_node, rng=rng), 150)

        doc_node = {"fileType": "pdf", "fileUrl": json.dumps({"url": "short", "has_txt_file": True, "page_count": 18})}
        self.assertEqual(compute_study_total(resolve_mooc_rule("pdf"), doc_node, rng=rng), 18)

        ppt_node = {"fileType": "ppt", "fileUrl": json.dumps({"url": "short", "duration": "00:10:00"})}
        total = compute_study_total(resolve_mooc_rule("ppt"), ppt_node, rng=rng)
        self.assertGreaterEqual(total, 1)
        self.assertLessEqual(total, 10)

    def test_adding_unsupported_rule_in_table_drives_both_grid_and_handler(self):
        custom = {"custom_lab": MoocUnitRule(action="unsupported", label="暂不支持的仿真实验")}
        client = Mock()
        client.study_design_list.return_value = [{"id": "ch1", "name": "第一章"}]
        client.study_record_list.return_value = []
        client.get_cell_list.return_value = [
            {"id": "u1", "name": "仿真实验", "fileType": "custom_lab", "courseId": "c1", "courseInfoId": "ci1"}
        ]
        course = {"id": "ci1", "courseId": "c1", "courseName": "实验课", "studySpeed": 0}

        with patch.dict(MOOC_UNIT_RULES, custom), patch("mooc.main.time.sleep", return_value=None):
            chapters = mooc_course_units(client, course)
            self.assertEqual(chapters[0]["units"][0]["state"], "skipped")
            AIMoocHandler(client=client, course_rows=[course], max_workers=1)

        client.study_record.assert_not_called()


class ZhsRulesTest(unittest.TestCase):
    def test_resolve_zhs_ai_rule_and_course_rule(self):
        self.assertEqual(resolve_zhs_ai_rule({"resourcesType": 1, "resourcesDistributeType": 3}, {}).action, "play_video")
        self.assertEqual(resolve_zhs_ai_rule({"resourcesType": 2, "resourcesDistributeType": 2}, {}).action, "play_video")
        doc_rule = resolve_zhs_ai_rule({"resourcesType": 3, "resourcesDistributeType": 1}, {})
        self.assertEqual((doc_rule.action, doc_rule.unit_kind, doc_rule.known), ("complete", "doc", True))
        unknown_rule = resolve_zhs_ai_rule({"resourcesType": 99, "resourcesDistributeType": 88}, {})
        self.assertEqual((unknown_rule.action, unknown_rule.known), ("complete", False))

        self.assertEqual(resolve_zhs_course_rule("shared").study_method, "study_shared")
        self.assertEqual(resolve_zhs_course_rule("shared").review_method, "review_shared")
        self.assertEqual(resolve_zhs_course_rule("ai").study_method, "study_ai")
        self.assertIsNone(resolve_zhs_course_rule("ai").review_method)
        self.assertIsNone(resolve_zhs_course_rule("flipped"))

    def test_adding_unsupported_zhs_ai_rule_skips_resource_and_records_finding(self):
        custom = {(8, 9): ZhsAiResourceRule(action="unsupported", unit_kind="unsupported", label="互动实验暂不支持")}
        client = Mock()
        client.ai_course_basic.return_value = {
            "cakeThemeList": [{"knowledgeList": [{"knowledgeId": 10, "knowledgeName": "知识点1"}]}]
        }
        item = {
            "studyStatus": 0,
            "resourcesDetail": {
                "resourcesUid": "u89",
                "resourcesName": "AI 互动实验",
                "resourcesType": 8,
                "resourcesDistributeType": 9,
            },
        }
        client.ai_resources.return_value = [item]
        row = {"courseName": "智慧实验课", "studySpeed": 10, "zhs": {"kind": "ai", "courseId": 1, "classId": 2}}

        with patch.dict(ZHS_AI_RESOURCE_RULES, custom):
            chapters = zhs_course_units(client, row)
            self.assertEqual(chapters[0]["units"][0]["state"], "skipped")
            ZHSHandler(client=client, course_rows=[row], sleep=lambda _s: None)

        client.ai_complete.assert_not_called()
        client.ai_report.assert_not_called()

    def test_assessment_rules_power_score_shares_offers_and_uncovered_list(self):
        self.assertEqual(SCORE_SHARES, tuple((r.key, r.api_field) for r in ZHS_ASSESSMENT_RULES))
        shares = {"progress": 30, "habit": 10, "interactive": 0, "knowledge": 15, "test": 10, "meet": 10, "final": 25}
        self.assertEqual(
            uncovered_assessment_shares(shares),
            [
                {"key": "knowledge", "label": "掌握度", "share": 15},
                {"key": "meet", "label": "见面课", "share": 10},
            ],
        )
        self.assertEqual(
            course_offers({"zhs": {"kind": "shared"}}, shares),
            {"review": True, "qa": False},
        )
        schema = assessment_schema()
        self.assertEqual([item["key"] for item in schema], [r.key for r in ZHS_ASSESSMENT_RULES])


if __name__ == "__main__":
    unittest.main()
