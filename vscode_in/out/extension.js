"use strict";
/**
 * STG Asset Preview - VS Code 扩展
 *
 * 功能:
 * - 悬停预览: 鼠标悬停在资产名称上时显示图片和属性
 * - 自动补全: 输入时提供资产名称补全，带图片预览
 * - 支持: 子弹、激光、动画、玩家等资产类型
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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const assetManager_1 = require("./assetManager");
const hoverProvider_1 = require("./hoverProvider");
const completionProvider_1 = require("./completionProvider");
let assetManager;
function activate(context) {
    console.log('[STG Asset Preview] Extension activated');
    // 初始化资产管理器
    assetManager = new assetManager_1.AssetManager();
    // 支持的语言
    const supportedLanguages = [
        { scheme: 'file', language: 'python' },
        { scheme: 'file', language: 'lua' },
        { scheme: 'file', language: 'json' },
        { scheme: 'file', language: 'javascript' },
        { scheme: 'file', language: 'typescript' },
    ];
    // 注册 Hover Provider
    const hoverProvider = new hoverProvider_1.STGHoverProvider(assetManager);
    for (const selector of supportedLanguages) {
        context.subscriptions.push(vscode.languages.registerHoverProvider(selector, hoverProvider));
    }
    // 注册 Completion Provider
    const completionProvider = new completionProvider_1.STGCompletionProvider(assetManager);
    for (const selector of supportedLanguages) {
        context.subscriptions.push(vscode.languages.registerCompletionItemProvider(selector, completionProvider, '"', "'", '_' // 触发字符
        ));
    }
    // 注册命令: 刷新资产
    context.subscriptions.push(vscode.commands.registerCommand('stg-asset-preview.refresh', async () => {
        await assetManager.loadAllConfigs();
        vscode.window.showInformationMessage('STG资产已刷新');
    }));
    // 注册命令: 显示所有资产
    context.subscriptions.push(vscode.commands.registerCommand('stg-asset-preview.showAll', () => {
        const assets = assetManager.getAllAssets();
        const items = assets.map(a => ({
            label: `${getTypeEmoji(a.type)} ${a.name}`,
            description: `${a.sheetName} - ${a.region.width}×${a.region.height}`,
            detail: `类型: ${a.type}, 区域: [${a.region.x}, ${a.region.y}]`,
            asset: a
        }));
        vscode.window.showQuickPick(items, {
            placeHolder: '搜索STG资产...',
            matchOnDescription: true,
            matchOnDetail: true
        }).then(selected => {
            if (selected) {
                // 插入资产名称到编辑器
                const editor = vscode.window.activeTextEditor;
                if (editor) {
                    editor.insertSnippet(new vscode.SnippetString(`"${selected.asset.name}"`));
                }
            }
        });
    }));
    // 注册命令: 搜索资产
    context.subscriptions.push(vscode.commands.registerCommand('stg-asset-preview.search', async () => {
        const query = await vscode.window.showInputBox({
            prompt: '输入资产名称关键词',
            placeHolder: '例如: bullet, laser, red...'
        });
        if (query) {
            const assets = assetManager.searchAssets(query);
            if (assets.length === 0) {
                vscode.window.showInformationMessage(`未找到匹配 "${query}" 的资产`);
                return;
            }
            const items = assets.slice(0, 100).map(a => ({
                label: `${getTypeEmoji(a.type)} ${a.name}`,
                description: a.sheetName,
                asset: a
            }));
            const selected = await vscode.window.showQuickPick(items, {
                placeHolder: `找到 ${assets.length} 个匹配的资产`
            });
            if (selected) {
                const editor = vscode.window.activeTextEditor;
                if (editor) {
                    editor.insertSnippet(new vscode.SnippetString(`"${selected.asset.name}"`));
                }
            }
        }
    }));
    // 状态栏
    const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBar.command = 'stg-asset-preview.showAll';
    context.subscriptions.push(statusBar);
    // 更新状态栏
    const updateStatusBar = () => {
        const count = assetManager.getAllAssetNames().length;
        statusBar.text = `$(file-media) STG: ${count} 资产`;
        statusBar.tooltip = '点击查看所有STG资产';
        statusBar.show();
    };
    assetManager.onAssetsChanged(updateStatusBar);
    updateStatusBar();
    console.log('[STG Asset Preview] Providers registered');
}
function getTypeEmoji(type) {
    switch (type) {
        case 'sprite': return '🎯';
        case 'animation': return '🎬';
        case 'laser': return '⚡';
        case 'bent_laser': return '🌀';
        default: return '📦';
    }
}
function deactivate() {
    if (assetManager) {
        assetManager.dispose();
    }
}
//# sourceMappingURL=extension.js.map