# 报表、接口观察与只读工具

尚未进入赛事、需要切换“用户”或跨用户找赛事时，先用[用户筛选工具](event-user-filter.md)。本页工具要求已进入明确赛事，不承担账号下赛事列表筛选。

`scripts/ptty_readonly.mjs` 通过已有浏览器 CDP 会话在当前页面读数或下载。Node.js 22+；会话 JSON 仅需 `pageSocket`，通过 `--session` 显式传入。它不负责登录，不保存 Cookie，不接受任意 JavaScript 或任意 API 名称。只允许`https://www.ptty.com.cn/`后台应用（默认HTTPS端口、无URL账号密码），并以明文赛事 ID 核对页面。网站与运动模块检查见[网站信息](website.md)。

```bash
node scripts/ptty_readonly.mjs --session /secure/browser-session.json --event SS目标ID --action snapshot --out snapshot.json
node scripts/ptty_readonly.mjs --session /secure/browser-session.json --event SS目标ID --action plan --out plan.json
node scripts/ptty_readonly.mjs --session /secure/browser-session.json --event SS目标ID --action report --kind getCjcData --out 成绩册.xlsx
node scripts/ptty_readonly.mjs --session /secure/browser-session.json --event SS目标ID --action qr --kind event --out 比赛二维码.png
```

先手动或用可用浏览器工具进入相应赛事。`plan` 需在“竞赛方案”；`report` 需在“出单管理”；`qr` 需在“比赛控制”。工具同时核对路由与组件，不在演示向导或同名组件的其他页面发请求。`snapshot` 只读取导航、组件名和赛事ID；不输出整页人员/联系方式。页面组件或字段变化时明确失败，检查页面后再更新适配器。报表和二维码读取结束或异常后恢复共享请求对象，报表还恢复原标签与项目选择；仍须串行调用。

`plan` 返回当前页及筛选信息，只有页码1、总数等于读取行数且没有搜索/筛选时才标 `complete:true`。`complete:false` 时不能称全量方案；按页面只读清除筛选或逐页收集，并核对总数与唯一项目阶段ID。计划界面当前默认每页500条，不能把这个容量当成永远不会分页的保证。

此工具仅是读取白名单，不是平台全部能力目录。它没有场次创建动作时，查[首次场次生成](match-generation.md)并使用已授权的浏览器操作；宿主缺少浏览器能力应如实说明工具缺口，不能推断平台没有入口。

## 全量比赛场次

在“赛程管理”`/trialScGlIndex`使用`--action matches`，按无筛选`scGl/mainLoadData`汇总、逐项目`getDwInfo`明细、再读汇总的顺序，核对总场数、项目场数、赛事身份与CCH唯一性。返回`match_count/matches_present/projects/rows`；未知计数、接口失败、明细不全、读取期间状态变化都报错，不转成零场次。汇总最多取1000项，若项目场数之和不足全赛总数，必须补做分页，工具不会声称完整。

同一路由只变`ssid`时，当前Vue组件可能继续持有旧赛事；工具会同时核对路由ssid、组件ssid与页面明文赛事ID。发现不一致时先返回赛事列表再进入目标赛事，等加载完成后重读，不能把失败改写成空列表。

该动作不接受项目子集，不改变页面搜索词，不生成或重置场次；时间场地和完整依赖验收仍单独执行。两个页面组件同名，不能在`/trialSsBpIndex`调用此动作。名单或种子不等于已有签位；有签位却读到零场次时，按[矛盾状态处理](match-generation.md)复查，不能删签重建。

```bash
node scripts/ptty_readonly.mjs --session /secure/browser-session.json --event SS目标ID --action matches --out 全量场次.json
```

## 出单管理

|报表|当前方法名|用途|
|---|---|---|
|名单公示|getMdGs|对外名单；包含所选项目/阶段，不能直接去重当原报名总人数|
|抽签公示|getCqGs|组号/签位、人员/队伍|
|节目单|getJmdData|赛事日程|
|秩序册|getZxcData|分组、淘汰结构及排期|
|成绩排名册|getCjpmData|循环组内名次和淘汰阶段排名；分别选择目标阶段|
|成绩册|getCjcData|局分、循环交叉表与淘汰结构|
|场序表|getCxbHandler|每场日期、场序、场地、双方、比分、裁判等|
|弃权统计表|getQqTjb|弃权状态核对|

当前页面 `TrialCdGlIndex` 使用 `cdGl`，`getDownUrl("1")` 返回下载文件链接。链接包含临时用户参数，只在内存使用，下载后丢弃；不把URL写入日志。工具先用已观察的 `currData` 只读入口刷新项目目录：名单公示取 `getXmIds`，其他报表取 `getCreateScXmIds`（已生成赛程项目），不复用上一标签的旧选项。默认选该报表目录的全部项目，`--project-ids` 可指定其子集；回执记录目录来源、可选数量及是否全选。已生成项目目录不等于所有报名项目；阶段排名应按确认范围下载。除非用户要求，不点击“汇总积分”或“出单设置→保存”。

批量操作按赛事串行导航；同一页面逐份报表串行下载，避免共享Vue状态与请求参数相互覆盖。一个报表可含多个项目，先核对阶段和工作表，再统计真实独立项目数；同项目两阶段不算两个不同赛事项目。

二阶段名单会再次列出晋级者，不能把全部阶段名单行数当独立参赛数。成绩排名册中的组内1名不等于赛事冠军；确认终结阶段及名次赛完成情况。未完成赛事文件可下载，但对外交付标“截至时间/暂定”。成绩详细字段的原始列名有重复，解析时按列位置与样例核对，不直接转成同名字典丢列。

## 只读核对范围

二维码原图允许PNG或JPEG，输出后缀必须与魔数一致；裁判码已观察为JPEG，可用`--kind referee --out 裁判二维码.jpg`。格式不匹配时检查实际签名再选择新文件名，不重建小程序码；保存后完整解码图像，实际扫码另验收。

下载真实文件后重新打开，核对文件签名、工作表、项目/阶段、人数、场数与比分，并保存SHA256。内容类型可能写 `application/vnd.ms-excel`，实际文件却为ZIP/XLSX；以魔数决定后缀。工具拒绝把HTML登录页保存成Excel。

查询调用也可能产生服务器访问日志、临时报表或图片缓存；这些与赛事业务记录不同。本工具白名单仅覆盖已观察的读取/导出入口，不调用名单锁定、配置保存、比赛生成、上传、发布或通知。

不要把赛程页“导出所有场次，更新赛号”当成普通下载；它带更新语义，应走写操作的范围确认和前后映射核对。本工具的出单管理场序表不调用该入口。

2026-10-07只读复核：既有测试赛方案3条记录全量通过；场序表和成绩册各下载全部3个可选项目，均可重新打开。随后隔离合成赛的名单公示、抽签公示、节目单、秩序册、成绩排名册、成绩册、场序表7类报表下载并打开通过；终结排名及逐场时间/场地/比分与离线结果一致。三种二维码原图可解码，观众/PAD负载核对通过；实际微信扫码仍未验证。各项证据分别记录，不覆盖弃权统计或所有运动模块。文件仅保存于赛事资料目录。
