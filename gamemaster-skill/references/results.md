# 离线成绩、排名与导出

输入是已核对的对阵图、赛事规则和逐场赛果。执行 `scripts/results_engine.py`，无需赛事平台；JSON/CSV 仅用 Python 标准库，Excel 需 `openpyxl`。默认排名表沿用现有表格列：循环“组号、名次、队名、姓名、备注”，淘汰“名次、队名、姓名、备注”。逐场明细与完整比分另表保存。成绩是可核验的静态快照，修改赛果后重算并导出新版本。

## 工作流程

1. 核对赛事、项目、阶段、场次 ID 与甲乙方向。接收记分表、Excel、图片、文字时，保留原文件/单元格来源；OCR 不确定的比分与同名身份先核实。
2. 逐项目确认计分、局盘制、循环同分顺序、弃权/退赛处理、名次赛及并列名次。使用 [sport-rules.md](sport-rules.md) 的已标明版本摘要，赛事自己的补充通知另行记录。
3. 将比分录入 `results`，保留局/盘/抢七结构和身份 ID。引擎检查终局是否合法、是否多打一局、胜方是否相符、前驱胜负/组内排名是否已经确定。
4. 输出循环排名和由明确名次赛得到的淘汰名次。未赛不能产生冠军；未确定的同分不能按姓名、报名顺序或 ID 强行排序。
5. 更正赛果时保存原值、原因、裁判依据和版本；重新计算所有后继、名次与已发布清单。后继旧赛果如与新晋级者不一致会报错，应保留历史并按实际裁定重录。
6. 输出 Excel、CSV、JSON，必要时用现有文档工具制作成绩公告、奖状名单或闭幕式获奖信息。用户模板优先，不能丢弃 ID 与完整比分；缺字段另附明细。

## 输入契约

直接沿用 `bracket_engine.py` 的 `projects / entries / athletes / groups / matches`。项目必须补 `scoring`；循环组必须补 `ranking`；赛果置于同一 JSON 的 `results`。项目、报名项、运动员、场次是不同 ID；双打的胜方是报名项 ID，不是两名运动员中任一人的 ID。

同项目不同阶段的局分制可用项目 `scoring_by_stage:{"1":{完整规则},"2":{完整规则}}`；场次独立变式用 `match.scoring`。优先级为场次、阶段、项目，均须填完整规则。实际选用的规则随该场成绩保存。

```json
{
  "projects": [{"id":"MS","sport":"badminton","scoring":{
    "mode":"points","best_of":3,"target":21,"win_by":2,"cap":30
  }}],
  "matches": [{"id":"F","project_id":"MS","sides":[
    {"kind":"winner","match_id":"SF1"},
    {"kind":"winner","match_id":"SF2"}
  ],"placement":{"winner":1,"loser":2}}],
  "results": [{"match_id":"F","status":"completed","winner_id":"E1",
    "score":{"games":[[21,19],[19,21],[30,29]]}}]
}
```

示例省略了报名项和前驱；运行输入需完整图。`sides.kind` 支持 `entry`、`winner`、`loser`、`group_rank`；组名次来源使用 `group_id / rank`。轮空是直接晋级，不建虚假已赛场次。`predecessors` 中的显式前置场次同样必须完结。

| 状态 | 录入方式 | 名次与统计 |
|---|---|---|
| `pending` | 不填终局比分、胜方 | 未赛，无晋级结论 |
| `completed` | 完整 `score`、`winner_id` | 两者必须一致 |
| `walkover` | 胜方、`reason`；`score` 留空 | 确有裁定分时另填 `awarded_score` 与 `awarded_score_reference`，不能当作实际对局 |
| `retired` | 胜方、原因；可附已完成局盘及 `partial_game` / `partial_set` | 保留实得分，不自动补成标准负分 |
| `cancelled` | 原因；不填胜方 | 阻断依赖它的名次与后继 |

未填充的预留名额不能取得赛果。退赛不等于整组除名；整组成绩作废需在该组 `excluded_entries` 中按 ID 填写裁定理由，引擎统一移除与其有关的组内结果，不把剩余比赛编造成弃权胜。

如果明确除名后有效组内排名已经完成，`group_rank` 后继允许略过该来源组中涉及被除名项的作废前驱，并在成绩里记录 `waived_predecessors` 及裁定理由。此例外只处理组名次出线：一般取消场次、其他组或直接 `winner / loser` 来源不能借此放行。现场排期仍按修订后的对阵图处理，不把作废场次标成已实际完赛。

## 比分结构

- 积分型项目：`{"mode":"points","best_of":3,"target":21,"win_by":2,"cap":30}`；分数均为非负整数，`cap:null` 表示无封顶。每局用 `[甲,乙]`。赛事指定 31 分一局等变式须显式覆盖，不根据项目名自动推断。
- 网球：`{"mode":"tennis","best_of":3,"games_to_win":6,"set_win_by":2,"tiebreak_at":6,"tiebreak_target":7,"match_tiebreak_target":10}`。无抢七的长盘用 `tiebreak_at:null`；决胜盘可另设 `final_tiebreak_at / final_tiebreak_target`；抢十替代决胜盘用 `match_tiebreak_target`，两种决胜方式不要混用。
- 网球赛果：`{"sets":[{"games":[6,4]},{"games":[6,7],"tiebreak":[5,7]},{"match_tiebreak":[10,7]}]}`。`7:6` 必须有相符抢七分。退赛的未完成盘另填 `partial_set`，不能混进已完盘列表。
- 团体：仅校验明确的队际胜负与盘数，例 `{"mode":"team","win_target":3,"play_all":false}`、`{"rubbers":[3,2]}`；若全打须设 `play_all:true / rubber_count`。阵容资格、兼项与团体各盘编排由明确的队员表及子场次另验；脚本不自动编造阵容或从队名推出运动员。

最终比分校验不能替代逐球执裁：网球发球、抢七发球顺序、匹克球侧出/每球得分、让分起始值等保留在赛事规则及记分记录中。

已确认的每局起始让分可在该场 `scoring` 加 `initial_points:[0,6]`，方向与实际甲乙对应；两方的终局/未完局分均不得低于起始分，起始状态也不能已经获胜。此配置同一场每局一致。根据双方已解析的性别、年龄等类别从已确认矩阵取值，再明确绑定到场次；不从项目名称猜测，也不把性别和年龄让分通用相加。逐局不同让分、扣分裁罚等另行建模，不能强套此单一起始值。

## 循环同分规则

每组有 `entry_ids / match_ids / expected_meetings`（单循环 1、双循环 2）。缺少一对对阵或重复场次时拒绝排名；仍未赛时名次留空。

```json
{"ranking":{
  "criteria":[
    {"metric":"wins","scope":"all"},
    {"metric":"game_diff","scope":"tied"},
    {"metric":"point_diff","scope":"tied"}
  ],
  "restart_after_split":true,
  "abnormal_results":"adjudicate"
}}
```

上述只是配置语法，不是通用官方顺序。`scope:all` 使用全组，`scope:tied` 仅使用当前同分子集的互赛；拆出部分名次后是否从首条重新比较由 `restart_after_split` 决定。指标支持胜次 `wins`、场积分 `match_points`、净胜局/分 `game_diff / point_diff`、胜负局/分比率 `game_ratio / point_ratio`。比率用精确分数；正数/0 大于有限比率，0/0 记 0，此约定也须符合采用的规程。

场积分需另填 `match_points:{win:2,loss:1,walkover_loss:0,retired_loss:0}` 等明确分值。遇弃权退赛，默认 `abnormal_results:adjudicate` 暂缓该组名次；`wins_only` 仅允许胜次/场积分指标；`recorded_score` 需 `abnormal_rule_reference`，表示已确认按实录分统计，不能当作各协会通用处理。

确有书面裁定或历史报表将弃权判为 31:0 等分值时，使用 `awarded_score:{games:[[31,0]]}`，并给出 `awarded_score_reference`。目前仅支持 points 局分制的 `walkover` / `retired`，须符合本场终局规则且胜方一致。`walkover.score` 留空；`retired.score` 可以单独保留中断时的实录分，如 `partial_game:[4,1]`，而裁定分为 `games:[[4,31]]`；行政计分不得改写已完成局或减去已打得分。该组只有明确设置 `abnormal_results:awarded_score` 和 `abnormal_rule_reference` 后，才把裁定分计入局分统计；默认仍待裁定。Excel/CSV 单列“行政判定比分（非实际对局）”，JSON 同时保留来源。历史报表中的星号可能覆盖此前正常完赛场次，不能仅凭参赛者带星号把所有比赛都改成弃权；应逐场查弃权标记，并核对胜次、净胜局。

网球指标 `games` 表示盘、`points` 表示普通局；抢十计一盘、计零普通局。使用这些指标前必须明确 `tennis_stat_policy:"sets_and_ordinary_games_excluding_match_tiebreak"`。若赛事用其他算法，先实现所需算法或保留待裁定，不能用此统计替代。

所有规则仍无法分开时保留并列待裁定。规程允许抽签/裁判裁定后，可给该组加入 `tie_decisions:[{order:["E3","E1"],confirmed:true,reason:"规程第X条；裁判确认的抽签记录"}]`。只接受恰好覆盖当前未解同分块的顺序，不能覆盖已分出的胜负名次。

## 淘汰成绩

名次由场次的 `placement:{winner:1,loser:2}` 或 `3/4`、`5/6` 等明确映射得到，不按总胜场数排序。决赛未完成时不输出冠军。无季军赛也不自动产生第三名。

规程明确并列第三时，可另设 `shared_placements:[{project_id:"MS",rank:3,source_match_ids:["SF1","SF2"],outcome:"loser",rule_reference:"规程第X条并列第三"}]`；所有所指半决赛完结后才生成并列名次。它与现有独占名次冲突会报错。

## 执行与输出

```bash
python scripts/results_engine.py event-with-results.json --output exports/results-v1
python scripts/results_engine.py event-with-results.json --output exports/results-v1-csv --no-xlsx
```

新目录包含 `成绩排名.xlsx / 成绩排名.csv / 逐场成绩.csv / 成绩数据.json`。JSON 保留输入哈希、逐场来源、同分计算轨迹及规则；公开分享前按用户要求隐藏身份、联系方式。脚本不执行任何上传、发布或通知。
