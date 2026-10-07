# 跑兔操作目录

本目录将用户意图映射到业务入口、读写性质和验收。机器目录 [operations.json](operations.json) 记录31个功能域、109类操作；它是导航与预检知识，不是可直接执行的后端SDK。先检索，按结果读取相关参考，不必一次加载全目录。

## 查找与预检

```bash
python scripts/operation_catalog.py search "调组"
python scripts/operation_catalog.py search "比分"
python scripts/operation_catalog.py show schedule.move
python scripts/operation_catalog.py validate
python scripts/operation_catalog.py preflight 赛事工作区/操作预检.json
```

搜索是标题、模块、接口名的关键词召回（多个词用空格），不是自动理解/执行。先按[意图与状态](intent-and-state.md)消除歧义，再选择确切的 operation ID。例：

```json
{
  "mode": "requested_changes",
  "operations": ["schedule.move"],
  "facts": {"target_identity": true, "role_access": true, "matches_present": true,
            "move_scope": true, "scheduling_valid": null}
}
```

`facts` 只放本次证据支持的布尔值：true已满足、false不满足、null/缺省未知；不放账号和人员资料。预检将未知项列为待补读，将不满足项列为阻塞，不代替算法验收或用户授权。`readonly` 默认模式禁止写入、通知、扣费、账户操作和AI外部计算；`requested_changes` 也只生成预检报告，不执行或宣告获准，不自动补上扣费、清空等前置操作。

字段含义：`route/component/op/methods` 定位页面合同；`requires` 需确认的业务事实；`impacts` 变更后复核范围；`acceptance` 验收目标。标注“当前合同”的条目尚未有足够参数证据，必须继续从页面核验。混合接口如增改删、查询/编辑须选择正确模式；不能把目录中的接口名直接全部调用。

还要确认当前可见入口确实绑定所读方法；残留组件、旧对话框和无调用方的方法不能单独证明功能可执行。人员替补的旧接口与当前人员编辑方法见[现场操作](live-operations.md)，`roster_current_entry_verified`须包含本次入口绑定和副作用核验，不能只凭脚本中存在方法名置为真。

## 页面与任务

|入口|任务与需要的参考|
|---|---|
|`/trialMainNavIndex`、`/index`|运动模块、赛事查询、创建/编辑/复制/删除；[网站身份](website.md)、[创建发布](publication.md)|
|`/trialReportIndex`|报名组别、资格限项、费用、人员/单位/项目/团体、白黑名单、会员优惠、交易；[现场操作](live-operations.md)|
|`/trialGhIndex`、`/trialRmdGlIndex`|竞赛方案、阶段计分排名、人数同步、最终名单及锁定；[平台流程](platform-workflow.md)|
|`/trialScGlIndex`、`/trialCqIndex`|生成或重置比赛场次、分组容量、种子和签位；[平台流程](platform-workflow.md)、[文件交接](handoff.md)|
|`/trialSsBpIndex`|网格/场序、自动或自定义编排、移动、清空、小节；[平台流程](platform-workflow.md)、[小节发布](publication.md)|
|`/aiSchedulePage`、`/trialAiGlIndex`、`/chatBotIndex`|AI候选、应用结果、知识库案例、AI聊天/创建；计算与保存分开|
|`/trialScreenSet`|各端控制、小节开放、通知、二维码、签名和弃权等设置；[现场操作](live-operations.md)、[二维码](qr-codes.md)|
|`/qdGlIndex`、`/trialKongChangGlIndex`|签到、控场、调场、团体名单、比分、弃权、呼叫；[现场操作](live-operations.md)|
|`/trialCdGlIndex`、`/trialClientSet`|报表生成下载/格式、积分、富文本、公开可见性；[只读报表](read-only.md)、[创建发布](publication.md)|
|`/trialCerGlIndex`|证书底图与文字坐标工具；坐标完成不代表已颁发证书|
|`/trialSsidCpyGlIndex`、`/trialCpyGlIndex`|赛事授权与全局裁判资料；[现场操作](live-operations.md)|
|`/childZhGlIndex`、`/userManagementIndex`|子账号/用户、锁定及密码管理；账户级任务单独定位|
|`/trialCwGlIndex`、`/trialShopIndex`、`/trialPtFzIndex`、`/trialJsrGlIndex`|财务查询、充值、分账、收款商户；查询与付款/绑定分开|
|`/trialBmjlGlIndex`|跨赛事报名与交易统计，先限定赛事集合再查询|

显示路由族：`/trialScreenIndex`、`/trialScreenIndexJdms`、`/trialScreenIndexN`、`/trialScreenIndexNJxp`、`/trialScreenIndexTaiWan`、`/trialScreenIndexNDcLbp`、`/trialScreenIndexWap`、`/trialScreenIndexWapStart`、`/trialScreenZbpIndex`；检录路由族：`/trialScreenJlIndex`、`/trialScreenJlIndexN`、`/trialScreenJlIndexNGD`、`/trialScreenJlIndexJd`。按当前菜单链接取实际大小写和参数，不能凭名称拼接入口；带检录、通知按钮的显示页并非全页只读。

`/trialCenterIndex` 会员中心查询充值、核销与余额，使用 `payGl/centerJyjl`、`centerKkjl`；充值操作另走充值页。`/trialCxIndex`、`/trialXxCqIndex` 当前静态实现未足以证明对应查询/线下抽签业务可用；查不到实现时转到已核验的报表、抽签页，不编造接口。`/test`、`/demo`、`/helloword`、`/webSocketExample` 是开发/演示入口，不作为业务完成路径。

## 当前实现的证据与陷阱

核验日期2026-10-07，当前官方羽毛球后台资源 `/static/js/app.1073f5c6401c322ed993.js`；SHA-256记录在JSON。已只读观察当前账户16个业务子页面及报名8个标签，核对菜单、字段和显示选项。目录动作证据保守标记 `static`：看到页面不等于测试其中全部动作。已验证的文件回读见专题参考；当前模块、角色及服务端变化后需重新验证。财务/分账/银行商户/全局用户等未出现在本账户菜单中的入口，仅保留代码证据，不绕过权限访问。

- **`/trialStepGlIndex` 创建比赛向导**：导入填入模拟人员，抽签/编排使用本地数组及延迟，开赛只改变本地状态。不能用它完成实际导入、抽签、编排或开赛。
- **`/trialCheckGlIndex` 比赛检查**：`callApi` 用 `Math.random()` 生成通过状态、数量及未开放数；`startMatch` 提示成功后跳转控场。这些值不能进入验收证据。
- 组件名有重复：赛程管理和赛事编排都叫 `TrialSsBpIndex`；首页/赛事列表都可叫 `Index`；财务和裁判库也有同名组件。定位须联合路由、组件方法、赛事和运动，不按组件名一项决定操作。
- 当前运动首页对羽毛球进入 `/index`，乒乓球/匹克球走另外的单点跳转，其他分支提示未开放。本目录不能直接套用于乒乓球、匹克球或网球后台。
- 页面开关可能立即保存；查询/编辑共用一个方法；生成候选也可能保存历史。禁止为“遍历功能”依次点击所有按钮。
- 方案页“生成赛程”实际调用 `scGl/czSc` 的 `type=create`，页面提示会清空赛程和编排，不能当成只新增。充值页 `getBmPayZjeHandler` 查询金额后继续 `payHandler` 创建订单，不能因为函数名带get就作为只读工具。赛事列表“确认对账”也会写入状态。
- 赛程管理“导出所有场次，更新赛号”是带更新语义的导出，不能并入只读白名单；是否改变赛号、CCH或其他映射需前后回读确认。只看现有场次时使用出单管理场序表，不触发此按钮。
