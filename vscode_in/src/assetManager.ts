/**
 * Asset Manager - 管理STG游戏的纹理资产
 * 解析JSON配置文件，提供资产查询和图片预览
 */

import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

/** 精灵区域定义 */
export interface SpriteRegion {
    x: number;
    y: number;
    width: number;
    height: number;
    centerX: number;
    centerY: number;
}

/** 精灵资产 */
export interface SpriteAsset {
    name: string;
    type: 'sprite' | 'animation' | 'laser' | 'bent_laser';
    sheetName: string;
    texturePath: string;
    region: SpriteRegion;
    radius?: number;
    rotate?: boolean;
    frames?: SpriteRegion[];  // 动画帧
    color?: string;  // 颜色变体
}

/** JSON配置结构 */
interface SpriteConfig {
    __image_filename: string;
    sprites?: Record<string, {
        rect: [number, number, number, number];
        center?: [number, number];
        radius?: number;
        rotate?: boolean;
    }>;
    animations?: Record<string, {
        frames: Array<{
            rect: [number, number, number, number];
            center?: [number, number];
        }>;
        frame_duration?: number;
        loop?: boolean;
    }>;
    lasers?: Record<string, {
        head?: [number, number, number, number];
        body?: [number, number, number, number];
        tail?: [number, number, number, number];
    }>;
}

export class AssetManager {
    private assets: Map<string, SpriteAsset> = new Map();
    private texturePaths: Map<string, string> = new Map();
    private imageCache: Map<string, string> = new Map();  // base64 cache
    private workspaceRoot: string = '';
    private _onAssetsChanged = new vscode.EventEmitter<void>();
    public readonly onAssetsChanged = this._onAssetsChanged.event;

    constructor() {
        this.initialize();
    }

    /** 初始化，查找工作区并加载资产 */
    async initialize(): Promise<void> {
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
    async loadAllConfigs(): Promise<void> {
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
    private async loadConfigsFromDir(dirPath: string): Promise<void> {
        const files = fs.readdirSync(dirPath);
        
        for (const file of files) {
            if (file.endsWith('.json')) {
                const configPath = path.join(dirPath, file);
                await this.loadConfig(configPath);
            }
        }
    }

    /** 加载单个配置文件 */
    private async loadConfig(configPath: string): Promise<void> {
        try {
            const content = fs.readFileSync(configPath, 'utf-8');
            const config: SpriteConfig = JSON.parse(content);
            
            const sheetName = path.basename(configPath, '.json');
            const dirPath = path.dirname(configPath);
            
            // 解析纹理路径
            let texturePath = '';
            if (config.__image_filename) {
                texturePath = path.join(dirPath, config.__image_filename);
            } else {
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
                    const frames: SpriteRegion[] = anim.frames.map(f => {
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

        } catch (e) {
            console.error(`[STG Asset Preview] Failed to load ${configPath}:`, e);
        }
    }

    /** 获取资产 */
    getAsset(name: string): SpriteAsset | undefined {
        return this.assets.get(name);
    }

    /** 搜索资产（模糊匹配） */
    searchAssets(query: string): SpriteAsset[] {
        const results: SpriteAsset[] = [];
        const lowerQuery = query.toLowerCase();

        for (const asset of this.assets.values()) {
            if (asset.name.toLowerCase().includes(lowerQuery)) {
                results.push(asset);
            }
        }

        return results.sort((a, b) => {
            // 完全匹配优先
            if (a.name.toLowerCase() === lowerQuery) return -1;
            if (b.name.toLowerCase() === lowerQuery) return 1;
            // 前缀匹配次之
            if (a.name.toLowerCase().startsWith(lowerQuery)) return -1;
            if (b.name.toLowerCase().startsWith(lowerQuery)) return 1;
            return a.name.localeCompare(b.name);
        });
    }

    /** 获取所有资产名称 */
    getAllAssetNames(): string[] {
        return Array.from(this.assets.keys());
    }

    /** 获取所有资产 */
    getAllAssets(): SpriteAsset[] {
        return Array.from(this.assets.values());
    }

    /** 获取资产图片的Base64数据URI */
    async getAssetImageBase64(asset: SpriteAsset, maxSize: number = 64): Promise<string | null> {
        if (!asset.texturePath || !fs.existsSync(asset.texturePath)) {
            return null;
        }

        const cacheKey = `${asset.name}_${maxSize}`;
        if (this.imageCache.has(cacheKey)) {
            return this.imageCache.get(cacheKey)!;
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
        } catch (e) {
            console.error(`[STG Asset Preview] Failed to load image for ${asset.name}:`, e);
            return null;
        }
    }

    /** 获取纹理文件的URI（用于webview） */
    getTextureUri(asset: SpriteAsset): vscode.Uri | null {
        if (!asset.texturePath || !fs.existsSync(asset.texturePath)) {
            return null;
        }
        return vscode.Uri.file(asset.texturePath);
    }

    /** 清除缓存 */
    clearCache(): void {
        this.imageCache.clear();
    }

    dispose(): void {
        this.assets.clear();
        this.texturePaths.clear();
        this.imageCache.clear();
        this._onAssetsChanged.dispose();
    }
}
