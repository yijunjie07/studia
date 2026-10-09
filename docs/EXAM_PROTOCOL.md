# 新版考试接口核对记录

核对日期：2026-10-10。以下是静态阅读公开网页资源得到的协议记录，不代表真实账号端到端验证。

## 来源

- 上游 PR #198，提交 `a276abd0627f44bc433a4b8d8bc74dc1e44c09ac`，提供列表、试卷与历史记录接口及导出逻辑。
- [平台答题页面脚本](https://ai.icve.com.cn/js/chunk-01472d86.1791543916907.js)：`getData`、`submitData`、`updateExamTime_Met`。
- [平台题型组件](https://ai.icve.com.cn/js/chunk-32fe7516.1791543916907.js)：选项 `SortOrder` 和判断题 `1/0` 的含义。
- [平台请求拦截器](https://ai.icve.com.cn/app~970f9218.1791543916907.js)：`/course/exam/record` 请求体编码。
- [平台 API 模块](https://ai.icve.com.cn/js/app~06837ae4.1791543916907.js)：交卷 POST 方法。

网页构建更新后这些资源地址可能失效。没有把第三方压缩脚本或账号数据复制进仓库。

## 请求

基础地址：`https://ai.icve.com.cn/prod-api`，授权使用当前账号 Bearer token。

| 操作 | 方法与路径 |
| --- | --- |
| 列表 | GET `/course/exam/record/getExamListByStudent` |
| 当前账号历史记录 | GET `/course/exam/record/getStudentRecordByExamId` |
| 进入试卷 | GET `/course/exam/paper?id=...&groupId=0` |
| 上报真实作答时间 | POST `/course/exam/record/updateExamTime` |
| 提交整份试卷 | POST `/course/exam/record` |

进入试卷可能创建草稿并启动倒计时，不能视为无副作用查询。程序先查本账号作答历史，存在已交卷/批阅中/未知状态时跳过。

2026-10-10 的实际读取确认：试卷接口可以直接返回含 `questions`、`taskExamRecord` 的对象，没有 `code/data` 外层。仅 GET 试卷接口接受这种经过结构校验的响应；显式错误码和提交接口仍必须严格校验，不能把缺少 `code` 一律当成功。

网页交卷载荷包含 `courseId`、`courseInfoId`、`examId`、`examName`、`device=1`、`categoryId`、`examTime`、`groupId=0`、`isLast=true`、`id=taskExamRecord.id`、`taskExamProblemRecordList`。

每条答案使用 `questionNo`、`paperId`、`answer`；子题另有 `paperSubId`，`questionNo` 是父子零基索引数组的 JSON 字符串。选择题还携带原始选项 JSON `optionSort`。单选答案是原始 `SortOrder`，多选用逗号连接；判断题正确为 `1`、错误为 `0`；填空为字符串数组的 JSON。

请求体不是普通 JSON：网页采用 `btoa(encodeURIComponent(JSON.stringify(payload)))`，Content-Type 为 `application/json;charset=UTF-8`。Python 实现必须匹配 encodeURIComponent 保留字符集。

没有假设 `isLast=false` 就是可靠的远端草稿接口。本项目“保存”指本地检查点与答案报告；自动交卷一次性发送完整答案。

## 结果和失败

HTTP 成功且业务 `code=200` 后，另查同一 task ID 的作答记录，只有 `status=2` 才标记 `submitted`。查询可短暂重试，交卷 POST 不自动重试。

提交前写入 `submitting` 检查点；超时、异常、进程中断或未确认状态均阻止下次自动重交。文件路径按账号、课程和任务隔离。平台状态与本地锁共同防止重复运行；不保证跨电脑实例的并发互斥。

`AttemptClock` 在真实经过 10 秒后才上报这段时间。它不会按目标时长高速累加，也不尝试跳过服务器最低作答时间或其他提交限制。有限时试卷在本地已用尽剩余时间后停止写入。

## 尚未验证

- 用户自选服务的实际模型可用性与答案质量。
- 当前账号各题型的真实交卷结果和平台时间限制。
- 附件题、音频/图片/公式、匹配题、完形填空等非支持题型。
- 未公开或变化后的平台响应结构。未知结构会停止处理，不当作空列表或提交成功。
