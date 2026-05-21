# 编码器源码树

`scripts/build_all.sh` 会在此目录（或 `$TOOLS_DIR` 环境变量指向的目录）下按名称 glob 查找四个编码器源码树。

## 预期目录结构

```
tools/
├── JM-JM-19.1/                     （或 JM-JM-19.x）
├── HM-HM-18.0/                     （或 HM-HM-18.x）
├── VVCSoftware_VTM-VTM-23.11/      （或 VTM-23.x）
├── ECM-ECM-18.0/                   （或 ECM-ECM-18.x / 17.x）
└── patches/                        （可选，见下文）
```

## 提供源码的两种方式

### 方式 A — 复制到本目录

```bash
cp -r /path/to/JM-JM-19.1                   tools/
cp -r /path/to/HM-HM-18.0                   tools/
cp -r /path/to/VVCSoftware_VTM-VTM-23.11    tools/
cp -r /path/to/ECM-ECM-18.0                 tools/
```

### 方式 B — 指向外部目录（推荐）

```bash
TOOLS_DIR=/path/to/JM_HM_VTM_ECM make build
```

如果你已经把四个源码树放在某个共享目录下，不想重复存放，推荐使用此方式。
编译脚本会读取 `TOOLS_DIR` 环境变量，转而在该目录下查找源码。

## Patch（修复 ARM macOS 兼容性问题）

如果某个编码器在 Apple Silicon 上编译失败，可以把 patch 文件放入
`tools/patches/<编码器小写>_arm_macos.patch`，例如：

- `tools/patches/ecm_arm_macos.patch`
- `tools/patches/vtm_arm_macos.patch`

编译脚本会在运行 CMake 之前，在对应源码树内自动执行 `git apply`。
如果 patch 已经被应用过，或上游已合并该修复，脚本会记录日志并继续，不会报错。

## 版本固定

Pilot 基线使用的精确版本：

| 编码器 | Tag |
|---|---|
| JM  | JM-19.1 |
| HM  | HM-18.0 |
| VTM | VTM-23.11 |
| ECM | ECM-18.0 |

这些版本记录在 `HANDOFF.md` 中。**不要**原地升级——如果需要改变版本，
请新建一个运行目录，以保证基线对比的有效性。
