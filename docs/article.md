# 从 MIUI、类原生、Pixel 到一加：为了 OPPO 相册，我开始修复整个旧媒体库

换到一加之后，我原本以为，迁移照片就是把旧手机的 DCIM 复制过来。

真正打开 OPPO 相册才发现，照片都在，属于它们的那些信息却不一定还在：有些拍摄时间变成了复制时间，有些机型一栏空着，有些明明还保留着镜头名字，相册却说“无相机信息”。过去在 MIUI、类原生、Pixel 和不同相机应用之间折腾留下的文件，终于在同一个相册里碰面了。

我想整理的不是几张照片，而是一整个跨设备、跨系统的旧媒体库。这件事最后让我重新认识了 EXIF：它不是相册里可有可无的装饰，而是软件理解一张照片的重要线索。

这篇文章把我的处理方法整理成可以复用的教程。既讲怎样找回有依据的信息，也讲怎样主动设定机型、时间、定位和摄影参数，让 ColorOS 相册读到自己希望展示的内容。

有些第三方相机只导出了画面，没有保存完整标签。如果我能从拍摄设备、同批原片或当时的记录确认信息，再把它写回，做的就是恢复；如果只是想换一个显示名称，用的仍是同一套写入方法。区别在于填写值的依据。图像里没有记录、外部也没有依据的精确快门、时间或坐标，脚本无法替我还原。

本文按 **Windows + Python / ExifTool** 来操作，界面结论来自已记录的 ColorOS 实测。第一次使用时，可以按下面的路线读，不必先读完大师模式和实况的研究：

```text
我手里是什么文件？
├─ 普通 JPEG/JPG
│  ├─ 先做一张：准备工具 → 单张机型修改 → 读回 → 手机详情验收
│  └─ 再做一批：指定源目录、新输出目录和所需字段
├─ 实况 / HDR / 带厂商尾部的 JPEG
│  └─ 先做只读结构检查；普通批处理会跳过，勿直接套普通照片命令
└─ MP4 视频
   ├─ 想设自己的机型、时间、地点：阅读文末的视频分步命令
   └─ 想复现字段对照：使用固定教学值的 video_lab.py 实验脚本
```

扩展名只是入口判断：同样以 .jpg 结尾，内部也可能带视频或增益图。上面的树是阅读路线，下面再解释文件里面的结构。

## 先弄清楚：照片的画面和照片的信息，是两回事

一张 JPEG 可以同时携带图像数据和元数据。前者决定你看到什么画面；后者描述设备、拍摄时间、镜头、曝光和位置等信息。

所以，给一张图写上“Pixel 4 XL”，不会让它获得 Pixel 的成像效果；把光圈写成 f/2.8，也不会重新计算景深。它改变的是文件中的说明，软件可能据此显示详情、排序或归类。

![AI 示意图：照片的像素与 EXIF 标签](images/exif-layers.png)

上图是 AI 生成的结构示意，不是相册截图。下面的对比图则来自真实手机界面。

EXIF 是常见的照片元数据标准，但“照片元数据”不只 EXIF。一张文件里还可能有 XMP、IPTC 和厂商私有信息。同名字段出现在不同位置时，也不一定是同一份值。

### 先读懂冒号：分组、字段和值

后文会不断出现 IFD0:Model、UserData:GPSCoordinates。它们不是需要在电脑上找到的路径，而是 **ExifTool 选择字段的写法**：

```text
UserData:GPSCoordinates = 39.9087 116.3975
└─分组──┘ └──字段名称──┘   └────字段值────┘

意思：选择 UserData 这一组里的 GPSCoordinates 字段，读取或写入它的值。
```

UserData 可以理解为工具给一组容器数据起的分组名；GPSCoordinates 是“位置坐标”这个字段的名称。这里的数值是公开教学坐标，不是私人样本的原位置。分组反映了工具如何组织标签，但并不保证每个分组名都等于文件内部某一层的原始名称。

读和写只差一个动作，下面先看句法，真正运行的完整步骤放在后文：

| 我想做什么 | 写法 | 含义 |
| --- | --- | --- |
| 读取 | -UserData:GPSCoordinates | 只选中这个字段，查看现有值 |
| 写入 | "-UserData:GPSCoordinates=39.9087 116.3975" | 把这个字段设为指定坐标 |
| 看清分组 | -G1 -s | 输出类似 [UserData] GPSCoordinates，而不是只显示一个中文描述 |

字段前面的减号是 ExifTool 的命令参数，冒号选分组，等号右侧是要写入的值。引号把含空格的一整个赋值参数包起来。相同的 GPSCoordinates 也可能出现在 Keys 组，**同名不代表相册会读同一个位置**。

### JPEG 里面的标签怎样组织？

下面是帮助定位字段的结构示意，不是 Windows 目录，也不是每张图必有的清单。EXIF 中的子目录通过指针关联，树中省略了缩略图等其他内容：

```text
sample.jpg
├─ 图像数据：压缩后的画面
├─ APP1 / Exif（如果文件包含 EXIF）
│  └─ TIFF 结构
│     └─ IFD0：基础图像信息
│        ├─ Make、Model、ModifyDate
│        ├─ ExifIFD 指针 → 拍摄信息子目录
│        │  └─ DateTimeOriginal、ISO、FNumber、ExposureTime、LensModel…
│        └─ GPS 指针 → 定位子目录
│           └─ GPSLatitude、GPSLatitudeRef、GPSLongitude、GPSLongitudeRef…
└─ 还可能包含 XMP、IPTC、厂商信息或其他附加数据
```

所以，“修改机型”在这里通常是修改 IFD0:Model；“修改纬度”则要写 GPS:GPSLatitude，并配好南北方向。它们都是元数据，却不是同一个字段，也不是在同一组里随便加一段描述文字。

我现在先看这几组：

| 想改什么 | ExifTool 常用字段 | 它的含义 |
| --- | --- | --- |
| 相机厂商、机型 | IFD0:Make、IFD0:Model | 例如 Google、Pixel 4 XL |
| 镜头厂商、型号 | ExifIFD:LensMake、ExifIFD:LensModel | 镜头信息，和相机机型分开 |
| 拍摄时间 | ExifIFD:DateTimeOriginal | 拍摄时的日期和时钟时间 |
| 数字化、修改时间 | ExifIFD:CreateDate、IFD0:ModifyDate | 与拍摄时间有关，但语义并非永远相同 |
| 时区、毫秒 | OffsetTimeOriginal、SubSecTimeOriginal | 为主要时间补充偏移量和亚秒 |
| 经度、纬度 | GPSLatitude、GPSLongitude 及各自 Ref | 数值与南北、东西方向要配套 |
| ISO、光圈、快门 | ISO、FNumber、ExposureTime | 例如 200、2.8、0.008 秒 |
| 实际、等效焦距 | FocalLength、FocalLengthIn35mmFormat | 两种焦距不能混为一谈 |
| 曝光补偿 | ExposureCompensation | ExifTool 对 EXIF ExposureBiasValue 的命名 |

表里的 IFD0、ExifIFD、GPS 是字段所在的分组。读写时带上分组，是为了减少“改了一个 Model，相册却读另一个 Model”的混淆。[ExifTool 的 EXIF 标签表](https://exiftool.org/TagNames/EXIF.html) 给出了这些字段的定义、分组和可写类型。

另一个容易混淆的东西是文件系统日期。Windows 资源管理器里的“修改日期”、Android 媒体库的导入时间，以及 EXIF 里的 DateTimeOriginal，分别属于不同层面。只修改文件的修改日期，不等于修好了拍摄时间。

## 先看效果：同一张公开图片，相册能读出什么

为了让对照可以公开复现，我没有使用私人照片，而是从 NASA 下载了 [Apollo 17 的“蓝色弹珠”图片](https://svs.gsfc.nasa.gov/30613/)。这份下载图没有相机与 GPS 字段，适合观察“没有信息”和“写入信息”之间的差别。

我给副本主动设定了这些值：

| 字段 | 教学设定 |
| --- | --- |
| 厂商 / 机型 | Demo / ColorOS EXIF Demo |
| 拍摄时间 / 时区 | 2020:06:01 12:34:56 / +08:00 |
| GPS | 北纬 39.9087、东经 116.3975，北京地区的公开演示坐标 |
| ISO / 光圈 / 快门 | 200 / f/2.8 / 1/125 秒 |
| 实际焦距 / 35mm 等效焦距 | 35 mm / 50 mm |
| 曝光补偿 | −0.7 EV |

这些是为了展示字段作用而设定的值，**不是这张太空照片的真实拍摄信息**。

修改前，相册显示“无相机信息”“暂无地点信息”，日期也不是 EXIF 提供的真实拍摄时间：

![修改前：完整的系统相册详情页](images/before-full.jpg)

修改副本、复制到手机的新图集并重新打开相册后：

![修改后：自定义机型、时间、地点与摄影参数](images/after-full.jpg)

这次用的是一加 Ace 3V、Android 16，系统相册版本为 16.40.22。可以直接看到，自定义机型、日期、地点、ISO、光圈、快门和焦距已经出现在详情里。

有两个细节比“成功”本身更有价值。

第一，我同时写了实际焦距 35 mm 和等效焦距 50 mm，这个版本显示的是 **50 mm**。如果你改了 FocalLength，却发现界面里的焦距没按预期变化，要检查等效焦距是否还在。

第二，同一个 ExposureCompensation=−0.7 字段，在 ACE 3V 上读回正常但界面显示“−”；后续一加 15 的实机截图则明确显示 ev −0.7，而且普通静态对照图也能显示。这是相册显示行为的差异，不能把 ACE 3V 的表现写成这个字段普遍无效。

地址也是相册根据 GPS 解析出来的结果，不是我直接把“北京市……”这段文字写进了 EXIF。图中地址来自演示坐标，不是我的实际位置。两张全屏截图已经检查，没有私人照片、账号或通知信息，所以没有遮挡字段和界面。

## 准备工具：先有原片，再做副本

我使用 [ExifTool](https://exiftool.org/) 来处理标签，用 Python 运行仓库中的封装脚本。先安装 Python 3.10 或更新版本，并下载 ExifTool 的 Windows 版。若可执行文件名带有 (-k)，将它整理为 exiftool.exe；下载包里的 exiftool_files 等配套目录也要一起保留。

将 ExifTool 所在文件夹加入 PATH 后，打开 **PowerShell**，确认这两个命令都能运行：

```powershell
python --version
exiftool -ver
```

如果 ExifTool 放在 C:\Tools\ExifTool，也可以先只为当前 PowerShell 窗口添加路径。请把示例目录替换成自己的真实目录：

```powershell
$env:Path = 'C:\Tools\ExifTool;' + $env:Path
exiftool -ver
```

接下来下载 [项目仓库](https://github.com/shisheng820/oppo-gallery-metadata-repair)。已安装 Git 时可以执行下面两行；也可以下载 ZIP、解压，然后在解压出的仓库目录打开 PowerShell：

```powershell
git clone https://github.com/shisheng820/oppo-gallery-metadata-repair.git
Set-Location oppo-gallery-metadata-repair
```

后文的 Python、PowerShell 脚本和 profiles 相对路径都以**仓库根目录**为起点。运行下面的只读命令能看到帮助，就说明当前目录正确。普通照片批处理只依赖 Python 标准库与 ExifTool，不需要安装开发测试用的 Pillow；视频实验需要的 FFmpeg / ffprobe 到视频部分再准备。

```powershell
python repair.py --help
```

下面的 ExifTool 单文件写入命令都应该在**工作副本**上执行。比如先把一张自己的普通 JPEG 复制为 D:\PhotoWork\sample.jpg，再设置路径。D 盘、目录和文件名都可以改；变量里的文件必须已经存在：

```powershell
$photo = 'D:\PhotoWork\sample.jpg'

# 只读：同时查看重复字段、所在组和短标签名
exiftool -a -G1 -s -Make -Model -LensMake -LensModel -time:all -GPS:all -ISO -FNumber -ExposureTime -FocalLength -FocalLengthIn35mmFormat $photo
```

这里的 -a 保留重复标签，-G1 显示分组，-s 使用短标签名。需要准确比较数值时再加 -n，例如将快门直接读成秒、GPS 读成十进制度。

ExifTool 默认会留下 _original 备份。下面的 -P 用来保留文件系统修改时间，不会阻止你明确修改 EXIF 时间。不要一开始就加 -overwrite_original，更不要为了解决一个字段缺失而执行 -all= 清空全部信息。

下文的单文件写入示例仅针对普通 JPEG。大师、实况、HDR 等复合图片请先使用仓库的 oplus_metadata.py inspect 检查；普通批量脚本会跳过此类容器。

### 第一次操作：只改一张普通照片的机型

先用只读检查确认它是不是复合文件：

```powershell
python oplus_metadata.py inspect $photo
```

输出的 compound=false，才进入这一条普通 JPEG 路线；如果为 true，先读后面关于实况/HDR 的部分。这不是让你先清空元数据，而是避免把带隐藏媒体的文件当作普通图处理。

下面只设置机型，不修改时间、位置和其他摄影参数。脚本输出目录要是**尚不存在的新目录**，与源目录分开：

```powershell
# 第一次只预览：不创建输出目录，不改原片
python repair.py $photo --output 'D:\PhotoWork-Model-01' --model 'My Custom Camera'

# 核对范围后再执行：创建新副本和报告，原片仍在原处
python repair.py $photo --output 'D:\PhotoWork-Model-01' --model 'My Custom Camera' --apply

# 检查输出副本，Model 应为 My Custom Camera
exiftool -G1 -s -Make -Model 'D:\PhotoWork-Model-01\sample.jpg'
```

如果你的输入不叫 sample.jpg，读回命令也要改成实际文件名。第二次重做请换一个新的输出目录，例如 PhotoWork-Model-02；不要先建输出目录，也不要直接覆盖旧结果。

最后把这个输出 JPG 按原文件复制到手机的新图集，等待扫描后重新打开相册详情，核对机型。**预览正确 → 写入副本 → 电脑读回正确 → 手机显示正确**，这才完成一轮。后文只是把同一套步骤扩展到时间、定位、参数与批量处理。

## 自改机型：相机型号和镜头型号不要改错位置

给当前工作副本写一个自定义机型：

```powershell
exiftool -P "-IFD0:Make=Demo" "-IFD0:Model=My Custom Camera" $photo
```

如果已经确认整批照片来自 Pixel 4 XL，则可以写：

```powershell
exiftool -P "-IFD0:Make=Google" "-IFD0:Model=Pixel 4 XL" $photo
```

我最早遇到的一类旧照片，Make 和 Model 不完整，但 LensMake 还保留 Google，LensModel 则类似：

```text
Pixel 4 XL back camera 4.38mm f/1.73
```

这串文字是恢复信息的线索：型号可能是 Pixel 4 XL，实际焦距是 4.38 mm，最大光圈信息是 f/1.73。但不能把整串内容不加区分地塞进 Model，也不能把这条规则套到所有 PXL 照片。

有依据地恢复机型，和主动写一个自己喜欢的显示名称，是两种用途。前者需要核对来源；后者是自定义标签。相册显示某个名字，并不能反过来证明照片真的由那台设备拍摄。

## 自改时间：先决定你要表达哪个时间

如果要把工作副本明确设为北京时间 2020 年 6 月 1 日 12:34:56，可以这样写：

```powershell
exiftool -P `
  "-ExifIFD:DateTimeOriginal=2020:06:01 12:34:56" `
  "-ExifIFD:CreateDate=2020:06:01 12:34:56" `
  "-IFD0:ModifyDate=2020:06:01 12:34:56" `
  "-ExifIFD:OffsetTimeOriginal=+08:00" `
  "-ExifIFD:OffsetTimeDigitized=+08:00" `
  "-ExifIFD:OffsetTime=+08:00" `
  "-ExifIFD:SubSecTimeOriginal=" `
  "-ExifIFD:SubSecTimeDigitized=" `
  "-ExifIFD:SubSecTime=" `
  $photo
```

最后三项清除旧的小数秒，是因为这个例子只指定到整秒。若实际时间还包含 .123 秒，可以将对应的 SubSecTime 字段写为 123。

这里把三组时间统一，是针对整理副本的一种主动选择，并不意味着它们的语义天然相同。比如胶片照片的拍摄时间、扫描数字化时间，本来就可能不同。

旧文件名也是重要线索，但要看它究竟包含什么：

- IMG_20200601_123456.jpg 含完整日期和时间，可以在确认命名含义后用于恢复。
- PXL_20200601_123456789.jpg 还可能包含毫秒，但文件名里的时钟是否按 UTC 命名，需要另外确认。
- IMG_1234.JPG 只有序号，无法据此恢复拍摄时间。
- LMC8.8_19 Nov 11_34_...jpg 缺少年份，必须补充可靠依据，不能自动拿复制年份代替。

尤其不要看到相差八小时就直接加八小时。JPEG 中的时钟、时区偏移与视频容器中的 UTC 时间，不应混用一套修复逻辑。

## 自改定位：写的是坐标，不是一个地名字符串

EXIF 的 GPS 不是一段“北京”“广州”的城市名称。最基本的位置信息需要纬度、经度及方向。ExifTool 官方也明确要求将这四个字段配套设置。[GPS 标签说明](https://exiftool.org/TagNames/GPS.html)。

下面使用同一组公开演示坐标：

```powershell
exiftool -P `
  "-GPS:GPSLatitude=39.9087" `
  "-GPS:GPSLatitudeRef=N" `
  "-GPS:GPSLongitude=116.3975" `
  "-GPS:GPSLongitudeRef=E" `
  "-GPS:GPSMapDatum=WGS-84" `
  $photo
```

N / S 表示北纬 / 南纬，E / W 表示东经 / 西经。此处数值使用绝对值，方向由 Ref 指定。后面的批量脚本可以接收带正负号的十进制度，并自动拆成数值和方向。

如果确实知道海拔，还可以补 GPSAltitude 与 GPSAltitudeRef；不知道就不要顺手编一个。海拔也不是相册地址栏出现地名的前提。

相册是否显示地址、显示多精细的地址，取决于它怎样解析坐标及其地址服务。直接改文件里的 IPTC 城市名称，不能保证系统相册地点栏就跟着改变。

定位也是需要留意的隐私字段。整理后准备公开的照片，应该重新检查 GPS，而不是只看画面有没有出现门牌。

## 自改摄影参数：注意单位和另一套表示

给工作副本设置 ISO 200、f/2.8、1/125 秒和两种焦距：

```powershell
exiftool -P `
  "-ExifIFD:ISO=200" `
  "-ExifIFD:FNumber=2.8" `
  "-ExifIFD:ExposureTime=0.008" `
  "-ExifIFD:FocalLength=35" `
  "-ExifIFD:FocalLengthIn35mmFormat=50" `
  "-ExifIFD:ExposureCompensation=-0.7" `
  $photo
```

ExposureTime 的单位是秒，0.008 秒就是 1/125 秒。FNumber 写数值 2.8，不是带单位的“f/2.8”。FocalLength 是实际焦距；FocalLengthIn35mmFormat 是 35mm 等效焦距，不能因为某一项在界面里更常见，就把两者都填成同一个数。

对于已经带有丰富 EXIF 的照片，还要检查 ApertureValue 和 ShutterSpeedValue。它们使用 APEX 表示，不能把 2.8 和 0.008 原样当作其底层数值。本文的批量脚本会同步维护这些关联字段；直接运行上面的手动命令后，应检查照片中是否还存在旧的关联值。

另外，EXIF 标准里的 ExposureBiasValue，在 ExifTool 中叫 ExposureCompensation；FocalLengthIn35mmFilm 在 ExifTool 中则叫 FocalLengthIn35mmFormat。不同库里的名字看起来很像，也不一定能直接互换。命令执行后必须读回，不能只看到“文件已更新”就结束。

## 文件多了以后：用一个脚本改整个文件夹

单张确认没有问题后，就可以批量处理。我把常用操作整理进了 [oppo-gallery-metadata-repair](https://github.com/shisheng820/oppo-gallery-metadata-repair)。

它的核心很简单：指定源目录、指定新输出目录、指定要修改的字段。没有填写的字段保持原值。运行时只依赖 Python 标准库与 ExifTool，不需要在手机上配置额外的控制环境。

以下命令继续在前面准备好的仓库根目录运行，不需要重新克隆，也不需要先把照片搬进仓库。源路径可以指向你自己的照片文件夹。

把整个目录及子目录里的 JPEG 统一设为某个机型，先预览：

```powershell
python repair.py 'D:\Photos' --output 'D:\Photos-Pixel' --make Google --model 'Pixel 4 XL' --recursive
```

预览不创建输出目录，也不修改图片。确认选中的文件范围后，在同一条命令末尾加上 --apply：

```powershell
python repair.py 'D:\Photos' --output 'D:\Photos-Pixel' --make Google --model 'Pixel 4 XL' --recursive --apply
```

只想改成自己取的名字，也可以：

```powershell
python repair.py 'D:\Photos' --output 'D:\Photos-Custom' --model 'My Custom Camera' --recursive --apply
```

这里的“整个目录”指该目录范围内支持的 JPEG/JPG。PNG、HEIC 和视频不会被偷偷转成 JPEG，而会列入不支持的文件清单。输出保留原文件名与相对目录，源照片不变。每次执行都要指定新的输出目录，避免覆盖上一次结果。

如果目标是“只补空白，不动已有机型”，再加 --only-missing。若要分别从每张照片的完整文件名恢复时间，可以使用：

```powershell
python repair.py 'D:\Photos' --output 'D:\Photos-Dated' --from-filename-time --recursive --apply
```

这个选项不会猜机型，也不会猜不完整的日期。不符合命名规则的文件会被跳过并写明原因；文件名中的时间按原样写入，不自动转换时区。

### 把常用参数保存成预设

如果常常需要同时改几项，比起每次手敲长命令，我更倾向于一份 JSON。仓库中的 profiles/demo.json 就是前面截图使用的教学预设：

```json
{
  "make": "Demo",
  "model": "ColorOS EXIF Demo",
  "taken_at": "2020:06:01 12:34:56",
  "utc_offset": "+08:00",
  "latitude": 39.9087,
  "longitude": 116.3975,
  "iso": 200,
  "aperture": 2.8,
  "exposure": "1/125",
  "ev": -0.7,
  "focal_length": 35,
  "focal_length_35mm": 50
}
```

修改预设后，一条命令应用到选定目录：

```powershell
python repair.py 'D:\Photos' --output 'D:\Photos-Demo' --profile profiles/demo.json --recursive --apply
```

Windows 用户也可以使用 PowerShell 入口：

```powershell
.\run.ps1 -Source 'D:\Photos' -Output 'D:\Photos-Demo' -Profile profiles/demo.json -Recursive -Apply
```

使用整套预设意味着主动将这一批照片统一为相同的时间、GPS 和摄影参数。**如果只是统一机型，就使用只包含 make、model 的预设，不要直接套用演示里的全部字段。**

预设里的时间可以带毫秒；坐标必须成对，超出范围会被拒绝；快门可以写分数或秒。完整选项及规则在仓库 README 中。

## 文件改好了，相册为什么还像没改？

这是迁移时最容易误判的一步。文件已经改变，相册却可能仍在展示旧索引；尤其是同目录、同名字直接覆盖，不能保证立即刷新。

我现在会先把几张修改后的 JPEG 放到手机的**新图集**，保留旧版本作对照。复制时只选输出照片，不把 _original 备份和 report.json 一起塞进相册。等待媒体扫描后重新打开相册，再查看详情。

如果还没变化，依次检查：

1. 电脑上对输出照片重新读标签，确认修改的是正确文件。
2. 手机上打开的是否是新版本，而不是旧图集里的同名文件。
3. 传输方式是否保留原文件，是否经过压缩或重新导出。
4. 使用新名字或新目录的小样本重新导入，判断是否是缓存问题。

我不建议从“清空相册数据库”开始，也不建议拿电脑上的部分 DCIM 去镜像手机整个 DCIM。复制工具显示完成，只能说明传输结束，不能代替相册里查看结果。

脚本会在输出目录生成 report.json，记录每张图请求改了什么、字段是否读回成功、原片哈希是否保持不变，以及 JPEG 扫描数据是否一致。后者用于确认图像扫描数据没有重新编码，不代表所有厂商私有元数据都被逐字节保留。

报告中也有 skipped、unsupported、failed。存在失败会返回非零退出码；即使没有失败，也要检查跳过项，不能把“命令没有报错”理解为目录里的所有文件都已修改。报告本身可能包含路径、时间和位置，不要随手公开。

## 后来我发现：有些 JPEG 里还住着视频和编辑历史

前面把照片分成“画面”和“标签”，是为了方便理解普通 JPEG。遇到一加较新的大师模式、实况和 ProXDR 照片，这张简化图就不够了：文件里可能还有增益图、另一张内嵌图、主视频、子视频，以及厂商自己的尾部目录。

这解释了为什么“把能读到的 EXIF 全复制过去”不一定能复现相册里的标识，甚至可能把不该复制的私人画面一并带走。

### 相册调整时间，究竟改了哪里？

对比一对调整前后的文件后，我发现，主图的 DateTimeOriginal、CreateDate、ModifyDate 确实被写成了新时间；与此同时，尾部新增了 capture.info.backup，保存 originalDateTakenMs 和 originalFileName。备份时间换算后与改前拍摄时间一致。

因此，它不是只加一个更高优先级的新日期：**当前时间在标准 EXIF，旧时间在厂商备份块里。** “保存旧值”与相册是否提供“恢复原时间”入口，是两个需要分开验证的问题。

这些备份也意味着，改时间或者换一个文件名，不一定就抹掉了旧时间和原名。发布私人照片之前，只检查主图详情是不够的。

### 为什么标签列表会让人误以为数据不见了？

这对文件的末尾标记从 jxrs 变成了 wtmk。核对当前 ExifTool 源码后，可以看到它的 OnePlus 检测路径只识别前者，于是改时文件里某些尾部字段没有出现在普通列表中。

但按 footer 的目录长度与反向偏移重新读取，既有厂商块仍在，主 JPEG 扫描数据也保持不变。这里丢失的是工具的识别，不是这些隐藏媒体本身。

我给仓库增加了支持两种尾标记的只读检查器。它会验证偏移边界，并且默认不把备份的私人日期、文件名和隐藏媒体内容打印出来：

```powershell
python oplus_metadata.py inspect 'D:\Photos\sample.jpg'
```

### 大师、实况和 HDR 不是同一个开关

大师样本里有 capture.mode=master、二进制预设和 oplus_ 开头的 UserComment 功能位。它们同时存在，不等于已经证明某一项就能单独控制标签；预设各槽位和完整功能位定义仍不能乱猜。

实况则还需要实际视频。XMP 中的 MotionPhoto 标记、对应静态图的微秒时间、容器长度，以及厂商的 VideoLength、live.subVideo 等必须彼此吻合。换了封面却留下原视频，既不是正确的内容替换，也会留下隐私。

HDR 增益图本身也是图像，不能从旧私人照片里整张搬到新图上。出现一个 ProXDR 字样，不足以证明新场景已经获得正确 HDR 渲染。

### 用一个完全不同的场景做对照

我另外生成了山湖场景，用它制作静态图、三秒变焦短片及无音轨子视频，再重建目录和索引；原样本里的私人画面、位置、原文件名、声音和调试段都没有导入。大师预设只用已审查的通用设置布局作为实验夹具，不把它称为官方通用写法。

下面这张是新场景在 ACE 3V 上的真实详情页，日期与机型均为人工设定：

![复合 JPEG 新场景的相册详情](images/oplus-lab-ace-details.jpg)

基础信息能够显示，改时版也显示当前 EXIF 的新日期，而不是备份里的旧日期。第一版在 ACE 3V 没有出现大师或实况入口；把这组文件复制到一加 15，先确认了其他字段的显示，随后再单独解决实况兼容。

普通静态对照图已经显示“广角摄像头”和 ev −0.7，说明这两项显示不以加入厂商尾部为前提：

![一加 15：普通 JPEG 已显示广角镜头与曝光补偿](images/oneplus15-baseline-details.jpg)

复合主样本则额外出现 PRO 相机图标，与大师标识的预期一致。这个对照验证的是整套实验字段组合；它还不能证明 capture.mode、功能位或预设中的哪一项可以独立控制标识：

![一加 15：复合样本出现大师标识](images/oneplus15-master-details.jpg)

改时版的调整页面能同时读出“原片时间”2020 年 6 月 1 日 12:34、调整后的 6 月 2 日 08:00，并出现“复原”按钮。这进一步验证了 capture.info.backup 可以被该相册读取。下面是操作入口；随后拿到实际点击“复原”后导出的文件，读回确认 DateTimeOriginal、CreateDate、ModifyDate 已恢复到 2020:06:01 12:34:56，SubSecTimeOriginal 恢复为 123。capture.info.backup 仍在，既有尾部块与主 JPEG 扫描数据保持不变。这次已经验证到文件写回，而不仅是按钮出现；复原也不等于删除编辑历史。



![一加 15：原片时间、调整后时间和复原入口](images/oneplus15-time-restore.jpg)

| 功能 | ACE 3V 的观察 | 一加 15 的反馈 |
| --- | --- | --- |
| 机型、日期、ISO、光圈、快门、焦距 | 显示 | 显示 |
| 广角镜头文字、−0.7 EV | 未显示相应文字或数值 | 普通对照图即显示 |
| 大师标识 | 未出现 | 复合主样本出现 |
| 原片时间与复原入口 | 未验证该入口 | 已显示，复原后的文件时间已读回验证 |
| 实况入口与相册播放 | v2 已识别，长按可播放 | 第一版未识别，v2 待复测 |

### 实况的关键，最后落在一段语义相同的 XML 上

最初我也怀疑视频编码：相机原片用了 HEVC Main 10、HLG 和 AAC 音轨，新场景却是 H.264、无音轨。但继续把一份原生长焦实况副本导入 ACE 3V，它能显示实况入口。这说明不能简单归因于这台手机不支持。

接下来固定主图扫描数据、视频、尾部块和全部属性值，只比较 XMP 的序列化。Python ElementTree 默认把命名空间声明集中放在最外层 x:xmpmeta；这份写法能被 XML 解析器正确读取，却没有被这个版本的相册识别。把声明改成相机样本采用的层级后，同一份内容出现了实况入口：

```xml
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
      xmlns:GCamera="http://ns.google.com/photos/1.0/camera/"
      xmlns:OpCamera="http://ns.oplus.com/photos/1.0/camera/"
      xmlns:Container="http://ns.google.com/photos/1.0/container/"
      xmlns:Item="http://ns.google.com/photos/1.0/container/item/">
      <!-- 实际文件还必须包含实况属性和完整的 Container:Directory -->
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
```

这段只是声明位置的示意，不能单独粘进去就制造实况。XML 标准允许从父元素继承命名空间，两种写法在语义上相同；这里记录的是相册解析的兼容现象，不是标准要求。仅调整 EXIF/XMP 的 APP1 顺序没有解决问题，仅移动部分声明也没有解决。仓库构造器现在固定使用实测成功的布局，保留 XML 转义，并重算全部长度。

![ACE 3V：修正后的新场景出现实况入口](images/ace-live-v2.jpg)

长按同一张新场景后，画面会播放预先生成的缓慢变焦短片。下面是播放中的另一个画面；两张截图仅裁去顶部状态栏，没有重绘画面或图标：

![ACE 3V：长按后实况短片播放中的变焦画面](images/ace-live-v2-playing.jpg)

这次主视频依旧是 H.264、无音轨，没有增益图。因此，HEVC、录音和 ProXDR 至少不是这组样本在该相册中识别、播放实况的必要条件。新版本的普通样本和改时样本都在 ACE 3V 上出现入口，主样本的长按播放已经截图确认；一加 15 上的新版本仍需要单独复测。

### 长焦样本还提醒了我两件事

另一份原生长焦实况没有大师预设，也没有 src.image，但仍有主视频、子视频和完整目录。它说明这些私有块并非每张实况都必须具备；不要把一张大师照片的所有字段当成通用清单。

镜头文字与焦距也要分别理解。LensModel 描述镜头，FocalLength 描述实际焦距；数码变焦后，DigitalZoomRatio 与 FocalLengthIn35mmFormat 还可能体现裁切后的视角。显示很大的等效焦距，不代表物理镜头也变成了同样的长度。自定义时应让这些值符合自己的用途，并分开验证相册究竟读取哪一项。

这组反馈也提醒我，设备上的显示差异要按字段逐项记录。机型不同不自动构成原因；相册版本、能力配置、导入方式和容器约定都可能影响结果。这里的一加 15 结果来自提供的实机截图及反馈，其确切软件版本尚未收集。

普通批量工具现在会跳过这些带实况、增益图或尾部数据的 JPEG。对这类文件，先理解容器、保留完整原片，比盲目覆盖几个标签更重要。[源码与字节布局解释](https://github.com/shisheng820/oppo-gallery-metadata-repair/blob/main/docs/oplus-container.md) 放在仓库里，实验构造器也与普通批处理分开。


## 旧媒体库里的视频，需要另一个抽屉

照片跑通以后，我又拿一段原生 HEVC 视频做了独立副本。它让我确认：视频同样能自定义机型、时间和定位，但应该改的字段，已经换了一套。

### 先把视频打开成一棵结构树

MP4 可以理解为装着音轨、视频轨和说明信息的容器。里面的块常叫 box 或 atom，moov、mdat、udta 是块的名字。它们不是你在资源管理器里能展开的文件夹，ExifTool 负责解析这些内部结构：

```text
sample.mp4（按本次样本简化；省略了其他块，不代表字节排列顺序）
├─ ftyp：文件类型与兼容标识
├─ mdat：压缩后的画面、声音等媒体数据
└─ moov：电影、轨道和元数据结构
   ├─ mvhd：电影头
   │  └─ CreateDate、ModifyDate → ExifTool 的 QuickTime 组
   ├─ trak：轨道，可有视频轨、音频轨等多个
   │  ├─ tkhd → TrackCreateDate、TrackModifyDate
   │  └─ mdia / mdhd → MediaCreateDate、MediaModifyDate
   ├─ meta：本次样本中一组 mdta 元数据
   │  ├─ keys：键名清单，例如 com.oplus.product.model
   │  └─ ilst：按键名编号关联的实际值，例如某个机型名称
   └─ udta：用户数据块
      └─ ©xyz：位置字符串 → ExifTool 显示为 UserData:GPSCoordinates
```

不同软件写出的 MP4，可能把 meta 放到其他合法位置，也可能没有上述某些字段。树的作用是解释这次读取的结构，不是要求把每段视频改成同一套布局。

这里还多了一层“工具名与底层名”的映射。ExifTool 为长键名提供较短的标签名，我们通常在命令里使用右栏：

| 本次涉及的底层键或块 | ExifTool 的选择写法 | 用途 |
| --- | --- | --- |
| com.apple.quicktime.model | Keys:Model | 通用机型名称键 |
| com.android.model | Keys:AndroidModel | Android 机型键 |
| com.oplus.product.model | Keys:OplusProductModel | 本次 OPPO/一加原片中的机型键 |
| udta 内的 ©xyz | UserData:GPSCoordinates | 这次被相册读取的位置 |
| com.apple.quicktime.location.ISO6709 | Keys:GPSCoordinates | 另一处也能存放坐标的键 |

因此，“定位在 UserData:GPSCoordinates”可以完整翻译为：**这份文件的位置数据在 udta 中的 ©xyz 块，ExifTool 把它归入 UserData 组，给它的字段名是 GPSCoordinates；我们用这个完整名称选中它。** 不是去磁盘上找一个 UserData 目录，也不是所有定位都属于这一组。

### 准备一个视频，先看它已经有哪些字段

下面继续在仓库根目录的 PowerShell 中运行。把路径换成自己的视频；输入文件需要存在，输出文件不要提前创建。先读取，不写入：

```powershell
$video = 'D:\VideoLab\source.mp4'
exiftool -a -G1 -s -Model -AndroidModel -OplusProductModel -CreateDate -TrackCreateDate -MediaCreateDate -CreationDate -GPSCoordinates $video
```

-a 保留重复字段，-G1 把分组显示出来。这里故意不限定某一组 GPSCoordinates，是为了先找到文件中存在的各组坐标；确定要改哪一处后，写入时再明确指定分组。

例如，输出中出现下面这两行时，应该按三列读。这里的内容为教学示例，不是私人原片的字段转录：

```text
[Keys]      OplusProductModel : Original Video Lab
[UserData]  GPSCoordinates    : 39 deg 54' 31.32" N, 116 deg 23' 51.00" E
 ↑ 分组       ↑ 字段名           ↑ 工具格式化后的值
```

想把坐标看成十进制数字，可以单独加 -n 读取：

```powershell
exiftool -G1 -s -n -UserData:GPSCoordinates $video
```

接下来的机型、时间、地点三个例子，**分别从同一个 source.mp4 生成不同副本，不会自动叠加修改**。只改一项就用对应例子；要一次设定三项，见后面的组合命令。

### 机型：先改字段，再看相册是否采纳

相册中原先的机型来自 Keys:OplusProductModel。新增 Keys:Model 后，显示名称随之改变；只新增 AndroidModel 却没有改变显示。把三个字段写成不同名字，最终显示 Keys:Model；去掉私有机型、只留 AndroidModel，则显示“无相机信息”。这些是 ACE 3V 相册 16.40.22 的实测结果，不能直接推广到所有设备。

普通机型可这样写入新副本：

```powershell
$video = 'D:\VideoLab\source.mp4'
exiftool -o 'D:\VideoLab\model.mp4' '-Keys:Model=My Video Camera' $video
```

-o 后面是输出副本的完整路径，最后的 $video 是输入原片。运行后应该读回**输出副本**，而不是继续检查原片：

```powershell
exiftool -G1 -s -Model -AndroidModel -OplusProductModel 'D:\VideoLab\model.mp4'
```

你应该在 [Keys] 的 Model 这一行看到 My Video Camera。原有的 OplusProductModel 可能还在；新增 Model 并不等于把其他机型字段全部删除了。

如果需要写 OPPO 私有机型，仓库提供了最小 ExifTool 配置，用于声明 com.oplus.product.model 这个实际键：

```powershell
exiftool -config profiles/oplus-video.config -o 'D:\VideoLab\oplus.mp4' '-Keys:OplusProductModel=My Video Camera' $video
```

-config 要放在实际命令行的前部，不能塞进参数文件后以为配置已经加载。每次都要读回字段；配置未生效时，即使别的字段更新了，也不能把整次实验记为成功。

### 八小时之差，先分清文件里的 UTC 和手机的本地时间

目标北京时间 2020 年 6 月 1 日 12:34:56，换算成 UTC 是 04:34:56。将电影、轨道和媒体头的六组时间明确写为这个 UTC 值，相册就显示 12:34；仅改电影头 CreateDate、保留旧轨道日期，详情日期也跟随了新的电影头。相反，单独新增另一个 Keys:CreationDate，没有覆盖这份样本的电影头时间。

具体执行时，不靠心算加减八小时，先用带时区的目标值换算，再写入新副本。+08:00 明确表示这个例子的北京时间；如果目标时刻属于其他时区，应填写相应偏移：

```powershell
$targetTime = [DateTimeOffset]::Parse('2020-06-01T12:34:56+08:00')
$utc = $targetTime.UtcDateTime.ToString('yyyy:MM:dd HH:mm:ss')
$utc  # 本例应输出 2020:06:01 04:34:56

exiftool -o 'D:\VideoLab\time.mp4' `
  "-QuickTime:CreateDate=$utc" "-QuickTime:ModifyDate=$utc" `
  "-QuickTime:TrackCreateDate=$utc" "-QuickTime:TrackModifyDate=$utc" `
  "-QuickTime:MediaCreateDate=$utc" "-QuickTime:MediaModifyDate=$utc" $video

exiftool -a -G1 -s -CreateDate -ModifyDate -TrackCreateDate -TrackModifyDate -MediaCreateDate -MediaModifyDate 'D:\VideoLab\time.mp4'
```

上面的 UTC 换算由 PowerShell 显式完成，没有再启用 ExifTool 的 QuickTimeUTC 自动时区转换。按这里的默认读法，电脑读回整数时间为 04:34:56，手机在北京时间环境显示 12:34，两者可以是同一时刻。多行命令末尾的反引号是 PowerShell 续行符，后面不要再加空格。

这不是“看到差八小时就全部加八小时”的理由。QuickTime 整数时间、带时区字符串和文件系统时间必须分开解释；在自己的媒体库里，先确认时间所表达的时刻，再决定如何写入。

### 视频定位也不是 JPEG 的 GPS 四件套

回到结构树中的 moov → udta → ©xyz：在这份样本中，修改这里的位置，相册才采用新的坐标。下面用公开的北京地区坐标演示，纬度在前、经度在后；写的是两个数字，不是“北京市”这段地名：

```powershell
exiftool -o 'D:\VideoLab\location.mp4' '-UserData:GPSCoordinates=39.9087 116.3975' $video

# 读回输出：应看到这两个十进制坐标
exiftool -G1 -s -n -UserData:GPSCoordinates 'D:\VideoLab\location.mp4'
```

这里输入的 39.9087 是北纬，116.3975 是东经；负数分别表示南纬和西经。ExifTool 会把数值转换成容器里的 ISO 6709 位置字符串，可能类似 +39.9087+116.3975/：正负号表示方向，最后的斜杠结束字符串。你不需要手工拼接这段底层字符串，使用上面的 ExifTool 数值写法即可。

文件中有坐标后，相册再通过地址服务把它解释成城市、道路等文字。ExifTool 读回坐标正确，是文件层面的检查；手机有没有显示相应地址，是相册层面的检查，两步都要做。

另一个对照只新增 Keys:GPSCoordinates、保留原 UserData 定位，界面仍显示原位置，所以不能省略分组随便写一个同名标签。这个结果没有证明所有相册都忽略 Keys 定位，也没有穷举其他字段缺失时的回退顺序。修改了这一处，也不等于视频里所有历史定位都被清理。

### 合并操作：给自己的一个视频设定机型、时间和地点

如果你希望三个修改都出现在**同一个副本**中，可以执行下面这段完整示例。修改开头的五个输入值，然后检查新输出文件名。纬度、经度和日期都是演示值，恢复真实信息时要替换成有依据的值：

```powershell
$video = 'D:\VideoLab\source.mp4'
$outputVideo = 'D:\VideoLab\custom-01.mp4'  # 该文件必须尚不存在
$model = 'My Video Camera'
$targetTime = [DateTimeOffset]::Parse('2020-06-01T12:34:56+08:00')
$coordinates = '39.9087 116.3975'  # 纬度 经度
$utc = $targetTime.UtcDateTime.ToString('yyyy:MM:dd HH:mm:ss')

exiftool -config profiles/oplus-video.config -o $outputVideo `
  "-Keys:Model=$model" "-Keys:AndroidModel=$model" "-Keys:OplusProductModel=$model" `
  "-QuickTime:CreateDate=$utc" "-QuickTime:ModifyDate=$utc" `
  "-QuickTime:TrackCreateDate=$utc" "-QuickTime:TrackModifyDate=$utc" `
  "-QuickTime:MediaCreateDate=$utc" "-QuickTime:MediaModifyDate=$utc" `
  "-UserData:GPSCoordinates=$coordinates" $video

# 检查所有机型、时间与坐标组，留意是否还有其他组里的旧值
exiftool -a -G1 -s -n -Model -AndroidModel -OplusProductModel -time:all -GPSCoordinates $outputVideo
```

这里显式同步三处机型，避免它们留下互相冲突的名字；它不是相册显示机型的普遍最低要求。时间和定位也只修改命令列出的字段，不会自动清除所有厂商数据。ExifTool 直接写入这一步**没有预览模式**，运行后就生成副本；原片不覆盖，输出重做时换一个新文件名。

读回后，把 $outputVideo 指向的 MP4 按原文件复制到手机的新目录，等待扫描并打开详情。核对文件名、机型、目标本地时间与地点；再播放视频，确认画面、时长和原有声音符合预期。不要把截图中出现一个自定义名字，反过来当成真实拍摄身份的证据。

为了公开展示，我又用同一套方法处理了一段没有私人画面和音轨的 AI 山湖短片：

![视频修改前：人工初始机型、日期，无定位](images/video-before-full.jpg)

![视频修改后：自定义机型、2020 年时间与北京演示坐标](images/video-after-full.jpg)

原生视频副本仍显示 HEVC、60 FPS 和原时长。逐个核对压缩音视频包的哈希、PTS、DTS 和时长，也没有发生变化；原片哈希保持一致。容器文件整体会因元数据变化而改变，这与重新编码画面是两回事。

### 最后才是实验脚本：一次生成五份字段对照

如果目标是设定自己的参数，前面的命令已经能完成；下面这一段是为了复现实验，**不是把自己的参数传给视频批处理**。video_lab.py 当前会固定写入教学值，不能像 repair.py 那样接收 --model、--taken-at 或 --latitude。

我把这轮对照整理成独立的五副本实验，而没有让 JPEG 批处理顺手接管整库视频。除了 Python、ExifTool，还需安装 FFmpeg，并让它附带的 ffprobe 能从 PATH 运行。前面的 ExifTool 手动写入不依赖 FFmpeg；这里需要它来检查压缩媒体包。先确认：

```powershell
ffmpeg -version
ffprobe -version
```

再预览、执行。输出是**新的目录**，而不是前面 ExifTool -o 所需的单个 MP4 文件路径：

```powershell
python scripts/video_lab.py 'D:\VideoLab\source.mp4' --output 'D:\VideoLab\trial-01'
python scripts/video_lab.py 'D:\VideoLab\source.mp4' --output 'D:\VideoLab\trial-01' --apply
```

生成的文件有明确分工：

```text
trial-01/                         # 实验输出目录
├─ MODEL_KEYS.mp4                 # 只写 Keys:Model
├─ MODEL_ANDROID.mp4              # 只写 Keys:AndroidModel
├─ MODEL_OPLUS.mp4                # 只写 Keys:OplusProductModel
├─ TIME_LOCATION.mp4              # 设定教学时间和北京演示坐标
├─ CUSTOM_VIDEO.mp4               # 合并教学机型、时间和坐标
└─ report.json                    # 原片哈希、各副本的压缩媒体包校验结果
```

脚本不会猜真实拍摄信息，也不是视频库批量修复工具。输出目录必须尚不存在，报告和私人视频均不要直接公开。report.json 的包校验不等于相册验收，生成后仍需逐份读回字段、复制到手机核对。[冲突矩阵与验证边界](https://github.com/shisheng820/oppo-gallery-metadata-repair/blob/main/docs/video-metadata.md) 保留在仓库里供查证；日常操作所需的步骤已经放在这篇正文。[ExifTool QuickTime 文档](https://exiftool.org/TagNames/QuickTime.html) 则用于核对字段定义。

这一轮已经验证 ACE 3V 的原生视频与合成视频；一加 15 的视频结果尚待复测。即使文件都以 PXL 开头，也仍然不能凭年份猜测它来自哪台 Pixel。

## 如果让 AI 帮忙，先把输入和验收条件说完整

我也会让 AI 协助整理命令，但不会只说一句“帮我修复元数据”。对自己和 AI 来说，先写清下面这些信息，往往比一开始堆更多字段更有效：

```text
运行环境：Windows / PowerShell；手机与相册版本按实际填写。
输入：一个明确的文件或源目录；说明 JPEG、MP4，还是实况/HDR。
输出：一个全新的目录或文件路径；保留原片。
修改目标：逐项列出字段和值，不需要修改的字段明确保留。
值的依据：设备记录、同批原片、拍摄记录，或纯粹的自定义显示。
时间：写完整日期、时钟和时区；无法确认的部分不要推测。
定位：提供纬度、经度及来源；没有依据就不补。
执行顺序：先读取和解释现状，再选相应入口，先用小样本验证。
验收：读回输出标签，检查媒体未被意外改变，再到手机核对详情。
```

判断结果时，我会分四层：命令执行了、标签读回正确、媒体完整性检查通过、相册显示符合预期。前一层不能代替后一层。比如 video_lab.py 的报告能校验压缩媒体包，却不能替我确认相册选中了哪个同名机型字段；手机上出现一个正确名字，也不能证明其他日期和定位都已经处理好。

对我来说，修复旧媒体库并不是给每一栏都填满。能从可靠信息恢复的，尽量恢复；确实不知道的，保留未知；主动自定义的，就知道它只是自己的标签。

当相册终于能把时间、地点和设备信息摆回合适的位置，那些散落在不同系统里的旧照片，才重新有了可以查找的线索。

---

演示照片署名：Image courtesy of the Earth Science and Remote Sensing Unit, NASA Johnson Space Center。素材来源为 [NASA SVS](https://svs.gsfc.nasa.gov/30613/)，按其[图片与媒体说明](https://www.nasa.gov/nasa-brand-center/images-and-media/)用于教学，不暗示 NASA 对本文或工具作出认可。AI 示意图与真实截图已分别标注。

实机截图分别说明 ACE 3V 的本地验证和一加 15 的用户复测；正文区分了第一版与 v2 的实况结果，并记录实际复原后的文件回读。v2 的一加 15 兼容性仍待复测。
