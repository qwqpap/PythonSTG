/**
 * Completion Provider - 自动补全资产名称并显示预览
 */

import * as vscode from 'vscode';
import { AssetManager, SpriteAsset } from './assetManager';

export class STGCompletionProvider implements vscode.CompletionItemProvider {
    constructor(private assetManager: AssetManager) {}

    provideCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        token: vscode.CancellationToken,
        context: vscode.CompletionContext
    ): vscode.CompletionItem[] | vscode.CompletionList {
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
        const items = assets.slice(0, maxItems).map(asset => 
            this.createCompletionItem(asset, prefix)
        );

        return new vscode.CompletionList(items, assets.length > maxItems);
    }

    async resolveCompletionItem(
        item: vscode.CompletionItem,
        token: vscode.CancellationToken
    ): Promise<vscode.CompletionItem> {
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

    private isInString(textBefore: string): boolean {
        // 简单检测是否在字符串内
        let inDouble = false;
        let inSingle = false;
        
        for (let i = 0; i < textBefore.length; i++) {
            const char = textBefore[i];
            const prevChar = i > 0 ? textBefore[i - 1] : '';
            
            if (char === '"' && prevChar !== '\\' && !inSingle) {
                inDouble = !inDouble;
            } else if (char === "'" && prevChar !== '\\' && !inDouble) {
                inSingle = !inSingle;
            }
        }

        return inDouble || inSingle;
    }

    private getPrefix(textBefore: string): string {
        // 获取引号内已输入的内容
        const lastQuote = Math.max(
            textBefore.lastIndexOf('"'),
            textBefore.lastIndexOf("'")
        );

        if (lastQuote === -1) {
            return '';
        }

        return textBefore.substring(lastQuote + 1);
    }

    private createCompletionItem(asset: SpriteAsset, prefix: string): vscode.CompletionItem {
        const item = new vscode.CompletionItem(
            asset.name,
            this.getCompletionKind(asset.type)
        );

        // 标签详情
        item.detail = `${this.getTypeName(asset.type)} - ${asset.sheetName}`;

        // 排序优先级
        if (asset.name.toLowerCase() === prefix.toLowerCase()) {
            item.sortText = `0_${asset.name}`;
        } else if (asset.name.toLowerCase().startsWith(prefix.toLowerCase())) {
            item.sortText = `1_${asset.name}`;
        } else {
            item.sortText = `2_${asset.name}`;
        }

        // 图标
        item.kind = this.getCompletionKind(asset.type);

        // 简短描述
        const r = asset.region;
        item.documentation = new vscode.MarkdownString(
            `**${asset.name}**\n\n` +
            `类型: ${this.getTypeName(asset.type)}\n\n` +
            `尺寸: ${r.width}×${r.height}`
        );

        return item;
    }

    private async createDocumentation(asset: SpriteAsset): Promise<vscode.MarkdownString> {
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

    private getCompletionKind(type: string): vscode.CompletionItemKind {
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

    private getTypeEmoji(type: string): string {
        switch (type) {
            case 'sprite': return '🎯';
            case 'animation': return '🎬';
            case 'laser': return '⚡';
            case 'bent_laser': return '🌀';
            default: return '📦';
        }
    }

    private getTypeName(type: string): string {
        switch (type) {
            case 'sprite': return '精灵';
            case 'animation': return '动画';
            case 'laser': return '激光';
            case 'bent_laser': return '曲线激光';
            default: return '未知';
        }
    }
}
