# 测试序列

本目录存放 pilot 使用的原始 YUV 文件。这些文件**不提交**到 git（见 `.gitignore`），
只有 `MANIFEST.csv` 会被追踪。

## Pilot 所需文件

| 文件名 | Class | 大小 | 分辨率 | 帧率 | 来源 |
|---|---|---|---|---|---|
| `BasketballDrill_832x480_50.yuv` | C | ~286 MB | 832×480 | 50 | JVET CTC |
| `BlowingBubbles_416x240_50.yuv`  | D | ~72 MB  | 416×240 | 50 | JVET CTC |

## 下载地址

JVET CTC 测试序列由 Fraunhofer HHI 及汉诺威大学等机构分发，常见获取途径：

- `ftp://hevc:US88Hula@ftp.tnt.uni-hannover.de/testsequences/`（镜像站）
- 直接向导师/课题组要（最可靠；请用下方 MD5 核验）

## 完整性校验

将文件放入本目录后，计算 MD5 并更新 `configs/sequences/` 中对应的 YAML：

```bash
# Linux
md5sum BasketballDrill_832x480_50.yuv
md5sum BlowingBubbles_416x240_50.yuv

# macOS
md5 BasketballDrill_832x480_50.yuv
```

MD5 填入 `configs/sequences/<name>.yaml` 后，`run_pilot.py` 会在启动时自动校验。

## 未来扩展（Class A）

```
Traffic_2560x1600_30_crop.yuv          ~1.2 GB
PeopleOnStreet_2560x1600_30_crop.yuv   ~1.2 GB
```

Pilot 阶段**不需要**这两个文件，扩展到完整 CTC 时再添加。
