"""
敌人预设查看工具

用于查看所有可用的敌人预设、行为预设和攻击预设。
可以在编辑器中使用此工具生成可选项列表。

使用方法：
    python tools/enemy/list_presets.py                    # 列出所有预设
    python tools/enemy/list_presets.py --detail fairy_red  # 查看具体预设的详细信息
    python tools/enemy/list_presets.py --export            # 导出为编辑器友好的JSON
"""

import sys
import json
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.game.stage.preset_enemy import (
    PresetManager,
    list_available_presets,
    get_preset_details
)


def print_header(title: str):
    """打印标题"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


def list_all_presets():
    """列出所有预设"""
    manager = PresetManager()
    manager.load_presets()

    # 敌人预设
    print_header("可用的敌人预设")
    presets = manager.list_presets()

    if not presets:
        print("  没有找到任何预设")
    else:
        for preset_id in sorted(presets):
            info = manager.get_preset_info(preset_id)
            print(f"  • {preset_id:20s} → {info}")

    # 行为预设
    print_header("可用的行为预设")
    behaviors = manager.list_behaviors()

    if not behaviors:
        print("  没有找到任何行为预设")
    else:
        for behavior_id in sorted(behaviors):
            behavior = manager.get_behavior_preset(behavior_id)
            name = behavior.get('name', behavior_id)
            desc = behavior.get('description', '')
            print(f"  • {behavior_id:20s} → {name}")
            if desc:
                print(f"    {desc}")

    # 攻击预设
    print_header("可用的攻击预设")
    if manager._presets and 'attack_presets' in manager._presets:
        attacks = list(manager._presets['attack_presets'].keys())

        if not attacks:
            print("  没有找到任何攻击预设")
        else:
            for attack_id in sorted(attacks):
                attack = manager.get_attack_preset(attack_id)
                name = attack.get('name', attack_id)
                attack_type = attack.get('type', 'unknown')
                print(f"  • {attack_id:20s} → {name} ({attack_type})")
    else:
        print("  没有找到任何攻击预设")

    print("\n" + "="*60 + "\n")


def show_preset_detail(preset_id: str):
    """显示预设的详细信息"""
    details = get_preset_details(preset_id)

    if not details:
        print(f"错误: 未找到预设 '{preset_id}'")
        return

    print_header(f"预设详细信息: {preset_id}")
    print(json.dumps(details, indent=2, ensure_ascii=False))
    print("\n" + "="*60 + "\n")


def export_for_editor(output_file: str = None):
    """导出为编辑器友好的JSON格式"""
    manager = PresetManager()
    manager.load_presets()

    # 构建编辑器友好的数据结构
    editor_data = {
        "enemy_presets": [],
        "behavior_presets": [],
        "attack_presets": []
    }

    # 敌人预设
    for preset_id in manager.list_presets():
        preset = manager.get_preset(preset_id)
        editor_data["enemy_presets"].append({
            "id": preset_id,
            "name": preset.get('name', preset_id),
            "sprite": preset.get('sprite'),
            "hp": preset.get('hp'),
            "score": preset.get('score'),
            "description": f"HP:{preset.get('hp')} 得分:{preset.get('score')} 掉落:{preset.get('drop', '无')}"
        })

    # 行为预设
    for behavior_id in manager.list_behaviors():
        behavior = manager.get_behavior_preset(behavior_id)
        editor_data["behavior_presets"].append({
            "id": behavior_id,
            "name": behavior.get('name', behavior_id),
            "description": behavior.get('description', ''),
            "phases_count": len(behavior.get('phases', []))
        })

    # 攻击预设
    if manager._presets and 'attack_presets' in manager._presets:
        for attack_id, attack_data in manager._presets['attack_presets'].items():
            editor_data["attack_presets"].append({
                "id": attack_id,
                "name": attack_data.get('name', attack_id),
                "type": attack_data.get('type', 'unknown')
            })

    # 输出
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(editor_data, f, indent=2, ensure_ascii=False)

        print(f"已导出到: {output_path}")
    else:
        print(json.dumps(editor_data, indent=2, ensure_ascii=False))


def generate_usage_code(preset_id: str, behavior_id: str = None):
    """生成使用示例代码"""
    print_header(f"使用示例代码")

    if behavior_id:
        print(f"""
# 方式1: 使用预设 + 行为（最简单）
from src.game.stage.preset_enemy import PresetEnemy

class My{preset_id.title().replace('_', '')}(PresetEnemy):
    preset_id = "{preset_id}"
    behavior_preset = "{behavior_id}"
    # 无需写 run() 方法，会自动执行预设行为


# 方式2: 动态创建（适合编辑器）
from src.game.stage.preset_enemy import create_preset_enemy

EnemyClass = create_preset_enemy(
    preset_id="{preset_id}",
    behavior="{behavior_id}"
)
enemy = EnemyClass()


# 方式3: 在波次中使用
from src.game.stage.wave_base import Wave

class MyWave(Wave):
    async def run(self):
        self.spawn_enemy_class(My{preset_id.title().replace('_', '')}, x=0.0, y=1.0)
        await self.wait(60)
""")
    else:
        print(f"""
# 使用预设 + 自定义行为
from src.game.stage.preset_enemy import PresetEnemy

class My{preset_id.title().replace('_', '')}(PresetEnemy):
    preset_id = "{preset_id}"

    async def run(self):
        # 自定义行为
        await self.move_to(self.x, 0.3, duration=60)

        self.fire_circle(
            count=8,
            speed=self.defaults['move_speed'],
            bullet_type=self.defaults['bullet_type'],
            color=self.defaults['bullet_color']
        )

        await self.wait(60)
        await self.move_to(self.x, -0.2, duration=60)
""")

    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(description='敌人预设查看工具')
    parser.add_argument('--detail', metavar='PRESET_ID', help='查看指定预设的详细信息')
    parser.add_argument('--export', metavar='OUTPUT_FILE', nargs='?', const='', help='导出为编辑器友好的JSON')
    parser.add_argument('--usage', metavar='PRESET_ID', help='生成使用示例代码')
    parser.add_argument('--behavior', metavar='BEHAVIOR_ID', help='与 --usage 一起使用，指定行为')

    args = parser.parse_args()

    if args.detail:
        show_preset_detail(args.detail)
    elif args.export is not None:
        output_file = args.export if args.export else None
        export_for_editor(output_file)
    elif args.usage:
        generate_usage_code(args.usage, args.behavior)
    else:
        list_all_presets()


if __name__ == '__main__':
    main()
