# Patches

这个目录存放针对 `tools/` 下编码器源码的兼容性补丁。

## 当前状态：备份用，不自动应用

本项目当前是把修改**直接 commit 到了** `tools/` 下的源码树（参见 `.gitignore` 注释）。这里的 patch 文件存在的目的是：

1. **diff 可读性**：以标准 unified-diff 格式记录每一处修改，方便 code review、写论文方法学章节、或在 git log 之外快速看清"我们改了什么"。
2. **再应用能力**：如果未来源码树被替换（比如升级到 JM-19.2、或者接手人重新解压 zip 覆盖），这些 patch 可以再次应用回去，不丢修改。

`scripts/build_all.sh` 目前**不**自动 apply 这些 patch（在源码已经修改的情况下 apply 会失败或者重复应用）。这是有意为之。

## 文件清单

| 文件 | 针对 | 改了什么 |
|---|---|---|
| `jm_arm_macos.patch` | `tools/JM-JM-19.1/` | 把 `-msse4.1` 编译 flag 限定到 x86/x86_64 才启用 |
| `hm_arm_macos.patch` | `tools/HM-HM-18.0/` | 同上 + 把 SSE/AVX 源文件 GLOB 和 per-file 编译 flag 都加 arm64 守卫 |

VTM-23.11 和 ECM-18.0 的上游 CMakeLists 已经做了 arm64 处理，**不需要 patch**。

## 如何在 pristine 源码上再应用

如果接手人不小心覆盖了 `tools/JM-JM-19.1/` 或 `tools/HM-HM-18.0/`（比如重新解压 zip）：

```bash
cd tools/JM-JM-19.1
git apply ../patches/jm_arm_macos.patch

cd ../HM-HM-18.0
git apply ../patches/hm_arm_macos.patch
```

`git apply` 在已经应用过的源码上会拒绝二次应用（输出 "patch does not apply"），所以**幂等地反复跑也不会出问题**。

如果想在 `git apply` 之外用普通 `patch` 工具：

```bash
cd tools/JM-JM-19.1
patch -p1 < ../patches/jm_arm_macos.patch
```

## 如何切换到"patch 化"工作流（未来如需）

如果项目体积超出 200 MB 想瘦身，可以改成：

1. 不 commit `tools/` 下的源码树（在 `.gitignore` 里加 `tools/*/`，但放行 `tools/patches/` 和 `tools/README.md`）
2. 让 `scripts/build_all.sh` 在编译前自动 apply 这些 patch（脚本里已经有 `apply_patch_if_present` 函数，把它从 ARM 专属改成默认调用即可）
3. 接手人先自己下载/解压编码器源码到 `tools/`，build 脚本自动打 patch

那时 repo 大小可以缩到几 MB，代价是接手人需要手工准备 `tools/` 源码（zip 下载链接写在 `tools/README.md`）。当前阶段不必这么做。

## 升级源码版本时的注意

如果你升级到 JM-19.2 / HM-19.0 等新版本，**这些 patch 大概率不再 apply-clean**（上下文行号会偏移，或者上游已经自带 arm64 守卫）。处理方式：

1. 先尝试 `git apply --check` 确认是否还能应用
2. 应用失败的话，对照 patch 内容手工再做一遍同样的修改
3. 用 `diff -u` 重新生成新版本对应的 patch 文件，替换这里的旧 patch
4. 在 `HANDOFF.md` 里记录版本变更
