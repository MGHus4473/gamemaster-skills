# 规程输出

先按 [规程制定](regulations.md) 完成信息询问与业务检查，措辞采用 [专业表述](regulation-language.md)。转换工具负责排版，不判断条款是否合理或赛事是否可行。生成 Word 时先读 [Word版式](word-formatting.md)；用户模板优先，默认样式不冒称法定公文标准。

## 格式能力

| 选择 | 交付及当前脚本范围 |
|---|---|
| Word | 可编辑 `.docx`；分级标题、正文/导语/落款/注释、显式编号条目、固定宽长表、附件另页、页眉及页码域。 |
| Markdown | UTF-8 `.md`，保留全部标题、条目编号、表格、附件及正文；编号和元字符按纯文本转义，避免自动重编号或误成HTML。分页以注释保留，字体/页边距不适用。 |
| 文本 | UTF-8 `.txt` 或直接贴正文；表格转为带字段名的逐条记录，显式条目编号保留，分页用换页符表示；无字体/缩进/列宽版式。 |
| PDF | 旧的一级章节＋普通段落/普通表格输入可用本地ReportLab生成可检索PDF；新分级条款、附件或自定义版式在此后端明确拒绝。高级Word内容应在本地办公软件导出PDF后逐页检查，或另行实现相应PDF排版。 |
| 直接LaTeX渲染 | 旧的简单输入可实际编译交付 `.pdf` 和 `.tex`；新结构或自定义版式明确拒绝，不能删内容后声称已完成。仅源文件不算渲染成功。 |

多选时共用正文。MD/TXT保留语义，不模拟Word分页；其他格式不得静默丢失不支持的块、表格属性或附件。Word标签可用于“开幕式致辞”“闭幕式致辞”“规则解读”等；不能因为换文件类型而忽略它的内容要求。

## 内容JSON

`scripts/render_regulations.py` 接收内部排版中间文件，不让用户手填。保持原有 `title/status/pending/sections[].heading/blocks[]` 合同兼容；旧块为 `paragraph` 与 `table`。

```json
{
  "title":"示例赛事竞赛规程",
  "subtitle":"草案-v1",
  "status":"draft",
  "pending":["确认具体场馆地址"],
  "sections":[{
    "heading":"一、时间与地点",
    "blocks":[
      {"type":"paragraph","text":"比赛地点：【待确认：具体场馆地址】"},
      {"type":"heading","level":2,"text":"（一）参赛要求"},
      {"type":"clause","level":1,"label":"1.","text":"参赛项目按已审核报名项登记。"},
      {"type":"table","caption":"表1 项目与名额","headers":["项目","名额"],"column_widths_mm":[110,50],"rows":[["男子单打","16人"]]},
      {"type":"paragraph","style":"issuer","text":"示例赛事组委会"},
      {"type":"paragraph","style":"date","text":"2026年10月6日"},
      {"type":"appendix","title":"附件1：报名说明","blocks":[{"type":"paragraph","text":"以已确认报名渠道接收材料。"}]}
    ]
  }]
}
```

顶层字段：

- `title`：非空单行标题；`subtitle` 可选，适合版本说明；`document_label` 可选，默认“竞赛规程”。草案额外显示明显标记，不能用标签掩盖草案状态。
- `status` 为 `draft` 或 `final`。`pending` 为待确认文字数组，正式稿须为空；草案清单最后单列“编制备注”。占位检查是辅助，不能代替必需信息核实。
- `sections` 为有序数组，每节包含单行 `heading`、可选标题 `level:1|2|3`（默认1）和非空 `blocks`。
- `word_style` 为可选Word样式覆盖对象，字段与默认 [样式资源](../assets/regulation-word-style.json) 一致，详见Word版式；不会把样式配置当正文发布。

块类型：

| `type` | 字段与行为 |
|---|---|
| `paragraph` | `text`；可选 `style` 为 `body`（默认）、`lead`、`issuer`、`date`、`note`。源换行在Word生成真实段落。 |
| `heading` | 单行 `text`、`level:1|2|3`；表示章节层次。 |
| `clause` | 单行 `label`、`text`、`level:1|2|3`；明确编号，不自动改号。`level` 表示条目嵌套，与标题层级分开；Word悬挂缩进，MD显式编号转义。编号不能靠首尾空格对齐。 |
| `table` | `headers`、`rows` 为纯文本；每行列数一致，空单元格用“—”。可选单行 `caption`、逐列 `column_widths_mm`、`allow_row_split` 布尔值。默认固定均分列宽、重复第一行表头、禁止拆分单行。 |
| `page_break` | 仅含 `type`，明确换页；不靠多个空段落推到下一页。 |
| `appendix` | 单行 `title`、非空 `blocks`，Word另页开始。附件内可有标题、条目和表格；不支持嵌套附件，用内部标题表达层次。 |

文字字段是纯文本，不混入HTML、Markdown标记或任意LaTeX命令；特殊字符由输出后端转义。未知字段/块会报错。脚本不支持图片、签章、复杂自动编号、合并单元格、复合表头或任意docx模板导入；有这些要求时使用相应文档工具并回读核验，不能丢弃要求。

## 执行

在skill根目录执行，输出放赛事文件目录，目标必须尚未存在：

```bash
python scripts/render_regulations.py 规程.json --format docx --output 规程-v1.docx
python scripts/render_regulations.py 规程.json --format docx --output 规程-用户版式-v1.docx --style-profile 用户样式.json
python scripts/render_regulations.py 规程.json --format md --output 规程-v1.md
python scripts/render_regulations.py 规程.json --format txt --output 规程-v1.txt
python scripts/render_regulations.py 简单规程.json --format pdf --output 规程-v1.pdf --font-file /path/chinese.ttf
python scripts/render_regulations.py 简单规程.json --format latex --output 规程-latex-v1.tex --cjk-font "Droid Sans Fallback"
```

Word默认中文正文宋体/标题黑体、西文Times New Roman。`--cjk-font` 同时替换Word两种中文字体，`--latin-font` 替换西文；分别配置标题字体用样式JSON。字体未安装时明确替代并复核，不假设输出声明等于真实渲染。`--style-profile`/`--latin-font` 仅适用于Word，不静默应用到其他格式。LaTeX默认中文字体仍为Droid Sans Fallback，可显式指定。

## 依赖与验收

- MD/TXT：Python 3标准库。Word：Node.js及 `docx` 包，可通过 `NODE_PATH` 指向本地依赖目录；不把node_modules打包入skill。
- PDF：`reportlab` 及中文TTF字体，使用 `--font-file` 或 `GAMEMASTER_FONT_FILE`。这一后端不是Word分页预览。
- LaTeX：本地XeLaTeX/Tectonic及ctex、geometry、longtable、array和字体。Tectonic强制 `--only-cached --untrusted`；`--tex-bundle` 只接受已有本地文件，不在离线运行阶段联网下载。其他引擎关闭shell执行。
- 缺少依赖时完成可生成格式并说明未完成的格式。编译失败保留tex和日志，不将源文件称为已渲染PDF；成功后检查缺字、溢出和实际页数。

回读日期、费用、资格、晋级、奖励、表格末行与附件末段，核对所有格式内容一致。Word先检查OOXML结构，再尽可能用Word/WPS/LibreOffice渲染逐页预览；缺少办公软件时明确仅结构检查通过。PDF逐页检查文字可检索、字体无缺字、表头和页码正常。正式稿不留草案/待确认项。返回实际文件链接、状态及尚待确认项；生成文件不等于已发布。
