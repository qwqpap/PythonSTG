"""Thin launcher into the existing main game and StageManager."""

import argparse
import os
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description='在正式 PySTG 游戏中运行 TH07 第五面。')
    parser.add_argument('--difficulty', choices=('easy', 'normal', 'hard', 'lunatic'),
                        help='固定难度；省略时在游戏中选择。')
    parser.add_argument('--start', choices=('road', 'midboss', 'youmu'), default='road')
    parser.add_argument('--phase', type=int, help='Boss 第N阶段，从1编号；中Boss1–2，关底1–6。')
    parser.add_argument('--seed', type=int, default=1337)
    parser.add_argument('--assets', type=Path)
    args, forwarded = parser.parse_known_args(argv)
    limit = {'road': 0, 'midboss': 2, 'youmu': 6}[args.start]
    if args.phase is not None and not 1 <= args.phase <= limit:
        parser.error('--phase需要中Boss或关底入口的有效阶段号。')
    if args.assets is not None:
        os.environ['PYSTG_TH07_STAGE5_ASSETS'] = str(args.assets.resolve())
    sys.path.insert(0, str(ROOT))
    from game_content.ports.th07_stage5.stage import TH07Stage5
    from game_content.ports.th07_stage5.resources import install_resources
    install_resources()
    TH07Stage5.seed_override = args.seed
    TH07Stage5.start_section = args.start
    TH07Stage5.initial_phase = None if args.phase is None else args.phase - 1
    print('TH07 第五面：普通Python API移植；原MSG对话与部分动画仍未完整还原。')
    print(f'难度 {args.difficulty or "游戏中选择"} / 入口 {args.start} / 随机种子 {args.seed}')
    print('开始游戏后选择难度；方向键选择，Z / Enter 确认，Esc 返回。')
    sys.argv = [str(ROOT / 'main.py'),
                '--content-entry=game_content.ports.th07_stage5.entry',
                '--stage=th07_stage5', *forwarded]
    if args.difficulty is not None:
        sys.argv.append('--difficulty=' + args.difficulty)
    runpy.run_path(str(ROOT / 'main.py'), run_name='__main__')


if __name__ == '__main__':
    main()
