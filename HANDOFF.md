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

如果你在 Mac Studio M4 Max 上跑完所有 64 个任务，应该会在 `results/pilot_baseline.csv`
看到我留下的基线数字（实际跑出来后我会 commit 上去；如果还没看到，说明 pilot 还没跑完，
基线由你自己的首次完整运行生成）。

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
make encode                     # 1–2 周
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

`scripts/compute_bdrate.py` 优先调用 `bjontegaard_metric` PyPI 包；如果不可用，
fallback 到内置实现。两者数值应该相差 < 0.5%。如果发现明显偏差，**优先信 PyPI 包**
（它实现的是 JVET excel 模板的精确移植）。

---

## 7. 论文写作时的注意

如果你接手到了准备投稿阶段：

1. **方法学章节**必须引用 `docs/JM_CTC_alignment.md` 的内容（或把它改写成 paper section）。
   审稿人最容易问的就是 "How did you align JM with CTC?"。
2. **报告 BD-rate** 时给出 Y/U/V 三个分量、给出 95% 置信区间（多序列平均）。
3. **报告 encoding time** 时给 ratio，不给绝对值。说明 host machine 是 Mac Studio M4 Max
   或者集群型号。
4. **图：BD-rate gain vs encoding time multiplier** 是论文卖点，确保画出来。
5. 引用 Ohm et al. IEEE TCSVT 2012 作为方法学基准；引用 Bross et al. Proc. IEEE 2021
   作为 VVC 章节的对照基准。

---

## 8. 联系

如果有问题不确定我当时为什么这么写，可以联系我：
**xiangyu.wan / wanxiangyu82@gmail.com**

祝顺利。

— xiangyu.wan, 2026-05
