# 规程与补充通知的内容模板

新建或实质修订规程、并组通知时读取。默认采用单位正式文件的组织方式：标题准确、事项分条、表格明确、发布主体和日期齐全；不自行添加红头、文号、印章、上级文件或宣传口号。用户已有有效模板优先，但仍核对业务字段。

## 模板和事实来源

- [规程正文模板](../assets/regulations-body-template.md)：十部分正文及条件条款，适合组织文件起草。
- [补充通知正文模板](../assets/supplement-body-template.md)：主送对象、原文件依据、调整前后、受影响事项、办理窗口、生效范围及落款。
- 自动生成时复制 [规程参数空表](../assets/regulation-content-template.json) 或 [通知参数空表](../assets/supplement-content-template.json) 到赛事目录，由助手根据资料填写；不让用户填写 JSON。
- 原文件和逐条来源记录放赛事目录。历史样例只提供结构和表达；金额、让分、年龄、开赛门槛、退费和竞赛规则须有本届依据。润色不得改变出生日期、参赛对象、收费单位或奖励。

每项信息分为“已确认／待确认／不适用”。询问只围绕影响当前稿件的缺项，可合并问“U组按什么年龄口径、能否跨龄和兼项、双打按谁的年龄判断”；不能先补成正式稿，再让用户检查猜测。青少年或年龄限制项目另读 [年龄与组别](age-group-design.md)。

平台元数据、报名项目名称和正文可能不一致。发现运动项目或组别冲突时记录来源差异并确认本届依据，不用系统下拉框的值自动覆盖正式规程。

## 从参数到文件

在 skill 根目录执行；各输出路径必须不存在：

```bash
python scripts/regulation_content.py check 赛事目录/规程参数.json 赛事目录/内容审查.json
python scripts/regulation_content.py build 赛事目录/规程参数.json 赛事目录/规程-v1
python scripts/render_regulations.py 赛事目录/规程-v1/document.json --format docx --output 赛事目录/规程-v1.docx
python scripts/render_regulations.py 赛事目录/规程-v1/document.json --format md --output 赛事目录/规程-v1.md
```

`build` 输出排版用 `document.json`、原参数 `content-source.json`、带来源摘要哈希的 `content-review.json` 和 `preview.md`。`status=draft` 可输出待确认稿；`final` 存在错误或待核实警告时拒绝生成。来源真实性、自由文本和规则适用性仍须人工核对；不得把校验通过称为已审核发布。更正事实后从参数重新生成，避免只改 Word 造成多份内容不一致。

渲染器只校验格式，不能用直接构造排版 JSON 绕过新规程的内容审查。既有文件的纯排版修订可保留原内容；涉及模型暂未支持的赛制、复杂收费或附件时，使用正文模板及完整人工审查表，明确哪些未被程序检查，不删减用户要求来通过程序。

## 参数字段

日期统一 `YYYY-MM-DD`；精确时点为赛事当地时间 `YYYY-MM-DDTHH:MM`。没有确定信息用 `null`，不要填“无”假装确认。明确不适用时写清事实，例如免费、不设奖励、内部邀请确认。

### 规程 `kind=regulations`

| 字段 | 含义与要求 |
|---|---|
| `event` | 名称 `name`、运动 `sport`（badminton/table_tennis/tennis/pickleball）、组织者 `organizer`、发布主体 `issuer`、版本 `version`、发布日期 `published`；比赛 `start/end`、场馆 `venue/address`、有效联系 `contact`、报名 `registration_open/registration_close/registration_channel`。报名渠道同时说明审核、缴费及成功确认方式。 |
| `max_entries_per_person` | 每人总报名项目数正整数；与团体对抗内子场兼项分别写。 |
| `policies` | 空表列出的资格核验、跨组兼项、退费、抽签日程、检录、异常成绩、异议、安全、变更、器材、规则版本等具体办法；涉及未成年人加 `guardian`。可以明确引用可获取的已确认附件。 |
| `groups[]` | 每个最终项目一个稳定 `id`、全称 `name`、`discipline=singles/doubles/team`、`sex=male/female/mixed/open`、`age` 和其他 `eligibility`；双打/团体补 `combination_rule`。男女并组单打用 open，mixed 表示混合组合。 |
| 规模与费用 | `min_entries` 为真实人/对/队门槛，`insufficient_policy` 写不足的办理办法；`fee={amount,unit}` 非负，unit 为人/对/队。特殊按人收费的双打同时给每对换算及解释，不擅自改收费事实。 |
| `stages[]` | `name/format/entrants/progression/rules`；format 为 round_robin 或 knockout。循环补 `ranking`；分组确定时填 `group_sizes`、`advance_per_group`。人数未定或结构未定用 `capacity_policy` 写触发方案和公布安排。不同阶段分别给计分办法。 |
| `awards` | `places` 录取至第几名（0无奖励）、`unit/description`；`bronze=playoff/joint/ranking/none` 分别为季军赛/并列第三/循环最终排名/不录取第三；第5名以后补 `placement_policy`。并列第三 places=3，获奖席位实际有4个，不能拿 places 当奖品数量。 |
| `count_rules[]` | 可选人数触发区间 `{min,max,action}`，按人/对/队从1连续覆盖；max=null 为无上限，报名上限以外写拒收，不能遗漏7、8、16、24等边界。自由文本内另有阈值时仍须人工对照。 |
| `age_partitions[]` | 仅对声明连续覆盖的同类年龄分区指定 `{groups:[id,...]}`，检查缺口；允许重叠时写 `overlap_policy`。不把公开组和成年组等合理重叠强制排斥。 |
| `extra_clauses[]` | `{heading,text}`，放本届已确认的服务、隐私、器材细节等额外正文。附件另用排版器 appendix 块或文档工具生成，并纳入最终人工核对。 |

`rules` 与 [成绩处理](results.md) 的计分模型一致：局分须明确 `mode=points,best_of,target,win_by,cap`（无封顶写 null）；网球须区分盘、局、抢七、决胜盘并显式指定 `no_ad`；匹克球阶段补 `scoring_system=side_out/rally`。团体 `mode=team` 描述整次对抗，另补 `team.roster/lineup/within_tie_limits/subevents` 写队员构成、阵容、对抗内兼项、子场及各自计分。程序不会验证这些自由文本的全部语义。

### 补充通知 `kind=supplement`

`event` 包含赛事名称、发布者、发布日期、版本；`base_document={title,version,published}` 锁定原文件。`scope/reason/effective_at` 写适用范围、原因、生效时点；`changes[]` 每项含 `section/before/after`。`impacts` 六项（eligibility/fees_refunds/schedule/scoring/awards/draw）均说明改变或维持原条款；`response_window/contact` 写确认、退出、退费的时限和渠道，不默认沉默代表同意。可填 `subject/recipients` 用于“关于……的补充通知”和主送对象。

并组/取消另填 `affected_source_ids` 和完整 `mapping[]`：原 `source_id/source_name/source_discipline`、`action=merge/retain/cancel`，非取消项给 `target_id/target_name/target_discipline`。双打拆组或单打转双打需先转换真实组合，不能只改 ID。用已确认的报名转换结果生成这些字段，见 [报名转竞赛](registration-transition.md)，不得另造一套并组决定。

`handicap` 明确 mode 为 none 或 matrix，`basis/application` 写本届依据、适用局次、叠加、封顶和换边。matrix 的 `pairs[]` 为 `{a,b,initial:[甲起始分,乙起始分],rules}`；a/b 指原类别 ID，每个合并项目内全部不同类别配对均须覆盖，不让分也写0:0。同类别不让分；同类别内部仍有差异时先细分类别。当前仅自动核验局分起始分，不支持凭自由文本计算年龄总和让分。

## 验收顺序

1. **依据**：逐项比对原件、用户确认和有效补充文件；原文矛盾单列。含 U、生日、人数、费用、规则、奖励、时间的内容不能仅做语言润色。
2. **内容**：运行 check，处理错误与警告；另核自由文本与结构字段一致、组合双方资格、团体子场、办理期限、奖励数量、附件引用。未覆盖的模型分支说明人工验收结果。
3. **执行**：关键人数各取边界前一项/边界/后一项演算；跨阶段席位、并列名次、每局让分等至少举一组可执行例子，验证结果不混入参赛者正文。
4. **文件**：按 [文档输出](regulation-output.md) 回读各格式，核对表格末行、日期端点、金额单位、附件、落款和版本；Word结构合格不等于分页已预览。

正式交付同时保存参数、内容审查和文件检查记录；核心条款未确认只交草案。模板是本 skill 的默认编制规范，不宣称符合某法定公文标准或替代具体协会规则。
