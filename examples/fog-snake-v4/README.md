# 迷雾贪吃蛇 v4

在只能看到局部棋盘的条件下，写一个在线策略，选择移动或花费资源探测，吃光食物后主动结束。裁判按通关与总成本评分。标准赛道包含菜园、成簇果园和昏暗地窖；湿地压轴还要追踪会跳开的目标。

## 自己试题

只把 `kit/` 发给解题者。题包包含[完整规则与交互协议](kit/README.md)、可运行的基线和裁判。使用 Python 3.10+ 标准库，在本例目录运行：

```sh
cd kit
python3 -m unittest -v test_game
python3 judge.py run baseline.py --suite standard --per-level 2 --jobs 1 --out practice.json
python3 judge.py run baseline.py --suite boss --per-level 2 --jobs 1 --out practice-boss.json
```

把命令中的 `baseline.py` 换成自己的策略即可试跑。正式挑战每图 20 局；每图须全部通关且至少 10 局成本达标。总成本包含移动费、探测费和延迟采摘损耗。标准和压轴分别判胜。

## 组织一次新对照

让两组在独立会话里从同一份题包出发，记录模型、实际用量和提交版本。两组定稿后，主持人生成一份新的 32 字节棋盘种子，两组运行时均传入同一份 `--key-file`。例如用 `python3 -c "from pathlib import Path; import secrets; Path('holdout.bin').open('xb').write(secrets.token_bytes(32))"` 生成文件。每组、每个赛道分别保存结果，再用 `python3 judge.py compare A.json B.json` 对比同赛道的配对成绩。需要重复批次时，每批换一个新种子。

[历史对照与复跑入口](study/README.md)供主持人或解题结束后查阅，含参赛策略与已公开的历史棋盘种子。
