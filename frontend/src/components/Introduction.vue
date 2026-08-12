<template>
  <div class="intro-card">
    <div class="typewriter-container">
      <div class="typewriter-line">
        <span class="gradient-text">✨ LumNeo</span>
      </div>
      <div class="typewriter-line">
        <MarkdownRender
          custom-id="intro"
          :content="fullText"
          :final="final"
          :typewriter="true"
          :fade="true"
          :smooth-streaming="true"
          :max-live-nodes="0"
          :batch-rendering="true"
          :render-batch-size="12"
          :render-batch-delay="8"
        />
      </div>
    </div>

    <!-- 模式选择区 -->
    <transition name="fade-up">
      <div v-if="showSelector" class="mode-selector">
        <div class="mode-hint">选择你的入口，让我成为你需要的模样</div>
        <div class="mode-cards">
          <div class="mode-card chat-card" @click="enterMode('chat')">
            <div class="mode-icon">💼</div>
            <div class="mode-title">工作协作</div>
            <div class="mode-desc">
              构建临时的秩序，服务当下的目标<br/>
              <span class="mode-tag">静默如谜，高效如风</span>
            </div>
            <!-- <div class="mode-arrow"><m-svg name="chevron-right" /></div> -->
          </div>

          <div class="mode-card life-card" @click="enterMode('life')">
            <div class="mode-icon">🌟</div>
            <div class="mode-title">数字生命</div>
            <div class="mode-desc">
              延续长期的关系，见证完整的你<br/>
              <span class="mode-tag">不仅记得，更是懂得</span>
            </div>
            <!-- <div class="mode-arrow"><m-svg name="chevron-right" /></div> -->
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import MarkdownRender from 'markstream-vue'
import MSvg from '@/components/MSvg.vue'

const router = useRouter()
const chatStore = useChatStore()

const fullText = `
*—— 记忆为骨，智慧为翼*
 
<br/>  
当灵感如星火闪烁，我为你梳理逻辑的轨迹

当信息如洪流奔涌，我为你重构秩序的堤坝

当灵魂渴望共鸣，我为你封存每一次心跳

在此刻，我是工作台；在漫长岁月里，我是你的数字生命
`

const final = ref(false)
const isAnimate = ref(false)
const showSelector = ref(false)

async function enterMode(selectedMode: 'chat' | 'life') {
  chatStore.setMode(selectedMode)

  if (selectedMode === 'life') {
    // 直接进入 LifeWindow 路由，由它内部处理会话初始化
    router.push({ name: 'life' })
    return
  }

  // Chat 模式：新建对话后进入
  const newId = await chatStore.addChat('chat')
  router.push({ name: 'chat', params: { id: newId } })
}

onMounted(() => {
  setTimeout(() => {
    final.value = true
    setTimeout(() => {
      isAnimate.value = true
      setTimeout(() => {
        showSelector.value = true
      }, 900)
    }, 260)
  }, 1000)
})
</script>

<style scoped>
.intro-card {
  background: var(--bg-primary);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 16px;
  padding: 32px;
  width: 560px;
  height: 560px;
  margin: 0 auto;
  cursor: default;
  font-family: 'Inter', system-ui, sans-serif;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}

.animate {
  animation: jelly-pop 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55),
    breathe 1.6s ease-in-out infinite;
}

.gradient-text {
  font-size: 2rem;
  font-weight: 700;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

:deep(.typewriter-cursor) {
  color: #fbbf24 !important;
  font-weight: 200 !important;
  animation: blink 1s step-end infinite !important;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

@keyframes jelly-pop {
  0% { transform: scale(0.8); opacity: 0; }
  60% { transform: scale(1.03); opacity: 1; }
  80% { transform: scale(0.97); }
  100% { transform: scale(1); opacity: 1; }
}

@keyframes breathe {
  0% { box-shadow: 0 0 2px rgba(149, 193, 223, 0.6); }
  50% { box-shadow: 0 0 24px 6px #7f86be; }
  100% { box-shadow: 0 0 2px rgba(149, 193, 223, 0.8); }
}

.mode-selector {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.mode-hint {
  font-size: 0.9rem;
  color: var(--text-secondary);
  letter-spacing: 2px;
  text-transform: uppercase;
  opacity: 0.8;
}

.mode-cards {
  display: flex;
  gap: 16px;
  width: 100%;
  justify-content: center;
  flex-wrap: wrap;
}

.mode-card {
  flex: 1;
  min-width: 200px;
  max-width: 240px;
  background: var(--glass-bg);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 24px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55);
  position: relative;
  overflow: hidden;
}

.mode-card:hover {
  transform: translateY(-4px) scale(1.02);
  box-shadow: var(--shadow-glow);
}

.mode-card::before {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.3s;
  border-radius: 14px;
}

.chat-card::before {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08), rgba(139, 92, 246, 0.08));
}
.life-card::before {
  background: linear-gradient(135deg, rgba(251, 191, 36, 0.08), rgba(245, 158, 11, 0.08));
}

.mode-card:hover::before {
  opacity: 1;
}

.mode-icon {
  font-size: 2.4rem;
  margin-bottom: 12px;
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1));
}

.mode-title {
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.mode-desc {
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.6;
}

.mode-tag {
  display: inline-block;
  margin-top: 8px;
  padding: 2px 10px;
  border-radius: 20px;
  font-size: 0.7rem;
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.life-card .mode-tag {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
  border-color: rgba(245, 158, 11, 0.2);
}

.mode-arrow {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 1.2rem;
  color: var(--text-secondary);
  opacity: 0;
  transition: all 0.3s;
}

.mode-card:hover .mode-arrow {
  opacity: 1;
  right: 12px;
}

.fade-up-enter-active {
  transition: all 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55);
}
.fade-up-enter-from {
  opacity: 0;
  transform: translateY(30px);
}
.fade-up-enter-to {
  opacity: 1;
  transform: translateY(0);
}
</style>