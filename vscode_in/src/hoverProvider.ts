/**
 * Hover Provider - 鼠标悬停时显示资产预览
 */

import * as vscode from 'vscode';
import { AssetManager, SpriteAsset } from './assetManager';

export class STGHoverProvider implements vscode.HoverProvider {
    constructor(private assetManager: AssetManager) {}

    async provideHover(
        document: vscode.TextDocument,
        position: vscode.Position,
        token: vscode.CancellationToken
    ): Promise<vscode.Hover | null> {
        // 获取当前位置的词
        const wordRange = document.getWordRangeAtPosition(position, /["']([^"']+)["']|[\w_]+/);
        if (!wordRange) {
            return null;
        }

        let word = document.getText(wordRange);
        
        // 去除引号
        if ((word.startsWith('"') && word.endsWith('"')) || 
            (word.startsWith("'") && word.endsWith("'"))) {
            word = word.slice(1, -1);
        }

        // 查找资产
        const asset = this.assetManager.getAsset(word);
        if (!asset) {
            return null;
        }

        // 创建hover内容
        const markdown = await this.createHoverContent(asset);
        if (!markdown) {
            return null;
        }

        return new vscode.Hover(markdown, wordRange);
    }

    private async createHoverContent(asset: SpriteAsset): Promise<vscode.MarkdownString | null> {
        const md = new vscode.MarkdownString();
        md.isTrusted = true;
        md.supportHtml = true;

        // 标题
        const typeEmoji = this.getTypeEmoji(asset.type);
        md.appendMarkdown(`### ${typeEmoji} ${asset.name}\n\n`);

        // 类型信息
        md.appendMarkdown(`**类型:** ${this.getTypeName(asset.type)}\n\n`);
        md.appendMarkdown(`**纹理表:** ${asset.sheetName}\n\n`);

        // 区域信息
        const r = asset.region;
        md.appendMarkdown(`**区域:** \`[${r.x}, ${r.y}, ${r.width}, ${r.height}]\`\n\n`);
        md.appendMarkdown(`**中心:** \`[${r.centerX}, ${r.centerY}]\`\n\n`);

        if (asset.radius !== undefined) {
            md.appendMarkdown(`**碰撞半径:** ${asset.radius}\n\n`);
        }

        if (asset.rotate !== undefined) {
            md.appendMarkdown(`**跟随旋转:** ${asset.rotate ? '是' : '否'}\n\n`);
        }

        if (asset.type === 'animation' && asset.frames) {
            md.appendMarkdown(`**帧数:** ${asset.frames.length}\n\n`);
        }

        // 图片预览
        const textureUri = this.assetManager.getTextureUri(asset);
        if (textureUri) {
            md.appendMarkdown('---\n\n');
            md.appendMarkdown('**预览:**\n\n');
            
            // 使用HTML来显示裁剪后的图片区域
            // 注意：VS Code的Hover对HTML支持有限，这里使用简化方式
            const imgStyle = `
                width: ${Math.min(r.width * 2, 128)}px;
                height: ${Math.min(r.height * 2, 128)}px;
                object-fit: none;
                object-position: -${r.x * 2}px -${r.y * 2}px;
                image-rendering: pixelated;
                background: #1a1a1a;
                border: 1px solid #444;
            `.replace(/\s+/g, ' ').trim();

            // VS Code hover不完全支持复杂CSS，使用图片链接
            md.appendMarkdown(`![${asset.name}](${textureUri})\n\n`);
            md.appendMarkdown(`*区域: (${r.x}, ${r.y}) - ${r.width}×${r.height}*`);
        }

        return md;
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
