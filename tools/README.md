# 发布检查

`release_check.py` 使用 Python 标准库，在发布前检查两个 skill、空白模板、公开工具和合成测试。它不会上传文件，也不会输出匹配到的敏感值。

```bash
# 开发目录：仅检查公开白名单；本地赛事 docs/ 留在本机。
python3 tools/release_check.py

# 独立发布目录：额外检查目录边界与实际暂存的 Git 内容。
python3 tools/release_check.py --root . --staged --strict-tree

# 回归检查：测试全部使用运行时生成的虚构数据。
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_release_check.py'
```

白名单包含 `gamemaster-skill/`、`ptty-skill/`、`tools/`、`tests/` 和根目录的 README、CHANGELOG、LICENSE、`.gitignore`。其他路径不应进入公开提交。默认模式只扫描白名单；`--strict-tree` 额外拒绝发布目录中的其他顶层文件。`--tracked` 按已跟踪路径检查工作区，`--staged` 检查将要提交的实际索引内容，能发现已暂存后才从工作区清掉的凭据。

检查内容包括账号、密码和会话的非占位字面量，常见令牌、签名链接、真实平台编号、本机个人路径、手机号和身份证号；也检查 ZIP/XLSX/DOCX 内部文本、作者及自定义元数据。未审阅的二进制、软链接、加密或超限压缩包会阻止发布。通用变量名、网站入口、空白表格标题不当作凭据。

可用 `--report <本地报告路径>` 保存只包含路径、规则和行号的结果。若有已知赛事名、人员姓名或其他专有值，在不发布的本地文件中逐行列出，使用 `--denylist <本地文件>` 补充检查。自由文本姓名、图片里的个人信息及刻意隐藏的秘密仍需人工审查；检查通过不能代替对每个拟提交文件和新仓库历史的确认。
