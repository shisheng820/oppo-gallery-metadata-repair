# 真实设备验证记录

测试日期：2026-10-28（Asia/Shanghai）。范围：单张 JPEG 的相机厂商与型号修复及 OPPO 系统相册显示。

## 环境

| 项目 | 实测版本 |
| --- | --- |
| 手机 | OnePlus Ace 3V |
| Android | 16 / API 36 |
| 系统相册 | com.coloros.gallery3d 16.40.22 |
| FireRPA 服务 / Python 客户端 | 10.9 / 10.9 |
| ExifTool | 13.59 |
| Python | 3.12 |

## 样本和对照设计

使用用户历史对话中同名的 Pixel 4 XL 真实 JPEG，分辨率 3024 × 4032，从手机 DCIM 只读复制到本地私有目录。读取发现原片当前已经是 `Make=Google` / `Model=Pixel 4 XL`，不能声称发现了一张仍损坏的原片。

因此额外制作隔离副本，仅移除 `IFD0:Make` 和 `IFD0:Model`，保留镜头信息。对照副本与原片分开放置。这是**受控复现实验**，不是对原片实施破坏。ExifTool 在制作对照时报告 ExifIFD 条目顺序异常并修正；没有将这个警告隐藏成“所有元数据完全不变”。

## 本次观察

| 验证项 | 真实结果 |
| --- | --- |
| 对照副本，Make/Model 均为空，镜头信息仍保留 | 相册详情 `tv_model` = 无相机信息 |
| 从 LensMake / LensModel 恢复相机厂商、型号 | 写回 Google / Pixel 4 XL |
| 本地写入验收 | 原输入 SHA-256 未变、JPEG 扫描数据未变、标签读回匹配 |
| ADB 复制后 | 手机测试副本 SHA-256 与本地修复副本一致 |
| 完整 run.ps1 一键流程 | 退出码 0；device-result.json 中 verified=true |
| 重开相册后的独立 CLI 检查 | 包名 com.coloros.gallery3d；型号 Pixel 4 XL；XML 文件名和路径匹配本次测试副本 |
| 手机 DCIM 原片 | SHA-256 与最初拉取的原片一致 |

修复前的实际 UI 裁剪：

![无相机信息](images/before-model.jpg)

修复后重新打开相册的实际 UI 裁剪：

![Pixel 4 XL](images/after-model.jpg)

以上图片均由 FireRPA 在主屏幕截取机型行区域，未合成、重绘或替换文字。由于隐私原因，不发布原照片、完整屏幕、完整 UI 树、原文件名、设备 IP、序列号或照片哈希。完整证据仅保留在操作者本地 `.private/`。

## 实际排障及修正

1. Python 缺少 lamda：在项目 `.venv` 安装依赖，不修改系统 Python。
2. 技能 CLI 参数文档与实现不一致：连接参数置于子命令后才可解析。
3. CLI `app-check` 忽略系统应用：用 CLI shell 查询安装包，结合当前 UI 验证。系统相册没有被卸载或重装。
4. CLI `app-stop` 未提供 user 时出现 protobuf None 错误：最终脚本通过 FireRPA shell 明确停止该包。
5. FireRPA 创建的临时同设备校验文件，ADB 默认无读取权限：只对该随机临时文件赋予 644，校验后精确删除。
6. 初版误把 `current_application()` 当作信息对象：核对本地 client 后改成 `.info().packageName`。
7. 详情按钮在开屏动画期的首次点击被忽略：增加空闲等待及一次条件重试，重读详情行，不把点击调用成功当成页面成功。

## 结论和边界

此版本证明：在上述环境和该 JPEG 上，写入标准 EXIF `IFD0:Make` / `IFD0:Model` 后，系统相册能够显示目标机型。无需写入视频的 `OplusProductModel`。

不据此宣称整个媒体库已修复，也不宣称 HEIC、MP4、其他相册版本、任意 OEM 私有标签或日期解析规则已通过测试。本版本有意只修改两个相机字段。旧文章里的日期及视频操作仍需分别验收。
