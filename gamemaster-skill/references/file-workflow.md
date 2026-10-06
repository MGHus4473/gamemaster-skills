# 文件输入、输出与平台交接

赛事原件、标准数据、输出和验证报告分别放用户指定赛事目录，不放skill本体。保存来源、版本和修改依据；文件名包含用途和版本，同一输入重算可复现，不覆盖旧确认稿。

## 输入与标准数据

表格优先直接读取单元格和合并结构，Word/PDF优先提取文字；图片或扫描页逐页识别，保留页/行来源，不猜模糊姓名和搭档关系。`xlsx/xls/csv`使用对应读写库，不改后缀伪装；公式值缺缓存须在本地办公软件重算，不把空缓存当零。用户自带模板先识别说明区、填写区、公式、打印范围及宏等特性，选择能保真的本地工具。

标准数据按业务层传递，不把不同层的字段强行混用：

| 层 | 关键数据及工具 |
|---|---|
| 名单 | `projects[].key`、`entries[].project/members`；`participant_roster.py`校验增补和输出 |
| 报名调整 | `registration_transition.py`输出独立`roster/ledger/summary`，原报名保留 |
| 方案 | 原21列格式见模板参考；复杂计分用扩展方案及完整`rules` |
| 抽签 | `draw_engine.py`项目ID和报名项ID，显式运动及种子/轮空，保存输入哈希 |
| 对阵 | `bracket_engine.py`：人员`athletes`、报名项`member_ids`、比赛`sides/predecessors` |
| 编排 | 对阵`matches`＋场地时段/休息→`schedule_engine.py`；不重抽签 |
| 成绩 | 同一对阵结构＋明确计分/排名规则＋真实赛果→`results_engine.py` |

姓名更正保持运动员ID；预留替换保持报名项ID，但挂接真实人员。源记录ID与平台ID分别保存。字段映射时核对项目与报名项全集、成员数量及未知预留，不能以数组下标或姓名充当可靠身份。

用`prepare_event.py`将已有标准名册和明确项目设置连接到抽签/对阵层，避免每次重新建立身份映射。设置涵盖运动、单/双打、赛制、单位回避、种子轮空、分组和交叉；具体契约见 [比赛结构](brackets.md)。

## 本地输出

所有命令在skill根目录执行，文件路径按实际赛事目录给出：

```bash
python scripts/participant_roster.py export 名单.json 名单.xlsx
python scripts/prepare_event.py prepare 名单.json 项目设置.json 准备输出目录
python scripts/export_competition_plan.py 方案21列.json 方案.xlsx
python scripts/export_event_tables.py plan 扩展方案.json 扩展方案.xlsx
python scripts/draw_engine.py 抽签输入.json 抽签结果.json
python scripts/export_event_tables.py draw 抽签输入.json 抽签结果.json 签表.xlsx
python scripts/prepare_event.py attach 准备输出目录/draw-input.json 准备输出目录/bracket-base.json 抽签结果.json 对阵输入.json
python scripts/bracket_engine.py 对阵输入.json 对阵.json --xlsx 场次.xlsx
python scripts/schedule_engine.py 编排输入.json 编排结果.json
python scripts/export_event_tables.py schedule 编排输入.json 编排结果.json 编排.xlsx
```

抽签表沿用20列签位字段；编排表保留“日期/时间/场序/第N号场地”网格，另有场次明细与核验；场次审阅沿用17列。每个本地文件明确使用本地ID，平台字段留空或另存，不要求在线分配ID。默认模板来源相同不表示这些离线文件都能直接导入平台。

扩展方案输入`confirmed:true, rows:[...]`。每行沿用 [21列字段](competition-plan-template.md)，增加`sport`和`rules`（使用 [成绩规则结构](results.md) 的计分对象）；单/双项目、常规一/二阶段。循环提供`group_sizes`；二阶段明确前组数及从1到出线名次。点分项目局数/目标分/封顶从rules填写，未封顶留空；网球这三个简化字段留空，完整盘/局/抢七规则在“运动规则”表。该扩展表不作为原平台导入表，规则和附加信息不能为凑列而丢弃。

成绩输出、未赛状态和裁定见 [成绩处理](results.md)；文稿多格式输出见 [文档输出](regulation-output.md)。表格中的姓名、单位等文字强制为文本，避免`=`开头内容被当公式；身份证和手机保留文本前导零。重新打开输出核对行数、类型、关键数值、阶段关系及模板样式。

## 两个skill的交接

`gamemaster-skill`输出文件与`handoff.json`；`ptty-skill`核对目标、模板和映射后执行用户要求的线上操作，再将回执和真实平台ID返回。离线任务不需要交接文件，也不要求安装ptty。

```bash
python scripts/handoff.py 交接说明.json 交接目录/handoff.json
```

交接说明最小结构：

```json
{
  "event":{"local_id":"LOCAL-001","name":"示例赛","sport":"badminton"},
  "input_version":"报名v2/方案v1", "rules_version":"本场确认规程v1",
  "artifacts":[{"kind":"roster","path":"名单.json"},{"kind":"schedule","path":"编排.xlsx"}],
  "mapping":{"event_id":"","project_ids":{},"entry_ids":{},"match_ids":{}}
}
```

文件先放交接目录；path相对`handoff.json`所在目录，不能为绝对路径、上级路径或越界链接。脚本写入`schema_version:1`和每个文件的SHA256，两个skill都校验哈希；修改文件后创建新版本交接包。`mapping`键是本地ID、值是真实平台ID，未知时保持空映射；未绑定赛事时event_id为空串。不通过本地UUID伪造平台内部ID。

交接内容只含本次需要的数据，不包含会话、登录口令、令牌或浏览器用户目录。模板填充、平台导入与实际创建比赛分别验收；回执成功必须结合人数/签位/前驱/日期场地回读。
