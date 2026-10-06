# 本地运行环境

业务计算不联网，也不依赖跑兔。离线使用前安装所需依赖、字体和文档工具；skill文件包不内嵌Python、Node、浏览器或大型字体。使用本机解释器/虚拟环境，不使用历史研究环境的绝对路径。

| 功能 | 依赖 |
|---|---|
| 对阵、抽签、排期、成绩计算；JSON/CSV/MD/文本 | Python 3.10+标准库 |
| XLSX模板、名单、报名调整、表格导出 | Python openpyxl |
| Word | Node.js 20+与docx包（package.json列依赖），中文字体 |
| PDF | Python reportlab、包含所需中文字符的TTF字体 |
| LaTeX PDF | 本地XeLaTeX或Tectonic，ctex等宏包与字体已缓存；仅本地编译 |
| 旧XLS/图片/扫描PDF输入 | 按输入实际需要准备xlrd、本地PDF/OCR或可用视觉读取能力；不将读取失败当空表 |

```bash
python scripts/check_runtime.py --feature core
python scripts/check_runtime.py --feature xlsx
python scripts/check_runtime.py --feature pdf --font-file /path/chinese.ttf
python scripts/check_runtime.py --feature docx
python scripts/check_runtime.py --feature latex
```

`requirements.txt`列Python输出依赖；Word依赖见`package.json`。可在联网准备阶段安装到虚拟环境，或把wheel/Node依赖/TeX缓存预先带到离线机器；运行阶段不自动安装或发起网络下载。用户提供图片时所需识别能力与计算引擎分开说明。

Tectonic执行时启用`--only-cached --untrusted`；`--tex-bundle`只接受本地文件。缓存缺失则保留tex与构建日志，明确未渲染，不能调用在线转换来绕过离线要求。Word的Node依赖可通过本地`NODE_PATH`指定；不把个人依赖目录硬编码进脚本。

默认名单模板支持单打/双打，团体须使用对应模板并展开已确认子场；复杂团体阵容、双败、前8之外的全名次赛等先扩展并验收。排期使用统一时间网格，每场占一个格，长场先选择合适网格；不缩短网球预计时长来强行适配15分钟。未实现的特殊约束如教练资源、复杂阵容等须明确建模后验证，不能仅写备注就声称已满足。

规则资料离线时使用已有确定版本；需要核对后来变更的官方规则时，由用户提供规则文件，或在允许联网的准备阶段核验后保存版本。文件制作和业务计算仍可全程离线。
