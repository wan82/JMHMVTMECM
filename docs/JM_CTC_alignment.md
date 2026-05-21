# JM CTC 对齐说明

> **目的**：说明本项目中 JM (H.264/AVC) 参考软件如何被配置为与 JVET CTC（Common Test Conditions）兼容的运行模式，以保证与 HM / VTM / ECM 的横向 BD-rate 对比有意义。
>
> **结论**：JM 19.1 官方在 `cfg/HM-like/` 下已经提供了与 HM CTC 风格对齐的配置文件，**不需要从零写一份 JM CTC**。本文档解释这些文件如何来的、为什么这么配，以及在 full-CTC 流程中应如何使用和扩展。

---

## 1. 背景：JM 时代为何没有"官方 CTC"

H.264/AVC 在 2003 年定稿，JVET 一直到 HEVC 时代（2010+）才正式引入 Common Test Conditions 文档（JCTVC-L1100 等）。JM 19.x 是历史遗留的 AVC 参考实现，**没有 JVET 编号的 CTC 文档**与之绑定。

但 JM 维护者注意到了横向对比研究的需求，**在 JM-15.x 之后逐步往 `cfg/HM-like/` 目录里加入了一组与 HM 配置对齐的样板配置**。我们用的 JM 19.1 已经包含完整一套：

```
cfg/HM-like/
├── encoder_JM_Intra_HE.cfg     # 对应 HM encoder_intra_main.cfg
├── encoder_JM_RA_B_HE.cfg      # 对应 HM encoder_randomaccess_main.cfg
├── encoder_JM_LB_HE.cfg        # 对应 HM encoder_lowdelay_main.cfg (B)
├── encoder_JM_LP_HE.cfg        # 对应 HM encoder_lowdelay_P_main.cfg
└── per-sequence_JM/            # 与 HM cfg/per-sequence/ 一一对应
```

"HE" = High Efficiency，也就是开启 RDO、CABAC、High Profile 等高效模式，对应 HM 的 main profile。**本项目直接采用这一组配置**，并将其拷贝到 `configs/jm/` 作为权威版本。

---

## 2. HM-like 配置做了什么对齐

下面对照 HM CTC 的几个关键维度，说明 JM HM-like 配置如何对应。

### 2.1 Profile 与 Level

| 维度 | HM CTC (Main) | JM HM-like (HE) | 说明 |
|---|---|---|---|
| Profile | Main (HEVC) | High Profile (`ProfileIDC = 100`) | AVC 的 High Profile 是最接近 HEVC Main 的内容工具集 |
| Entropy | CABAC | CABAC (`SymbolMode = 1`) | UVLC 已被淘汰 |
| Transform | 4x4 / 8x8 (HEVC: 多尺寸 TU) | `Transform8x8Mode = 1` | 启用 8x8 整型变换 (FRExt) |
| Bit depth | 8 (或 10) | 8 (`SourceBitDepthLuma = 8`) | 内部 10-bit 默认开（`InternalBitDepth = 10`） |

### 2.2 GOP 结构

#### All Intra (AI)

| | HM `encoder_intra_main.cfg` | JM `encoder_JM_Intra_HE.cfg` |
|---|---|---|
| IntraPeriod | 1（每帧都是 I 帧） | `IntraPeriod = 1`, `IDRPeriod = 1` |
| Hierarchy | 不适用 | `HierarchicalCoding = 0` |
| NumberBFrames | 0 | 0 |

→ 完全对齐。AI 在两个标准下都是"每帧 I 帧"。

#### Random Access (RA)

| | HM `encoder_randomaccess_main.cfg` | JM `encoder_JM_RA_B_HE.cfg` |
|---|---|---|
| GOP 大小 | 16（hierarchical B） | `NumberBFrames = 7`（即 GOP=8 层级 B；HM-like 模板默认值，full-CTC 会按分辨率调整） |
| Hierarchy | 4 层 hierarchical-B | `HierarchicalCoding = 3`（显式 GOP）+ `ExplicitHierarchyFormat = "B3r1B1r2b0e3b2e3B5r2b4e3b6e3"` |
| Random access | CRA + open GOP | `CRA = 1`, `HM50RefStructure = 1` |
| Reference 管理 | HM 5.0 风格 RPS | `BLevel0MoreRef = 1`, `BIdenticalList = 1`, `ReferenceReorder = 1` |
| IntraPeriod | 由序列决定（见 §3） | `IntraPeriod = 0`（默认每序列重写） |

→ 关键飞跃：JM HM-like 通过 `HM50RefStructure = 1` 这个 flag **显式启用**了 HM 5.0 时代的参考帧管理模式，让 JM 的 B-picture referencing 与 HM RA 在结构上对齐。这是该配置最重要的一个开关。

#### Low-Delay B (LB) / Low-Delay P (LP)

| | HM lowdelay | JM `encoder_JM_LB_HE.cfg` / `LP_HE.cfg` |
|---|---|---|
| LowDelay | 是 | `LowDelay = 1` |
| GOP 长度 | 4（hierarchical B with reference cascade） | `NumberBFrames = 3`，`HierarchicalCoding = 3` + 显式 GOP |
| IntraPeriod | 1 秒（≈fps 帧）插入一次 I | `IntraPeriod = 0` 默认（每序列覆写） |
| LDRefSetting | 用 JCTVC-F701 风格 | `LDRefSetting = 1` |
| P-only? | LP 用 P-slice 替换 B | LP 用 `PReplaceBSlice = 1` |

### 2.3 RD-cost / Lambda

每个 HM-like JM 配置中都有：

```
LambdaWeightISlice    = 0.65
LambdaWeightPSlice    = 0.68
LambdaWeightBSlice    = 0.68
LambdaWeightRefBSlice = 0.68
```

实际 lambda 公式：

```
λ = LambdaWeight_X · 2^((QP - 12) / 3)
```

这与 HM 的 lambda 公式形式上一致（HM 用 `α · W_k · 2^((QP-12)/3)`，其中 α 和 W_k 取决于 slice type 和 temporal layer）。**两者不可能数值上完全一样**——因为各自针对自己的工具集做了 retune——但量纲、形式、对 QP 的依赖完全对齐。

> **这一点回应你之前问的"如何统一 RD-cost"**：JM HM-like 没有把 lambda 改成与 HM 一致，而是保持 JM 自己 retune 过的 lambda（让 JM 在自身 RDO 框架下达到最佳压缩），这恰恰是 Ohm 2012 倡导的方法学。详情见 §5。

### 2.4 高复杂度 RDO 模式

```
RDOptimization        = 1   # RD-on (high complexity)
SearchMode            = 3   # EPZS
SearchRange           = 64  # CTC 默认值（HE 配置中用 128，对 1080p+ 序列也要对齐 HM）
UseRDOQuant           = 1   # RDOQ on
EarlySkipEnable       = 1   # 与 HM fast skip 等价
RDPictureDecision     = 1   # multi-pass RD decision
```

→ JM 在 HE 模式下打开了所有高质量编码工具，这是与 HM "Main" 配置做公平比较的前提。**禁止改成 max performance 模式（`encoder_max_performance.cfg`），那会偏向 JM 不利。**

### 2.5 Weighted Prediction

```
WeightedPrediction    = 1   # explicit
WeightedBiprediction  = 1   # explicit
```

HEVC 默认带 weighted prediction，HM-like JM 配置同样启用，确保在 fade/cross-dissolve 场景下不会因为缺工具而吃亏。

---

## 3. Full-CTC 流程下如何使用 JM HM-like 配置

### 3.1 命令行调用约定

JM 与 HM/VTM/ECM 的 CLI **语法不同**，需要分别处理。

#### HM/VTM/ECM 风格

```bash
TAppEncoder \
    -c configs/hm/encoder_randomaccess_main.cfg \
    -c configs/sequences/BasketballDrill.cfg \
    --InputFile=sequences/BasketballDrill_832x480_50.yuv \
    --BitstreamFile=runs/.../bs.bin \
    --ReconFile=/dev/null \
    -q 32 \
    --FramesToBeEncoded=64 \
    --IntraPeriod=32 \
    --SEIDecodedPictureHash=1 \
    > runs/.../log.txt 2>&1
```

支持多个 `-c` 累加；命令行 override 用 `--Key=Value`。

#### JM 风格

```bash
lencod \
    -d configs/jm/encoder_JM_RA_B_HE.cfg \
    -f configs/sequences/BasketballDrill_JM.cfg \
    -p InputFile="sequences/BasketballDrill_832x480_50.yuv" \
    -p OutputFile="runs/.../bs.264" \
    -p ReconFile="/dev/null" \
    -p QPISlice=32 -p QPPSlice=32 -p QPBSlice=32 \
    -p FramesToBeEncoded=64 \
    -p IntraPeriod=32 -p IDRPeriod=32 \
    > runs/.../log.txt 2>&1
```

JM 用 `-d` 表示主配置（"default config"），`-f` 表示二次合并的配置，`-p KEY=VALUE` 表示参数覆盖。注意 **`-p` 后面紧跟键值对，不能有空格**。

本项目的 `scripts/run_pilot.py` 负责屏蔽这两种 CLI 的差异，对所有四个编码器对外暴露统一的接口。

### 3.2 IntraPeriod 按 CTC 推荐

CTC 给每种 (分辨率, 帧率) 组合规定了一个 IntraPeriod：

| 帧率 | IntraPeriod |
|---|---|
| 24 fps | 32 |
| 30 / 50 fps | 32 |
| 60 fps | 64 |

对 Pilot 涉及的两个序列（BasketballDrill@50fps、BlowingBubbles@50fps），CTC 推荐 IntraPeriod = 32。`run_pilot.py` 会从 sequence YAML 中读 fps 并自动计算。**JM 与 HM/VTM/ECM 用相同的 IntraPeriod**，这是公平对比的硬约束。

### 3.3 QP 列表

CTC 标准：`QP ∈ {22, 27, 32, 37}`。

- HM/VTM/ECM：用 `-q 32` 一个参数即可，编码器内部根据 slice type 和 hierarchy level 自动 cascade。
- JM HM-like：需要同时设置 `QPISlice`、`QPPSlice`、`QPBSlice` 三个，**用相同的 QP**，HM-like 配置内部的 `LambdaWeight*` 和 `BRefPicQPOffset` 会处理后续 cascade。

`run_pilot.py` 会按这个约定生成命令行。

### 3.4 帧数与 FrameSkip

`FramesToBeEncoded` 在 pilot 中固定为 64（覆盖 AI 1 个 GOP 和 RA 2 个 GOP）。扩展到完整 CTC 时，应改为每个序列的完整长度（写在 sequence YAML 的 `total_frames` 字段）。

JM HM-like 配置默认 `FrameSkip = 0`。CTC 也是从第 0 帧开始。**不要改**。

### 3.5 per-sequence 配置

JM 19.1 已经在 `cfg/HM-like/per-sequence_JM/` 下提供了所有 JVET CTC 序列的 JM 风格 per-sequence 配置（含 BasketballDrill、BlowingBubbles、以及未来要用的 Traffic、PeopleOnStreet 等）。

但这些文件用的是 Windows 路径（`InputFile = "../../origCfP/..."`），所以本项目**不直接使用它们**，而是在 `run_pilot.py` 中根据 `configs/sequences/<Name>.yaml` 动态生成一份临时 JM per-sequence cfg。这样有几个好处：

- 路径跨平台（macOS / Linux）
- `FramesToBeEncoded`、QP、IntraPeriod 等可以从 pilot.yaml 集中控制
- 不污染原始上游配置

---

## 4. Profile 选择的取舍

HM CTC Main profile 是 8-bit。VVC Main 10 profile 是 10-bit。这两个标准的"参考点"位深不一样。在本 pilot 中：

| 编码器 | 输入 | 内部 | 输出 |
|---|---|---|---|
| JM (High@8) | 8-bit | 8-bit | 8-bit |
| HM Main | 8-bit | 8-bit | 8-bit |
| VTM Main 10 | 8-bit → 上变换到 10 | 10-bit | 10-bit |
| ECM | 同 VTM | 10-bit | 10-bit |

**这是 CTC 默认行为，本项目不偏离**。PSNR 计算在 YUV 重建后做（HM/VTM/ECM 的 log 中已给出 8-bit 输入对应的 PSNR，可直接对比 JM 的 PSNR）。

如果未来要做 10-bit 对比（Class A 的 NebutaFestival 和 SteamLocomotiveTrain 本身就是 10-bit），需要把所有编码器都切到 10-bit profile，详见 §6。

---

## 5. RD-cost 的"统一"——澄清一个常见误解

> **常被误解为**：要做公平横向对比，必须把 JM、HM、VTM、ECM 的 lambda 公式改成一样。
>
> **正确做法**：保留各自的 lambda（每代都是针对自家工具集 retune 过的最优），但**在外部协议层面统一**：同一序列、同一 IntraPeriod、同一 QP 集合、同一帧数、等价的 GOP 结构。比较 BD-rate（多个 QP 操作点拟合的 RD 曲线），而不是单点。

JM HM-like 配置 **没有** 把 `LambdaWeight*` 强行改成 HM 的数值。它做的是结构对齐（GOP、参考管理、profile、工具集），**让 JM 跑在它自己被调好的 RDO 工作点上，但在外部测试条件上与 HM 一致**。这正是 Ohm 2012 IEEE TCSVT 用的方法学。

**重要纪律**：

- 不要去改 `configs/jm/encoder_JM_*_HE.cfg` 中的 `LambdaWeight*` 字段。
- 不要去改 `configs/hm/`、`configs/vtm/`、`configs/ecm/` 下的 lambda 相关项。
- 任何一行改动都必须在 `docs/JM_CTC_alignment.md` 和 `HANDOFF.md` 中记录原因。

---

## 6. 扩展到 full-CTC（Class A1/A2 与 10-bit）

接手人在 pilot 通过后扩展到完整 CTC 时，关于 JM 的注意事项：

### 6.1 添加 Class A1/A2 序列

- 把 `cfg/HM-like/per-sequence_JM/{Traffic,PeopleOnStreet,NebutaFestival_10bit,SteamLocomotiveTrain_10bit}.cfg` 作为参考。
- 写本项目的 `configs/sequences/{Traffic,PeopleOnStreet}.yaml`（已留了 stub）。
- Class A 是 2560x1600 @ 30 fps，IntraPeriod 仍是 32。
- 序列长度由 sequence YAML 控制；CTC 推荐 150 帧。

### 6.2 切换到 10-bit (NebutaFestival, SteamLocomotiveTrain)

对 JM HM-like 需要改：

```
ProfileIDC            = 110     # High 10 (替换原来的 100)
SourceBitDepthLuma    = 10
SourceBitDepthChroma  = 10
OutputBitDepthLuma    = 10
OutputBitDepthChroma  = 10
InternalBitDepth      = 10      # 已经是 10
```

对 HM/VTM/ECM：用 `encoder_intra_main10.cfg` / `encoder_randomaccess_main10.cfg` 等 10-bit 变体（HM 有，VTM/ECM 直接 Main 10 是默认）。

### 6.3 LDB / LDP 配置启用

只需在 `configs/pilot.yaml` 的 `configs:` 列表中取消注释 LDB / LDP 即可：

```yaml
configs:
  - AI
  - RA
  - LDB    # 取消注释
  - LDP    # 取消注释
```

`run_pilot.py` 会自动映射到：

- JM: `encoder_JM_LB_HE.cfg` / `encoder_JM_LP_HE.cfg`
- HM: `encoder_lowdelay_main.cfg` / `encoder_lowdelay_P_main.cfg`
- VTM: `encoder_lowdelay_vtm.cfg` / `encoder_lowdelay_P_vtm.cfg`
- ECM: `encoder_lowdelay_ecm.cfg` / `encoder_lowdelay_P_ecm.cfg`

---

## 7. Sanity Check：JM 跑出来的结果合不合理

CTC RA + BasketballDrill (832x480 @ 50fps) 64 帧的典型 JM 输出（QP=32），可大致期望：

| 指标 | 期望区间（QP=32） |
|---|---|
| 比特率 | 800–1500 kbps |
| Y-PSNR | 34–37 dB |
| 与 HM 同条件比较 | HM 节省 ~35–45% 比特率 |

如果 JM 跑出来比 HM **更省比特率**或 PSNR 更高，**立即排查**：

1. JM 是否真的开了 `HierarchicalCoding = 3` + `HM50RefStructure = 1`？
2. JM 的 `IntraPeriod` 是否与 HM 一致？
3. JM 是否在用 `encoder_baseline.cfg`/`encoder_max_performance.cfg` 而非 HM-like？

---

## 8. 参考

- JM source: `tools/JM-JM-19.1/cfg/HM-like/README*` 和 `JM-19.1/CHANGES.TXT`
- HM CTC: JCTVC-L1100, "Common Test Conditions and Software Reference Configurations"
- VTM CTC: JVET-Y2010 及更新版本
- ECM CTC: JVET 最新会议输出（与 ECM tag 配套的 software guidelines）
- Ohm, Sullivan, Schwarz, Tan, Wiegand, *Comparison of the Coding Efficiency of Video Coding Standards—Including HEVC*, IEEE TCSVT, Vol. 22, No. 12, Dec. 2012.
