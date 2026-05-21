# 教程目录

这个目录是项目教程的入口。按以下顺序阅读：

| 文件 | 内容 | 适合谁先看 |
|---|---|---|
| [00_overview.md](00_overview.md) | 项目大背景、论文动机、scope 设计 | 所有人 |
| [01_project_structure.md](01_project_structure.md) | 每个目录、每个文件做什么用 | 所有人 |
| [02_jm_config_explained.md](02_jm_config_explained.md) | JM 配置的两层"调整"详解 | 准备写论文方法学章节的人 |
| [03_how_to_run.md](03_how_to_run.md) | 从零开始把 pilot 跑起来 | 第一次动手的人 |

读完这 4 篇 + 项目根目录的 [README.md](../README.md) + [HANDOFF.md](../HANDOFF.md)，你应该完全掌握这个项目。

## 这个目录里还会有什么

除了上面 4 篇人工教程，运行 `make report` 后会自动生成：

- `pilot_results.md` —— 最终结果报告（每次重跑都会被覆盖）
- `figures/` —— PNG 图表（RD 曲线、BD-rate 汇总、编码时间比）

这些是项目的"产出物"，与教程性质不同。教程文件（00–03）入 git，结果文件在 .gitignore 之外但通常也建议入库一份当快照。

## 后续可能增加的文档

按需添加：

- `04_extending_to_full_ctc.md` —— 详细说明扩展到完整 CTC 的步骤
- `05_paper_section_drafts.md` —— 论文章节草稿
- `06_troubleshooting.md` —— 实际跑过程中遇到的坑汇总

如果你在跑或扩展过程中发现教程缺失某些细节，记得回过头来补上。
