# gamemaster-skills

面向羽毛球、乒乓球、网球和匹克球的赛事工作流，分为两个可独立使用的 skill：本地制作赛事资料，以及操作跑兔赛事系统。

| Skill | 负责内容 | 运行方式 |
| --- | --- | --- |
| [gamemaster-skill](gamemaster-skill/README.md) | 规程、报名名单、并组与预留名额、方案、抽签、对阵、编排、成绩、文稿及羽毛球规则知识库 | 业务脚本与规则快照检索可离线运行；核验最新规则时联网查官方来源 |
| [ptty-skill](ptty-skill/README.md) | 跑兔查询下载、创建与更新流程、图片与内容发布、报表与小节、导入适配、二维码 | 在线操作需要用户有权使用的跑兔会话及浏览器工具；文件适配和请求包准备可离线完成 |

两个 skill 通过文件、校验哈希与身份映射交接。只制作文件可单独使用 `gamemaster-skill`；只查询跑兔可单独使用 `ptty-skill`。这是供支持 skills 的智能体宿主加载的指令与工具集合，执行能力取决于宿主提供的文件、脚本、浏览器和文档工具。

## 安装

```bash
git clone https://github.com/MGHus4473/gamemaster-skills.git
cd gamemaster-skills
```

按宿主的 skill 安装说明，加载需要的完整目录；保留各目录中的 `SKILL.md`、`references`、`scripts` 与 `assets`。同时使用时推荐保持两个 skill 同级；分开放置时，跑兔文件适配脚本可用 `--core-skill` 指向离线 skill。宿主的扫描目录、安装命令及显式调用语法以其文档为准。

基础算法需要 Python 3.10+。下面是可选依赖的联网准备示例；离线部署可预先下载依赖后安装。

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r gamemaster-skill/requirements.txt
# 使用跑兔文件适配或二维码功能时安装：
python -m pip install -r ptty-skill/requirements.txt
# 输出 Word 时另需 Node.js 20+：
npm --prefix gamemaster-skill install
```

只读浏览器工具需要 Node.js 22+ 和已建立的本地 CDP 会话。PDF、LaTeX、OCR、中文字体等按任务另行准备，详见各 skill 的运行说明。业务脚本离线运行不代表宿主模型本身离线；后者取决于宿主部署。

## 使用示例

可直接向宿主提出任务，并指定所用 skill：

> 使用 gamemaster-skill，整理这份报名表和后续补报名，保留来源记录。先列出与规程不一致的组别，再生成审核后的参赛名单 Excel。

> 使用 gamemaster-skill，为这场乒乓球赛制作 Word 规程。沿用我提供的模板，缺少的资格、计分、晋级和奖项信息先列出来确认。

> 使用 gamemaster-skill，根据已确认签表编排比赛。先确认场地、日期、上午下午时段、休息和兼项口径；校验运动员重场、连续比赛和前后依赖，再尽量压缩结束时间。

> 使用 ptty-skill，从当前已登录的跑兔赛事下载竞赛方案、秩序册和成绩册，只读核对，不修改赛事。

> 联合两个 skill：先制作并校验补充通知，随后按我确认的赛事和项目范围发布到跑兔，回读正文及公开端显示结果。

## 组合流程

1. 整理规程与报名原件，确认本场运动规则、人数单位和输出模板。
2. 在本地完成报名调整、正式方案、抽签、对阵与排期；保留运动员、报名项、项目和场次的独立身份。
3. 输出文件与 `handoff.json`，记录版本、文件哈希及待绑定的平台 ID。
4. 跑兔 skill 核对当前赛事、运动模块与最新模板，在用户授权范围内执行导入或发布，并回读比较。
5. 以实际赛果生成成绩、获奖名单及闭幕文稿；更正后重新核验受影响的后继比赛和发布内容。

## 能力与边界

- 离线引擎支持单/双打的单循环、双循环、单淘汰，以及分组循环后淘汰；包含轮空、种子与单位分散、明确的名次赛。四种运动分别配置计分、种子和同分规则。复杂团体阵容、双败和特殊赛制需扩展并验收。
- 排期检查真实运动员的跨项重场、休息与前驱依赖。默认满足约束后整体尽早结束，再兼顾单项收尾；启发式结果不声称达到数学最优。只检查已确定选手时，晋级或替补后需复核。
- Word 有明确的字体、缩进、标题、表格、附件及页码规范。复杂 Word 内容转 PDF 需本地办公软件或相应排版实现；仅检查文件结构不能证明实际分页无误。
- 默认 Excel 模板沿用跑兔常见字段，用户模板优先。离线文件生成、平台导入、线上创建与公开展示分别验收；本地场次 ID 不等于平台 `CCH`。
- 跑兔 skill 包含已核验的流程说明、只读下载工具、离线导入适配和发布请求包。实际写入由可用浏览器工具按当前页面接口完成；新建赛事等尚未完成实写验证的能力会在参考文档中单独说明。

## 网站与数据

跑兔后台入口为 [https://www.ptty.com.cn/](https://www.ptty.com.cn/)。手机观赛入口取自目标赛事的真实二维码，保留原协议、域名、路径和参数；不能自行改写。入口区别及已观察到的部署问题见 [网站与入口](ptty-skill/references/website.md)。本项目与跑兔网站分别维护，平台变更后需重新核对适配。

仓库只包含通用 skill、公开说明和合成测试。赛事原件、名单、快照、二维码、日志与输出放在 skill 目录外的受限赛事工作区。账号、密码、Cookie、令牌、浏览器会话和带签名下载链接不进入源码、示例、交接包或公开提交。提交问题或改进时，请使用合成数据并附可复现步骤。

## 开发验证

编排输入使用 `constraint_sources` 记录硬约束依据；旧输入未记录来源时，须补齐后重新生成才能正式导出。项目优先、优化目标、前移验收及参数见 [时间与场地编排](gamemaster-skill/references/time-court-scheduling.md)。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
node tests/test_ptty_site_guard.mjs
python3 tools/release_check.py --staged
```

这些合成测试覆盖编排休息与依赖、局部优化、导出验收，以及运动身份、网站入口、公开链接与发布脱敏边界，不访问线上赛事。提交前检查实际暂存内容；检查方式及限制见 [发布检查](tools/README.md)，更新记录见 [CHANGELOG](CHANGELOG.md)。
