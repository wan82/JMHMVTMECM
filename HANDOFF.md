# HANDOFF — codec-comparison-pilot

> 写给在我（xiangyu.wan）毕业后接手这个项目并把它扩展到完整 JVET CTC 的同学/师弟师妹。

---

## 1. 你拿到了什么

一个端到端可运行的 pilot 项目，覆盖：

- 4 个参考软件（JM-19.1 / HM-18.0 / VTM-23.11 / ECM-18.0）
- 2 个测试序列（BasketballDrill Class C + BlowingBubbles Class D）
- 2 种配置（AI + RA）
- 4 个 QP（22, 27, 32, 37）

并且已经把脚手架搭好了：

- 跨平台编译脚本（macOS + Linux 都支持）
- Python venv（不依赖 conda）
- 任务调度（可恢复、可并发）
- 日志解析、BD-rate 计算、报告生成
- Pilot baseline 验证脚本

Pilot 在 Mac Studio M4 Max 上已经跑完，基线 commit 在 git 历史里
（搜 `Pilot baseline`）。当时拿到的 headline 数字（RA, Y-PSNR）：

| 对比 | BasketballDrill | BlowingBubbles |
|---|---|---|
| HM vs JM | −46.4% | −32.4% |
| VTM vs HM | −35.2% | −24.8% |
| ECM vs VTM | −27.8% | −22.1% |
| **ECM vs JM (累积四代)** | **−74.7%** | **−59.9%** |

时间 ratio（相对 JM, RA）：HM 0.77×（更快，见 §7.6），VTM 9.5×，ECM 99×。

如果你的复现数字偏离这些超过 1%，先排查 §6 的 pitfalls，再考虑环境差异。

---

## 2. 第一件事：复现 pilot

**不要直接扩展到完整 CTC**。先确认你的环境能复现 pilot：

```bash
cd codec-comparison-pilot
make venv
source .venv/bin/activate

# Either copy encoder sources into tools/ or point TOOLS_DIR
export TOOLS_DIR=/path/to/encoder/sources

make build
make sanity                     # 几分钟，验证编译
# Drop YUVs into sequences/ (see sequences/README.md)
make encode                     # pilot: 4-8 小时 (M4 Max);  full CTC: 1–2 周
                                # 内部会先调 make subsample-ai 生成 AI 8 帧 YUV
make parse bdrate report
make verify-baseline            # 关键：必须 PASS
```

如果 `verify-baseline` 没过，**不要**继续扩展，先排查：

- 编码器版本是否对齐？（见 §3）
- 序列文件 MD5 是否对齐？
- 配置文件是否被修改过？

误差容忍：`|ΔY-PSNR| < 0.05 dB` 且 `|Δbitrate|/baseline < 1%`。

---

## 3. 编码器版本——绝对不要改

| Encoder | Pinned Tag |
|---|---|
| JM  | JM-19.1 |
| HM  | HM-18.0 |
| VTM | VTM-23.11 |
| ECM | ECM-18.0 |

**任何版本变化都使既有 baseline 失效**。如果你必须升级（比如 ECM 出了新 release），
按以下流程做：

1. 在 README.md 和这里的表格中更新 tag
2. 重新跑 pilot scope（make encode）
3. 把新的 raw_metrics.csv 拷贝为新的 baseline（`make verify-baseline` 在没有 baseline 时
   会自动 stamp 当前结果为基线）
4. **明确告知导师**版本变化，记录在 git commit message 里

---

## 4. 扩展到完整 CTC

### 4.1 Class A1 / A2 (4K)

需要做的事：

1. 在 `configs/pilot.yaml` 中取消注释 `Traffic` 和 `PeopleOnStreet`：

   ```yaml
   sequences:
     - BasketballDrill
     - BlowingBubbles
     - Traffic
     - PeopleOnStreet
   ```

2. 下载对应 YUV，放到 `sequences/`，更新 MANIFEST 中的 MD5。

3. 调整 `frames_to_encode`。Pilot 用了 64 帧；完整 CTC 应当跑完整序列（150 帧
   对 Class A）。`configs/sequences/Traffic.yaml` 里的 `total_frames` 字段是单一来源。

4. **内存检查**：Mac Studio 36GB **跑不动 4K ECM RA 并行**。Class A 部分**必须**
   切到 Linux 集群（见 §5）。或者把 `parallel_jobs` 降到 1，串行跑（但 ECM 4K
   RA 一个 QP 可能要几天）。

### 4.2 LDB / LDP 配置

取消注释 `configs/pilot.yaml` 中的 LDB / LDP：

```yaml
configs:
  - AI
  - RA
  - LDB
  - LDP
```

`run_pilot.py` 内的 `CONFIG_MAP` 已经把 LDB/LDP 映射到了每个编码器的对应配置文件，
不需要改代码。

### 4.3 完整序列长度

把 `configs/pilot.yaml` 的 `frames_to_encode` 改成一个明显大于任何序列长度的值
（例如 100000），然后 `run_pilot.py` 会自动用 sequence YAML 中的 `total_frames`
做上限。**当前实现没做这个 clamp**，需要小改。Pilot 不需要这个。具体修改：

`scripts/run_pilot.py` 里 `build_command()` 调用前，加一行：

```python
frames = min(int(pilot_cfg["frames_to_encode"]), seq["total_frames"])
```

替换原来的 `frames = int(pilot_cfg["frames_to_encode"])`。

### 4.4 其他 Class（B / E / F）

- **Class B (1080p)**：BQTerrace、Cactus、Kimono、ParkScene、BasketballDrive、Tango2、
  FoodMarket4、MarketPlace、RitualDance、CatRobot1 等。每个加一份
  `configs/sequences/<Name>.yaml`。
- **Class E (720p)**：FourPeople、Johnny、KristenAndSara。
- **Class F (屏幕内容)**：BasketballDrillText、ChinaSpeed、SlideEditing、SlideShow。
  注意 Class F 通常需要 screen content coding 工具，配置稍有不同（HM/VTM/ECM 各有
  对应的 `_scc.cfg` 变体，pilot 没复制，需要手工 cp 过来并加到 `CONFIG_MAP`）。

### 4.5 AI 模式的子采样（JVET CTC TSR=8）

Pilot 已经按 JVET VVC CTC 的官方做法实现了 AI 子采样：每 8 帧取 1 帧
（`TemporalSubsampleRatio=8`）。原因是 AI 完全 intra，相邻 intra 帧 R-D 数据接近重复——
JVET 自己也只采样测试。**全 CTC 扩展时此设定无需改动**。

实现细节（万一你要扩展或排查）：

- VTM/ECM 的 `encoder_intra_*.cfg` **默认就有** `TemporalSubsampleRatio=8`
- HM 18.0 的 AI cfg 默认是 1，pilot 在 `run_pilot.py` 里强制传 `--TemporalSubsampleRatio=8`
- JM 没有这个参数，pilot 通过 `scripts/extract_ai_subsample.py` 预先把每 8 帧抽出 1 帧
  写到 `sequences/<Name>_AI_TSR8.yuv`，JM 再读这个文件
- 为了让 bitrate kbps 单位一致（HM/VTM/ECM 内部按 fps/8 算，比如 50fps → 6.25Hz），
  JM 被告知 `FrameRate=fps/8`
- `make encode` 会自动调 `make subsample-ai`，幂等，不会重复生成

如果你（按导师建议）想**只跑 RA、不要 AI**，把 `configs/pilot.yaml` 里 `configs:` 改成：

```yaml
configs:
  - RA
```

即可。所有 AI 相关逻辑会被自动跳过。

### 4.6 QP 范围（重要！pilot 不够宽）

Pilot 用了 `qps: [22, 27, 32, 37]`，跑出来的 BD-rate 报告里有 9 条
`Insufficient curve overlap` warning（重叠度 47-73%，低于推荐 75%）。

跨代编码器（尤其 JM vs ECM）在同 QP 下 bitrate 差太大，4 个点拟合不够稳。
**完整 CTC 强烈建议** 扩到 6 个 QP 点：

```yaml
qps: [17, 22, 27, 32, 37, 42]
```

QP17 给 JM/HM 一个低码率端的锚点；QP42 给 ECM 一个高码率端的锚点。这样 BD-rate 数字
跟 JVET 公布值会贴得很近（pilot 的 ECM-vs-VTM Y 跑出 −22~−28%，偏高，主要就是
overlap 不够；JVET 公布在 −10% 量级）。

---

## 5. 迁移到 Linux 集群

`scripts/build_all.sh` 在 Linux 上原样可用（自动检测 `Linux` 平台、用 `nproc`）。

`scripts/run_pilot.py` 用的是 `concurrent.futures.ProcessPoolExecutor`，单机多进程。
集群上有两种走法：

### 5.1 单大节点 + 提高 parallel_jobs

如果集群给你一个 64+ 核的大节点，直接：

```yaml
# configs/pilot.yaml
parallel_jobs: 32
```

够大、够省事。

### 5.2 SLURM job array

每个 (encoder, sequence, config, qp) 提交一个独立 SLURM job：

```bash
# 提交骨架（需要自己写一个简单的 wrapper）
python scripts/run_pilot.py --dry-run | \
  awk '/^# / && !/jobs/' | \
  while read -r line; do
    JOB_ID=$(echo "$line" | awk '{print $2}')
    sbatch --job-name="$JOB_ID" --output=runs/<run_id>/logs/"$JOB_ID".slurm \
           --wrap="$(echo "$line" | sed 's/^# //')"
  done
```

更系统的做法是写一个 `scripts/run_cluster.py`，复用 `run_pilot.py` 里的 `expand_matrix`
和命令构建逻辑，把任务转换成 SLURM `--array=0-N` 提交。**这部分 pilot 没实现**。

ECM RA 4K 单任务可能 ≥ 24 小时，记得 `--time` 给充分（72:00:00 比较安全）。

---

## 6. 已知 Pitfalls

### 6.1 JM 配置不能用 max performance

`tools/JM-JM-19.1/cfg/encoder_max_performance.cfg` 是 JM 关掉 RDOQ、多 pass 等
高质量工具的版本——**不能用它做对比**。本项目用的是 `cfg/HM-like/encoder_JM_*_HE.cfg`。
见 `docs/JM_CTC_alignment.md`。

### 6.2 ECM 在 ARM macOS 上编译失败

如果碰到 `error: use of undeclared identifier '_mm_xxx'` 类似的 x86 intrinsic 报错：

1. 看 ECM 那次提交是不是临时引入了 x86-only 代码
2. 把对应文件加 `#ifdef __x86_64__` 守卫，写成 patch 放进 `tools/patches/ecm_arm_macos.patch`
3. build_all.sh 会在编译前自动 `git apply` 此 patch

### 6.3 编码时间在 M4 Max 上不能直接外推到 Linux 服务器

报告时**只用 time ratio（相对 JM 或相对 HM）**，不要用绝对秒数。绝对数字与机器强相关。

### 6.4 路径里有空格

把项目放到不带空格的路径下。JM 的 `-p InputFile=...` 在 shell 转义上对空格非常脆弱。

### 6.5 BD-rate 实现差异

`scripts/compute_bdrate.py` 用的是 FAU-LMS 的 `bjontegaard` PyPI 包（注意是
`bjontegaard` 不是 `bjontegaard_metric`——后者已废弃）。如果未来想换实现做
sanity check，用同一份 raw_metrics.csv 算出来应该相差 < 0.5%。

### 6.6 HM/VTM/ECM 的 `--Level=` 只接受标准字符串

不接受 `"3.0"` / `"5.0"` 这种带尾零的写法，会报错：

```
Error parsing option "Level" with argument "3.0".
```

合法字符串：`"1", "2", "2.1", "3", "3.1", "4", "4.1", "5", "5.1", ...`
JM 不受影响，它用自己的 Profile/Level IDC 参数（如 51 = Level 5.1）。

`configs/sequences/*.yaml` 里所有序列的 `level` 字段已经统一到合法格式。
**加新序列时务必注意**：BlowingBubbles 用 `"3"`、Traffic 用 `"5"`，不要写 `"3.0"`。

### 6.7 VTM/ECM AI cfg 自带 `TemporalSubsampleRatio=8`

`configs/vtm/encoder_intra_vtm.cfg` 和 `configs/ecm/encoder_intra_ecm.cfg` 第 61 行
默认 `TemporalSubsampleRatio: 8`。这是 JVET VVC CTC 的官方做法
（见 §4.5），但 HM 18 默认是 1。

**陷阱**：如果你不 aware 这件事，pilot 早期会出现 "VTM/ECM AI 只编了 8 帧、HM 编了 64
帧"的诡异不对称——HM 走 64 帧，VTM/ECM 默默走了 8 帧子采样，BD-rate 比的根本不是同一组
源帧。pilot 期间撞过这个坑，最后统一到全部走 TSR=8。

`scripts/run_pilot.py` 现在对所有 AI 任务都强制 `TemporalSubsampleRatio=8`：HM/VTM/ECM
走 `--TemporalSubsampleRatio=8` CLI，JM 用预抽的 `<Name>_AI_TSR8.yuv`。

### 6.8 编码器 log 格式不统一（解析器要分四套）

`scripts/parse_logs.py` 内部维护两套正则：

| 编码器 | summary 块格式 | PSNR 行格式 |
|---|---|---|
| JM 19  | `Average data all frames` | `Y { PSNR (dB), cSNR (dB), MSE } : { 41.514, ...` |
| HM 18  | `SUMMARY ----------` | `Total Frames \| Bitrate Y-PSNR ...` |
| VTM 23 | `LayerId 0`（无 SUMMARY 前缀） | 同 HM |
| ECM 18 | `LayerId 0`（无 SUMMARY 前缀） | 同 HM |

VTM/ECM 跟 HM 的列宽和分隔符也不完全一致——现在的正则用 `\s+` 容忍这种差异。如果以后
升级到 VTM 24+ 或新版 ECM，先用 `make parse` 试一下，看 "WARN: could not parse" 行
数。如果新版又改了格式，往 `parse_logs.py` 里的 `RE_HM_SUMMARY` 加一个 fallback。

### 6.9 BD-rate "Insufficient curve overlap" warning

`bjontegaard` 包在跨代对比时会打这种 warning（pilot 跑出 9 条）：

```
UserWarning: Insufficient curve overlap: '47.40'. Minimum overlap: '75.00'.
```

意思是两个编码器在 4 个 QP 点产生的码率范围重叠不够 75%，BD-rate 在重叠区外是外推
而非积分，数值噪声较大。pilot 选 4 个 QP 是为了快；完整 CTC 时按 §4.6 扩到 6 QP 可缓解。

**不影响 BD-rate 的符号和量级，只影响小数点后第二位的精度**。论文里报告时建议给出
overlap 度作为附注。

---

## 7. 论文写作时的注意

如果你接手到了准备投稿阶段：

1. **方法学章节**必须引用 `docs/JM_CTC_alignment.md` 的内容（或把它改写成 paper section）。
   审稿人最容易问的就是 "How did you align JM with CTC?"。
2. **报告 BD-rate** 时给出 Y/U/V 三个分量、给出 95% 置信区间（多序列平均）。同时
   引用 §6.9 的 overlap warning——如果你按 §4.6 扩了 QP 范围就不用说，不扩就要老实说明。
3. **报告 encoding time** 时给 ratio，不给绝对值。说明 host machine 是 Mac Studio M4 Max
   或者集群型号。
4. **图：BD-rate gain vs encoding time multiplier** 是论文卖点，确保画出来。Pilot 已经
   有了 `report/figures/time_scaling.png` 的雏形，但 RA/AI 没用不同 marker 区分，扩 CTC
   后建议升级。
5. 引用 Ohm et al. IEEE TCSVT 2012 作为方法学基准；引用 Bross et al. Proc. IEEE 2021
   作为 VVC 章节的对照基准。
6. **AI 子采样要说清楚**：pilot 用了 JVET CTC 默认的 TSR=8。如果只跑 RA 就不用提；
   保留 AI 的话，方法学里写"AI BD-rate computed over frames {0, 8, 16, ..., 56}
   per JVET CTC convention, with FrameRate adjusted to source_fps/TSR for consistent
   kbps units across all four encoders"。
7. **HM 比 JM 还快**（pilot 上 HM RA 比 JM 快约 25%）—— **不是编码算法本身**的快慢
   差异。JM 19.1 几乎无 SIMD 优化，HM 18.0 经 10+ 年成熟优化。如果你想做"算法复杂度"
   论证，注明"all measured times include reference-software optimization level differences"
   即可；不要给"HEVC 比 AVC 算法上简单"这种误导性结论。
8. **Class D 上 BD-rate 偏小**（pilot 跑 BlowingBubbles 比 BasketballDrill 各 pair
   小 10-15 个百分点）—— well-known 的"小分辨率下新工具收益受限"现象。论文里
   按 class 报告 BD-rate（不要混合平均），跟 JVET 自己的做法对齐。

---

## 8. 联系

如果有问题不确定我当时为什么这么写，可以联系我：
**xiangyu.wan / wanxiangyu82@gmail.com**

祝顺利。

— xiangyu.wan, 2026-05（pilot 完整 baseline 跑完并记录）
