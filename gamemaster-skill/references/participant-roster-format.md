# 参赛名单数据与模板

依据：2026-10-06读取 `导入模板/03参赛名单/名单导入模板 (10)/(11)/(12).xlsx`，共17个项目工作表，包含单打与双打。已清除源赛事数据和XMID，提取为内置双工作表模板。

## 表格契约

第1行：项目标题。第2行：A为系统项目XMID，B为项目名称/组别，C为类型编码，E保留个人组说明。第3行字段，第4行起名单；空尾列保留。单打模板11列范围、8个有名字段；双打21列范围、20个有名字段。

|类型|字段顺序|
|---|---|
|单打A–H|队伍全称/简称*、姓名*、性别、队内技术号、种子号、身份证/出生年份(必须为纯数字)、年龄、手机号|
|双打A–F|队伍全称1/简称1*、姓名1*、身份证1/出生年份1(必须为纯数字)、年龄1、性别1、手机号1|
|双打G–L|第2位运动员的上述六项|
|双打M–R|第3位运动员的上述六项；普通双打留空|
|双打S–T|队内技术号、种子号|

本地性别样例为M男、W女，不擅自改为F。2026-10-06跑兔实测：混双成员性别为空会整表报错（“性别必须为M或者W”），即使列头未标星。系统导出模式要求全部运动员填M/W；不明时查证或询问用户，不能猜填。普通双打第3人即使表头带星也不填；历史无表头尾列出现-1，语义未确认，不复制该值。模板“纯数字”标题与部分身份证末位X的源数据矛盾：保留证件文本，实际导入兼容性另核验。个人参赛确认为个人且规程允许时使用模板提示“个人组”，不能把未知单位都改成个人组。

## 标准JSON

顶层：`event_id`（线下可省），`projects`，`entries`，`reviewed`，`unresolved`（数组），`exclusive`（是否禁止跨项目兼项，须依据规程显式给true/false）。

每个project：`key`稳定本地项目编号、`name`、`type`（MS/WS/SS/MD/WD/XD/SD）、可选`system_id`、可选`expected_count`（确认方案的参赛单位数，含明确预留项，不含轮空签位）、可选`expected_real_count`（真实有效报名项数）。没有方案时可省expected_count。

每个entry：`id`稳定报名记录ID、`project`对应key、`status`（active/withdrawn）、`source`原件位置、`members`数组；可选`technical_no`、`seed`。更正及换搭档保留entry ID。退赛记录保留在数据而不输出名单。

真实项省略`kind`或设`real`。预留项设`kind:placeholder`、`members:[]`、唯一`id`与`label`，以及`reservation:{confirmed:true,replacement_deadline,eligibility,unfilled,allocation}`（后四项是明确文字）；不伪造运动员、性别和联系方式，不设种子。预留在本地表按1行/参赛单位输出、性别留空；`--system`遇未填预留会拒绝。`summarize()`分别返回真实报名项、预留项、计划报名项与已知运动员数量。完整流程及替换约束见 [预留与替换](reserved-entries.md)。

每个member：`id`稳定运动员ID、`name`、`unit`，可选`gender`（M/W）、`identity`（证件或出生年份原样文本）、`age`非负整数、`phone`文本。带性别限制的项目须明确gender；一般单打/双打可空。脚本不验证身份证真实性、年龄资格或单位资格，这些须在reviewed前从来源审核。人员跨项目使用同一ID；同名不是分配同一ID的依据。

`reviewed:true` 表示已完成来源/身份消歧和规程资格审核，`unresolved:[]` 表示无影响正式输出的未决项。不得为通过程序而伪造这两个值。导出校验重复人员ID、同项目重复报名、重复种子/技术号、双打人数与性别、项目人数及限项；不会以姓名自动去重。

## 增补操作JSON

`{"operations":[{"id":"批次操作唯一ID","action":"add|replace|withdraw","source":"文件页行或用户消息依据",...}]}`。

add/replace携带完整`entry`；replace必须引用已存在entry.id，新增未出现字段需显式保留旧值，不做隐式稀疏更新。withdraw携带`entry_id`，只标退赛。恢复用replace明确设status=active。相同操作ID且内容相同跳过，内容不同报冲突；同entry ID、内容相同的add跳过，内容不同拒绝，不能隐式覆盖。

merge输出保留`history`中的操作与before/after，增加version并重置reviewed=false；复核来源、未决项及方案人数后才可导出。重复提交未改变数据的操作不增加版本也不撤销已完成审核。项目变更配置仍需根据确认后的方案单独调整。
