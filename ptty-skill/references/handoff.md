# 文件交接与身份映射

独立报名项、运动员、项目和场次 ID 由离线系统持有；`SSID / XMID / XMNM / CCH` 是跑兔映射。项目简称、方案编号、姓名、显示赛号均不能替代内部 ID；跨赛事不复用。两人同名要按原件、单位和身份依据区分，双打以完整组合识别。

`handoff.json` 契约与 `gamemaster-skill/scripts/handoff.py` 一致：

```json
{
  "schema_version": 1,
  "event": {"local_id": "event-local", "name": "赛事名称", "sport": "badminton"},
  "input_version": "v1",
  "rules_version": "规程v1+补充通知v2",
  "artifacts": [{"kind": "roster", "path": "output/名单.xlsx", "sha256": "文件SHA256"}],
  "mapping": {"event_id": "", "project_ids": {}, "entry_ids": {}, "match_ids": {}}
}
```

文件路径相对交接包根目录；拒绝绝对路径、`..`、越界软链接、缺失文件、重复路径与哈希不符。`metadata` 可附确认参数和时间，不放会话令牌。运行：

```bash
python scripts/validate_handoff.py path/to/handoff.json
```

校验通过仅证明文件完整性；导入前仍核对目标赛事、运动模块、项目阶段、人数单位、名单状态及模板。ID 映射来自当前赛事查询，不从编码规律猜造。映射 JSON 字段为本地 ID → 平台 ID；报名赛事的 `XMID` 与最终比赛项目的 `XMID` 分开记录。

## 文件适配

基础21列竞赛方案和单/双打名单模板由离线 skill 维护。平台下载模板优先于历史样例；网球盘制、匹克球边出计分等不能被羽毛球模板表达时，应核实对应运动模块或保留附加配置，不能丢字段后宣称兼容。

- 名单：读取当前赛事 `XMID` 后填项目元数据，每名真实运动员的性别 M/W 来自已确认资料。未填身份预留项直接导入尚未验证；不得编造性别、证件或运动员来过校验。
- 抽签：`export_draw.py` 适配已核验20列抽签表；N—T为人员区，模板识别码 `XMNM` 与人员/组合整体移动。导入不等于保存种子元数据。
- 编排：`export_schedule.py` 适配赛事编排工作表；每个场地单元格末行使用当前真实 `CCH`。独立本地 ID 在交接映射中保留。
- 两个适配器通过 `--core-skill` 读取离线算法校验器；具体参数用 `--help` 查看。

需要导入文件时运行（仅生成本地文件，不会自动联网上传）：

```bash
python scripts/export_draw.py draw-input.json draw-result.json entry-map.json 当前抽签模板.xls 抽签导入.xls --core-skill /path/to/gamemaster-skill
python scripts/export_schedule.py schedule-input.json schedule-result.json 当前编排模板.xlsx 编排导入.xlsx 编排审阅.xlsx --core-skill /path/to/gamemaster-skill
```

两个 skill 安装于同级目录时可省略 `--core-skill`。抽签导出自动另存 `_审阅.xlsx`；编排指定独立审阅文件。输出必须使用新路径，旧版成果保留；抽签模板/输出为真实 `.xls`，编排模板/输出为 `.xlsx`。编排校验输入哈希、赛事、完整时段网格、场次ID及硬约束，拒绝结果与输入版本错配。当前编排适配器只接受第二张“场次工作表”为空的已验证结构；发现其他内容先核实新模板，不携带旧场次直接输出。

`entry-map.json` 为数组，逐项提供本地 `project_id、entry_id`，目标 `platform_project_id`（当前阶段XMID）、`XMNM`，以及核对字段 `name、club、seed`。同一本地项目的所有项映射到同一平台项目；不同本地项目不共用一个目标XMID。历史数据本地项目ID本身即XMID时可省略 `platform_project_id`，新离线流程应显式绑定，不能为了适配模板而重写本地项目ID。

Python 3.10+ 依赖见 `requirements.txt`：抽签导出需要 `xlrd、xlwt、xlutils、openpyxl`，编排和交接Excel需要 `openpyxl`；二维码另需 `qrcode、Pillow、zxing-cpp`。纯交接校验仅用标准库；只读浏览器工具另需 Node.js 22+ 和已建立的本地CDP会话。可提前下载这些依赖离线安装，不把当前机器的 `/tmp` 路径作为运行条件。

## 结构创建与导入限制

17列“场次信息表”已观察到仅修改已有赛号，不能据此宣称支持新增比赛；“赛事编排”也依赖既有 CCH。平台生成赛程与独立生成赛程是不同业务操作。用户要求独立生成时，缺乏已验证的完整场次创建入口，就交付本地结构并明确线上步骤未完成；不得调用自动生成后改号冒充独立创建。

回执至少记录 `operation、event_id、input_sha256、before_counts、after_counts、differences、verified_at`。下载文件不保存含 `uisStr` 等签名的URL。与离线名单或规程有冲突时，先定位有效版本和来源，不自动用线上旧数据覆盖新文件。
