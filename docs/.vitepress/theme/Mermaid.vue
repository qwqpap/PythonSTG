<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import mermaid from 'mermaid'

const props = defineProps<{
  encoded: string
}>()

const container = ref<HTMLElement | null>(null)
const code = ref('')

mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'strict',
  theme: 'base',
  themeVariables: {
    background: 'transparent',
    primaryColor: '#eef2ff',
    primaryTextColor: '#172033',
    primaryBorderColor: '#6b7cff',
    lineColor: '#6b7280',
    secondaryColor: '#e0f2fe',
    tertiaryColor: '#f8fafc',
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif'
  }
})

async function renderDiagram() {
  await nextTick()
  if (!container.value) return

  code.value = decodeURIComponent(
    Array.from(atob(props.encoded))
      .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, '0')}`)
      .join('')
  )

  const id = `mermaid-${Math.random().toString(36).slice(2)}`
  try {
    const { svg } = await mermaid.render(id, code.value)
    container.value.innerHTML = svg
  } catch (error) {
    container.value.textContent = code.value
    console.error('Failed to render Mermaid diagram', error)
  }
}

onMounted(renderDiagram)
watch(() => props.encoded, renderDiagram)
</script>

<template>
  <figure class="vp-mermaid">
    <div ref="container" />
  </figure>
</template>
