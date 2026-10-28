# ColorOS 相册兼容性

本页补充教程的适用范围。测试环境：OnePlus Ace 3V、Android 16 / API 36、系统相册 com.coloros.gallery3d 16.40.22，ExifTool 13.59，Python 3.12。测试日期：2026-10-28。

## 已在实际详情页看到的字段

| 内容 | 写入值 | 详情页结果 |
| --- | --- | --- |
| 自定义型号 | IFD0:Model = ColorOS EXIF Demo | ColorOS EXIF Demo |
| 拍摄日期 | DateTimeOriginal / CreateDate / ModifyDate = 2020:06:01 12:34:56 | 2020 年 6 月 1 日 12:34 |
| 时区 | OffsetTimeOriginal 等 = +08:00 | 日期保持目标本地时间；界面没有单独显示时区 |
| 地点 | GPS 39.9087, 116.3975 | 北京市、东城区等地址文本 |
| 感光度 | ISO = 200 | ISO 200 |
| 光圈 | FNumber = 2.8 | f 2.8 |
| 快门 | ExposureTime = 0.008 秒 | 1/125 s |
| 焦距 | FocalLength = 35；FocalLengthIn35mmFormat = 50 | 50 mm |
| 曝光补偿 | ExposureCompensation = -0.7 | 标签读回存在；此版本界面仍为“−” |

制造商 Demo、镜头标签、GPS 高度、毫秒和秒的完整显示没有获得同等界面验收，不能把字段可写等同于界面逐项展示。GPS 字符串由相册的地址服务解析，不等同于 EXIF 内存在同一地址文字。示例坐标不代表操作者或原照片的真实位置。

## 原图保护

本次演示从 NASA 下载公开 JPEG，原文件没有相机与 GPS 字段。使用仓库的一键入口和演示预设生成新副本后，原输入 SHA-256 保持不变；JPEG 扫描数据哈希保持不变；全部请求字段读回通过；复制到手机后的文件 SHA-256 与输出一致。

完整截图：[修改前](images/before-full.jpg)、[修改后](images/after-full.jpg)。人工审查确认只含公开地球图、教学设定值、通用测试目录和相册界面，无个人通知、账号、私人照片或真实个人位置，因此未作遮挡。它们不是 AI 模拟界面。

[EXIF 示意图](images/exif-layers.png) 由 AI 生成，图内已注明“非实机截图”，用于说明概念，不能当作测试证据。

## 可复现性与范围

电脑脚本的测试样本是动态生成的纯色 JPEG，测试涵盖批量与子目录、单字段/完整预设、GPS 方向和高度、时间与亚秒、无关标签和像素保留、非法参数拒绝、输出目录隔离及中文文件名。

当前批量工具只处理 JPEG/JPG，不对 HEIC、PNG、MP4 或不同版本相册做成功保证。旧教程中涉及的视频字段与时间体系需要单独处理。
