# 03 — 启动教程

> 这一篇按从零开始的顺序，把整个 pilot 从安装到出报告的每一步都走一遍。
> 假设你刚 clone 完这个项目（或者刚拿到导师拷给你的文件夹），还没装任何东西。

---

## 0. 前置条件

机器与软件最低要求：

| 项 | 要求 |
|---|---|
| 操作系统 | macOS 14+（推荐 M 系列 Apple Silicon）或 Linux Ubuntu 22.04+ |
| 内存 | ≥ 16 GB（Pilot 推荐 36 GB；4K 扩展需要更多） |
| 磁盘空间 | ≥ 50 GB 可用（YUV 占大头） |
| Python | 3.10+ |
| CMake | 3.22+ |
| C++ 编译器 | clang 14+ 或 gcc 11+ |
| Git | 2.40+（用于 patch apply） |

macOS 上 Xcode Command Line Tools 装了就行（`xcode-select --install`），不需要完整 Xcode。Linux 上 `build-essential` + `cmake` + `python3-venv` 即可。

---

## 1. 检查项目位置

确保你在正确目录下：

```bash
cd /path/to/JM_HM_VTM_ECM/codec-comparison-pilot
pwd
# 应该显示上面这个路径
```

确认四个编码器源码在兄弟目录：

```bash
ls ..
# 应该看到：
#   ECM-ECM-18.0/
#   HM-HM-18.0/
#   JM-JM-19.1/
#   VVCSoftware_VTM-VTM-23.11/
#   codec-comparison-pilot/    ← 你在这里
```

---

## 2. Step 1：创建 Python 虚拟环境

```bash
make venv
```

这会调 `scripts/setup_env.sh`，做几件事：

- 找到 `python3`（要 ≥ 3.10）
- 在项目根创建 `.venv/`
- 装 `requirements.txt` 里的所有依赖

预计耗时：1–2 分钟。

完成后激活：

```bash
source .venv/bin/activate
```

激活后 shell 提示符会带上 `(.venv)` 前缀。验证：

```bash
which python
# 应该输出 .../codec-comparison-pilot/.venv/bin/python
python -c "import pandas, matplotlib, yaml, bjontegaard_metric; print('OK')"
# 应该输出 OK
```

---

## 3. Step 2：编译四个编码器

### 3.1 指定源码位置

四个编码器源码在 `../`（项目的父目录）。告诉 build 脚本去那里找：

```bash
export TOOLS_DIR=$(cd .. && pwd)
echo "TOOLS_DIR=$TOOLS_DIR"
# 例如：/path/to/JM_HM_VTM_ECM
```

> 这一行需要在每次新开 shell 时重新执行。如果嫌烦，可以把它加进 `~/.zshrc` 或者写一个 `setup.sh` 在项目根 source。

### 3.2 编译

```bash
make build
```

`scripts/build_all.sh` 会顺序编译 JM → HM → VTM → ECM。预计耗时（Mac Studio M4 Max，并行编译）：

| 编码器 | 编译时间 |
|---|---|
| JM | ~1 分钟 |
| HM | ~3–5 分钟 |
| VTM | ~5–10 分钟 |
| ECM | ~10–20 分钟 |
| **总计** | **~20–35 分钟** |

如果只想先试一个：

```bash
make build-jm    # 或 build-hm / build-vtm / build-ecm
```

### 3.3 编译验证

完成后检查：

```bash
ls -lh bin/
# 应该看到：
#   lencod              (JM, ~1MB)
#   TAppEncoder         (HM, ~10MB)
#   EncoderApp_VTM      (~15MB)
#   EncoderApp_ECM      (~20MB)
```

每个二进制都跑一下 `--help`（HM/VTM/ECM）或 `-h`（JM）确认能起来：

```bash
./bin/TAppEncoder --help 2>&1 | head -5
./bin/EncoderApp_VTM --help 2>&1 | head -5
./bin/EncoderApp_ECM --help 2>&1 | head -5
./bin/lencod -h 2>&1 | head -5   # JM 用 -h
```

### 3.4 如果编译失败

**JM 编不过**：很罕见，JM 代码是纯 C，几乎在任何平台都能编。看报错栈，通常是 `#include` 缺失，装个 `xcode-select --install` 或 Linux 上 `apt install build-essential` 即可。

**HM 编不过**：可能是 CMake 版本太老（要 ≥ 3.22）。`brew upgrade cmake` 或 `pip install cmake --upgrade`。

**VTM/ECM 在 ARM macOS 上编不过**：最常见的报错是某个文件用了 x86-only 内联汇编。报错栈贴出来。临时绕过：

```bash
# 找到问题文件，加 #ifdef __x86_64__ 守卫
# 然后保存成 patch
cd $TOOLS_DIR/ECM-ECM-18.0
git diff > /path/to/codec-comparison-pilot/tools/patches/ecm_arm_macos.patch
```

下次 `make build-ecm` 时脚本会自动 apply 这个 patch。

---

## 4. Step 3：准备测试序列

### 4.1 下载 YUV

Pilot 需要两个序列：

| 文件名 | 来源 | 大小 |
|---|---|---|
| `BasketballDrill_832x480_50.yuv` | JVET CTC 官方 | ~286 MB |
| `BlowingBubbles_416x240_50.yuv` | JVET CTC 官方 | ~72 MB |

JVET 官方 FTP（账号 hevc，密码 US88Hula）：

```
ftp://hevc:US88Hula@ftp.tnt.uni-hannover.de/testsequences/
```

也可以从导师组里要——这是最稳定的方式。

下载完放到 `sequences/`：

```bash
ls sequences/
# BasketballDrill_832x480_50.yuv
# BlowingBubbles_416x240_50.yuv
# MANIFEST.csv
# README.md
```

### 4.2 验证 MD5

下载完算 MD5：

```bash
# macOS
md5 sequences/BasketballDrill_832x480_50.yuv
md5 sequences/BlowingBubbles_416x240_50.yuv

# Linux
md5sum sequences/BasketballDrill_832x480_50.yuv
md5sum sequences/BlowingBubbles_416x240_50.yuv
```

把 MD5 填回 `configs/sequences/BasketballDrill.yaml` 和 `BlowingBubbles.yaml` 的 `md5:` 字段。也可以填到 `sequences/MANIFEST.csv` 里。

---

## 5. Step 4：Sanity check（必跑）

```bash
make sanity
```

`scripts/build_sanity_check.py` 会用 BlowingBubbles 16 帧 AI@QP37 对每个编码器跑一次最小编码。预期输出：

```
=== Sanity check: JM ===
  OK (3142 bytes)

=== Sanity check: HM ===
  OK (2891 bytes)

=== Sanity check: VTM ===
  OK (2654 bytes)

=== Sanity check: ECM ===
  OK (2401 bytes)

Summary: 4 ok, 0 failed.
```

如果**任何一个 FAIL**，**先不要继续**——把错误贴出来排查。常见原因：

- 二进制不存在 → 回到 Step 2 检查 build
- 序列 YUV 不存在 → 回到 Step 3
- 编码器配置文件找不到 → 检查 `configs/{enc}/` 目录是否完整
- ECM 跑了几分钟超时 → ECM 启动慢是正常的，但 16 帧 AI 不应该超 5 分钟，可能是 binary 有问题

---

## 6. Step 5：Dry-run 检查任务矩阵

```bash
make encode-dry
```

会打印 **64 个任务的完整命令行**，但不执行。检查几个点：

1. **总任务数是 64**（4 encoder × 2 sequence × 2 config × 4 QP）
2. **JM 命令含 `-p QPISlice=`、`-p QPPSlice=`、`-p QPBSlice=` 三个，且数值相同**
3. **HM/VTM/ECM 命令含 `--QP=` 一个**
4. **所有命令含 `--IntraPeriod=32`**（50fps 序列）
5. **路径都是绝对路径**，不会有 Windows 风格 `D:\` 或者相对路径

任何异常都说明 cfg 或脚本被改坏了。

---

## 7. Step 6：跑 Pilot

### 7.1 启动

```bash
make encode
```

或者直接调脚本（更灵活）：

```bash
python scripts/run_pilot.py
```

启动后会打印：

```
Run directory: runs/2026-05-19_1430_pilot
Pending: 64 / Total: 64 (parallel=4)
[1/64] 0001_jm_BlowingBubbles_AI_QP22 -> DONE (elapsed=12.3s)
[2/64] 0002_jm_BlowingBubbles_AI_QP27 -> DONE (elapsed=10.5s)
...
```

### 7.2 预计耗时（M4 Max, 4 路并发）

| 阶段 | 累计时间 |
|---|---|
| JM 全部 16 任务 | < 30 分钟 |
| HM 全部 16 任务 | ~3–5 小时 |
| VTM 全部 16 任务 | ~2–3 天 |
| ECM 全部 16 任务 | ~5–10 天 |
| **总计** | **~1–2 周** |

ECM 是绝对瓶颈。建议工作日下班前启动，让它周末连续跑。

### 7.3 可以做的事

**断点续跑**：如果中途断了（断电、kill、机器重启），重新跑 `make encode` 会自动跳过 status=DONE 的任务，从未完成的接着跑。

**监控进度**：另开一个 terminal：

```bash
# 看任务状态
cat runs/2026-05-19_*_pilot/jobs.csv | column -t -s, | head -20

# 看最新跑出来的指标
tail -f runs/2026-05-19_*_pilot/logs/$(ls -t runs/2026-05-19_*_pilot/logs/ | head -1)
```

**调整并发度**：如果发现 4 路并发让机器太热，临时降到 2：

```bash
python scripts/run_pilot.py --jobs 2
```

**改 scope**：编辑 `configs/pilot.yaml`（比如先去掉 ECM 看看其他三档），保存后重新跑。`run_pilot.py` 会重新展开矩阵——**注意会创建新的 runs/<timestamp>/ 目录**，不会污染之前的运行。

### 7.4 完成判定

跑完后看：

```bash
ls runs/2026-05-19_*_pilot/
# bitstreams/    ← 64 个文件
# logs/          ← 64 个 .log
# jobs.csv       ← 所有 status=DONE
```

`jobs.csv` 里所有行 `status` 都应该是 `DONE`，`exit_code=0`。如果有 `FAILED`：

```bash
# 看具体哪些失败
awk -F, '$6 == "FAILED"' runs/2026-05-19_*_pilot/jobs.csv
```

对失败任务先看 log 排查：

```bash
tail -30 runs/2026-05-19_*_pilot/logs/<failed_job_id>.log
```

如果只是个别任务失败（比如某次磁盘满了），删 jobs.csv 里那一行的 status 字段或改成 `PENDING`，重跑 `make encode` 会重试。

---

## 8. Step 7：解析、计算 BD-rate、出报告

按顺序跑三个：

```bash
make parse      # 1秒：从 logs 提取指标到 results/raw_metrics.csv
make bdrate     # 1秒：计算 BD-rate 到 results/bdrate_table.csv
make report     # 几秒：生成 Markdown 报告 + PNG 图
```

也可以一行：

```bash
make parse bdrate report
```

### 8.1 检查结果

```bash
# 看原始指标（64 行）
column -t -s, results/raw_metrics.csv | head -10

# 看 BD-rate 汇总
column -t -s, results/bdrate_table.csv

# 看编码时间比
column -t -s, results/time_ratio.csv

# 看最终报告
cat report/pilot_results.md

# 看图
open report/figures/   # macOS
# 或
xdg-open report/figures/  # Linux
```

### 8.2 sanity check 你的结果

BD-rate 应该落在以下区间（Y 分量，RA 配置）：

| 对比 | 期望 BD-rate（Y, RA） |
|---|---|
| HM-vs-JM | -35% ~ -45% |
| VTM-vs-HM | -30% ~ -40% |
| ECM-vs-VTM | -15% ~ -25% |
| ECM-vs-JM | -75% ~ -85% |

如果数字明显偏离：

- **绝对值偏小** → JM 是不是被默认 cfg 跑了？检查 `configs/jm/encoder_JM_RA_B_HE.cfg` 是不是 HM-like 版本。
- **绝对值偏大** → JM 是不是被 max_performance cfg 跑了？或者 IntraPeriod 没对齐？
- **某代退化（数字正）** → BUG，立刻排查 cfg、IntraPeriod、QP 对齐。

---

## 9. Step 8：固化 baseline

第一次完整跑通且数字合理后：

```bash
make verify-baseline
```

首次运行时没有 baseline，脚本会把当前 `results/raw_metrics.csv` 拷贝成 `results/pilot_baseline.csv`，作为基线。

**记得把 baseline 提交进 git**：

```bash
git add results/pilot_baseline.csv results/bdrate_table.csv results/time_ratio.csv
git commit -m "pilot v1 baseline: JM-19.1/HM-18.0/VTM-23.11/ECM-18.0 on Class C+D, 64 frames"
```

之后任何升级（编码器版本、加序列、加配置），重新跑 → `make verify-baseline` 必须通过（容差 0.05 dB / 1% bitrate），不通过说明引入了回归，必须排查。

---

## 10. 常用 Cheatsheet

```bash
# 完整全套（首次运行）
make venv
source .venv/bin/activate
export TOOLS_DIR=$(cd .. && pwd)
make build
# 下载 YUV 到 sequences/
make sanity
make encode-dry           # 检查矩阵
make encode               # 实际跑（1-2 周）
make parse bdrate report
make verify-baseline      # stamp baseline

# 日常重跑
source .venv/bin/activate
make encode               # 自动跳过 DONE 任务
make parse bdrate report

# 调试单任务
python scripts/run_pilot.py --dry-run | grep "jm_BasketballDrill_AI_QP22"
# 把命令贴出来手动跑

# 清空重来
make clean-runs           # 只清 runs/
make clean                # 清 .venv/bin/runs/results
```

---

## 11. 接下来

跑通 pilot 之后建议读：

- [HANDOFF.md](../HANDOFF.md) —— 毕业前要怎么把这个项目交出去
- [docs/JM_CTC_alignment.md](../docs/JM_CTC_alignment.md) —— 论文方法学章节的素材
- [02 JM 配置详解](02_jm_config_explained.md) —— 如果对 JM 细节还有疑问

如果跑 pilot 的过程中遇到不在本教程覆盖的问题，记下来加进 [HANDOFF.md](../HANDOFF.md) §6 "已知 Pitfalls" 部分——下一个接手的人会感谢你。
