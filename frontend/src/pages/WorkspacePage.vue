<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { moduleNavItems } from '../app/modules'
import { useAuthStore } from '../stores'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const NOTICE_TEXT = '请勿上传或处理敏感、涉密数据。本平台内容由 AI 生成，仅供参考。'

/* ── 顶栏提示语：跑马灯常滚 ── */

/** 滚动速度，px/s。定速而非定时长，否则文案一改快慢就变了。 */
const NOTICE_SPEED = 45

const noticeRef = ref<HTMLElement | null>(null)
const noticeTextRef = ref<HTMLElement | null>(null)
let noticeObserver: ResizeObserver | null = null

function measureNotice() {
  const box = noticeRef.value
  const text = noticeTextRef.value
  if (!box || !text) return
  // 一个单位 = 一份文本 + 它的尾部间隔，位移正好这么多就能接回原位。
  const unit = text.getBoundingClientRect().width
  if (unit <= 0) return
  box.style.setProperty('--notice-unit', `${unit}px`)
  box.style.setProperty('--notice-duration', `${(unit / NOTICE_SPEED).toFixed(1)}s`)
}

const userInitial = computed(() =>
  (authStore.username || 'A').slice(0, 1).toUpperCase(),
)

/**
 * The top bar is the only thing a contributed tool shares with this app, so the
 * entries after 报告生成 come straight from the module registry: registering a
 * tool puts it in the bar, and the bar needs to know nothing about it.
 */
const navItems = computed(() => [
  { key: 'reports', label: '报告生成', to: { name: 'conversation-new' } },
  ...moduleNavItems(),
])

/** Routes declare which top-bar entry owns them; the path is a last resort. */
const activeNav = computed(() =>
  String(route.meta.nav || route.path.split('/')[1] || ''),
)

onMounted(async () => {
  await nextTick()
  measureNotice()
  // Chinese glyphs land at a different width once the webfont swaps in, which
  // decides whether this line overflows at all.
  void document.fonts?.ready.then(measureNotice)
  noticeObserver = new ResizeObserver(measureNotice)
  if (noticeRef.value) noticeObserver.observe(noticeRef.value)
})

onUnmounted(() => {
  noticeObserver?.disconnect()
  noticeObserver = null
})

async function handleLogout() {
  authStore.logout()
  await router.push('/login')
}
</script>

<template>
  <div class="workspace">
    <!-- 顶栏：严格对齐 ai-report-dev 3 项导航风格 -->
    <header class="top-bar">
      <div class="brand-area">
        <img src="/logo.png" alt="Logo" class="brand-logo" />
        <span class="brand-divider" aria-hidden="true"></span>
        <div class="brand-copy">
          <strong>AI数据分析工作台</strong>
          <span class="brand-copy-en">AI Analysis</span>
        </div>
      </div>

      <nav class="primary-nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.key"
          :to="item.to"
          class="primary-nav-item"
          :class="{ active: activeNav === item.key }"
          >{{ item.label }}</RouterLink
        >
      </nav>

      <div class="top-bar-trail">
        <div ref="noticeRef" class="top-notice" :title="NOTICE_TEXT">
          <div class="top-notice-track">
            <!-- 两份相同文本首尾相接，位移一个单位即可无缝循环 -->
            <span ref="noticeTextRef" class="top-notice-text">{{ NOTICE_TEXT }}</span>
            <span class="top-notice-text" aria-hidden="true">{{ NOTICE_TEXT }}</span>
          </div>
        </div>

        <div class="account-area">
          <span class="avatar" aria-hidden="true">{{ userInitial }}</span>
          <span class="account-name">{{ authStore.username || '未登录' }}</span>
          <button
            class="logout-button"
            type="button"
            @click="handleLogout"
          >退出</button>
        </div>
      </div>
    </header>

    <!-- 顶栏之下由路由决定：报告工作台自带会话侧栏，能力目录下的工具只继承顶栏。 -->
    <RouterView />
  </div>
</template>

<style scoped>
.workspace {
  display: flex;
  height: 100vh;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-bg-app, #f7f5fb);
}
/* ── 顶栏 58px：严格 ai-report-dev 截图 ── */
.top-bar {
  height: 58px;
  flex-shrink: 0;
  background: #fff;
  border-bottom: 1px solid
    var(--color-primary-border, rgba(111, 50, 155, 0.14));
  /* 三栏网格：左右列用 minmax(0, 1fr) 强制等宽，导航才落在顶栏真正的中线上。
     用 flex + justify-content:center 只能在导航自己那段空间里居中，
     而左侧品牌区比右侧账号区宽得多，结果是偏右的。 */
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  padding: 0 24px;
  gap: 24px;
}
/* 右栏：提示语 + 账号区。账号区靠最右，提示语占它左边的剩余空间 */
.top-bar-trail {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 20px;
  min-width: 0;
  /* 空间不够时先吃掉提示语，而不是把账号区顶出格 */
  overflow: hidden;
}
.brand-area {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  /* 品牌区不参与压缩：标题被截断比提示语变窄更糟 */
  flex-shrink: 0;
}
/* 合规提示：跑马灯常滚，顶栏挤不下时由它独自让位 */
.top-notice {
  flex: 1 1 auto;
  min-width: 0;
  max-width: 460px;
  overflow: hidden;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--color-error);
}
.top-notice-track {
  display: flex;
  width: max-content;
  animation: notice-marquee var(--notice-duration, 8s) linear infinite;
}
/* 想看清整句时停一下 */
.top-notice:hover .top-notice-track {
  animation-play-state: paused;
}
.top-notice-text {
  white-space: nowrap;
  /* 间隔算进单位宽度里，位移一个单位才能严丝合缝地接上 */
  padding-right: 48px;
}

@keyframes notice-marquee {
  to { transform: translateX(calc(-1 * var(--notice-unit, 0px))); }
}
/* 先牺牲英文名：中文名是主标识、提示语是合规要求，都比它重要。
   去掉它之后品牌区约 332px，等宽列到 1050px 都还放得下，居中得以保留。 */
@media (max-width: 1200px) {
  .brand-copy-en {
    display: none;
  }
}
/* 再窄就放弃严格居中：等宽列已经容不下品牌区，会把产品名裁掉。
   导航偏移可以接受，产品名被截断不行。 */
@media (max-width: 1050px) {
  .top-bar {
    display: flex;
  }

  .primary-nav {
    flex: 1;
  }
}
/* 关掉动效时不跑马灯，改成可手动横向滚动，并且只留一份文本 */
@media (prefers-reduced-motion: reduce) {
  .top-notice {
    overflow-x: auto;
  }

  .top-notice-track {
    animation: none !important;
    transform: none !important;
  }

  .top-notice-text + .top-notice-text {
    display: none;
  }
}
.brand-logo {
  height: 28px;
  width: auto;
  display: block;
}
.brand-divider {
  width: 1px;
  height: 22px;
  background: var(--color-border, #e9e6ef);
}
.brand-copy {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  font-size: 18px;
  color: var(--color-text-dark, #102a43);
  letter-spacing: 0.3px;
}
.brand-copy strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.brand-copy-en {
  flex-shrink: 0;
  white-space: nowrap;
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-light, #9ca3af);
  letter-spacing: 0.4px;
}
/* 网格中间列，宽度由内容决定 —— 居中交给 minmax(0,1fr) 的左右列 */
.primary-nav {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.primary-nav-item {
  display: inline-flex;
  align-items: center;
  height: 36px;
  padding: 0 18px;
  /* 没有 nowrap 时中文的 min-content 宽是一个字，顶栏一挤导航就会被压成竖排 */
  white-space: nowrap;
  flex-shrink: 0;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-medium, #486581);
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease;
  cursor: pointer;
  font-family: inherit;
}
.primary-nav-item:hover {
  background: var(--color-primary-light);
  color: var(--color-primary);
}
.primary-nav-item.active {
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 600;
}
.account-area {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.account-area .avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary-light);
  color: var(--color-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
}
.account-name {
  font-size: 13px;
  color: var(--color-text-medium);
  font-weight: 500;
}
.logout-button {
  border: 1px solid var(--color-border, #e4e1ea);
  background: #fff;
  color: var(--color-text-medium);
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s ease;
}
.logout-button:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
/* ── 侧边栏 240px 单态会话列表，严格 ai-report-dev ── */
/* ── sb-toggle 半胶囊：top:74px 严格 ai-report-dev ── */
/* ── 主区域 ── */
</style>
