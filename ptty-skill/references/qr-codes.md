# 二维码导出与本地定制

“比赛控制”当前有三个不同用途：

|用途|来源|处理|
|---|---|---|
|比赛二维码|`trialItemGl/generateQrCode`，返回 `qrCodeBase64、url`|标准QR；采用平台返回的真实观赛网址，允许本地重建与定制|
|裁判端二维码|`ssGl/getCpyTwoCode`，`ssidEn` 取当前会话赛事值|微信小程序码；下载平台原图，保留码体，不用普通QR替代|
|PAD裁判员端码|`ssGl/getPadTwoCode`|样例为内容仅有明文 SSID 的标准QR；按原用途导出，不当观赛链接|

赛事管理列表的“成绩查询二维码”在所查前端是固定图片入口；不能据它猜出某场专属链接。比赛QR与裁判码用途不同，公开物料不默认放裁判入口。尚未核验观众专用微信小程序码入口；用户要“小程序端码”时先按用途区分，不把裁判小程序码冒充观众码。

观众二维码保留平台返回的原始协议、路径和赛事参数；不要自动升级HTTP为HTTPS。工具检查官方手机入口和路由后才保存平台观众网址，详细部署异常处理见[网站信息](website.md)。此地址检查与图片解码不能证明手机页面实际可访问。生成URL二维码或处理已有URL码时均拒绝登录凭据、临时下载签名和令牌参数，不把这类链接印到公开物料中。

## 排版

原图按文件魔数保存：PNG用`.png`，JPEG用`.jpg/.jpeg`。已实测裁判码返回JPEG，不能因不是PNG判为接口失败；也不能只改扩展名冒充另一格式。下载工具检查魔数与后缀，交付前再用图像库完整解码。文件可打开不等于微信扫码已通过。

Python依赖：`qrcode、Pillow、zxing-cpp`。自定义logo默认放码体上方；`--logo-position center` 对新生成的普通QR可用，限制遮盖面积，并对最终图解码。底部文字位于静区外。中文文字需提供可用中文字体。

```bash
python scripts/qr_export.py --url-file 比赛二维码.png.url.txt --out 赛事二维码.png --logo logo.png --footer '扫码查看赛程和成绩' --font 中文字体.ttf --pdf
python scripts/qr_export.py --source-image 裁判端二维码.png --miniapp --out 裁判端物料.png --footer '裁判员入口' --font 中文字体.ttf
```

标准QR使用高纠错H、至少4模块静区与黑白码体；生成后对最终PNG解码并比较原始负载，失败就不交付。自定义中心logo通过当前解码不等于所有手机都可扫，实际打印前检查微信/相机及打印尺寸。正常下载的QR也可用 `--source-image` 和 `--expected-payload-file` 保留原码并核验。

小程序码保持平台原图码体像素及宽高，只在外围添加文字/上方logo；禁止中心遮盖。普通QR解码器不能校验微信专有码，输出记录标 `platform_original_preserved`，并要求实际微信扫码核对目标赛事/用途，不宣称已经完成手机端验证。

工具输出 PNG、可选PDF及 `.verification.json`；二维码内容可能是带赛事访问标识的真实链接，按用户指定范围分享，不在公共 skill 包中附带具体赛事二维码。工具不保存logo到平台，也不会更改客户端设置。
