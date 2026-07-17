<template>
  <div class="profile-panel-container">
    <n-card :bordered="false" size="small" class="panel-card">
      
      <!-- 标题区域 -->
      <div class="panel-header">
        <div class="panel-title">
            <n-flex>
            <n-avatar class="avatar" round :size="40" :src="`/images/avatars/${profile.avatar}`"/>
            {{ profile.name }} 
            <!-- <span class="panel-subtitle">角色</span> -->
            </n-flex>
        </div>
        <div class="time-badge">
          <span class="time-ampm">{{ ampm }}</span>
          <span class="time-clock">{{ currentTime }}</span>
        </div>
      </div>

      <!-- 中间区域：场景 + 属性 -->
      <div class="panel-body">
        <div class="scenes-box">
          <div class="scenes-wrapper">
            <n-image
              src="/images/scenes/s_01.jpg"
              width="100%"
              height="100%"
              object-fit="cover"
            />
          </div>
        </div>

        <div class="stats-box">
          <div class="stat-row">
            <span class="stat-label">TEMPERATURE</span>
            <div class="stat-bar-bg">
              <div class="stat-bar-fill cyan" :style="{ width: getStatPercent(profile.temperature, 2) }"></div>
            </div>
            <span class="stat-value">{{ profile.temperature }}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">TOP-P</span>
            <div class="stat-bar-bg">
              <div class="stat-bar-fill green" :style="{ width: getStatPercent(profile.top_p, 1) }"></div>
            </div>
            <span class="stat-value">{{ profile.top_p }}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">TOP-K</span>
            <div class="stat-bar-bg">
              <div class="stat-bar-fill purple" :style="{ width: getStatPercent(profile.top_k, 100) }"></div>
            </div>
            <span class="stat-value">{{ profile.top_k }}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">FREQUENCY</span>
            <div class="stat-bar-bg">
              <div class="stat-bar-fill yellow" :style="{ width: getStatPercent(profile.frequency_penalty, 2) }"></div>
            </div>
            <span class="stat-value">{{ profile.frequency_penalty }}</span>
          </div>
        </div>
      </div>

      <!-- 天赋 -->
      <div class="talent-section">
        <div class="section-title" style="color:#34d399">| 天赋 Talent</div>
        <n-space>
          <n-tag v-for="name in profile.tools" :bordered="false" type="info">
            {{ toolStore.toolsInfo[name]?.title ?? name }}
          </n-tag>
        </n-space>
      </div>

      <!-- 技能 -->
      <div class="skills-section">
        <div class="section-title">| 技能 Skills</div>
        <n-space>
          <n-tag v-for="skillId in profile.skills" :key="skillId" :bordered="false" type="warning">
            {{ getSkillNameById(skillId) }}
          </n-tag>
        </n-space>
      </div>

      <!-- 描述 -->
      <div class="lore-section">
        <span class="lore-title">[ 描述 ]</span>
        <span class="lore-text">{{ profile.profile_prompt }}</span>
      </div>

    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { NImage, NCard, NAvatar, NFlex, NTag, NSpace } from 'naive-ui'
import { useToolStore } from '@/stores/tools'

interface SkillItem {
  id: string
  name: string
  isGlobal: boolean
  description?: string
}

const props = defineProps<{
  profileData?: any
}>()

const defaultProfile = ref({
  sceneImage: '',
  skills: [],
})

const profile = computed(() => {
  return { ...defaultProfile.value, ...props.profileData }
})

const toolStore = useToolStore()

// 工具函数：属性条百分比
const getStatPercent = (current: number, max: number) => {
  return Math.min((current / max) * 100, 100) + '%'
}

// ---------- 动态时间 ----------
const now = ref(new Date())
let timer: ReturnType<typeof setInterval> | null = null

const ampm = computed(() => now.value.getHours() >= 12 ? 'PM' : 'AM')
const currentTime = computed(() => {
  const h = now.value.getHours()
  const m = now.value.getMinutes()
  const displayHour = h % 12 === 0 ? 12 : h % 12
  return `${String(displayHour).padStart(2, '0')}:${String(m).padStart(2, '0')}`
})

onMounted(() => {
  timer = setInterval(() => {
    now.value = new Date()
  }, 1000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
// --------------------------

// 技能相关
const allSkills = ref<SkillItem[]>([])

async function loadAllSkills() {
  try {
    const url = props.profileData.id
      ? `/api/skills/list?profile_id=${props.profileData.id}`
      : '/api/skills/list'
    const res = await fetch(url)
    const data = await res.json()
    allSkills.value = (data || []).map((item: any) => ({
      id: item.id,
      name: item.name || item.id,
      isGlobal: !!item.is_global,
      description: item.description,
    }))
  } catch (e) {
    // ignore
  }
}

function getSkillNameById(id: string): string {
  const skill = allSkills.value.find(s => s.id === id)
  return skill?.name ?? '未知技能'
}

onMounted(async () => {
  await loadAllSkills()
  const res = await fetch(`/api/profiles/${props.profileData.id}/skills`)
  const data = await res.json()
  defaultProfile.value.skills = data || []
})
</script>

<style scoped>
/* ---- 容器 ---- */
.profile-panel-container {
  width: 100%;
  max-width: 650px;
  background: #0a0f1d;
  border: 1px solid #1e3a5f;
  border-radius: 6px;
  box-shadow: 0 0 20px rgba(0, 150, 255, 0.05);
  font-family: system-ui, -apple-system, sans-serif;
}

.panel-card {
  background: transparent !important;
  padding: 0 !important;
  color: #bdd3ff;
}

/* ---- 头部 ---- */
.panel-header {
  position: relative;
  padding: 16px 20px 8px;
  border-bottom: 1px solid #1e3a5f;
}

.panel-title {
  font-family: '微软雅黑', serif;
  font-size: 26px;
  font-weight: bold;
  color: #fff;
  letter-spacing: 1px;
  text-shadow: 0 0 10px rgba(0, 200, 255, 0.3);
}
.avatar {box-shadow: 0 0 2px rgba(128,128,128,.3);border:2px solid #fff;}
.panel-subtitle {
  font-size: 14px;
  color: #00e5ff;
  letter-spacing: 2px;
  margin-top: 18px;
  font-weight: 600;
}

.time-badge {
  position: absolute;
  right: 20px;
  top: 16px;
  background: #7c3aed;
  padding: 2px 12px;
  border-radius: 4px;
  display: flex;
  align-items: baseline;
  gap: 4px;
  color: #fff;
}

.time-ampm {
  font-size: 12px;
  font-weight: bold;
}

.time-clock {
  font-size: 20px;
  font-weight: bold;
}

/* ---- 中间区域 ---- */
.panel-body {
  display: flex;
  padding: 16px 20px;
  gap: 16px;
}

.scenes-box {
  flex: 0 0 35%;
  border: 1px solid #1e3a5f;
  border-radius: 4px;
  height: 180px;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #0d1424;
}

.scenes-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.stats-box {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-around;
}

.stat-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.stat-label {
  font-size: 11px;
  font-weight: bold;
  color: #8899bb;
  width: 100px;
  text-align: right;
}

.stat-bar-bg {
  flex: 1;
  height: 4px;
  background: #1a2940;
  border-radius: 2px;
}

.stat-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s;
}

.stat-bar-fill.cyan {
  background: #00e5ff;
  box-shadow: 0 0 8px #00e5ff88;
}
.stat-bar-fill.green {
  background: #34d399;
  box-shadow: 0 0 8px #34d39988;
}
.stat-bar-fill.purple {
  background: #a78bfa;
  box-shadow: 0 0 8px #a78bfa88;
}
.stat-bar-fill.yellow {
  background: #fbbf24;
  box-shadow: 0 0 8px #fbbf2488;
}

.stat-value {
  font-size: 14px;
  font-weight: bold;
  color: #fff;
  width: 40px;
  text-align: right;
}

/* ---- 天赋 ---- */
.talent-section {
  padding: 12px 20px;
  border-top: 1px solid #1e3a5f;
  border-bottom: 1px solid #1e3a5f;
  background: #0b1324;
}

/* ---- 技能 ---- */
.skills-section {
  padding: 12px 20px;
  border-top: 1px solid #1e3a5f;
}

.section-title {
  color: #c084fc;
  font-weight: bold;
  font-size: 12px;
  margin-bottom: 10px;
  letter-spacing: 2px;
}

/* ---- 描述 ---- */
.lore-section {
  padding: 16px 20px;
  border-top: 1px solid #1e3a5f;
  font-size: 12px;
  line-height: 1.6;
  color: #94a3b8;
}

.lore-title {
  color: #67e8f9;
  font-weight: bold;
  margin-right: 6px;
}

.lore-text {
  font-style: italic;
}

/* ---- 响应式 ---- */
@media (max-width: 600px) {
  .panel-body {
    flex-direction: column;
  }
  .scenes-box {
    flex: none;
    height: 150px;
  }
}
</style>