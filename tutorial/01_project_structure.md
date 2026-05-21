# 01 — 项目结构详解

> 这一篇逐项说明每个目录和每个文件做什么用，让你打开任意文件都知道为什么它在那里。
> 这份文档与 `README.md` 互补：README 偏入口和 quick-start，这一篇偏"文件级 walkthrough"。

---

## 1. 顶层视图

```
codec-comparison-pilot/
├── README.md                ← 项目入口与 quick-start
├── HANDOFF.md               ← 毕业交接文档
├── Makefile                 ← 顶层 make targets
├── requirements.txt         ← Python 依赖
├── .gitignore               ← 忽略列表
├── .venv/                   ← Python 虚拟环境（make venv 创建）
│
├── configs/                 ← 所有 CTC 配置 + pilot scope 控制
├── docs/                    ← 项目级技术文档
├── tutorial/                ← 你正在读的教程（00–03 + 入口 README）
├── report/                  ← 最终结果报告与图（build_report.py 产出）
├── scripts/                 ← 全部 8 个 Python/Shell 脚本
├── tools/                   ← 编码器源码（已入 git，跨平台 patch 必须随源码走）
├── sequences/               ← 原始 YUV（git ignored，外挂）
├── bin/                     ← 编码器二进制（make build 产出）
├── runs/                    ← 每次运行的中间产物
├── results/                 ← 解析后的 CSV 与 baseline
└── logs/                    ← 顶层级别的日志（基本未用，预留）
```

下面分四类详细说明：**入口文件**、**配置目录**、**脚本目录**、**输出目录**。

---

## 2. 顶层入口文件

### 2.1 `README.md`

项目第一眼看到的文件。包含：

- 项目 scope 摘要（2 序列、2 配置、4 QP）
- 快速启动命令（`make venv` → `make build` → `make encode`）
- 整体目录结构示意图
- 编码器版本固定表
- 平台支持说明

**适用读者**：第一次接触本项目的人。看完应该能动手开始跑。

### 2.2 `HANDOFF.md`

写给毕业后接手的同学的文档。包含：

- 如何复现 pilot baseline（**第一件事**）
- 编码器版本不能改的纪律
- 如何扩展到完整 CTC（Class A、LDB/LDP、Linux 集群）
- 已知 pitfalls（ARM macOS 编译、路径空格、BD-rate 实现差异）
- 论文写作时的注意事项

**适用读者**：师弟师妹、未来的项目维护者。

### 2.3 `Makefile`

整个项目对外暴露的 entry point。所有具体逻辑都委托给 `scripts/` 下的脚本，Makefile 本身保持轻薄。Targets：

| Target | 委托给 | 用途 |
|---|---|---|
| `make help` | (Makefile 自身) | 列出所有 targets |
| `make venv` | `scripts/setup_env.sh` | 创建 .venv 并装依赖 |
| `make build` | `scripts/build_all.sh` | 编译四个编码器 |
| `make build-<encoder>` | 同上，单编码器 | 单独编译 JM/HM/VTM/ECM |
| `make sanity` | `scripts/build_sanity_check.py` | 每个编码器跑一次最小编码 |
| `make encode-dry` | `scripts/run_pilot.py --dry-run` | 打印任务矩阵但不执行 |
| `make encode` | `scripts/run_pilot.py` | 跑完整 pilot 矩阵 |
| `make parse` | `scripts/parse_logs.py` | 从日志提取指标 |
| `make bdrate` | `scripts/compute_bdrate.py` | 计算 BD-rate |
| `make report` | `scripts/build_report.py` | 生成 Markdown 报告 |
| `make verify-baseline` | `scripts/verify_baseline.py` | 与 baseline 对比验证 |
| `make clean-runs` | (rm) | 清空 runs/ |
| `make clean` | (rm) | 清空 .venv、bin、runs、results |

### 2.4 `requirements.txt`

Python 依赖列表，固定最低版本但不锁死：

```
numpy>=1.26
pandas>=2.2
scipy>=1.12
matplotlib>=3.8
pyyaml>=6.0
tqdm>=4.66
bjontegaard-metric>=1.0.4
```

依赖很轻，没有任何"重型"科学计算包。`bjontegaard-metric` 是 BD-rate 计算的成熟实现，避免自己写一份。

### 2.5 `.gitignore`

约束哪些东西不进 git。规则覆盖：

- Python 产物：`.venv/`, `__pycache__/`, `*.pyc`
- 编码器二进制：`bin/`（每台机器自己编）
- 原始视频与编码输出：`sequences/*.yuv`, `*.bin`, `*.264`, `*_rec.yuv` 等
- 运行产物：`runs/`（按时间戳分目录，本地堆几十 GB）
- OS 杂物：`.DS_Store`, `Thumbs.db`

**保留进 git** 的东西：脚本、配置、文档、`results/*.csv`（pilot baseline 的 CSV 必须入库）、`sequences/MANIFEST.csv`（序列清单，但不包括 YUV 本身）。

---

## 3. `configs/` — 配置中心

这是项目最重要的目录之一。所有"什么序列、什么 QP、什么配置"的决策都集中在这里。

```
configs/
├── pilot.yaml                  ← scope 总控
├── jm/
│   ├── encoder_JM_Intra_HE.cfg   ← JM 全 Intra (AI)
│   ├── encoder_JM_RA_B_HE.cfg    ← JM Random Access
│   ├── encoder_JM_LB_HE.cfg      ← JM Low-Delay B
│   └── encoder_JM_LP_HE.cfg      ← JM Low-Delay P
├── hm/
│   ├── encoder_intra_main.cfg
│   ├── encoder_randomaccess_main.cfg
│   ├── encoder_lowdelay_main.cfg
│   └── encoder_lowdelay_P_main.cfg
├── vtm/
│   ├── encoder_intra_vtm.cfg
│   ├── encoder_randomaccess_vtm.cfg
│   ├── encoder_lowdelay_vtm.cfg
│   └── encoder_lowdelay_P_vtm.cfg
├── ecm/
│   ├── encoder_intra_ecm.cfg
│   ├── encoder_randomaccess_ecm.cfg
│   ├── encoder_lowdelay_ecm.cfg
│   └── encoder_lowdelay_P_ecm.cfg
└── sequences/
    ├── BasketballDrill.yaml    ← Class C, pilot 启用
    ├── BlowingBubbles.yaml     ← Class D, pilot 启用
    ├── Traffic.yaml            ← Class A1, 未来扩展用 stub
    └── PeopleOnStreet.yaml     ← Class A2, 未来扩展用 stub
```

### 3.1 `configs/pilot.yaml`

scope 控制文件。改这一个文件就能改整个 pilot 的范围：

```yaml
encoders:    [jm, hm, vtm, ecm]
configs:     [AI, RA]         # 取消 LDB/LDP 注释来扩展
qps:         [22, 27, 32, 37]
sequences:   [BasketballDrill, BlowingBubbles]
frames_to_encode: 64
parallel_jobs: 4
job_timeout_sec: 86400
keep_recon: false
run_dir_pattern: "%Y-%m-%d_%H%M_pilot"
```

`scripts/run_pilot.py` 把这份 YAML 作为单一真理源。

### 3.2 `configs/{jm,hm,vtm,ecm}/`

每个编码器 4 个 CTC 配置文件（AI / RA / LDB / LDP）。

**这些文件不是我手写的，是从各编码器源码 `cfg/` 目录原样拷过来的**：

- JM 的来自 `tools/JM-JM-19.1/cfg/HM-like/`（JM 维护者为对齐 HM CTC 专门提供的）
- HM / VTM / ECM 的来自各自 `cfg/` 根目录的官方 CTC 配置

详见 [02 JM 配置详解](02_jm_config_explained.md)。

### 3.3 `configs/sequences/<name>.yaml`

每个测试序列一个 YAML，记录元数据（不含具体 codec 参数）：

```yaml
name: BasketballDrill
class: C
width: 832
height: 480
fps: 50
bit_depth: 8
chroma_format: 420
total_frames: 500
level: "3.1"
yuv_filename: BasketballDrill_832x480_50.yuv
md5: ""                       # 下载后填入
source_url: "ftp://..."
```

`run_pilot.py` 根据这些字段动态生成传给编码器的命令行参数。

**为什么不直接用各编码器自带的 per-sequence cfg？** 因为它们路径写死、互不一致、JM 的还是 Windows 路径。本项目用一份统一的 YAML，运行时翻译成各编码器的方言。

### 3.4 `configs/sequences/{Traffic,PeopleOnStreet}.yaml`

Class A1/A2 的 stub。Pilot **不用**，但提前写好，毕业后扩展时直接取消 pilot.yaml 里对应行的注释就生效，不用现写。

---

## 4. `scripts/` — 全部 8 个脚本

```
scripts/
├── setup_env.sh              ← (Bash) Python venv 创建与依赖安装
├── build_all.sh              ← (Bash) 跨平台编译四个编码器
├── build_sanity_check.py     ← (Python) 每编码器跑一次最小编码
├── run_pilot.py              ← (Python) 任务调度与执行
├── parse_logs.py             ← (Python) 日志解析为统一 CSV
├── compute_bdrate.py         ← (Python) BD-rate 计算
├── build_report.py           ← (Python) 生成 Markdown 报告与图
└── verify_baseline.py        ← (Python) 与 baseline 比较验证
```

### 4.1 `setup_env.sh`

幂等的 venv 初始化脚本。逻辑：

1. 找一个 Python 解释器（优先 `python3`）
2. 检查版本 ≥ 3.10
3. 在 `.venv/` 创建虚拟环境（如已存在则跳过）
4. 升级 pip / wheel / setuptools
5. `pip install -r requirements.txt`

可以反复运行，不会破坏已有环境。

### 4.2 `build_all.sh`

跨平台编译脚本，是本项目最重要的 Bash 脚本。

关键设计：

- **平台自动检测**：`uname -s` 区分 Darwin / Linux，分别用 `sysctl -n hw.ncpu` / `nproc` 获取并发度
- **源码外挂**：默认在 `tools/` 下找各编码器源码；可通过 `TOOLS_DIR` 环境变量指向外部目录
- **glob 匹配**：用 `JM-JM-*` / `HM-HM-*` / `VVCSoftware_VTM-VTM-*` / `ECM-ECM-*` 模糊匹配，不锁死版本号小数位
- **统一编译流程**：每个编码器都是 `cmake ... -DCMAKE_BUILD_TYPE=Release && cmake --build . --target <ENC>`
- **ARM macOS 兼容**：自动 apply `tools/patches/<encoder>_arm_macos.patch`（若存在）
- **支持子集**：`./scripts/build_all.sh vtm ecm` 只编 VTM 和 ECM
- **统一命名**：编译产物都拷到 `bin/`，二进制改名为 `lencod` / `TAppEncoder` / `EncoderApp_VTM` / `EncoderApp_ECM`

### 4.3 `build_sanity_check.py`

编译后的第一道质量门。逻辑：

- 用 BlowingBubbles 的前 16 帧 AI 配置 QP=37（最便宜的工作负载）
- 对每个编码器跑一次完整编码
- 验证：进程 exit code = 0，且 bitstream 文件非空
- 任何编码器失败都报错并打印 stderr 末尾 10 行

跑通 sanity 之后才有底气跑完整 64 任务的 pilot。

### 4.4 `run_pilot.py`

任务调度核心。约 300 行 Python，做几件事：

1. 读取 `configs/pilot.yaml` + 各 sequence YAML
2. 展开任务矩阵：(encoder × sequence × config × qp) = 64 个 Job
3. 为每个 Job 构造命令行（JM 和 HM/VTM/ECM 的 CLI 语法不同，分别处理）
4. 用 `concurrent.futures.ProcessPoolExecutor` 并发执行
5. 任务状态持久化到 `runs/<timestamp>/jobs.csv`，支持断点续跑

关键设计点：

- **CLI 抽象**：`build_cmd_jm` 和 `build_cmd_hm_vtm_ecm` 两个函数屏蔽编码器差异
- **可恢复性**：每个 Job 跑完立即更新 jobs.csv，中断重启时跳过 status=DONE 的任务
- **按预期耗时排序**：JM → HM → VTM → ECM 升序，让"便宜"任务先 fail 早暴露问题
- **支持 `--dry-run`**：打印所有命令但不执行，便于调试
- **支持 `--jobs N`**：覆盖 pilot.yaml 中的并发度
- **支持 `--run-id`**：恢复一个已有运行目录

### 4.5 `parse_logs.py`

日志解析器，把各编码器的输出格式统一成 CSV。

关键正则：

- **HM/VTM/ECM**：找 `SUMMARY ---` 块，提取 frame count、bitrate、Y/U/V PSNR、total time
- **JM**：找 `PSNR Y(dB)`、`PSNR U(dB)`、`PSNR V(dB)`、`Bit rate`、`Total encoding time` 几个字段（JM 的输出格式更松散，需要多个独立正则）

输出 `results/raw_metrics.csv`：

```csv
job_id,encoder,sequence,config,qp,frames_encoded,bitrate_kbps,
psnr_y_db,psnr_u_db,psnr_v_db,enc_time_sec
```

写完后自动做单调性检查（QP↑ → bitrate↓ 应该总成立），任何反例都警告。

### 4.6 `compute_bdrate.py`

BD-rate 计算。对每个 (sequence, config) 计算四组对比：

- HM vs JM
- VTM vs HM
- ECM vs VTM
- ECM vs JM（累计）

对 Y/U/V 三个分量分别算。

实现策略：

1. 优先调 PyPI 的 `bjontegaard-metric` 包（社区成熟实现）
2. 找不到就 fallback 到内置的 piecewise cubic 实现（Bjøntegaard 2001 经典做法）

输出 `results/bdrate_table.csv` 和 `results/time_ratio.csv`（编码时间倍数）。

### 4.7 `build_report.py`

生成最终 Markdown 报告 + PNG 图表。

会产生：

- `report/pilot_results.md` —— 主报告（BD-rate 表 + 时间比表 + 图）
- `report/figures/rd_<sequence>_<config>.png` —— 每个 (序列, 配置) 一张 RD 曲线
- `report/figures/bdrate_summary.png` —— BD-rate 柱状图汇总
- `report/figures/time_scaling.png` —— 编码时间比散点（log 尺度）

### 4.8 `verify_baseline.py`

质量护栏。逻辑：

- 比较 `results/raw_metrics.csv`（当前）与 `results/pilot_baseline.csv`（基线）
- 容差：`|ΔY-PSNR| < 0.05 dB` 且 `|Δbitrate|/baseline < 1%`
- 第一次运行（无 baseline）时，自动把当前结果 stamp 为 baseline
- 不通过则打印偏差超标的所有 (encoder, sequence, config, qp) 组合

这是接手人扩展时必跑的回归测试。**如果未来某次升级 ECM 后这个脚本不过，团队就该停下来排查**，而不是闷头继续跑完整 CTC。

---

## 5. `tools/` — 编码器源码（入 git）

```
tools/
├── README.md                       ← 解释源码放置方式
├── patches/                        ← ARM macOS 兼容补丁（空目录，按需添加）
├── JM-JM-19.1/
├── HM-HM-18.0/
├── VVCSoftware_VTM-VTM-23.11/
└── ECM-ECM-18.0/
```

**四个编码器源码都入 git**。原因：本项目对 `JM-JM-19.1/CMakeLists.txt`、`HM-HM-18.0/CMakeLists.txt` 以及 `HM-HM-18.0/source/Lib/TLibCommon/CMakeLists.txt` 做了 ARM macOS 兼容性修改（把硬编码的 `-msse4.1` 改为只在 x86 上启用）。这些修改必须随项目分发，不能只靠下载方提示对方"自己再改一次"——所以源码连同修改一起入 git。

`.gitignore` 排除掉了构建产物：

- `tools/*/build/`  ← CMake 生成的 build 目录
- `tools/*/lib/`    ← HM/VTM/ECM 编译出来的静态库目录（注意：JM 的 `source/lib/` 不受影响，那是真正的源码库）
- `tools/*/bin/`    ← 编译出来的二进制（通过项目根的 `bin/` 全局规则覆盖）

source/、cfg/、cmake/、CMakeLists.txt、README 等都入库。

### 体积

四个编码器源码 commit 后约 **170 MB**（ECM 最大，约 130 MB，其他都很小）。对 git 不算夸张，clone 一次就够用。

### `tools/patches/`

留给未来如果还有不便直接修改源码的兼容性补丁。当前为空——直接改源码更直接，patch 机制保留为后备方案。

### 如果你需要换源码版本

如果未来要升级到 JM-19.2 / HM-19.0 / VTM-24.x / ECM-19.x，建议这样做：

1. 把新版本源码替换到 `tools/<encoder>-<new-version>/`
2. 把对应的 ARM 兼容补丁再应用一次（diff 旧版 CMakeLists 看具体改动）
3. 更新 `scripts/build_all.sh` 的 glob pattern（如果版本号格式变了）
4. 更新 `README.md` 和 `HANDOFF.md` 的版本固定表
5. 重跑 pilot，验证 baseline 在新版本下的差异

---

## 6. `sequences/` — 原始 YUV

```
sequences/
├── README.md           ← 下载与放置说明
├── MANIFEST.csv        ← 文件清单 + 期望 MD5
└── *.yuv               ← 实际 YUV 文件（gitignored）
```

### `sequences/MANIFEST.csv`

序列文件清单，记录文件名、分辨率、帧率、位深、总帧数、MD5、来源 URL。这个文件**入 git**，作为序列依赖的官方声明。

### `sequences/README.md`

告诉接手人到哪里下载 YUV、怎么计算 MD5、怎么把 MD5 填回 `configs/sequences/<name>.yaml`。

### YUV 文件

不入 git。文件大（Class C 一条 ~286MB，Class A 一条 1+ GB），且来自 JVET 官方仓库，每个人自己下。

---

## 7. `docs/` — 项目级技术文档

```
docs/
└── JM_CTC_alignment.md   ← JM 如何与 CTC 对齐（论文方法学章节的素材）
```

目前只有一份，因为只有 JM 这一块需要特别解释（HM/VTM/ECM 都用各自的官方 CTC，没什么好特别说明的）。

未来如果加更多 docs（比如 `BDrate_method.md`、`Cluster_migration.md`），都放这里。

---

## 8. `tutorial/` — 项目教程

```
tutorial/
├── README.md                       ← 教程入口
├── 00_overview.md                  ← 项目大背景
├── 01_project_structure.md         ← 本文档
├── 02_jm_config_explained.md       ← JM 配置详解
└── 03_how_to_run.md                ← 启动教程
```

这一组是给人看的、手写的教程，全部入 git。它们与项目代码一同维护，新功能或踩坑笔记应该回填到对应章节里。

## 9. `report/` — 最终结果输出

```
report/
├── pilot_results.md                ← (build_report.py 产出)
└── figures/                        ← (build_report.py 产出)
    ├── rd_<sequence>_<config>.png
    ├── bdrate_summary.png
    └── time_scaling.png
```

这一组由 `make report` 自动生成，每次跑完都会被覆盖。**不要手工编辑这些文件**——下次重跑会丢。如果你想标注解读，新建一份 `report/notes_<date>.md` 旁边放着。

通常 `pilot_results.md` 和图建议也 commit 一份当快照，方便不跑代码的人直接看结果。

---

## 10. 运行时产物目录

### `bin/` — 编译产物

```
bin/
├── lencod                 ← JM
├── TAppEncoder            ← HM
├── EncoderApp_VTM         ← VTM
└── EncoderApp_ECM         ← ECM
```

由 `make build` 产出。完全本地，不入 git。换机器要重新编译。

### `runs/` — 每次运行的中间产物

每次 `make encode` 会创建一个时间戳目录：

```
runs/
└── 2026-05-19_1430_pilot/
    ├── jobs.csv              ← 任务状态与命令记录
    ├── bitstreams/           ← 编码输出的 .264 / .bin 文件
    ├── logs/                 ← 每个任务一个 .log
    └── tmp_configs/          ← (预留，目前未用)
```

不入 git。可以堆几十 GB。`make clean-runs` 一键清空。

### `results/` — 解析后的最终数据

```
results/
├── raw_metrics.csv          ← 每个任务一行的指标
├── bdrate_table.csv         ← BD-rate 汇总
├── time_ratio.csv           ← 时间比汇总
└── pilot_baseline.csv       ← 基线（首次成功跑完后 stamp）
```

**入 git**。Pilot baseline 是项目的质量护栏，必须版本化。

### `logs/` — 顶层日志（保留）

目前未用。预留给以后可能的全局日志（比如 `make encode` 启动横幅、错误汇总等）。

---

## 11. 一张图总结

```
         ┌─────────────┐
         │ pilot.yaml  │  ← 你只动这个文件改 scope
         └──────┬──────┘
                │
                ▼
   ┌────────────────────────────────┐
   │  scripts/run_pilot.py          │
   │  (读取 configs/ 下所有 cfg)    │
   └─────────────┬──────────────────┘
                 │ 调度
                 ▼
         ┌───────────────┐         ┌────────────────┐
         │  bin/lencod   │         │  sequences/    │
         │  bin/TAppEnc  │ ◄─读─── │  *.yuv         │
         │  bin/Enc_VTM  │         │  (gitignored)  │
         │  bin/Enc_ECM  │         └────────────────┘
         └──────┬────────┘
                │ 编码
                ▼
   ┌─────────────────────────────────┐
   │  runs/<timestamp>/              │
   │    ├── bitstreams/              │
   │    ├── logs/                    │
   │    └── jobs.csv                 │
   └─────────────┬───────────────────┘
                 │
                 ▼
         ┌───────────────────┐
         │ parse_logs.py     │
         │ compute_bdrate.py │  ──► results/*.csv  (入 git)
         │ build_report.py   │  ──► report/pilot_results.md + figures/
         │ verify_baseline   │
         └───────────────────┘
```

每个箭头都是一个 Makefile target：`make encode` → `make parse` → `make bdrate` → `make report` → `make verify-baseline`。

如果你能在这张图上指出"我要改 scope 应该改哪里"、"我要看每次跑出来的具体数字去哪"、"我要复现 baseline 怎么验"——你就掌握了这个项目的全部结构。

---

下一篇：[02 JM 配置详解](02_jm_config_explained.md) —— 解释为什么 JM 这一档需要单独一篇文档。
