# 附件作业的目录类型

2026-10-10 静态读取官网公开网页和 JavaScript；未登录，未读取账号配置，未调用任何真实作业、考试或测验接口。

## 一手来源

- [智慧学习中心首页](https://ai.icve.com.cn/) 当前引用构建号 `1791603407155`。
- [官网作业列表及共享 SjCard 组件](https://ai.icve.com.cn/js/chunk-c13dfc0a.1791603407155.js)。读取内容 SHA-256：`678beebfeb6b65b1e8239e3d42117fe3d16715b5ae086869239455408b983ff7`。构建更新后此链接可能失效，仓库不存储第三方完整压缩脚本。

## 核实结果

同一脚本的列表请求为 GET `/course/exam/record/getExamListByStudent`，`getData` 把响应 `t.rows` 直接赋给 `e.sjlist`。列表传给共享 `SjCard` 渲染，因此分类字段已存在于目录项，不需要进入试卷或请求详情。

共享卡片标题后的渲染条件与文字如下（仅摘录判断表达式）：

| 字段条件 | 官网标签 | 分类含义 |
| --- | --- | --- |
| `1==n.typeId` | `题库` + 路由标题 | 题库作业、考试或测验 |
| `3==n.typeId` | `附件作业` | 本次要识别和禁选的附件任务 |
| `4==n.typeId` | `数字教材` + 路由标题 | 不属于本次附件类型 |
| `3==n.questionSettingMethod` | `文档试卷` | 独立字段，不等于附件作业 |

`typeId=3` 的标签判断没有 `categoryId` 限制。脚本里的列表查询另外按路由标题选择 `categoryId`：作业为 1，考试为 2，其余为 3。故 `typeId` 与 `categoryId` 不能混用，即使任务来自其他目录分类也不能忽略明确的附件类型。

JavaScript 使用宽松比较 `3==n.typeId`，数值 `3` 与字符串 `"3"` 均符合。Python 分类函数接受这两种常见目录编码；缺字段、未知枚举及任务名称包含“附件”均不自行推断为附件作业。`questionSettingMethod=3` 也不单独触发附件判定。

## 实现边界

`task_capabilities.is_attachment_task(item, category)` 只读取目录项；`task_type_label` 为附件返回“附件作业”，普通任务沿用作业、考试、测验分类。选择器、AI 执行及导出入口须在进入试卷前利用该能力判断阻止附件任务，并在列表显示“暂不支持”。

GET `/course/exam/paper` 可能创建作答记录并启动考试，不能作为分类探测请求；此次调查没有调用它，也没有验证真实附件提交协议。现有副作用说明见 [考试协议](../EXAM_PROTOCOL.md)。
