# 00 — 项目大背景

> 这一篇说明：这个项目要解决什么问题、为什么这么设计、对应到什么论文方向、以及 pilot 阶段的取舍。
> 读完这一篇你应该能在 5 分钟内回答："这个 repo 是干嘛的？为什么要这么搞？"

---

## 1. 项目缘起

导师提出一个 conference paper 的方向：横向对比四代视频编码标准的**参考软件实现**，看从 H.264/AVC 到正在开发中的 post-VVC 之间，压缩效率和编码复杂度是如何演化的。

四代标准与对应的参考软件：

| 标准 | 完成年 | 参考软件 | 维护方 |
|---|---|---|---|
| H.264 / MPEG-4 AVC | 2003 | **JM** (Joint Model) | Fraunhofer HHI |
| H.265 / HEVC | 2013 | **HM** (HEVC test Model) | JCT-VC |
| H.266 / VVC | 2020 | **VTM** (VVC Test Model) | JVET |
| 暂未命名 (post-VVC) | 仍在开发 | **ECM** (Enhanced Compression Model) | JVET |

每代之间相隔大约 7–10 年，每一代相对前一代都号称"码率节省 ~50% 同 PSNR"。这个数字在 JVET 的官方报告里反复出现，但**每次都是孤立的两两对比**，缺少一个**统一方法学下的横向四代视图**——这就是本项目要填的空。

## 2. 同类工作的参考标尺

横向对比的方法学有一篇经典论文：

> Ohm, Sullivan, Schwarz, Tan, Wiegand,
> *Comparison of the Coding Efficiency of Video Coding Standards — Including HEVC*,
> IEEE Trans. on Circuits and Systems for Video Technology, Vol. 22, No. 12, Dec. 2012.

它做了 MPEG-2 / H.263 / MPEG-4 / AVC / HEVC 五代标准的统一对比，奠定了后续这类工作的范式：

- **不统一各编码器内部的 lambda / RDO 公式**——每代的 lambda 都是开发者针对自家工具集 retune 过的最优值
- **统一外部测试协议**：同序列、同 QP 集合、可比的 GOP 结构、相同的 IntraPeriod
- **BD-rate 衡量差距**：对每个 (sequence, config) 扫 4 个 QP 拟合 RD 曲线，比较曲线之间的码率差

本项目继承这套方法学，把它**从 5 代延伸到 7 代**（增加 VVC 和 ECM，淘汰已过时的 MPEG-2/H.263）。直接面向的 paper 角度是 ECM 时代的 "Ohm 2012 续集"。

## 3. 项目目标

最终产出（论文中要给出的）：

1. **BD-rate 表**：每代相对前代的码率节省（Y / U / V 各分量，AI / RA 至少两种配置）。
2. **累计 BD-rate**：ECM 相对 JM 的总节省量——回答 "AVC 到 post-VVC 这 20 年累计省了多少"。
3. **编码时间膨胀曲线**：JM → HM → VTM → ECM 的编码时间倍数。这是论文的差异化卖点；Ohm 2012 没重点做这个角度。
4. **方法学描述**：每个编码器的版本、配置、序列、QP、帧数全可复现。

预期结论的量级（基于已发表数据外推）：

| 对比 | 期望 Y-PSNR BD-rate（RA 配置） |
|---|---|
| HM vs JM | -35% ~ -45% |
| VTM vs HM | -30% ~ -40% |
| ECM vs VTM | -15% ~ -25% |
| ECM vs JM（累计） | -75% ~ -85% |

数字落在上述区间就算正常；若严重偏离，**先怀疑流水线有 bug**，再怀疑配置错了。

## 4. Pilot vs 完整 CTC

完整 JVET CTC 覆盖 7 个 Class（A1/A2/B/C/D/E/F），约 20+ 序列，4 种配置（AI/RA/LDB/LDP），4 个 QP，4 个编码器 ≈ **1280 个独立编码任务**。完全跑下来在 Mac Studio M4 Max 单机上要数月时间，特别是 ECM 这一档。

所以 pilot 阶段做了大幅 scope 缩减：

| 维度 | Pilot | 完整 CTC（后续） |
|---|---|---|
| 测试序列 | 2 条（Class C + D） | ~20+ 条（A1/A2/B/C/D/E/F） |
| 最大分辨率 | 832×480 (Class C) | 2560×1600 (Class A) |
| 配置 | AI + RA | + LDB + LDP |
| 帧数 | 64（1–2 GOP） | 完整序列长度 |
| QP | 22, 27, 32, 37 | 同 |
| 编码任务总数 | 64 | ~1280 |
| 预计 wall-clock | ~1–2 周 | 单机不可行，需集群 |

**Pilot 的目的不是产生论文级数据**，而是：

1. 把整套 pipeline 从编码器编译到 BD-rate 报告**端到端跑通**
2. 产出一组小规模但可信的**基线数据**作为后续扩展的回归测试
3. 把项目以可交接的形式留给团队，毕业后由师弟师妹接力跑完整 CTC

## 5. 硬件目标与团队交接

**Pilot 跑在**：Mac Studio (Apple M4 Max, 36 GB RAM, macOS)。

- 单机够用，散热好，可以连续高负载跑 1–2 周
- 但**不够用**于 4K (Class A) 或完整序列长度——这部分会切换到 Linux 集群

项目设计原则之一是 **macOS 与 Linux 双平台一等支持**。构建脚本 `scripts/build_all.sh` 自动检测平台，所有 Python 脚本不依赖任何平台特定 API。师弟师妹接手后切到集群只需要改 `configs/pilot.yaml` 的几个字段，不需要碰代码。

## 6. 这个 repo 的"心法"

如果用三句话概括项目设计哲学：

1. **配置不动，运行时注入**：所有 CTC 配置文件原样使用各编码器维护者提供的官方版本，不在源文件里写死任何 per-run 参数（路径、QP、帧数等）。这些参数运行时通过 CLI 传入。
2. **Pilot 是后续扩展的护栏**：Pilot 数据 commit 到 repo 作为 baseline，任何后续扩展（集群、新序列、新版本编码器）必须先复现 baseline 才能继续。
3. **不修改上游软件**：JM/HM/VTM/ECM 源码绝对不改。要应对平台兼容性问题（比如 ECM 在 ARM macOS 上的 x86 intrinsic），用 patch 文件外挂，便于追踪和回退。

## 7. 阅读顺序

- 本篇（00）：**项目大背景**——为什么做、怎么做、scope。
- [01 项目结构](01_project_structure.md)：每个目录、每个文件是干嘛的。
- [02 JM 配置详解](02_jm_config_explained.md)：JM 这一档的对齐细节（这是审稿人最容易问的地方，必读）。
- [03 启动教程](03_how_to_run.md)：从零开始把 pilot 跑起来。

阅读完这四篇 + `README.md` + `HANDOFF.md`，你就掌握了这个项目的全貌。
