import random
import time
import threading
from typing import List, Dict, Any

from base.api_client import RequestRateLimited
from base.auth import AuthenticationExpired
from base.concurrency import validate_workers
from base.study import run_resources, check_study_response
from reporting import Reporter
from MoocMain.log import Logger
from ZYKMoocMain.api import ZYKMoocApi
from base.util import parse_duration, get_mp3_duration


class ZYKMoocHandler:
    def __init__(self, username: str = "", password: str = "", jump_content: str = "", token: str = None, *, client=None, course_rows=None, on_progress=None, max_workers=1, cancel_event=None):
        """初始化 API 客户端和日志"""
        self.max_workers = validate_workers(max_workers)
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self.jump_list = []
        if jump_content and '#' in jump_content:
            self.jump_list = jump_content.split('#')[1:]

        # 根据是否提供token选择不同的初始化方式
        if client is not None:
            self.client = client
        elif token:
            self.client = ZYKMoocApi(token=token)
        else:
            self.client = ZYKMoocApi(username, password)

        self.course_rows = course_rows
        self.logging = Logger(__name__).get_log()
        self.progress = Reporter(on_progress)
        try:
            self.start_courses()
        finally:
            if client is None:
                self.client.close()

    def start_courses(self) -> None:
        """获取并处理课程列表"""
        try:
            if self.course_rows is None:
                courses = self.client.my_course_list(page_size=9999)
                course_rows = courses.get("rows", [])
            else:
                course_rows = self.course_rows
            total_courses = len(course_rows)

            if not course_rows:
                self.logging.warning("当前没有课程数据")
                return
            self.progress.begin("学习管理", total_courses, "门课程")
            for course in course_rows:
                if self.cancel_event.is_set():
                    break
                course_name = course.get("courseName", "未知课程")
                self.progress.resources(f"{course_name} · 正在读取资源目录", 0)
                if any(s in course.get("courseName") for s in self.jump_list):
                    self.progress.result(course_name, "skipped")
                    continue
                self._course_failed = False
                self._course_processed = False
                self.progress.detail(course_name)
                self.process_course(course)
                status = "error" if self._course_failed else "success" if self._course_processed else "skipped"
                self.progress.result(course_name, status)

        except Exception as e:
            self.logging.error(f"获取课程失败: {e}")
            self.progress.result("读取或处理课程", "error")

    def process_course(self, course: Dict[str, Any]) -> None:
        """处理单个课程"""
        course_name = course.get("courseName", "未知课程")
        teacher = course.get("presidingTeacher", "未知教师")
        course_info_name = course.get("courseInfoName", "未知课程信息")
        study_time = course.get("studyTime", "未知")
        final_score = course.get("finalScore", "未知")
        course_info_id = course.get("courseInfoId")

        self.logging.info(
            f" 课程: {course_name} ({course_info_name}) | 教师: {teacher} |  学习时长: {study_time} | 成绩: {final_score}"
        )

        if course_info_id:
            study_design_list = self.client.study_design_list(course_info_id)
            run_resources(self, self.print_course_structure(study_design_list), course_name)
        else:
            self.logging.warning(f" 课程 {course_name} 缺少 CourseInfoId，跳过")

    def print_course_structure(self, nodes: List[Dict[str, Any]], indent: int = 0):
        """递归打印课程结构，按原顺序产出资源参数"""
        prefix = " " * (indent * 4)  # 每层缩进 4 个空格

        for node in nodes:
            name = node.get("name", "未知")
            file_type = node.get("fileType", "未知")
            self.logging.info(f"{prefix}- {name} ({file_type})")

            children = node.get("children", [])
            if children:
                yield from self.print_course_structure(children, indent + 1)
            else:
                yield (node, indent)

    def handle_resource(self, node: Dict[str, Any], indent: int = 0) -> str:
        """处理最终的资源，并保存学习记录"""
        resource_name = node.get("name", "未知资源")
        self.progress.detail(resource_name)
        file_type = node.get("fileType", "未知类型")
        student_study_record = node.get('studentStudyRecord')
        speed = (student_study_record or {}).get('speed', 0)
        prefix = " " * ((indent + 1) * 4)  # 每层缩进 4 个空格

        self.logging.info(f"{prefix}  资源: {resource_name} | 类型: {file_type} | 进度: {speed}")

        # 跳过作业
        if file_type == "作业":
            self.logging.info(f"{prefix}  跳过作业")
            return "skipped"

        # 进度已经到100的不再处理
        if speed == 100:
            self.logging.info(f"{prefix}  跳过进度: {speed}")
            return "skipped"

        try:
            # 默认学习总数1：图片
            total_num = 1
            source_id = node.get("id")
            # 获取课件信息
            course_content = self.client.course_content(source_id)
            # 不知道应该学习多久，需要调用接口并转换
            url_short = course_content.get("urlShort")
            # mp3 时长接口无法查询，本地获取
            if file_type == "mp3":
                mp3_duration = get_mp3_duration(course_content.get('fileUrl'))
                total_num = int(mp3_duration)
            if file_type == "zip":
                total_num = 1
            elif url_short:
                file_status = self.client.upload_file_status(url_short)
                file_status_args = file_status.get('args')
                # 视频类型
                file_status_args_duration = file_status_args.get('duration')
                # 文件类型
                file_status_args_has_txt_file = file_status_args.get('has_txt_file')
                if file_status_args_duration:
                    total_num = parse_duration(file_status_args_duration)
                elif file_status_args_has_txt_file:
                    total_num = file_status_args.get('page_count')

            course_info_id = node.get("courseInfoId")
            parent_id = node.get("parentId")
            study_time = total_num

            wait_time = random.randint(1, 3)

            self.logging.info(f"{prefix}  学习数: {total_num}，等待 {wait_time} 秒...")

            time.sleep(wait_time)
            if self.cancel_event.is_set():
                self._course_failed = True
                return "cancelled"
            response = self.client.study_record(course_info_id, parent_id, study_time, source_id,
                                                total_num, total_num, total_num)
            check_study_response(response, parsed=True)
            self.logging.info("学习记录已保存")
            self._course_processed = True
            return "success"
        except (AuthenticationExpired, RequestRateLimited):
            self.cancel_event.set()
            raise
        except Exception as e:
            self._course_failed = True
            self.logging.error(f"处理资源失败: {e}")
            return "error"
