# 完全离线生成对阵

对阵图决定“谁与谁打、晋级从哪里来”；日期、场序和场地交给 `schedule_engine.py`。先完成资格、并组和预留名额决策，再确认抽签。生成对阵时保持已确认签位，不重新随机抽签。

`scripts/bracket_engine.py` 支持单循环、双循环、单淘汰（含轮空、可选决 3–4 名或前 8 名完整名次赛）、分组循环后按明确交叉表晋级淘汰。四项运动共用对阵结构；计分、抽签规则和排名规则分别配置。团体赛先建立团体对阵与单场顺序，再展开已确定运动员的子赛；本引擎不把整支队伍冒充一个运动员。

## 输入及执行

从已审核的 `participant_roster.py` 名册开始时，使用 `scripts/prepare_event.py` 连接现有数据结构，无须手工重建人员身份：

```bash
python scripts/prepare_event.py prepare 名册.json 编排准备参数.json 准备目录
python scripts/draw_engine.py 准备目录/draw-input.json 抽签结果.json
python scripts/prepare_event.py attach 准备目录/draw-input.json 准备目录/bracket-base.json 抽签结果.json 对阵输入.json
```

准备参数含 `confirmed:true`、本地 `event_id`、`event_name`、预先记录的 `random_seed` 及 `projects`。每项 `id` 必须对应名册的 `projects[].key`，并明确 `sport`、`format`、`entry_size`、`unit_policy` 和该赛制的参数。例如已核实名册中项目 `MS` 的单淘汰准备项：

```json
{"id":"MS","sport":"badminton","format":"knockout","entry_size":1,
 "unit_policy":"full_unit","seed_profile":"badminton_bwf","third_place":true}
```

`full_unit` 使用报名表完整单位，双打两人的单位必须相同；跨单位组合或另有上级单位回避口径时用 `unit_policy:"entry_map"`，并提供全部真实报名项的 `club_by_entry:{"报名项ID":"已确认回避单位"}`。显式空字符串表示本次确认不对该项施加单位回避，例如复核历史签位时的个人散报；不能仅凭“个人”等名字自动清除回避。该映射只用于回避，不更改运动员原单位。预留项保持空成员、空回避单位、0 种子。

循环模式明确 `group_sizes` 和 `seed_policy:"snake"`；分组晋级另有 `advance_per_group`、`knockout_slots` 与 `third_place`。固定组/签位通过本场确认的 `fixed_entries:{"报名项ID":{"group":1,"position":3}}` 输入，不自动从原报名序号推导。非羽毛球淘汰使用明确的自定义种子位置、轮空表。`ranking`、`scoring`、`scoring_by_stage`、`duration_minutes` 可随项目进入下游。

输出 `draw-input.json`、`bracket-base.json`、`provenance.json`，保留全局人员 ID、出处、源版本、退赛排除记录和预留状态。名册或参数有改动时重新准备；`attach` 校验抽签输入哈希、事件、随机种子、项目覆盖和签位，防止混用旧版本。准备目录和最终输入文件均拒绝覆盖已有路径。此适配需 `openpyxl`（复用名册校验器），后续纯 JSON 对阵生成使用标准库。

```bash
python scripts/bracket_engine.py 对阵输入.json 离线对阵.json --xlsx 赛程审阅.xlsx
```

JSON 使用标准库；Excel 另需 `openpyxl`。输出路径须未存在，避免覆盖已审阅版本。最小输入：

```json
{
  "event_id": "LOCAL-EVENT-001", "event_name": "示例赛", "reviewed": true,
  "athletes": [{"id":"A1","name":"甲"},{"id":"A2","name":"乙"}],
  "entries": [
    {"id":"E1","project_id":"P1","member_ids":["A1"]},
    {"id":"E2","project_id":"P1","member_ids":["A2"]}
  ],
  "projects": [{"id":"P1","name":"单打","sport":"badminton",
    "entry_size":1,"format":"knockout","third_place":false}],
  "draw": {"event_id":"LOCAL-EVENT-001","projects":[{
    "project_id":"P1","format":"knockout","bracket_size":2,
    "assignments":[{"entry_id":"E1","group":1,"position":1},
                   {"entry_id":"E2","group":1,"position":2}]
  }]}
}
```

- `athletes[].id` 为全赛事统一人员身份键，兼项时复用；双打的 `entry` 有两个 `member_ids`。`entry.id` 是报名项键，不能代替运动员身份。姓名订正保持身份键；同名必须先消歧。
- `sport`：`badminton`、`table_tennis`、`tennis`、`pickleball`；`entry_size` 为 1 或 2。真实报名项须有已核实成员，未知身份预留项为 `kind:"placeholder", member_ids:[]`，必须单独标识。
- `draw.projects` 可直接采用 `draw_engine.py` 的结果，事件、项目和报名项 ID 须一致。引擎核对签位完整性，不替代种子、单位回避和资格审查。
- 单淘汰签位数为容纳参赛项的最小 2 次幂，首轮不允许双空；轮空由签位空缺产生，另记自动晋级，不生成虚假场次或比分。`third_place` 必须明确；决 3–4 名至少需四个参赛项。需要完整取前 8 名时另设 `classification_places:8`，须至少 8 个淘汰参赛项并设 `third_place:true`；增加四名八强负者的两场 5–8 名半决赛、5–6 名与 7–8 名决赛，共比含季军赛的主签表多 4 场。不得仅凭晋级数自动启用。
- `format:"round_robin"` 配合 `draw.format:"groups"` 的单个小组；组内位置从 1 连续编号。`legs` 默认为 1，可设 2；双循环第二次双方位置反转。循环“轮次”默认只是配对批次，不强制整轮打完再开下一轮；有该要求时设 `enforce_round_order:true`。
- `format:"groups_knockout"` 使用多组抽签结果，每组至少两个报名项。明确 `advance_per_group`、`third_place`，以及按淘汰签位排列的 `knockout_slots`。例如两组各出线两项：`[{"group":1,"rank":1},{"group":2,"rank":2},{"group":2,"rank":1},{"group":1,"rank":2}]`。轮空签位用 `null`；每个出线名次只能出现一次。多组成绩横向比较、附加资格赛、双败及特殊名次赛须另外建立明确赛制适配，不默认为单淘汰。
- `ranking` 将原样进入小组配置；生成对阵可以先不解排名，正式出线前须补齐排名顺序、同分比较、弃权处理，由成绩引擎执行。`duration_minutes` 可按项目指定预计单场时长。

## 输出与下游衔接

输出 `gamemaster.brackets.v1`：`projects`、`entries`、`athletes`、`groups`、`matches` 和 `automatic_advances`。每个实际场次包含：

| 字段 | 含义 |
| --- | --- |
| `id` / `code` | 稳定本地场次 ID / 显示赛号；与平台 ID 无关 |
| `project_id`, `stage`, `round`, `position` | 项目、阶段、轮次、该轮位置 |
| `sides` | `entry`、`winner`、`loser`、`group_rank` 两个来源 |
| `predecessors` | 必须结束后才能开始本场的全部前驱；小组名次依赖该小组全部场次 |
| `athletes` | 当前已确定的实际人员身份，不含虚构的待定选手 |
| `possible_athletes` | 可到达本场的已知真实人员候选全集 |
| `placement` | 明确胜负对应名次，如 1–2、3–4、5–6、7–8 |
| `platform_match_id` | 始终为空；平台适配由独立 skill 处理 |

`winner`/`loser` 用 `match_id` 引用来源；`group_rank` 用 `group_id`、`rank` 和 `match_ids`。赛果 `winner_id` 表示胜方报名项 ID，单双打均如此。小组输出含 `id`、`project_id`、`entry_ids`、`match_ids`、`expected_meetings`（单循环 1、双循环 2）和 `ranking`，可交给成绩模块统计排名和解析晋级。

把输出 `matches` 和 `outcome_disjoint_pairs` 合入已确认的编排配置，即可调用 `schedule_engine.py`。不得删除依赖以压缩场序。`known` 模式只保证已确定人员无冲突；`possible` 模式保守检查已知候选。预留项尚未填入身份时，两种模式都不能保证替换后的跨项目安全，替换或出线确认后须再次检查休息和冲突。

决赛与季军赛，以及 5–6 名与 7–8 名决赛可并行，仅在各自两条半决赛人员来源互不相交、胜负支路明确时输出 `outcome_disjoint_pairs`。多名小组出线者候选集合可能重叠，未经证明不自动豁免。

ID 基于事件、项目、对阵结构摘要、阶段和位置的 UUID5：重复运行稳定，改变签位或赛制会更换 ID，避免错误继承旧赛果；文字订正不改变 ID。预留替换维持报名项 ID 可保留签位，仍须复核资格和编排。

抽签完成后替补或改搭档，应将已确认的所有组号/签位作为`fixed_entries`带入新准备参数，并刷新人员候选及兼项检查。只沿用随机种子后重新运行抽签不能保证原签位不变，因为输入姓名等字段参与随机摘要。有既有赛果时先按[成绩处理](results.md)保存成员绑定，不能把同一报名项ID当作成员未变的证据。

Excel 默认保留熟悉的 17 列顺序，平台项目 ID、场次 ID、原赛号为空；另附本地 ID 与依赖表。该文件用于离线审阅，不声称可上传某一平台。若指定其它模板，根据同一 JSON 映射后复读核对，不在表格中手改依赖关系。
