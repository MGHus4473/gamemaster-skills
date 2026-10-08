# 账号下用户筛选与赛事检索

用户说“切换用户”“看某用户的赛事”，且指向赛事管理页的“用户”下拉框时，进入`/index`的`Index`组件，执行列表筛选。它不切换登录身份、不编辑子账号、不转移赛事归属。选中另一用户也不证明新建赛事会归其所有；创建时另行核对保存后的创建人。

## 当前页面合同

- 下拉框可见条件：`uis.QXBH`为`MAIN`或`SMALL`，且`ISKY === '1'`。不可见时报告当前会话无此入口，不改角色、伪造用户编号或调用账号编辑接口。
- 选项来自当前`main.RYDMLIST`：值为`RYBH`，标签为`USERNAME(DQ)`；“全部”的筛选值为空字符串。不能从截图姓名猜编号，或把账号登录名与筛选用户编号混用。
- 选中项绑定`main.search.rybh`。选择之后还要执行检索；当前页面`searchHandler()`会把页码重置到1，调用`ssGl/getSsList`，请求包含`pageSet`与完整`main.search`。只改变下拉显示而沿用旧表格不算完成。
- 回读`content`赛事列表、`totalNums`、`lsData.RYDMLIST/ISKY`。指定用户时核对每条赛事的`RYBH`，显示创建人字段为`USERNAME`。保留未要求修改的赛事名、状态、收费等筛选；查询为空时先说明残留筛选条件，不直接认定用户没有赛事。

同名用户按地区完整标签或当前选项ID消歧；仍有多个候选时让用户选择，不任取第一个。找不到赛事时先核对当前用户筛选和分页，不能只在登录人第一页搜索，也不能直接新建一场同名赛事。

## 可执行工具

Node.js 22+，复用已登录本机浏览器的CDP会话。先进入`https://www.ptty.com.cn/#/index`。工具仅调用已核验的`getSsList`读取，查询成功后同步当前页面的用户筛选、第一页表格及总数；不会保存赛事数据或重登账号。

```bash
node scripts/ptty_events.mjs --session /secure/browser-session.json --action users --out 可选用户.json
node scripts/ptty_events.mjs --session /secure/browser-session.json --action list --user-label "用户甲(地区甲)" --all-pages --out 用户甲赛事.json
node scripts/ptty_events.mjs --session /secure/browser-session.json --action list --user-id 当前选项ID --search-text "赛事关键词" --out 检索结果.json
node scripts/ptty_events.mjs --session /secure/browser-session.json --action list --all-users --all-pages --out 全部可见赛事.json
```

先读取可选用户，用文件中的真实ID或完整标签替换示例。`--user-id`、`--user-label`、`--all-users`三选一；省略则沿用当前用户筛选。`--search-text ""`显式清除名称条件；不传则保留。不要将真实姓名、用户ID、赛事数据或会话文件写进skill。

默认仅取第一页，`complete:false`明确表示还有记录；需要找赛事或完整盘点时用`--all-pages`。全量读取逐页去重并核对总数，页面仍显示第1页；返回文件记录实际抓取页数。默认最多100页，超限会失败，按任务缩小筛选或显式设置`--max-pages`。读取期间总数、登录身份或筛选改变时停止；重试前检查现场状态。即使总数不变，平台也不提供事务快照，繁忙赛事需按具体ID再核对。

## 验收与进入赛事

1. 下拉选项真实存在且当前角色可见；请求中的筛选值与所选用户一致。
2. 检索完成后核对页面选中标签、筛选值、第一页行数、总数；所选用户的赛事归属全部匹配。“全部”允许不同创建人，不能当作没有权限边界的全站列表。
3. 列表输出不含手机号等无关字段。用返回的`event_id`和`event_route_id`定位赛事；进入后再次核对明文ID、名称及运动类型，再使用[赛事内只读工具](read-only.md)或其他已授权操作。
4. 按用户要求留下目标筛选；自动回归测试应恢复原筛选，不能因此覆盖用户后来主动选择的新条件。

2026-10-08只读实测通过两名其他用户、全部用户及原用户的切换；完整分页查询与下拉框真实选中标签、赛事归属、登录身份均核对。查询失败、无可见入口、同名歧义、分页重复/总数变化、错误归属有合成回归。此证据不等于账号身份切换或赛事转移已实现。
