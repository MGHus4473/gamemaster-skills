# 创建、图片、内容与发布

依据 2026-10-06 客户端 `app.60686ba611d579bcc83d.js` 与实际提交、后台及公开端回读。已验收图片上传、既有赛事编辑、SSGC规程与SSZN通知保存、ISZXC秩序册与ISJMD节目单发布、指定项目完整`saveSet`保存及已知报名原值恢复，以及两个小节的场序分配和手机端开放。该证据不覆盖ADD新建、其他内容/报表类型、裁判端或出场名单端开启；这些仍须按具体任务执行并核验。获授权的任务沿用授权范围，不把本地预案成功说成线上成功。`ptty_readonly.mjs` 始终只读。

2026-10-07补充：新版`app.1073f5c6401c322ed993.js`已实际ADD一个隔离合成赛事，同名全量查询确认新增唯一对象；表单`QSLXID:"1"`与当前羽毛球枚举一致，列表及编辑回读却为`"0"/乒乓球`。完整页面表单UPT返回成功仍未修正。用户允许不影响功能的异常保留后，继续完成4人淘汰流程验证，详见[流程验收](recovery-and-testing.md#流程与意图回归)。其中小节先只开放手机端，再开放裁判/控场端，均检查其余开关不变；未验证实际微信裁判操作或出场名单端开启。原始运动差异仍存在；其他操作不因此自动通过，按[运动身份例外](website.md#运动身份检查)限定范围。

## 先分清目标

|用户要做的事|实际载体|
|---|---|
|新建赛事、换赛事logo/主页图|赛事管理 → 赛事操作表单；图片上传后还需保存赛事表单|
|填写规程、报名说明、补充通知、参赛确认书|客户端设置中的独立富文本；提交修改即写入对应内容，不是通用草稿箱|
|发布秩序册、成绩册、名单、抽签、节目单|客户端设置的逐项目可见开关或一键发布；展示系统已有数据|
|发布自行排版的Word/PDF|当前入口未证实有通用文档附件上传；先交付文件。可以另选用户指定托管链接或经审核的文本/图片形式，不假装替换了系统秩序册|
|划分小节、对各端开放小节|赛事编排里分配场序范围；比赛控制里分别开放裁判、手机和出场名单端|

用户只要求准备文件或验证能力时保持只读；明确要求发布时，沿用该次授权范围，核对内容版本、目标赛事、项目及受众即可执行。强制弹窗、头像公示、微信消息发送各有独立影响，不由普通报表发布自动推定。

## 赛事创建与图片

1. 在赛事管理检查同名赛事及日期/场馆，避免已有创建请求超时后重复新建。按[运动身份检查](website.md#运动身份检查)核对当前模块、表单枚举和目标元数据，不能把静态默认 `QSLXID:"1"` 当全部运动的映射；冲突未解决时不生成或执行相关写请求。
2. 填 `SSMC` 名称、`cityId` 两级实际区域ID、`CGMC` 场馆、`CDSArray` 场地号、`STARTDATE/ENDDATE`（YYYY-MM-DD）。当前场地选项1—35；`SSLX` 是项目类型集合，不能与运动大类混用。
3. 节目安排明确 `JMDLX:"0"`按时间或`"1"`按场序、`BSSJLX:QT/AM/PM/EM`、`MCFZS`每场分钟及`JMDLIST`。每个区间为`QJLXID/QJLXMC/QSDATA/JZDATA`；时间用HH:MM。创建页面初始模板为上午08:00—11:00、下午13:00—17:00、晚上18:00—22:00，场地初始1—10、每场30分钟；这些只是初始值，应改为本场已确认安排。
4. 联系人`SQLXR/SQTEL`为可选。普通任务不启用身份收费认证、直播或团体兼项等未要求的扩展。按场序的初始化`QSDATA/JZDATA`都为场数文本，当前编辑处理函数却带时间冒号判断；新场序配置需在当次页面验证，不承诺该历史前端无此缺陷。
5. logo最多1张、主页背景最多3张；实际接收JPEG或PNG，单张**严格小于512000字节**。提示文案“只能JPG”与实际判断不一致，以当前校验及回读为准；未观察到固定像素尺寸或比例要求。保留原图，需要调整时另存副本并检查实际显示。
6. 图片选择会立即上传到`trialUploadImage`。成功的`content.filePath/filePath_ys/url`分别进入表单图片记录`IMGPATH/IMGPATH_YS/url`；不要伪造路径。上传成功不等于已绑定赛事。提交表单前用当前数据保存其余字段；提交后只读`getSsList/getEditor`核对新SSID、名称日期场地与图片，再看客户端显示。

创建请求合同：`headerData:{ssid:"",op:"ssGl",methodName:"insertOrUpdateOrDeleteSs"}`，`busData`为完整表单，`TYPE:"ADD",SSID:"ADD"`；编辑用`TYPE:"UPT"`与真实SSID。`CDS`由场地号组成带尾逗号的文本。`ssGl/getCityList`读取区域选项；`ssGl/getEditor`的`busData:{ssid:明文赛事ID}`读取既有完整表单。只读调查不调用创建权限检查、提交或上传来“试试看”。

`getEditor`原始响应不是可直接重交的页面表单：实际编辑器会补充`cityId`等字段，提交前按当前编辑器转换核对完整模型。字段补齐只能修复请求形状，不代表运动身份异常已解决；以回读值为准。

## 富文本规程与补充通知

客户端`TrialClientSet`的`clientSet/mainLoadData`返回当前内容、项目列表、可见性与报名设置。规程内容由离线skill制作和审核，本skill只转换必要的富文本载体并核对发布版本。

|按钮/内容|TYPE及内容字段|额外选项|
|---|---|---|
|填写赛事规程|SSGC|无独立“发布规程”按钮证据；提交修改即保存|
|填写报名内容|BMNR|保留与规程一致的报名条件|
|补充通知|SSZN|ISQZSHOWTCC为0/1，是否强制弹出|
|参赛确认书|CCQRS|不与通知混写|
|手机端自定义九宫格通知|ZDYNR|ZDYICONTXT为图标名称|

进入对应编辑器，插入本次确认的文字/表格/图片；核对标题、版本、日期、让分/并组条款和落款后点击“提交修改”。保存调用`clientSet/saveEditor`，`busData:{EDITORHTML,TYPE,ISQZSHOWTCC,ZDYICONTXT}`。**每一种TYPE都会带两个全局选项**，只改规程也须先读取并保留当前弹窗和图标名。报名设置下的`ISSHOW`、项目报表开关与富文本保存分别核验，不声称保存就是所有受众可见。

编辑器为HTML载体，非Markdown/LaTeX解释器。本地纯文本应HTML转义并保留换行；HTML使用正文片段，不直接塞完整网页、脚本或本地文件URL。富文本图片同样上传`trialUploadImage`，字段`file`；当前编辑器单图上限8MiB、每次最多6张、超时180秒、禁止base64直接保存。上传后插入`mainUrl+"images/"+content.filePath_ys`。6是单批上传数量，不是整篇最多6张；没有固定像素限制证据。

保存后再次调用`mainLoadData`比较对应HTML、图片URL和全局选项，再用真实客户端查看可见性和排版。首次写入前后应比较完整相关设置，不能只查目标正文：已观察到后台将既有空字段初始化为默认值，但未单独采样时不能断言由哪一步触发。对这类非任务变化，在授权任务范围内用最新完整表单恢复已知原值，再回读确认，不覆盖其他新变化或猜测原值。已观察到服务器仅移除HTML末尾、最外层的换行LF：先做完整字符串比较，若不等则记录差异，只有确认差异全部位于最外层空白时才可归一后比较；正文、标签、属性、内部空白和图片URL仍须严格一致。不得为消除这种末尾差异盲目重复保存。补充通知引用所修改的规程版本及条款；强制弹窗不是微信消息推送。不要把临时报表的带签名下载链接放进公开HTML。

## 系统报表发布

`XMLIST`中的项目以XMID定位，`ISZXC/ISCJC/ISGSMD/ISGSCQ/ISJMD`分别控制秩序册、成绩册、名单、抽签、节目单。

- **只改指定项目**：逐行设置所需列，其余不变，再“保存设置”。请求`clientSet/saveSet`携带完整`setInfo`，包含报名日期/模式、内容、总显示设置和整个XMLIST；先刷新快照，避免用部分旧值覆盖其他设置。读响应`ISGRBM/ISLDBM`两个字段必须齐全，且均为字符串`""/"0"/"1"`；忠实复现页面转换：`('1','1')→ALL`、`('0','1')→LDBM`、`('1','0')→GR`，其余合法组合保持空模式。已实际遇到`('','')`和`('','1')`，不得将原始空值强转为关闭或开启；其他类型/值仍拒绝。`ISSHOW`直接原样保留；标签“是否对客户端显示”不证明空值等于否，也不证明后台开关已决定QR直达入口的可见性，仍须公开端核验。
- **全项目发布所选报表类型**：打开“一键发布”，明确选择类型，然后发布或取消发布。`clientSet/saveYjfbData`携带`{type:"1"或"0",dataArray:[类型...]}`；没有项目子集参数，不能拿来只发布一个组。
- “是否公示头像照”选择项绑定`setTxImg`，改动会立即写入，不等最后点击一键发布。只读浏览时不得试切换。普通秩序册发布不自动授权增加头像公示。
- 发布之前下载同版报表，核对项目阶段、人数、签位、日期场地和已确认成绩。之后回读全部XMLIST相应开关并核实实际客户端入口；没有比赛数据时打开开关也不能补出不存在的秩序册。

自定义文档链接或图片只能通过明确选择的富文本内容位提供，不替代上述系统报表开关。撤回指定类型同样须核对范围，并保留其他已发布类型。

## 公开端回读

从实际赛事二维码获取入口及ssid，保留原协议、域名和路径。已实际确认同域HTTP与HTTPS的`/wap/`返回不同应用：HTTP入口能回读手机端数据，HTTPS入口返回后台应用。不能强制替换为HTTPS，或把替换协议后的空白归因于未发布；打不开时检查实际页面资源和路由。以下合同来自手机端`app.64c9eb671611156b6035.js`，变更部署后须重新核对。

公共页面使用`wapGL`，请求头ssid为二维码中原值。`sendPost`向`http://wap.ptty.com.cn/trialWapApi`发送已有客户端封装，勿误用`trialWriteApi`。沿用页面工具时不需要自行实现认证；若独立回读，按已观察合同封装：`inner=Base64(UTF8(JSON(paramData)))`，再发送`Base64(UTF8(JSON({paramData:inner,mac:MD5(inner+"trialSystem000000000001")})))`，Content-Type为`application/x-www-form-urlencoded`。

|核验对象|methodName与busData|比较内容|
|---|---|---|
|规程、补充通知|`getSsxx`；`{pageSet:{currentPage:1,pageSize:10,totalNums:0},search:{info:"",qslx:"",bszt:"",ssid}}`|`content[0].SSGC/SSZN`对应`/ssgcIndex`、`/ssznIndex`正文；名称、图片及正文版本也核对|
|秩序册项目入口|`getAllXmData`；`{}`|`content`每项目`XMID/SSZL/ISZXC`；页面要求ISZXC为字符串`"1"`|
|秩序册内容|`getZxcData`；`{XMID,SSZL}`取自上一响应|`content`实际对阵和`lsData.XMLIST/LZGZID`，不只检查开关|
|节目单与小节|`getJmd`；`{ryInfo:"",pageSet:{currentPage:1,pageSizeS:[20,50,100,1000],pageSize:6,totalNums:0},wapIsks:[],selectedDate:""}`|逐页读取到`totalCount`，核对场序格、日期时间、场地与`lsData.XJKZLIST`；`getTrainDate`的空busData读取比赛日期|

节目单`wapIsks:[]`对应页面“全部”；默认`["0","1"]`仅未开赛和比赛中，不能据此判断全部比赛已显示。小节`SHOWLX:[]`在该手机端解释为全部字段可见；非空列表按RQ/SJ/CXH/CDH筛选，未匹配小节不显示这些字段。公开首页及上述报表组件未直接使用赛事级`ISSHOW`或`ISJMD`做显示判断；后台如何筛选仍以真实返回为准，不据静态代码扩大可见性结论。

## 小节分配与各端发布

1. 先完成编排导入与回读，`bpGl/getCxList`的`content[].CXH`给出当前真实可选场序。导入并不自动完成小节；本地空场序可能已被平台省略，不能从本地时间索引直接猜CXH。
2. 赛事编排的“小节/起始序号/截止序号”选择实际范围，点击“生成小节”。当前小节选项1—50；写请求`bpGl/createXj`为`{node,startCxh,endCxh}`，是给既有编排分配小节，不生成比赛。跨日/午休与场序关系先核对，多个范围不重叠；覆盖既有小节时明确本次调整范围。
3. 分页回读编排，核对范围内每场CCH的XJ和`lsData.ALLDATA.noXjCount`，再读取比赛控制`trialItemGl/getXjs`的`content.listXj`。
4. 比赛控制三个开关分别为`ISQY`裁判端（控场、大屏同步）、`ISWAPQY`手机端、`ISCCMDQY`填写出场名单端；这些开关**一改就保存**，无统一提交按钮。手机端开启后可选显示字段`SHOWLX:[RQ,SJ,CXH,CDH]`；空数组的界面提示为“全部显示”，实际展示仍要回读检查。
5. `setXjData`总是同时提交三类状态：`{xjs:"1,",type:"ADD"或"DEL",ISWAPQY:"1,",wapType:"ADD"或"DEL",ccmdType:"ADD"或"DEL",SHOWLX:"[\"RQ\",\"SJ\"]"}`。只改手机端也必须保留裁判/名单端状态，SHOWLX是JSON数组字符串。发布后读`getXjs`并分别检查授权开放的客户端；生成小节不等于已发布，关闭某一端不等于删除小节。

## 离线发布包

`scripts/publication_packet.py`仅准备和校验本地数据，没有网络传输或执行开关。依赖Python3.10+；含图片时需Pillow。文件放赛事资料目录，路径相对输入JSON所在目录且不能越界：

```bash
python scripts/publication_packet.py prepare publish-spec.json 新发布包目录
python scripts/publication_packet.py validate 新发布包目录/publication-packet.json
```

顶层：`schema_version:1,event:{id,name,sport},source_version,baseline,assets,operations`。新建时id为空且仅做create_event；创建回读取得真实ID后再准备内容与发布包。既有赛事baseline含同一`event_id`、`captured_at`，按操作加入`client`（mainLoadData原content）、`event`（getEditor原content）、`sections`（getXjs的listXj）、`scene_numbers`（实际CXH整数）。快照用于生成预案，实际执行前再刷新比较，哈希并不代替授权或实时一致性检查。

执行前补充`sport_identity`：`{source:"current_page",captured_at:"实际采集时间",page_url:"https://www.ptty.com.cn/#/实际路由",module_sport:"badminton",selected_id:"页面选中的值",options:[{id:"页面选项值",label:"羽毛球",sport:"badminton"}]}`。记录当前真实选项，`page_url`只保留无查询参数的页面路由。默认要求已有赛事`baseline.event.QSLXID`或新建`fields.QSLXID`与选中值相同，`QSLXMC`与任务运动一致；已有赛事已核实的显示缺陷可使用下述例外。缺少现场证据的预案标记`unverified/write_blocked`；一致时标`observed_consistent/requires_live_recheck`。`valid:true`不表示允许线上写入。

元数据例外：在`sport_identity`加入实际`client_sha256`及`metadata_exception`：

```json
{
  "event_id": "SYNTHETIC-EVENT", "user_authorized": true,
  "observed": {"QSLXID": "原始异常代码", "QSLXMC": "原始异常标签"},
  "client_sha256": "与现场证据相同的64位小写SHA256",
  "verified_operations": ["materials_all"],
  "reason": "具体缺陷及不影响本次操作的依据",
  "evidence_reference": "赛事工作区/本次功能回读记录.json"
}
```

上例是字段说明，须换成实际证据。`verified_operations`使用本表的`operation.kind`，只列已实际验证的功能；不能因方案或名单导入成功就填写内容发布也已验证。用户已接受当前缺陷时沿用授权，不重复要求确认。工具核对赛事、原始异常、客户端哈希及操作范围，输出`accepted_metadata_exception`，仍要求实时复核。例外不适用于新建表单、缺失代码、错误模块/选项，也不修改原始回读。工具无法独立证明证据真实性。尚未验证的下一步只能在用户授权的隔离测试范围内逐步实测，不能借用该例外直接认定正常。

|operation.kind|字段|
|---|---|
|create_event|fields为已确认创建字段，logos/backgrounds为资产ID数组；记录所用表单默认项|
|set_event_images|logos或backgrounds为要替换的完整列表；未给的列表保留，空数组表示明确移除|
|editor|field为上述TYPE；path指向UTF-8片段，format为html/text；SSZN可带force_popup布尔值，ZDYNR可带icon_name|
|material_flags|changes:[{project_id:实际XMID,flags:{ISZXC:true}}]，只改指定项目|
|materials_all|scope:"all_projects",types:["ISZXC"],visible:true/false|
|section_assign|section/start_scene/end_scene为整数，必须使用当前CXH范围|
|section_visibility|section及要改的referee/mobile/lineup布尔值、show_fields数组；未给的保留当前值|

资产为`{id,path,role}`，role选`event_logo/event_background/editor_image`。HTML内用`<img src="asset:图片ID">`引用尚未上传的正文图；本地包校验真实JPEG/PNG、字节数和尺寸，记录像素尺寸而不编造平台比例要求。输出保留待绑定项；未来上传后用真实响应替换，不能把`asset:`或`$uploaded_asset`当可用URL提交。图片批量上传按编辑器每批6张执行。

请求模板中的`$current_page.ssid`绑定已核对赛事的当前页面值，不自行将明文ID或编码字符串混用。图片绑定要检查**整个包的每一个请求**：稍后的完整`saveSet`可能再次携带前一个editor的HTML，脚本会传播`pending_asset_ids/pending_bindings`。保留源预案，所有占位引用替换为真实回执后另存执行版本，不只替换第一处。

新建包必须先创建并回读，新增小节必须先分配并回读，再根据真实listXj准备发布包。baseline和完整表单预案可能带既有正文、联系人等个人信息，只在本任务受限赛事目录保存必要副本，不放skill、公开测试或发布文件。packet校验检查文件及内容哈希，不证明线上创建、上传或发布通过。执行回执另存前后快照、实际请求范围及逐字段差异；若服务器同时初始化既有空字段，须记录该变化，不能声称所有非目标字段均未变。超时先只读查结果，再决定是否重试。
