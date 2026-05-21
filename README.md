# codec-comparison-pilot

对 JM (AVC) / HM (HEVC) / VTM (VVC) / ECM (post-VVC) 在一组 JVET CTC 序列上进行横向对比的 pilot 项目。
设计上支持在 pilot 阶段结束后由团队扩展到完整 CTC。

> **License note.** Third-party encoder sources under `tools/` (JM, HM, VTM, ECM)
> are redistributed under their respective licenses — see each
> `tools/<encoder>/COPYRIGHT_ITU.txt`, `COPYRIGHT_ISO_IEC.txt`, and
> `disclaimer.txt` file. The pilot scaffolding (scripts, configs, docs in this
> repo) is original work and may be reused freely for academic purposes.

## 范围（pilot）

- 测试序列：**BasketballDrill**（Class C）+ **BlowingBubbles**（Class D）
- 配置：**AI**（全帧内）+ **RA**（随机接入）
- QP：22、27、32、37
- 每次编码帧数：64（覆盖 1 个 AI GOP 和 2 个 RA GOP）
- 总计：4 个编码器 × 2 个序列 × 2 种配置 × 4 个 QP = **64 次编码**
- 目标硬件：Mac Studio M4 Max 36 GB
- 预计耗时：约 1–2 周（ECM 是瓶颈）

Class B 序列被有意去掉，以保持 pilot 的可控性。
如需修改范围，见 `configs/pilot.yaml`。

## 快速开始

```bash
# 1. 创建 Python venv 并安装依赖
make venv
source .venv/bin/activate

# 2. 指定编码器源码目录（二选一）
#    (a) 将源码复制到 tools/ — 详见 tools/README.md
#    (b) 或设置 TOOLS_DIR 环境变量：
export TOOLS_DIR=/path/to/JM_HM_VTM_ECM   # 改成你机器上四个编码器源码所在的父目录

# 3. 编译全部四个编码器（M4 Max 上约需 10–30 分钟）
make build

# 4. 将 YUV 文件放入 sequences/ — 详见 sequences/README.md
#    (BasketballDrill_832x480_50.yuv, BlowingBubbles_416x240_50.yuv)

# 5. 快速验证（每个编码器跑一次极小编码，约 1 分钟）
make sanity

# 6. 打印任务矩阵但不实际执行
make encode-dry

# 7. 正式运行 pilot 编码矩阵
make encode

# 8. 解析日志、计算 BD-rate、生成报告
make parse bdrate report
```

## 目录结构

```
codec-comparison-pilot/
├── README.md                ← 当前文件
├── HANDOFF.md               ← 团队交接说明
├── Makefile                 ← 顶层入口
├── requirements.txt         ← Python 依赖
├── .venv/                   ← 由 `make venv` 创建
│
├── configs/
│   ├── pilot.yaml           ← 范围与并发配置
│   ├── jm/                  ← JM HM-like CTC 配置文件
│   ├── hm/                  ← HM 官方 CTC 配置文件
│   ├── vtm/                 ← VTM 官方 CTC 配置文件
│   ├── ecm/                 ← ECM 官方 CTC 配置文件
│   └── sequences/           ← 每条序列的 YAML 元数据
│
├── docs/
│   └── JM_CTC_alignment.md  ← JM 如何与 CTC 对齐的说明
│
├── tutorial/                ← 项目教程（00–03 + 入口 README）
├── scripts/                 ← 编译、运行、解析、BD-rate、报告、验证脚本
├── tools/                   ← 编码器源码树（入 git；build/ 和 bin/ 已忽略）
├── sequences/               ← 原始 YUV 文件（已加入 .gitignore，manifest 被追踪）
├── bin/                     ← 编译好的编码器二进制（已加入 .gitignore）
├── runs/                    ← 每次运行的日志与码流（已加入 .gitignore）
├── results/                 ← 解析后的 CSV + 基线（被追踪）
└── report/                  ← 最终结果报告与图（build_report.py 产出）
```

## 固定的编码器版本

| 编码器 | Tag        |
|--------|------------|
| JM     | JM-19.1    |
| HM     | HM-18.0    |
| VTM    | VTM-23.11  |
| ECM    | ECM-18.0   |

不要原地升级版本；任何版本变更都应视为一次全新运行。

## 平台支持

- **macOS** Apple Silicon（首要目标 — Mac Studio M4 Max）
- **Linux**（Ubuntu 22.04+）— 完全支持，用于团队迁移到集群跑完整 CTC 时

编译脚本会自动检测平台并选择合适的并行度。
ARM macOS 的特殊问题见 `tools/README.md`。

## 如何扩展范围

打开 `configs/pilot.yaml`，取消注释所需内容：

```yaml
configs:
  - AI
  - RA
  - LDB    # 取消注释以支持完整 CTC
  - LDP    # 取消注释以支持完整 CTC

sequences:
  - BasketballDrill
  - BlowingBubbles
  - Traffic         # Class A1 — 取消注释以支持完整 CTC
  - PeopleOnStreet  # Class A2 — 取消注释以支持完整 CTC
```

然后重新运行 `make encode`（会新建一个 `runs/<时间戳>/` 目录）。

## 更多说明

- `docs/JM_CTC_alignment.md` — 解释 JM 如何配置以与 HM/VTM/ECM CTC 方法论对齐
- `HANDOFF.md` — pilot 阶段结束后的团队交接指南
