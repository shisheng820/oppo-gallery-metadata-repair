# 让 ColorOS 相册读懂你的照片

批量修改指定文件夹内 **JPEG/JPG** 的机型、拍摄时间、GPS 和摄影参数，输出到新目录，保留原片。可以把整批照片设成同一机型，也可以只改一个字段。

**只需要 Python 3.10+ 和 [ExifTool](https://exiftool.org/)**，不需要手机自动化环境或 Python 运行时依赖。实测环境为 Windows、Python 3.12、ExifTool 13.59、ColorOS 系统相册 16.40.22。

[阅读完整教程：从 MIUI、类原生、Pixel 到一加](docs/article.md)

## 一条命令，把整个文件夹改成指定机型

安装 Python 与 ExifTool，并确保 `python`、`exiftool` 在 PATH 中：

```powershell
python --version
exiftool -ver

# 先预览，不写入文件
python repair.py 'D:\Photos' --output 'D:\Photos-Pixel' --make Google --model 'Pixel 4 XL' --recursive

# 确认后执行；源目录不变，输出目录必须尚不存在
python repair.py 'D:\Photos' --output 'D:\Photos-Pixel' --make Google --model 'Pixel 4 XL' --recursive --apply
```

`--recursive` 包含子文件夹；不加则只处理当前层。支持单个 JPEG，也支持目录。输出保留原文件名和相对目录；其他格式列在报告中，**不会转换或修改 PNG、HEIC、视频**。修改 EXIF 不等于转换图像格式。

Windows 也可使用 PowerShell 入口：

```powershell
.\run.ps1 -Source 'D:\Photos' -Output 'D:\Photos-Pixel' -Make Google -Model 'Pixel 4 XL' -Recursive -Apply
```

PowerShell 入口优先使用项目已有的 `.venv`，否则使用 PATH 中的 Python。若系统执行策略不允许运行 PS1，可直接用上面的 Python 命令。

## 其他常见修改

```powershell
# 只修改机型，其他字段保留
python repair.py 'D:\Photos' --output 'D:\Photos-Custom' --model 'My Custom Camera' --apply

# 整批统一为同一拍摄时间；这是明确的统一设置，不是自动恢复每张照片的真实时间
python repair.py 'D:\Photos' --output 'D:\Photos-Time' --taken-at '2020:06:01 12:34:56' --utc-offset=+08:00 --apply

# 每张照片分别从完整文件名中取日期；不猜 IMG_1234 或缺少年份的 LMC 文件
python repair.py 'D:\Photos' --output 'D:\Photos-Dated' --from-filename-time --apply

# 修改 GPS：示例为公开的北京地区坐标，不是使用者当前位置
python repair.py 'D:\Photos' --output 'D:\Photos-GPS' --latitude 39.9087 --longitude 116.3975 --apply

# 摄影参数：实际焦距 35 mm，35mm 等效焦距 50 mm
python repair.py 'D:\Photos' --output 'D:\Photos-Exposure' --iso 200 --aperture 2.8 --exposure 1/125 --focal-length 35 --focal-length-35mm 50 --apply

# 仅补缺失机型；不覆盖已有机型
python repair.py 'D:\Photos' --output 'D:\Photos-Missing' --make Google --model 'Pixel 4 XL' --only-missing --apply
```

任意字段参数可以组合。默认不根据文件名前缀、年份或镜头文字自动猜测机型。

`--from-filename-time` 接受严格的 `IMG_YYYYMMDD_HHMMSS.jpg` 及 `PXL_YYYYMMDD_HHMMSSsss[.PORTRAIT].jpg` 等完整格式；不符合规则或非法日期的文件标记为 skipped，不写入输出。文件名中的时间**按原样使用**，不会自动把 UTC 转成本地时间，请先确认其含义。它不能与 `--taken-at` 同用。

## 用 JSON 预设完成一键修改

修改 [profiles/demo.json](profiles/demo.json)，然后运行：

```powershell
python repair.py 'D:\Photos' --output 'D:\Photos-Demo' --profile profiles/demo.json --recursive --apply

# PowerShell 等价命令
.\run.ps1 -Source 'D:\Photos' -Output 'D:\Photos-Demo' -Profile profiles/demo.json -Recursive -Apply
```

预设只应包含准备修改的字段，省略的字段保持原值。命令行值覆盖预设中的同名值。仓库另附只改机型的 Pixel 4 XL、Redmi Note 8 Pro 预设；它们是用户主动选择的标签值，不是设备识别结果。

| JSON 字段 | Python 参数 | PowerShell 参数 | 说明 |
| --- | --- | --- | --- |
| make / model | --make / --model | -Make / -Model | 厂商与自定义机型，建议用 ASCII 名称以减少旧相册兼容问题 |
| taken_at | --taken-at | -TakenAt | 年月日时分秒，可追加 .123 毫秒；同时写 Original、Create、Modify 三组时间 |
| utc_offset | --utc-offset | -UtcOffset | 如 +08:00；负偏移用 --utc-offset=-03:00 |
| latitude / longitude | --latitude / --longitude | -Latitude / -Longitude | 十进制度，必须成对；负值为南纬 / 西经；写 WGS-84 基准 |
| altitude | --altitude | -Altitude | 米；负值表示海平面以下 |
| iso / aperture | --iso / --aperture | -Iso / -Aperture | ISO 整数 / 光圈数值，如 200 / 2.8 |
| exposure | --exposure | -Exposure | 秒，支持 1/125 或 0.008 |
| ev | --ev | -ExposureCompensation | 如 -0.7；ACE 3V 未显示，一加 15 已由截图确认显示 |
| focal_length | --focal-length | -FocalLength | 实际焦距，mm |
| focal_length_35mm | --focal-length-35mm | -FocalLength35mm | 35mm 等效焦距，整数 mm |
| lens_make / lens_model | --lens-make / --lens-model | -LensMake / -LensModel | 镜头标签，与相机厂商/型号分开 |

设定拍摄时间时会同步亚秒字段；未提供小数秒会清除旧的亚秒值，防止留下不属于新时间的毫秒。时区字段只在明确提供 `utc_offset` 时修改；未提供则保留原时区，务必检查是否仍适用。光圈和快门同时维护相应 APEX 字段，避免留下互相冲突的两种表示。

## ColorOS 的真实显示效果

演示素材为 NASA 公开的 [Blue Marble](https://svs.gsfc.nasa.gov/30613/)。以下机型、时间、地面位置及参数均为教学设定，**不代表这张照片的真实拍摄信息**。

| 修改前 | 修改后 |
| --- | --- |
| ![修改前的完整相册详情](docs/images/before-full.jpg) | ![修改后的完整相册详情](docs/images/after-full.jpg) |

修改后实机显示：

- 机型：ColorOS EXIF Demo
- 时间：2020 年 6 月 1 日 12:34（字段含秒，界面此处显示到分钟）
- 地点：北京地区地址，由相册对示例 GPS 反向解析
- 参数：ISO 200、f/2.8、1/125 s、50 mm

实际焦距写入 35 mm、等效焦距写入 50 mm 时，ACE 3V 显示 50 mm。`ExposureCompensation=-0.7` 在 ACE 3V 界面仍为“−”，后续一加 15 普通静态对照已确认显示 ev -0.7。字段存在与界面显示需要分别验收。

两张完整截图经人工检查，无私人照片、通知、账号或真实个人位置，因而没有打码；图中地址是预设的公共演示坐标解析结果。[兼容性与隐私说明](docs/validation.md)。

## 怎么让手机相册刷新

先将少量输出 JPEG **复制到手机的新图集**，保留手机旧文件。可用 USB 文件传输或现有文件同步工具；不要把输出里的 `_original`、JSON 报告也导入相册。

等待 Android 扫描后，重新打开相册并查看详情。同文件名原地覆盖可能继续显示旧缓存；换新目录/新名字做对照，更容易判断文件与索引是否已经更新。不要先清空相册数据库，也不要在没有完整备份时镜像整个 DCIM。

本工具只编辑电脑上的副本，不控制手机，也不清除相册数据。

## 报告、退出码与回退

- 默认仅预览；`--apply` 才创建新输出目录。拒绝已有输出目录、源目录自身以及与源目录嵌套的路径。
- ExifTool 默认在输出目录内另留 `<原名>.jpg_original`。回退时使用原输入即可；原图从未被写入。
- 每张照片检查原文件 SHA-256 未变、目标字段读回匹配、首个 JPEG SOS 至文件末尾的数据哈希不变；最后一项验证扫描数据未重新编码，不保证所有私有元数据逐字节不变。
- `report.json` 记录逐文件字段变化、读回结果、警告、跳过原因和失败。存在失败则退出码 1；部分文件仍可能已经输出，先检查报告。skipped / unsupported 也要核对，退出码 0 不等于所有目录文件均被修改。
- 报告可能含原路径、日期和 GPS，应保存在仓库外或被忽略的 `.private/`。未知预设字段、非法时间、越界 GPS 和无效曝光值会在写入前拒绝。
- 不调用 `-all=`，不批量擦除既有 EXIF，不删除手机数据。修改元数据不会让照片获得另一台设备的成像效果。

## 测试

运行时只需 Python 标准库；Pillow 仅用于测试生成无隐私样本：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# 公开前先暂存预期文件，再检查公开文件清单
.\.venv\Scripts\python.exe scripts/audit_public.py
```

代码采用 [MIT](LICENSE)。NASA 图片来源及使用条件见 [素材说明](docs/media-sources.md)，相册截图仅作为界面教学；AI 示意图标注为非实机截图。

## 大师模式、实况、HDR 与相册调时备份

部分 OnePlus/OPPO 的 JPEG 实际上是复合容器。普通批处理现在会跳过有 MPF、增益图、实况标记或 JPEG EOI 后数据的文件，并在报告中写明原因，不把它们当作普通 JPEG 盲目改写。

```powershell
# 只读结构检查：支持本次观察到的 jxrs / wtmk 尾标记
# 默认不输出备份里的原时间、原文件名或隐藏媒体内容
python oplus_metadata.py inspect 'D:\Photos\sample.jpg'
```

新模块包含带边界校验的 JPEG / XMP / OnePlus 尾部解析，以及实验性的全新场景容器构造器。它不提供“一键克隆私人照片所有元数据”，也不会从私人样本导入缩略图、src.image、旧视频或声音。

已确认，相册调时样本同时改写标准 EXIF，并新增 `capture.info.backup` 保存原时间和原文件名；它不是只用一个高优先级新日期覆盖旧日期。大师标记、预设、实况视频和 HDR 增益图也属于不同层面。见 [源码与格式解释](docs/oplus-container.md)。

实验构造器需要自己准备的新 JPEG 和 MP4，使用 `python oplus_metadata.py build --help` 查看选项。`--example-master-preset` 只是对一份已观察设置布局的显式实验夹具，字段语义未完全解码；不应当作官方通用写入规范。ACE 3V 未出现大师/实况入口；一加 15 用户复测已确认大师标识、广角镜头、曝光补偿，以及原片时间与复原入口。实际点击复原后的文件回读尚未记录。实况在两台设备上仍未识别，不能宣称已完成实况兼容。详见[对照证据](docs/validation.md)。
