"""Launch the stage 6 port through the existing main game, not a new runtime."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import runpy
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description='在正式 PySTG 游戏中运行 TH07 第六面移植。')
    parser.add_argument('--difficulty', choices=('easy', 'normal', 'hard', 'lunatic'),
                        help='固定难度；省略时在游戏中选择。')
    parser.add_argument('--start', choices=('road', 'youmu', 'yuyuko'), default='road')
    parser.add_argument('--seed', type=int, default=1337)
    parser.add_argument('--phase', type=int, help='从指定 Boss 的第 N 阶段继续（从 1 开始）。')
    parser.add_argument('--assets', type=Path, help='本地素材缓存；不修改原版游戏目录。')
    args, forwarded = parser.parse_known_args(argv)
    if args.phase is not None:
        limit = 2 if args.start == 'youmu' else 10 if args.start == 'yuyuko' else 0
        if not 1 <= args.phase <= limit:
            parser.error('--phase 需要 --start youmu（1–2）或 --start yuyuko（1–10）。')
    if args.assets is not None:
        os.environ['PYSTG_TH07_STAGE6_ASSETS'] = str(args.assets.resolve())
    sys.path.insert(0, str(PROJECT_ROOT))
    from game_content.ports.th07_stage6.stage import TH07Stage6
    from game_content.ports.th07_stage6.resources import install_resources
    # Fail before opening a window if local original resources are missing.
    install_resources()
    TH07Stage6.start_section = args.start
    TH07Stage6.seed_override = args.seed
    TH07Stage6.initial_phase = None if args.phase is None else args.phase - 1
    TH07Stage6.skip_dialogue = True
    print('TH07 第六面：已接入原场景、符卡背景及标题；原对话与部分动画尚未完整还原。')
    print(f'难度 {args.difficulty or "游戏中选择"} / 入口 {args.start} / 随机种子 {args.seed}')
    print('开始游戏后选择难度；方向键选择，Z / Enter 确认，Esc 返回。')
    print('进入主菜单后选择“开始游戏”；方向键移动，Z 射击，Shift 慢速，Esc 暂停。')
    sys.argv = [str(PROJECT_ROOT / 'main.py'),
                '--content-entry=game_content.ports.th07_stage6.entry',
                '--stage=th07_stage6', *forwarded]
    if args.difficulty is not None:
        sys.argv.append('--difficulty=' + args.difficulty)
    runpy.run_path(str(PROJECT_ROOT / 'main.py'), run_name='__main__')


if __name__ == '__main__':
    main()
