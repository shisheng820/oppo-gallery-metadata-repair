# OPPO 相册照片机型修复

把 JPEG 的相机厂商、机型写入**新副本**，再通过 FireRPA 操作 OPPO/一加系统相册，检查详情页实际显示。ADB 仅用于文件传输与同设备校验。

**已实测：** 2026-10-28，一加 Ace 3V，Android 16 / API 36，系统相册 `com.coloros.gallery3d` 16.40.22，FireRPA 10.9，ExifTool 13.59。真实 Pixel 4 XL 照片的隔离对照副本从“无相机信息”恢复为“Pixel 4 XL”。[完整验证记录](docs/validation.md)。

| 修复前 | 修复后 |
| --- | --- |
| ![相册显示无相机信息](docs/images/before-model.jpg) | ![相册显示Pixel 4 XL](docs/images/after-model.jpg) |

截图仅保留真实详情页的机型一行，没有原片画面、地址或通知。原片、完整 XML、调试日志和详细报告均不进入 Git。

## 安装

需要 Windows PowerShell、Python 3.12（本次测试版本）、[ExifTool](https://exiftool.org/)、[Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)。`exiftool` 和 `adb` 应在 PATH 中。手机启动 [FireRPA](https://github.com/firerpa/lamda) 服务并完成 ADB 调试授权。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
exiftool -ver
adb devices -l
```

本工具不会安装手机服务、修改权限、清除相册缓存或数据库。FireRPA 服务需要已有执行 shell、访问 UI 的能力。

## 先预览，再一键修复和验证

输入必须是单张 JPEG；输出必须是**尚不存在的新目录**。请将媒体和输出目录放在 Git 之外，或放到已忽略的 `.private/` 中。

```powershell
# 只读预览；不会写照片、创建输出目录或连接手机
.\run.ps1 -Source 'D:\Photos\input.jpg' -Output '.private\sample-01'
```

默认从 `LensMake` 和 `LensModel` 读取来源，例如 `Google` 与 `Pixel 4 XL back camera 4.38mm f/1.73`。只移除明确的 `back/front camera ...` 后缀；不会根据 PXL/IMG 前缀或年份猜机型。没有可信镜头信息时，显式传 `-Make 'Google' -Model 'Pixel 4 XL'`。这两个值必须由使用者确认。

```powershell
# 仅生成修复副本和本地报告，不连接手机
.\run.ps1 -Source 'D:\Photos\input.jpg' -Output '.private\sample-01' -Apply

# 一条命令：修复 → 传输 → 扫描 → 重开系统相册 → 点击详情 → 校验型号、文件名和路径
# 每次选择新的输出目录；把地址和序列号替换为自己的实际值
$deviceAddress = 'your-device-host'
$adbSerial = 'your-adb-serial'
.\run.ps1 -Source 'D:\Photos\input.jpg' -Output '.private\sample-02' `
  -Apply -VerifyPhone -DeviceHost $deviceAddress -Port 65000 -Serial $adbSerial
```

TLS 服务还需 `-Certificate 'D:\Keys\lamda.pem'`，端口使用实际配置值。脚本不会猜测设备地址。可以在不重新修复的情况下单独重试手机验证：

```powershell
.\.venv\Scripts\python.exe verify_gallery.py '.private\sample-02\repaired.jpg' `
  --host $deviceAddress --port 65000 --serial $adbSerial `
  --expected-model 'Pixel 4 XL' --evidence '.private\sample-02\device-retry'
```

`verify_gallery.py` 启用 lamda 调试日志。需要保存时，将输出重定向到 `.private/` 内；日志可能包含设备路径和 UI 文本，不要公开。

## 安全边界与报告

- 只修改 `IFD0:Make`、`IFD0:Model`，不改拍摄时间、时区、GPS、镜头参数；此版本不支持批量、HEIC 或 MP4。历史教程里的视频私有字段不在本次验收范围。
- `repair.py` 默认预览。`--apply` 只操作新目录的 `repaired.jpg`，ExifTool 默认另留 `repaired.jpg_original` 备份，不使用 `-all=`。
- 写入后检查原文件 SHA-256 未变、目标标签读回一致，以及首个 JPEG SOS 起至文件末尾的数据哈希未变。后者验证图像扫描数据未重新编码，**不是对所有私有元数据逐字节保留的保证**。
- `before.json` / `after.json` 记录详细标签；`report.json` 记录字段变化和校验。它们可能包含位置、路径等隐私，均应留在本地。ExifTool 警告也保存，不悄悄忽略。
- 手机每次新建独立的 `Pictures/MetadataRepair-<随机值>/repaired.jpg`，不覆盖 DCIM。传输后校验 SHA-256；校验 ADB 与 FireRPA 指向同一手机；扫描后查询 MediaStore 实际行，再用 `content://` 打开。
- 相册会被停止并重开，不会清除数据。详情按钮使用已实测的资源 ID，等待空闲，首次点击未生效时只重试一次。版本变化、登录或权限弹窗会报错退出，不会继续猜坐标。
- 退出码 0 才表示本阶段通过。完整成功需 `report.json` 的三个校验为 true，且 `device/device-result.json` 的 `verified` 为 true；还应使用 FireRPA CLI 独立读取详情页。
- 所有新增测试副本留在手机上供复核，不自动删除。需要撤销时，只手动删除报告中列出的独立测试图集及本地输出目录；原文件从未改动。

## FireRPA CLI 独立检查

操作检查按 [firerpa 技能](https://github.com/firerpa/lamda) 配套的 `scripts/firerpa.py` 执行（CLI 不在本仓库内，也不复制第三方源码）。将下面路径设置为自己的技能 CLI 位置：

```powershell
$cli = 'D:\Skills\firerpa\scripts\firerpa.py'
$py = '.\.venv\Scripts\python.exe'
& $py $cli server-info --host $deviceAddress --port 65000
& $py $cli dump --host $deviceAddress --port 65000 -o '.private\verify.xml'
& $py $cli app-current --host $deviceAddress --port 65000
& $py $cli get-text --host $deviceAddress --port 65000 `
  --resource-id 'com.coloros.gallery3d:id/tv_model'
```

本次技能 CLI 有两个实际兼容性问题：连接参数必须放在子命令**后面**；`app-check` 只遍历非系统应用，会误报系统相册未安装。可用 CLI `shell` 的 `pm path com.coloros.gallery3d`、`dumpsys package com.coloros.gallery3d` 加当前 UI 确认实际安装情况。`app-stop` 应显式传 `--user 0`，避免此 CLI 将 None 传给 protobuf。交付脚本用已验证的 FireRPA shell 完成停止与启动。

## 测试与公开前审计

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
git add .gitignore README.md LICENSE repair.py verify_gallery.py run.ps1 requirements*.txt tests docs scripts
.\.venv\Scripts\python.exe scripts/audit_public.py
git diff --cached --stat
```

测试使用动态生成的纯色图片，覆盖预览不写入、原片不变、无关 Artist 标签保留、像素一致、重复输出拒绝、没有来源时不猜机型等行为。仓库不包含个人照片或原始聊天导出。

`.gitignore` 不能清理已经提交的隐私历史；本仓库从空目录建立，首个提交前检查 Git 文件清单。如果自行扩展，请重新检查所有提交，而不仅仅是当前工作区。

许可证：[MIT](LICENSE)。
