/**
 * STG Asset Preview - VS Code 扩展
 * 
 * 功能:
 * - 悬停预览: 鼠标悬停在资产名称上时显示图片和属性
 * - 自动补全: 输入时提供资产名称补全，带图片预览
 * - 支持: 子弹、激光、动画、玩家等资产类型
 */

import * as vscode from 'vscode';
import { AssetManager } from './assetManager';
import { STGHoverProvider } from './hoverProvider';
import { STGCompletionProvider } from './completionProvider';

let assetManager: AssetManager;

export function activate(context: vscode.ExtensionContext) {
	console.log('[STG Asset Preview] Extension activated');

	// 初始化资产管理器
	assetManager = new AssetManager();

	// 支持的语言
	const supportedLanguages = [
		{ scheme: 'file', language: 'python' },
		{ scheme: 'file', language: 'lua' },
		{ scheme: 'file', language: 'json' },
		{ scheme: 'file', language: 'javascript' },
		{ scheme: 'file', language: 'typescript' },
	];

	// 注册 Hover Provider
	const hoverProvider = new STGHoverProvider(assetManager);
	for (const selector of supportedLanguages) {
		context.subscriptions.push(
			vscode.languages.registerHoverProvider(selector, hoverProvider)
		);
	}

	// 注册 Completion Provider
	const completionProvider = new STGCompletionProvider(assetManager);
	for (const selector of supportedLanguages) {
		context.subscriptions.push(
			vscode.languages.registerCompletionItemProvider(
				selector,
				completionProvider,
				'"', "'", '_'  // 触发字符
			)
		);
	}

	// 注册命令: 刷新资产
	context.subscriptions.push(
		vscode.commands.registerCommand('stg-asset-preview.refresh', async () => {
			await assetManager.loadAllConfigs();
			vscode.window.showInformationMessage('STG资产已刷新');
		})
	);

	// 注册命令: 显示所有资产
	context.subscriptions.push(
		vscode.commands.registerCommand('stg-asset-preview.showAll', () => {
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
		})
	);

	// 注册命令: 搜索资产
	context.subscriptions.push(
		vscode.commands.registerCommand('stg-asset-preview.search', async () => {
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
		})
	);

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

function getTypeEmoji(type: string): string {
	switch (type) {
		case 'sprite': return '🎯';
		case 'animation': return '🎬';
		case 'laser': return '⚡';
		case 'bent_laser': return '🌀';
		default: return '📦';
	}
}

export function deactivate() {
	if (assetManager) {
		assetManager.dispose();
	}
}
