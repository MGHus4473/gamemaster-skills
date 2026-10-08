---
name: ptty-skill
description: 操作跑兔体育（ptty.com.cn）的赛事、报名、抽签、编排、检录、控场、成绩与发布，下载报表和二维码；按用户意图定位操作、核对依赖并回读。离线赛事文件由 gamemaster-skill 制作。
---

# 跑兔赛事操作

本 skill 负责跑兔中的读取、下载、上传和操作回读。离线规程、名单清洗、并组、抽签计算、编排优化、成绩计算和文稿制作交给 `gamemaster-skill`；只做跑兔查询或下载时无需安装它。

## 工作方式

1. 按[意图与状态](references/intent-and-state.md)明确对象、目标变化及范围，用[操作目录](references/operation-map.md)定位入口。核对赛事名称、ID、运动模块和比赛状态，报名赛事与比赛赛事可能不同。沿用当前会话授权；只读任务不导入、保存、生成赛程、锁名单、发布或删除。
2. 按[网站与运动身份](references/website.md)使用官方后台及现有登录会话，保留赛事二维码原始协议与路由。区分选错模块和元数据缺陷；用户接受且已验证不影响目标操作的缺陷可按赛事/版本/操作限定豁免，保留异常原值与证据。接口来自当前页面调用或已核验记录；未知参数先读页面与模板。会话、下载签名和密码不进入skill或交接包。
3. 有离线成果时校验 [交接与身份映射](references/handoff.md) 和文件版本；有现成跑兔文件时先下载并交给离线 skill。默认模板相似不等于所有运动模块都能接受同一配置。
4. 执行 [平台流程](references/platform-workflow.md) 中对应一步，按[恢复与验收](references/recovery-and-testing.md)全量回读并比较直接及下游结果。保存前快照、输入哈希和差异；成功提示不能代替验收。超时先查落库；部分成功先核验增量/整表语义，出现非预期变化停止覆盖。当前创建向导和比赛检查含模拟数据及随机检查，不能用于真实创建或验收。

## 按任务读取

|任务|参考与工具|
|---|---|
|网站入口、登录、手机页异常、运动类型冲突与脱敏|[网站与运动身份](references/website.md)|
|切换账号下的用户、按创建人找赛事、查询全部用户赛事|[用户筛选与赛事检索](references/event-user-filter.md)，`scripts/ptty_events.mjs`|
|找入口、消除歧义、判断变更影响、识别模拟页面|[操作目录](references/operation-map.md)、[意图与状态](references/intent-and-state.md)，`scripts/operation_catalog.py` 离线检索及预检|
|字段合同、临场变更、部分成功/超时恢复、任务范围及流程回归|[恢复与验收](references/recovery-and-testing.md)，`scripts/task_contract.py`、`scripts/workflow_state.py` 离线检查|
|已有签位但没有场次、首次生成比赛后编排|[首次场次生成](references/match-generation.md)，`scripts/prepare_match_generation.py`；先用`ptty_readonly.mjs --action matches`全量复查；确无场次且无签位才在竞赛方案页首次生成，不删签绕过保护|
|报名设置、并组名单、方案、抽签、赛程和编排|[平台流程](references/platform-workflow.md)；下载编排信息前先检查场地数据，缺失时按[首次网格初始化](references/platform-workflow.md#下载编排信息前的场地数据检查)点击“生成场地数据”并回读；[按钮执行工具](references/schedule-grid-button.md)|
|创建表单、赛事图片、规程/补充通知、报表可见性、小节分配和各端发布|[创建与发布](references/publication.md)，`scripts/publication_packet.py`离线准备与校验|
|独立计算结果上传、平台 ID 绑定、导入边界|[交接与身份映射](references/handoff.md)|
|成绩、名单、抽签、秩序册及场序表下载|[报表与只读工具](references/read-only.md)，`scripts/ptty_readonly.mjs`|
|签到检录、控场、比分修正、团体名单、通知、权限和财务|[现场与账户操作](references/live-operations.md)|
|赛事二维码、裁判小程序码、PAD码，定制logo和底部文字|[二维码获取与交付](references/qr-codes.md)；先用`ptty_readonly.mjs --action qr --kind event --navigate`从平台取码，再按[草料流程](references/qr-cli-im.md)美化，用`verify_qr.py`验收；不默认要求用户提供平台已有的入口|

规程、补充公告、开闭幕致辞和规则解释先由离线 skill 制作；要求发布时再传入对应页面，发布或通知范围遵循用户明确指令。规则变化、收费、退款、开赛和结果更正不由“完成赛事创建”自动推定。

## 验收边界

区分文件生成、只读平台核对、实际写入回读三种证据。只读演练不能称线上创建已通过。平台不支持的运动、模板或自建场次入口明确标注，保留完整离线成果，不借用另一赛事 ID 或自动改用平台生成来冒充独立算法。

运行依赖与命令见相关参考。产物与测试记录置于 skill 目录外；本目录不保存账号数据、具体赛事样例或浏览器配置。
