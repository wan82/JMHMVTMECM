# 02 — JM 配置详解

> JM 是四个编码器里**唯一需要专门解释**的一档。HM / VTM / ECM 都有 JVET 官方 CTC 文档可以直接照搬，但 JM 是 AVC 时代的产物，**没有任何带 JVET 编号的 CTC 文档**与之配套。
>
> 这一篇说明：JM 的"对齐"是怎么做的、做到哪一层、哪些是 JM 维护者帮我们做好的、哪些是我们运行时注入的。
>
> 这也是论文方法学章节最容易被审稿人攻击的地方——务必读完这一篇。

---

## 1. 为什么 JM 是个特殊问题

视频编码标准的 CTC（Common Test Conditions）体系是 JVET 在 HEVC 时代（约 2010 年起）才正式建立的。在那之前的 AVC 时代，**只有 ad-hoc 的对比实验配置**，每个研究组用自己习惯的参数，论文之间不可比。

到了横向对比四代标准的研究场景，问题就出现了：

| 编码器 | 有对应的 JVET CTC 文档吗 |
|---|---|
| JM (AVC) | **无**——CTC 体系建立时它已经"过时"了 |
| HM (HEVC) | 有（JCTVC-L1100 等） |
| VTM (VVC) | 有（JVET-Y2010 等） |
| ECM (post-VVC) | 有（最新 JVET 会议输出） |

**如果直接用 JM 默认的 `cfg/encoder_main.cfg`，会得到一个"AVC 老配置"对比"HEVC/VVC CTC 配置"的非对称比较**——JM 跑出来的数字会比真实潜力差很多，让 HEVC/VVC/post-VVC 的增益虚高。

## 2. 解决方案：JM 19.x 自带的 HM-like 配置

幸运的是，JM 维护者意识到了这个问题。从 JM-15.x 之后，他们在源码 `cfg/` 目录下加入了一个 `HM-like/` 子目录，**专门为对齐 HM CTC 调好了一套配置**：

```
tools/JM-JM-19.1/cfg/HM-like/
├── encoder_JM_Intra_HE.cfg     ← 对齐 HM encoder_intra_main.cfg
├── encoder_JM_RA_B_HE.cfg      ← 对齐 HM encoder_randomaccess_main.cfg
├── encoder_JM_LB_HE.cfg        ← 对齐 HM encoder_lowdelay_main.cfg (B)
├── encoder_JM_LP_HE.cfg        ← 对齐 HM encoder_lowdelay_P_main.cfg
└── per-sequence_JM/
    ├── BasketballDrill.cfg
    ├── BlowingBubbles.cfg
    ├── Traffic.cfg
    └── ...                     ← 与 HM cfg/per-sequence/ 一一对应
```

"HE" = **High Efficiency**，即开启 CABAC、High Profile、RDOQ、multi-pass RD 等全部高质量编码工具。

本项目的核心做法就是：**把这 4 个 HE 配置文件原样拷到 `configs/jm/`**：

```
configs/jm/
├── encoder_JM_Intra_HE.cfg      ← 与 tools/JM-JM-19.1/cfg/HM-like/ 下完全一致
├── encoder_JM_RA_B_HE.cfg
├── encoder_JM_LB_HE.cfg
└── encoder_JM_LP_HE.cfg
```

可以用 diff 验证字节一致：

```bash
diff configs/jm/encoder_JM_RA_B_HE.cfg \
     tools/JM-JM-19.1/cfg/HM-like/encoder_JM_RA_B_HE.cfg
# 没有任何输出 = 完全一致
```

## 3. HM-like 配置到底改了什么

把 HM-like 配置和 JM 默认的 `cfg/encoder_main.cfg` 对比，关键差异落在 5 个领域。

### 3.1 GOP 结构：启用 HM-5.0 风格 RA 参考帧管理

这是**最重要的差异**。HM-like 在 RA 配置里打开了一组 flag，让 JM 的 B-picture 参考管理逻辑与 HM 5.0 起的 hierarchical-B 拓扑对齐：

```
HM50RefStructure       = 1     # 默认 0；这一项是核心开关
CRA                    = 1     # 默认 0；启用 Clean Random Access 风格
BLevel0MoreRef         = 1     # 默认 0；底层 B 帧多用参考帧（对齐 HM）
BIdenticalList         = 1     # 默认 0；底层 B 帧 list 0 = list 1
ReferenceReorder       = 1     # 配合上面用，按 POC 重排参考帧
HierarchicalCoding     = 3     # 默认 0；3 = 显式 GOP
ExplicitHierarchyFormat = "B3r1B1r2b0e3b2e3B5r2b4e3b6e3"
NumberBFrames          = 7     # 默认 0；7 = GOP 大小 8（含 1 个 anchor）
```

**没有 `HM50RefStructure = 1` 这一项，JM 与 HM 的 GOP 结构完全没法比**。这是 JM 维护者最关键的一笔贡献。

### 3.2 Profile 与熵编码：High Profile + CABAC + 8×8 变换

```
ProfileIDC             = 100   # High Profile (FRExt)，对齐 HEVC Main
SymbolMode             = 1     # CABAC（默认可能是 UVLC）
Transform8x8Mode       = 1     # 启用 8×8 整型变换（FRExt 工具）
```

AVC High Profile 是工具集最接近 HEVC Main 的子档——支持 8×8 变换、加权预测、监控量化等。**不能用 Baseline 或 Main Profile**，那会限制 JM 的能力。

### 3.3 RD 优化：高复杂度全开

```
RDOptimization         = 1     # High-complexity RDO（最强模式）
UseRDOQuant            = 1     # RDOQ on（与 HM 一致）
RDPictureDecision      = 1     # 多 pass RD 决策
SearchMode             = 3     # EPZS 运动搜索（fast & accurate）
EarlySkipEnable        = 1     # 早 skip 检测（与 HM 一致）
SelectiveIntraEnable   = 1     # 选择性 intra 决策
```

这一组对齐了 HM 的"准全开"工具状态。**禁止改成 `encoder_max_performance.cfg`**——那是 JM 关掉 RDOQ 和 multi-pass 的速度优先版本，会让 JM 看上去比真实能力差 1.5–3 dB，对比就不公平了。

### 3.4 加权预测

```
WeightedPrediction       = 1   # P 帧 explicit weighted prediction
WeightedBiprediction     = 1   # B 帧 weighted bi-prediction
ChromaWeightSupport      = 1
UseWeightedReferenceME   = 1
```

HEVC 默认带加权预测，AVC 也支持但默认关闭。HM-like 把它打开，避免在 fade/cross-dissolve 场景被 HEVC 单方面碾压。

### 3.5 Lambda 权重：保持 JM 自己 retune 过的值

```
LambdaWeightISlice       = 0.65
LambdaWeightPSlice       = 0.68
LambdaWeightBSlice       = 0.68
LambdaWeightRefBSlice    = 0.68
```

**注意**：这些 lambda 权重**不等于** HM 的 `α · W_k`。每代标准的 lambda 都是针对自家工具集 retune 过的最优值。JM 用这套权重，HM 用 HM 自己的——**两者数值上不一样，但都让各自跑在自家 RDO 框架下的最优工作点**。

这与你之前问的 "怎么统一 RD-cost" 是同一个问题。再强调一遍：

> **不要试图统一各编码器的 lambda 公式。要统一的是外部测试协议——序列、QP、IntraPeriod、GOP 结构、帧数——而不是 RDO 内部的代价函数。**

这是 Ohm 2012 IEEE TCSVT 论文的方法学，也是 JM HM-like 配置的设计原则。

---

## 4. 运行时 CLI override：第二层"调整"

光有 HM-like cfg 还不够——里面有些字段是序列特定的（路径、尺寸、帧率），还有些是每次运行要变的（QP、IntraPeriod），不能写死在 cfg 里。

`scripts/run_pilot.py` 的 `build_cmd_jm` 函数负责在运行时通过 JM 的 `-p key=value` CLI 机制注入这些参数。

### 4.1 实际生成的命令长什么样

例：跑 BasketballDrill RA QP=32：

```bash
bin/lencod \
    -d configs/jm/encoder_JM_RA_B_HE.cfg \
    -p InputFile=sequences/BasketballDrill_832x480_50.yuv \
    -p OutputFile=runs/2026-05-19_1430_pilot/bitstreams/0017_jm_BasketballDrill_RA_QP32.264 \
    -p ReconFile= \
    -p SourceWidth=832 \
    -p SourceHeight=480 \
    -p OutputWidth=832 \
    -p OutputHeight=480 \
    -p FrameRate=50 \
    -p FramesToBeEncoded=64 \
    -p FrameSkip=0 \
    -p SourceBitDepthLuma=8 \
    -p SourceBitDepthChroma=8 \
    -p OutputBitDepthLuma=8 \
    -p OutputBitDepthChroma=8 \
    -p QPISlice=32 \
    -p QPPSlice=32 \
    -p QPBSlice=32 \
    -p IntraPeriod=32 \
    -p IDRPeriod=32 \
    > runs/2026-05-19_1430_pilot/logs/0017_jm_BasketballDrill_RA_QP32.log 2>&1
```

### 4.2 每个 override 字段的来源

| 字段 | 来源 | 备注 |
|---|---|---|
| `InputFile` | `configs/sequences/BasketballDrill.yaml` + `sequences/` 路径 | cfg 里默认是 Windows 路径 `D:\origCfP\...`，必须覆盖 |
| `OutputFile` | `runs/<timestamp>/bitstreams/<job_id>.264` | 自动生成，job_id 唯一标识 |
| `ReconFile=` | 空字符串 | **关掉重建 YUV**——磁盘节省，pilot 不需要 |
| `SourceWidth/Height` | sequence YAML | 832, 480 |
| `OutputWidth/Height` | sequence YAML | **JM 要求两组都填**（HM/VTM/ECM 只要 SourceWidth） |
| `FrameRate` | sequence YAML | 50 fps |
| `FramesToBeEncoded` | `configs/pilot.yaml` | Pilot=64（1–2 GOP） |
| `FrameSkip` | 固定 0 | CTC 从第 0 帧开始 |
| `SourceBitDepth*` | sequence YAML | 都是 8（pilot 全 8-bit） |
| `OutputBitDepth*` | sequence YAML | 同上 |
| `QPISlice/PSlice/BSlice` | `configs/pilot.yaml` 的 `qps` 列表 | **三个都设成同一个 QP**（CTC 约定） |
| `IntraPeriod` | `ctc_intra_period(fps)` | 50fps→32, 60fps→64 |
| `IDRPeriod` | 同 IntraPeriod | RA 配置下与 IntraPeriod 一致 |

### 4.3 几个细节要注意

**`QPISlice = QPPSlice = QPBSlice`**

JM 默认 cfg 里给的是 `QPISlice=32, QPPSlice=33`——P 帧故意比 I 帧 QP 高 1。**不要**保留这个 cascade。HM-like cfg 里的 `LambdaWeight*`、`BRefPicQPOffset` 和 hierarchical-B 结构内部已经做了 QP cascading，外部传一个 QP 即可。所有四个编码器（JM/HM/VTM/ECM）都按这个约定走，才能公平对比。

**`IntraPeriod` 全编码器对齐**

CTC 规定每种帧率对应一个 IntraPeriod：50/30 fps → 32，60 fps → 64。`run_pilot.py` 的 `ctc_intra_period(fps)` 函数集中处理这个映射。**所有四个编码器用同一个 IntraPeriod 值**——这是公平对比的硬约束。

**AI 配置下强制 IntraPeriod=1**

AI = All Intra = 每帧都是 I 帧。HM-like 的 `encoder_JM_Intra_HE.cfg` 默认就是 1，但 `run_pilot.py` 又显式覆盖了一次，防止从 RA cfg 切过来时漏掉。

**`ReconFile=` 空字符串**

JM 默认会输出一份重建 YUV，对 832×480 64 帧的序列大概 30 MB。64 个任务全开就是 ~2GB——pilot 不需要重建 YUV（PSNR 在编码器内部已经算好），关掉省磁盘和 IO 时间。

**`OutputWidth/Height` 必填**

HM/VTM/ECM 只需要 SourceWidth/SourceHeight，但 JM 的 `lencod` 还需要 OutputWidth/OutputHeight（用于支持 source resize，虽然我们没用这个功能）。如果只设 SourceWidth，JM 会用默认值 176x144 输出，编码结果就错了。**这是一个静默 bug 陷阱**。

---

## 5. 我"调整"了什么——精确版本

到此你应该清楚：我没有改任何 JM 的 .cfg 文件。"调整"分成两层：

### 第一层：选用 JM 自带的 HM-like 配置而不是默认配置

| 我们选 | 我们不选 |
|---|---|
| `cfg/HM-like/encoder_JM_RA_B_HE.cfg` | `cfg/encoder_main.cfg`（默认） |
| `cfg/HM-like/encoder_JM_Intra_HE.cfg` | `cfg/encoder_baseline.cfg` |
| `cfg/HM-like/encoder_JM_LB_HE.cfg` | `cfg/encoder_max_performance.cfg`（速度优先） |
| `cfg/HM-like/encoder_JM_LP_HE.cfg` | `cfg/encoder_extended.cfg` |

这一层"选择"本身就是一个决定——HM-like 是 JM 维护者为横向对比做好的对齐版本。

### 第二层：运行时通过 CLI 注入 per-run 参数

把 HM-like cfg 里写死的路径、QP、帧数、IntraPeriod 在每次运行时覆盖掉。这一层的逻辑完全集中在 `scripts/run_pilot.py` 的 `build_cmd_jm` 函数里，约 30 行代码。**有变更，git diff 一眼就能看到**。

---

## 6. 验证 JM 跑得"对不对"

跑通 sanity check 之后，用一次手动 dry-run 来验证生成的命令是合理的：

```bash
make encode-dry | grep -A1 "jm_BasketballDrill_RA_QP32"
```

应该看到类似上面 §4.1 的命令。检查几个点：

1. `-d` 指向 `configs/jm/encoder_JM_RA_B_HE.cfg` （不是默认 main 或 baseline）
2. `-p` 列表里有 `QPISlice/PSlice/BSlice` 三个，且数值都是 32
3. `IntraPeriod` 是 32（50fps），不是 0 或 16
4. `ReconFile=` 是空（关掉重建）

然后跑一次：

```bash
python scripts/run_pilot.py --jobs 1 --dry-run | head -50
```

如果一切正常，跑出来的 JM 结果应该符合：

| 指标 | 期望区间（BasketballDrill, RA, QP=32, 64 帧） |
|---|---|
| Bitrate | 800–1500 kbps |
| Y-PSNR | 34–37 dB |
| 相对 HM | HM 节省 ~35–45% 码率 |

如果 JM 跑出来**比 HM 还省码率**或 Y-PSNR 更高——**不正常**，立刻排查：

1. JM 的 cfg 是不是被替换或修改了？
2. JM 的 `HM50RefStructure` 是不是 1？
3. JM 与 HM 的 `IntraPeriod` 是不是一致？
4. JM 的 QP 是不是真的传进去了？

---

## 7. 扩展场景

### 7.1 切到 10-bit 序列（NebutaFestival、SteamLocomotiveTrain）

未来扩展 Class A 时会遇到 10-bit 序列。需要：

- HM/VTM/ECM：换 `encoder_*_main10.cfg`（HM）/ VTM/ECM 默认就是 10-bit profile
- JM：在 `build_cmd_jm` 中根据 `seq['bit_depth']` 添加 override：

```python
if seq['bit_depth'] == 10:
    overrides.append("ProfileIDC=110")    # High 10 Profile
```

`InternalBitDepth=10` 在 HM-like cfg 里已经是默认值，不用改。

### 7.2 启用 LDB / LDP 配置

在 `configs/pilot.yaml` 中取消注释：

```yaml
configs:
  - AI
  - RA
  - LDB
  - LDP
```

`run_pilot.py` 的 `CONFIG_MAP` 已经把 LDB/LDP 映射到了 `encoder_JM_LB_HE.cfg` / `encoder_JM_LP_HE.cfg`，**不需要改代码**。

### 7.3 IntraPeriod 按 CTC 表精确取

当前 `ctc_intra_period(fps)` 只区分两档（≥55fps → 64，否则 → 32）。如果未来扩展到 24/25 fps 序列，按 CTC 正式表：

| 帧率 | IntraPeriod |
|---|---|
| 24 fps | 32 |
| 25 fps | 32 |
| 30 fps | 32 |
| 50 fps | 32 |
| 60 fps | 64 |
| 100 fps | 96 |

可以扩 `ctc_intra_period()` 函数。

---

## 8. 引用

- `tools/JM-JM-19.1/CHANGES.TXT` —— JM 19.x 系列改动记录
- `tools/JM-JM-19.1/cfg/HM-like/` —— 上游 HM-like 配置目录
- `docs/JM_CTC_alignment.md` —— 项目内部的方法学文档（即将成为论文 Section）
- Ohm, Sullivan, Schwarz, Tan, Wiegand, *Comparison of the Coding Efficiency of Video Coding Standards—Including HEVC*, IEEE TCSVT, 2012 —— 横向对比方法学基准
- JCT-VC, *Common Test Conditions and Software Reference Configurations*, JCTVC-L1100 —— HM CTC 文档（JM HM-like 的对齐目标）

---

下一篇：[03 启动教程](03_how_to_run.md) —— 从零开始把这个项目跑起来。
