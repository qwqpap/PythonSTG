import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'PySTG Docs',
  description: 'Python + OpenGL 东方 Project 风格弹幕射击游戏引擎文档',
  base: '/PythonSTG/',
  lang: 'zh-CN',
  cleanUrls: true,
  lastUpdated: true,
  markdown: {
    config(md) {
      const defaultFence = md.renderer.rules.fence

      md.renderer.rules.fence = (tokens, idx, options, env, self) => {
        const token = tokens[idx]
        const info = token.info.trim()

        if (info === 'mermaid') {
          const encoded = Buffer.from(token.content, 'utf-8').toString('base64')
          return `<Mermaid encoded=${JSON.stringify(encoded)} />`
        }

        return defaultFence
          ? defaultFence(tokens, idx, options, env, self)
          : self.renderToken(tokens, idx, options)
      }
    }
  },
  themeConfig: {
    logo: '/logo.png',
    repo: 'qwqpap/PythonSTG',
    search: {
      provider: 'local'
    },
    nav: [
      { text: '首页', link: '/' },
      { text: '快速开始', link: '/getting-started' },
      { text: '弹幕脚本', link: '/STAGE_SCRIPTING_GUIDE' },
      { text: 'GitHub', link: 'https://github.com/qwqpap/PythonSTG' }
    ],
    sidebar: [
      {
        text: '开始',
        items: [
          { text: '首页', link: '/' },
          { text: '快速开始', link: '/getting-started' }
        ]
      },
      {
        text: '内容开发',
        items: [
          { text: '弹幕脚本开发指南', link: '/STAGE_SCRIPTING_GUIDE' },
          { text: '敌人预设系统', link: '/ENEMY_PRESET_SYSTEM' },
          { text: '代码驱动编辑器', link: '/EDITOR_PRODUCT_VISION' },
          { text: '编辑器工具', link: '/EDITOR_TOOLS_GUIDE' },
          { text: '开发工具链', link: '/DEVTOOLS_PHASE1' },
          { text: '编辑器架构边界', link: '/EDITOR_ARCHITECTURE' },
          { text: '编辑器实施 TODO', link: '/EDITOR_IMPLEMENTATION_TODO' }
        ]
      },
      {
        text: '引擎开发',
        items: [
          { text: '架构概览', link: '/architecture' },
          { text: '纹理资产系统', link: '/TEXTURE_ASSET_SYSTEM' }
        ]
      },
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/qwqpap/PythonSTG' }
    ],
    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Copyright © 2026 PySTG contributors'
    },
    outline: {
      label: '本页目录',
      level: [2, 3]
    },
    docFooter: {
      prev: '上一篇',
      next: '下一篇'
    },
    lastUpdated: {
      text: '最后更新'
    }
  }
})
