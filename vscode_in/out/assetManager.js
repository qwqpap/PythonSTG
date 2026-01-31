"use strict";
/**
 * Asset Manager - 管理STG游戏的纹理资产
 * 解析JSON配置文件，提供资产查询和图片预览
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.AssetManager = void 0;
const vscode = __importStar(require("vscode"));
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
class AssetManager {
    assets = new Map();
    texturePaths = new Map();
    imageCache = new Map(); // base64 cache
    workspaceRoot = '';
    _onAssetsChanged = new vscode.EventEmitter();
    onAssetsChanged = this._onAssetsChanged.event;
    constructor() {
        this.initialize();
    }
    /** 初始化，查找工作区并加载资产 */
    async initialize() {
        const workspaces = vscode.workspace.workspaceFolders;
        if (!workspaces || workspaces.length === 0) {
            return;
        }
        // 查找包含 assets 文件夹的工作区
        for (const ws of workspaces) {
            const assetsPath = path.join(ws.uri.fsPath, 'assets');
            if (fs.existsSync(assetsPath)) {
                this.workspaceRoot = ws.uri.fsPath;
                break;
            }
        }
        if (!this.workspaceRoot) {
            // 使用第一个工作区
            this.workspaceRoot = workspaces[0].uri.fsPath;
        }
        await this.loadAllConfigs();
        // 监听文件变化
        const watcher = vscode.workspace.createFileSystemWatcher('**/assets/**/*.json');
        watcher.onDidChange(() => this.loadAllConfigs());
        watcher.onDidCreate(() => this.loadAllConfigs());
        watcher.onDidDelete(() => this.loadAllConfigs());
    }
    /** 加载所有配置文件 */
    async loadAllConfigs() {
        this.assets.clear();
        this.texturePaths.clear();
        const assetsRoot = path.join(this.workspaceRoot, 'assets');
        if (!fs.existsSync(assetsRoot)) {
            return;
        }
        // 配置文件路径模式
        const configDirs = [
            'images/bullet',
            'images/laser',
            'images/item',
            'images/enemy',
            'images/background',
            'images/ui',
            'images/misc',
            'players/reimu',
            'players/sakuya',
        ];
        for (const dir of configDirs) {
            const dirPath = path.join(assetsRoot, dir);
            if (fs.existsSync(dirPath)) {
                await this.loadConfigsFromDir(dirPath);
            }
        }
        this._onAssetsChanged.fire();
        console.log(`[STG Asset Preview] Loaded ${this.assets.size} assets`);
    }
    /** 从目录加载配置 */
    async loadConfigsFromDir(dirPath) {
        const files = fs.readdirSync(dirPath);
        for (const file of files) {
            if (file.endsWith('.json')) {
                const configPath = path.join(dirPath, file);
                await this.loadConfig(configPath);
            }
        }
    }
    /** 加载单个配置文件 */
    async loadConfig(configPath) {
        try {
            const content = fs.readFileSync(configPath, 'utf-8');
            const config = JSON.parse(content);
            const sheetName = path.basename(configPath, '.json');
            const dirPath = path.dirname(configPath);
            // 解析纹理路径
            let texturePath = '';
            if (config.__image_filename) {
                texturePath = path.join(dirPath, config.__image_filename);
            }
            else {
                // 尝试同名png
                const pngPath = configPath.replace('.json', '.png');
                if (fs.existsSync(pngPath)) {
                    texturePath = pngPath;
                }
            }
            this.texturePaths.set(sheetName, texturePath);
            // 解析精灵
            if (config.sprites) {
                for (const [name, sprite] of Object.entries(config.sprites)) {
                    const [x, y, w, h] = sprite.rect;
                    const [cx, cy] = sprite.center || [w / 2, h / 2];
                    this.assets.set(name, {
                        name,
                        type: 'sprite',
                        sheetName,
                        texturePath,
                        region: { x, y, width: w, height: h, centerX: cx, centerY: cy },
                        radius: sprite.radius,
                        rotate: sprite.rotate
                    });
                }
            }
            // 解析动画
            if (config.animations) {
                for (const [name, anim] of Object.entries(config.animations)) {
                    const frames = anim.frames.map(f => {
                        const [x, y, w, h] = f.rect;
                        const [cx, cy] = f.center || [w / 2, h / 2];
                        return { x, y, width: w, height: h, centerX: cx, centerY: cy };
                    });
                    if (frames.length > 0) {
                        this.assets.set(name, {
                            name,
                            type: 'animation',
                            sheetName,
                            texturePath,
                            region: frames[0],
                            frames
                        });
                    }
                }
            }
            // 解析激光
            if (config.lasers) {
                for (const [name, laser] of Object.entries(config.lasers)) {
                    // 使用body作为主区域
                    const rect = laser.body || laser.head || laser.tail;
                    if (rect) {
                        const [x, y, w, h] = rect;
                        this.assets.set(name, {
                            name,
                            type: 'laser',
                            sheetName,
                            texturePath,
                            region: { x, y, width: w, height: h, centerX: w / 2, centerY: h / 2 }
                        });
                    }
                }
            }
        }
        catch (e) {
            console.error(`[STG Asset Preview] Failed to load ${configPath}:`, e);
        }
    }
    /** 获取资产 */
    getAsset(name) {
        return this.assets.get(name);
    }
    /** 搜索资产（模糊匹配） */
    searchAssets(query) {
        const results = [];
        const lowerQuery = query.toLowerCase();
        for (const asset of this.assets.values()) {
            if (asset.name.toLowerCase().includes(lowerQuery)) {
                results.push(asset);
            }
        }
        return results.sort((a, b) => {
            // 完全匹配优先
            if (a.name.toLowerCase() === lowerQuery)
                return -1;
            if (b.name.toLowerCase() === lowerQuery)
                return 1;
            // 前缀匹配次之
            if (a.name.toLowerCase().startsWith(lowerQuery))
                return -1;
            if (b.name.toLowerCase().startsWith(lowerQuery))
                return 1;
            return a.name.localeCompare(b.name);
        });
    }
    /** 获取所有资产名称 */
    getAllAssetNames() {
        return Array.from(this.assets.keys());
    }
    /** 获取所有资产 */
    getAllAssets() {
        return Array.from(this.assets.values());
    }
    /** 获取资产图片的Base64数据URI */
    async getAssetImageBase64(asset, maxSize = 64) {
        if (!asset.texturePath || !fs.existsSync(asset.texturePath)) {
            return null;
        }
        const cacheKey = `${asset.name}_${maxSize}`;
        if (this.imageCache.has(cacheKey)) {
            return this.imageCache.get(cacheKey);
        }
        try {
            // 读取整个纹理图片
            const imageBuffer = fs.readFileSync(asset.texturePath);
            // 使用简单的PNG裁剪（需要sharp或其他库来做真正的裁剪）
            // 这里我们返回整个图片的base64，在Markdown中用CSS控制显示区域
            const base64 = imageBuffer.toString('base64');
            const mimeType = 'image/png';
            const dataUri = `data:${mimeType};base64,${base64}`;
            this.imageCache.set(cacheKey, dataUri);
            return dataUri;
        }
        catch (e) {
            console.error(`[STG Asset Preview] Failed to load image for ${asset.name}:`, e);
            return null;
        }
    }
    /** 获取纹理文件的URI（用于webview） */
    getTextureUri(asset) {
        if (!asset.texturePath || !fs.existsSync(asset.texturePath)) {
            return null;
        }
        return vscode.Uri.file(asset.texturePath);
    }
    /** 清除缓存 */
    clearCache() {
        this.imageCache.clear();
    }
    dispose() {
        this.assets.clear();
        this.texturePaths.clear();
        this.imageCache.clear();
        this._onAssetsChanged.dispose();
    }
}
exports.AssetManager = AssetManager;
//# sourceMappingURL=assetManager.js.map