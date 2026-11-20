# 引擎架构概览

本文介绍 PySTG 引擎运行时的分层结构、核心模块职责以及单帧数据流。声明式作者工程经 `src.authoring` 解析、`src.compiler` 生成后，也运行在这套引擎之上；关卡编辑器自身架构见 [编辑器架构](EDITOR_ARCHITECTURE.md)。

## 分层结构

```mermaid
flowchart TB
    main["main.py<br/>入口、主循环与游戏状态机"]
    core["src.core<br/>配置 / 碰撞 / 窗口 / 输入 / 音频流"]
    resource["src.resource<br/>纹理 / 图集 / 精灵服务"]
    game["src.game<br/>弹幕 / 关卡 / 自机 / Boss / 激光 / 粒子 / 背景"]
    ui["src.ui<br/>HUD / 菜单 / 对话 / 文字叠加"]
    render["src.render<br/>OpenGL / ModernGL 渲染管线"]
    content["game_content/<br/>手写关卡与编译生成的关卡包"]
    ctx["StageContext<br/>内容脚本与引擎之间的边界"]

    main --> core
    main --> resource
    main --> game
    main --> ui
    core --> render
    resource --> render
    game --> render
    ui --> render
    content --> ctx --> game
```

内容脚本通过 `StageContext` 和高层基类调用引擎能力，不直接耦合渲染器或底层数组实现。

## 模块说明

### `src/core` — 基础设施

| 模块 | 职责 |
| --- | --- |
| `config.py` | 全局配置常量（逻辑分辨率 `384×448`、窗口视口、缓冲上限） |
| `window.py` / `input_manager.py` | GLFW 窗口、固定帧率时钟与键盘输入 |
| `collision.py` / `collision_shapes.py` | Numba 加速碰撞检测（圆、旋转矩形 SAT、激光与曲线段几何、擦弹） |
| `audio_backend.py` / `bgm_stream.py` | miniaudio 混音后端与流式 PCM 音乐解码（支持样本级循环点与淡入淡出） |
| `sprite_registry.py` | 全局精灵 UV 注册表 |
| `project_context.py` | `res://` 项目相对路径解析 |
| `preview_protocol.py` | 编辑器与预览子进程的 NDJSON 通信协议 |

### `src/resource` — 资源管理

| 模块 | 职责 |
| --- | --- |
| `texture_asset.py` | 纹理图集加载、精灵与帧动画定义、UV 计算 |
| `unified_texture.py` | 跨图集统一纹理管理 |
| `service.py` / `asset_manager.py` | 资源服务与缓存 |
| `sprite/` | 精灵兼容层 |

### `src/game` — 游戏逻辑

| 模块 | 职责 |
| --- | --- |
| `bullet/` | `OptimizedBulletPool`（SoA 结构化数组 + Numba）、多阶段行为（`behavior.py`）、批量快照（`batch.py`）、穿屏后处理（`motion.py`）与终结转换队列（`termination.py`） |
| `stage/` | 关卡核心：`StageScript`、`Wave`、`EnemyScript`、`SpellCard`、`BossBase`、`StageContext`、`StageManager`、移动曲线（`motion.py`）、预设敌人、对话与练习模式 |
| `tasks.py` | 固定 60 Hz 帧任务调度与取消/清理作用域 |
| `state.py` | 跨关 `RunState` 与分系统暂停/慢速控制（`TimeControl`） |
| `player/` | 自机移动、射击、子机、持续激光/爆炸攻击池（`player_bullet.py`）与受击救援契约（`hit.py`） |
| `damage.py` | 统一伤害事实（`DamageHit`）与同帧目标伤害分发 |
| `laser.py` | 直线激光与曲线激光池化管理 |
| `item.py` | SoA 道具池、吸附逻辑与稀疏收集规则入口 |
| `particle.py` / `animation.py` / `trail.py` | 独立非碰撞粒子池、角色主/附属动画控制、连续纹理拖尾 |
| `background.py` / `background_render/` | 无 GL 的 3D 背景状态（静态面片、相机、雾、屏幕层）与 OpenGL 背景渲染器 |
| `overlay.py` / `screen_effects.py` | 游戏区/HUD 文字叠加、闪屏脉冲与屏幕震动 |
| `audio.py` | 双层音频库（全局音频 + 关卡私有覆盖） |
| `userdata/` | 设置、进度与 Replay 录制/回放 |

### `src/render` — 渲染管线

| 模块 | 职责 |
| --- | --- |
| `renderer.py` | 主渲染器，协调各子渲染器、视口裁剪与加载期资源预热 |
| `optimized_bullet_renderer.py` | 敌弹与自机弹批量实例化绘制 |
| `particle_renderer.py` | 粒子、角色受控动画与连续拖尾复用实例/网格绘制 |
| `laser_renderer.py` | 直线与曲线激光几何构建及绘制 |
| `player_renderer.py` / `item_renderer.py` | 自机、判定点与道具绘制 |

### `src/ui` — 界面

| 模块 | 职责 |
| --- | --- |
| `hud.py` / `ui_renderer.py` | HUD 侧栏、LRU 文字缓存与游戏区文字叠加绘制 |
| `bitmap_font.py` | 位图字体渲染 |
| `dialog_gl_renderer.py` | 对话框与立绘渲染 |
| `main_menu_renderer.py` / `pause_menu_renderer.py` / `continue_menu_renderer.py` / `loading_renderer.py` / `staff_roll_renderer.py` | 各游戏界面渲染 |

### `src/authoring`、`src/compiler`、`src/editor` — 关卡编辑器链路

| 包 | 职责 |
| --- | --- |
| `src/authoring/` | 声明式 DSL、AST/tokenize 源码读写、模板展开、Headless 模型与 Timeline 投影 |
| `src/compiler/` | 确定性代码生成、Source Map、事务构建与内容入口加载 |
| `src/editor/` | PySide6 桌面关卡编辑器界面、单一 `EditorSession`、预览进程宿主 |

## 单帧数据流

### 控制更新顺序（60 Hz）

```mermaid
flowchart LR
    input["输入处理"] --> time["采样分系统时间倍率"]
    time --> pools["已有弹幕 / 激光 / 粒子 / 道具更新"]
    pools --> player["自机更新"]
    player --> stage["关卡协程 / 敌人 / Boss 推进"]
    stage --> collision["碰撞检测与伤害分发"]
    collision --> render["渲染输出"]
```

当前帧中由脚本新发射的子弹或转换生成的新敌人，均从下一仿真步开始运动与碰撞，避免行为受底层槽位编号顺序影响。

### 关卡内部执行流

```mermaid
flowchart TB
    stage["StageScript.run()"]
    wave["run_wave(WaveClass)"]
    dialogue["play_dialogue([...])"]
    boss["run_boss(BossDef)"]
    phases["按阶段顺序执行 BossPhase"]
    nonspell["NonSpell.run()"]
    spell["SpellCard.run()"]

    stage --> wave --> dialogue --> boss --> phases
    phases --> nonspell
    phases --> spell
```

### 子弹生命周期

```mermaid
flowchart LR
    fire["脚本调用 fire / create_bullets_batch"] --> ctx["StageContext 单位转换"]
    ctx --> spawn["OptimizedBulletPool 写入结构化数组"]
    spawn --> jit["Numba JIT 批量更新与阶段扫描"]
    jit --> endstate{"到期 / 出界 / 命中?"}
    endstate -- 否 --> spawn
    endstate -- 是 --> recycle["记录终结事件并回收槽位"]
```

### 渲染层级（从后到前）

```mermaid
flowchart LR
    bg["背景与屏幕层"] --> enemy["敌人与 Boss"] --> particleBack["后景粒子"]
    particleBack --> item["道具"] --> playerShot["自机弹"] --> player["自机"]
    player --> enemyBullet["敌弹"] --> laser["激光"] --> particleFront["前景粒子"]
    particleFront --> fx["闪屏 / 判定点"] --> ui["HUD 与文字"] --> dialog["对话框"]
```

### 音频查找顺序

```mermaid
flowchart TB
    play["play_se('shoot')"] --> stageBank{"关卡私有音频库存在?"}
    stageBank -- 是 --> stagePath["game_content/stages/stageN/audio/se/"]
    stageBank -- 否 --> gameBank{"全局音频库存在?"}
    gameBank -- 是 --> globalPath["assets/audio/se/"]
    gameBank -- 否 --> warn["记录缺失并跳过"]
```

关卡私有音效和 BGM 可直接覆盖全局同名音频。
