"""
背景渲染系统 - 支持多层2D卷轴、3D摄像机、后处理特效

功能特性 (根据todo.md实现):
Phase 1: 基础2D卷轴
- 多层纹理支持 (BackgroundLayer)
- UV滚动动画
- 透明度与混合模式 (Normal/Add/Multiply)
- 视差滚动

Phase 2: 3D摄像机
- 3D摄像机路径系统
- 距离雾效
- 3D平面/Billboard支持
- 对象生成器与自动回收

Phase 3: 后处理特效
- 屏幕扭曲/波动
- 颜色重映射 (反色、色调偏移)
- 符卡背景切换

Phase 4: 配置系统
- 从Lua背景脚本解析配置
- JSON配置文件支持
- 统一的纹理管理
"""

from .background_renderer import (
    BackgroundRenderer,
    BackgroundLayer,
    Background3DObject,
    BlendMode,
    Camera3D,
    PostEffect,
)

from .background_config import (
    BackgroundConfig,
    BackgroundTextureConfig,
    Camera3DConfig,
    FogConfig,
    LayerConfig,
    load_background_config,
    save_background_config,
)

from .procedural_background import (
    ProceduralBackground,
    Quad3D,
    LakeBackground,
    GensokyoSkyBackground,
    TempleBackground,
    BambooBackground,
    MagicForestBackground,
    SpellcardBackground,
    PROCEDURAL_BACKGROUNDS,
    create_background,
    list_backgrounds,
)

from .data_driven_background import (
    DataDrivenBackground,
    BackgroundData,
    CameraConfig,
    FogConfig as DataFogConfig,
    ScrollConfig,
    LayerConfig as DataLayerConfig,
    list_available_backgrounds,
)

__all__ = [
    # 渲染器
    'BackgroundRenderer',
    'BackgroundLayer', 
    'Background3DObject',
    'BlendMode',
    'Camera3D',
    'PostEffect',
    # 配置
    'BackgroundConfig',
    'BackgroundTextureConfig',
    'Camera3DConfig',
    'FogConfig',
    'LayerConfig',
    'load_background_config',
    'save_background_config',
    # 程序化背景 (旧版)
    'ProceduralBackground',
    'Quad3D',
    'LakeBackground',
    'GensokyoSkyBackground',
    'TempleBackground',
    'BambooBackground',
    'MagicForestBackground',
    'SpellcardBackground',
    'PROCEDURAL_BACKGROUNDS',
    'create_background',
    'list_backgrounds',
    # 数据驱动背景 (推荐)
    'DataDrivenBackground',
    'BackgroundData',
    'CameraConfig',
    'DataFogConfig',
    'ScrollConfig',
    'DataLayerConfig',
    'list_available_backgrounds',
]
