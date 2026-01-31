"use strict";
/**
 * Completion Provider - 自动补全资产名称并显示预览
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
exports.STGCompletionProvider = void 0;
const vscode = __importStar(require("vscode"));
class STGCompletionProvider {
    assetManager;
    constructor(assetManager) {
        this.assetManager = assetManager;
    }
    provideCompletionItems(document, position, token, context) {
        // 检查是否在字符串内
        const lineText = document.lineAt(position).text;
        const textBefore = lineText.substring(0, position.character);
        // 检测是否在引号内
        const inString = this.isInString(textBefore);
        if (!inString) {
            return [];
        }
        // 获取当前输入的前缀
        const prefix = this.getPrefix(textBefore);
        // 搜索匹配的资产
        const assets = prefix
            ? this.assetManager.searchAssets(prefix)
            : this.assetManager.getAllAssets();
        // 限制数量
        const maxItems = 50;
        const items = assets.slice(0, maxItems).map(asset => this.createCompletionItem(asset, prefix));
        return new vscode.CompletionList(items, assets.length > maxItems);
    }
    async resolveCompletionItem(item, token) {
        // 获取关联的资产 - 使用label获取名称
        const assetName = typeof item.label === 'string' ? item.label : item.label.label;
        if (!assetName) {
            return item;
        }
        const asset = this.assetManager.getAsset(assetName);
        if (!asset) {
            return item;
        }
        // 添加详细文档
        item.documentation = await this.createDocumentation(asset);
        return item;
    }
    isInString(textBefore) {
        // 简单检测是否在字符串内
        let inDouble = false;
        let inSingle = false;
        for (let i = 0; i < textBefore.length; i++) {
            const char = textBefore[i];
            const prevChar = i > 0 ? textBefore[i - 1] : '';
            if (char === '"' && prevChar !== '\\' && !inSingle) {
                inDouble = !inDouble;
            }
            else if (char === "'" && prevChar !== '\\' && !inDouble) {
                inSingle = !inSingle;
            }
        }
        return inDouble || inSingle;
    }
    getPrefix(textBefore) {
        // 获取引号内已输入的内容
        const lastQuote = Math.max(textBefore.lastIndexOf('"'), textBefore.lastIndexOf("'"));
        if (lastQuote === -1) {
            return '';
        }
        return textBefore.substring(lastQuote + 1);
    }
    createCompletionItem(asset, prefix) {
        const item = new vscode.CompletionItem(asset.name, this.getCompletionKind(asset.type));
        // 标签详情
        item.detail = `${this.getTypeName(asset.type)} - ${asset.sheetName}`;
        // 排序优先级
        if (asset.name.toLowerCase() === prefix.toLowerCase()) {
            item.sortText = `0_${asset.name}`;
        }
        else if (asset.name.toLowerCase().startsWith(prefix.toLowerCase())) {
            item.sortText = `1_${asset.name}`;
        }
        else {
            item.sortText = `2_${asset.name}`;
        }
        // 图标
        item.kind = this.getCompletionKind(asset.type);
        // 简短描述
        const r = asset.region;
        item.documentation = new vscode.MarkdownString(`**${asset.name}**\n\n` +
            `类型: ${this.getTypeName(asset.type)}\n\n` +
            `尺寸: ${r.width}×${r.height}`);
        return item;
    }
    async createDocumentation(asset) {
        const md = new vscode.MarkdownString();
        md.isTrusted = true;
        md.supportHtml = true;
        // 标题
        const emoji = this.getTypeEmoji(asset.type);
        md.appendMarkdown(`## ${emoji} ${asset.name}\n\n`);
        // 类型
        md.appendMarkdown(`**类型:** ${this.getTypeName(asset.type)}\n\n`);
        md.appendMarkdown(`**纹理表:** \`${asset.sheetName}\`\n\n`);
        // 区域
        const r = asset.region;
        md.appendMarkdown(`**区域:** \`[${r.x}, ${r.y}, ${r.width}, ${r.height}]\`\n\n`);
        md.appendMarkdown(`**尺寸:** ${r.width} × ${r.height} 像素\n\n`);
        if (asset.radius !== undefined) {
            md.appendMarkdown(`**碰撞半径:** ${asset.radius}\n\n`);
        }
        if (asset.type === 'animation' && asset.frames) {
            md.appendMarkdown(`**帧数:** ${asset.frames.length}\n\n`);
        }
        // 图片预览
        const textureUri = this.assetManager.getTextureUri(asset);
        if (textureUri) {
            md.appendMarkdown('---\n\n');
            md.appendMarkdown(`![Preview](${textureUri}|width=128)`);
        }
        return md;
    }
    getCompletionKind(type) {
        switch (type) {
            case 'sprite':
                return vscode.CompletionItemKind.Value;
            case 'animation':
                return vscode.CompletionItemKind.Event;
            case 'laser':
                return vscode.CompletionItemKind.Field;
            case 'bent_laser':
                return vscode.CompletionItemKind.Interface;
            default:
                return vscode.CompletionItemKind.Text;
        }
    }
    getTypeEmoji(type) {
        switch (type) {
            case 'sprite': return '🎯';
            case 'animation': return '🎬';
            case 'laser': return '⚡';
            case 'bent_laser': return '🌀';
            default: return '📦';
        }
    }
    getTypeName(type) {
        switch (type) {
            case 'sprite': return '精灵';
            case 'animation': return '动画';
            case 'laser': return '激光';
            case 'bent_laser': return '曲线激光';
            default: return '未知';
        }
    }
}
exports.STGCompletionProvider = STGCompletionProvider;
//# sourceMappingURL=completionProvider.js.map