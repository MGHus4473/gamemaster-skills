# 报名调整脚本字段

原报名使用 [标准名单JSON](participant-roster-format.md)，只有真实项，`version`记录来源版本；并组前先完成身份与资料审核，不能把报名上限写成`expected_count`。

`registration_transition.py apply`的方案字段：

| 字段 | 含义 |
|---|---|
| `id` | 本次确认方案的唯一ID |
| `reviewed:true, unresolved:[]` | 本场的映射、人数、资格、让分和预留参数已确认，不是系统自动授权标志 |
| `source_version, source_event_id` | 与原名单版本/赛事一致；线下无赛事ID时省略source_event_id |
| `event_id` | 可选目标赛事ID，不能自动沿用来源赛事ID |
| `seed_policy` | `clear`清除原组种子；`retain`保留并继续校验重复。新种子另按确认结果填入 |
| `projects` | 最终组列表，见下表 |
| `cancelled` | 整组取消：`source_key/reason/handling`；最后一项写退费、退出、转项等实际安排 |
| `entry_decisions` | 可选逐项覆盖，键为原entry ID，值含`target`（最终项目key或null）、`reason`，取消时另须`handling`。不能通过此方式恢复已退赛项 |
| `handicaps` | 键为采用matrix的最终project key，值见让分表 |
| `notice` | 生成补充通知时需提供的发布信息及逐项目变化，见下文 |

每个最终project：

| 字段 | 含义 |
|---|---|
| `key/name/type` | 最终本地编号、名称、MS/WS/SS/MD/WD/XD/SD；同龄男女合单打通常SS，混合组合双打通常SD，保留真实性别 |
| `system_id` | 可选，经核实的目标XMID，不从原报名项目复制 |
| `source_keys` | 来自哪些原报名组；每个原组恰好映射一次或列入cancelled，空组同样处理 |
| `min_actual` | 本场确认的最低真实报名单位数（整数≥2），常用建议8；不自动默认 |
| `below_min_reason` | 实际低于本场门槛时，记录用户确认例外及安排。不足2项不输出可开赛项目 |
| `reserve_count` | 0或确认的名额数；超过3须`extra_reserves_confirmed:true` |
| `reserve_policy` | 有预留时必需：`confirmed:true,replacement_deadline,eligibility,unfilled,allocation`（后四项为文字） |
| `qualification_policy` | 并组后资格、年龄判断基准与材料审核结论 |
| `handicap_mode` | `none`或`matrix`；none须`no_handicap_reason`，明确本场不让分的依据 |

`expected_count/expected_real_count`由脚本依据流向重算。单人转入非默认目标可使用entry_decisions，随后重新校验目标资格/性别、最少人数和让分类别。原始来源、退出、逐项取消保存在原名单与结果ledger；取消项不会混进新的活动名单。

每个让分rule：

```json
{
  "confirmed": true,
  "source": "本场确认记录/补充通知版本",
  "application": "each_game_initial_score",
  "stages": ["第一阶段", "第二阶段"],
  "target_points": 21,
  "cap_points": 21,
  "classes": ["类别甲", "类别乙"],
  "entry_classes": {"真实报名项1": "类别甲", "真实报名项2": "类别乙"},
  "matrix": {"类别甲": {"类别甲": 0, "类别乙": -4}, "类别乙": {"类别甲": 4, "类别乙": 0}},
  "combination_policy": "这是字段示例；本场需确认完整性别/年龄组合，不自动叠加",
  "ends": "本场间歇和换边的明确办法",
  "serving": "本场发接发和起始比分对应场区办法",
  "ranking": "本场循环排名是否采用让分后的比分及比较顺序"
}
```

示例矩阵表示甲让乙4分、每局0:4开始，不是本skill的默认分值。entry_classes须恰好覆盖本项目真实报名项；预留暂不分配真实类别，classes可提前包含允许补录的全部类别。矩阵完整、对角0、反向取负、整数且绝对值小于目标分；不要求三类之间分值相加相等。公开通知输出文字类别和起始比分，不输出个人身份。

`notice`：`title/base_version/version/effective_at/issuer/participation_deadline/participation_handling/publication_channel`均为明确文本；`awards/format_changes/score_changes`各为覆盖所有最终project key的文本映射。不得用空白或“待定”值冒充正式确认。脚本生成MD，其他格式用既有规程渲染流程。

`replace`使用的实际补录JSON：`registration_entry_id/source/members/eligibility_confirmed:true/downstream_reviewed:true`，涉及让分时另给`handicap_class`。members沿用标准运动员数据；两个确认字段分别代表已经查证资格/截止与下游开赛状态/回避/排程影响，不能为通过校验自动设true。最终复核仍由操作者完成，脚本不会以布尔值证明事实。
