<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const username = ref('admin')
const password = ref('admin')
const errorMessage = ref('')
const isSubmitting = ref(false)
const showPassword = ref(false)

async function handleLogin() {
  if (!username.value.trim() || !password.value) {
    errorMessage.value = '请输入管理员账号和密码。'
    return
  }
  isSubmitting.value = true
  errorMessage.value = ''
  try {
    const ok = await authStore.login(username.value.trim(), password.value)
    if (ok) {
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/conversations/new'
      await router.push(redirect)
      return
    }
    errorMessage.value = '账号或密码不正确，请重新输入。'
  } catch (e) {
    errorMessage.value = `登录失败：${String(e)}`
  } finally {
    isSubmitting.value = false
    password.value = ''
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-brand-panel">
      <div class="brand-lockup">
        <img src="/logo.png" alt="AI数据分析工作台" />
        <div>
          <strong>AI数据分析工作台</strong>
          <span>AI Analysis</span>
        </div>
      </div>

      <div class="brand-message">
        <h1>让数据分析师专注分析，而非报告撰写。</h1>
        <p>从数据梳理到报告成文，AI 陪伴分析师规划、查询与写作，全面提升数据分析效率。</p>
      </div>

      <div class="brand-footer">
        <span>© 2026 中国光大银行 版权所有</span>
        <span>仅供内部使用，请勿外传</span>
      </div>
    </section>

    <section class="login-form-panel">
      <div class="login-form">
        <h2 class="form-title">欢迎回来</h2>
        <p class="form-subtitle">登录以使用 AI数据分析工作台</p>

        <div v-if="errorMessage" class="form-error">
          {{ errorMessage }}
        </div>

        <label class="form-field">
          <span class="form-label">账号</span>
          <input
            v-model="username"
            type="text"
            autocomplete="username"
            placeholder="请输入管理员账号"
            class="form-input"
            @keyup.enter="handleLogin"
          />
        </label>

        <label class="form-field">
          <span class="form-label">密码</span>
          <div class="password-wrap">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              placeholder="请输入密码"
              class="form-input"
              @keyup.enter="handleLogin"
            />
            <button
              type="button"
              class="toggle-password"
              :title="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              <svg v-if="showPassword" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-10-8-10-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
            </button>
          </div>
        </label>

        <button
          type="button"
          class="submit-btn"
          :disabled="isSubmitting"
          @click="handleLogin"
        >
          <span v-if="isSubmitting" class="spinner-small" aria-hidden="true" />
          {{ isSubmitting ? '登录中…' : '登录' }}
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.login-page {
  display: grid;
  min-height: 100vh;
  grid-template-columns: minmax(420px, 1.1fr) minmax(420px, 0.9fr);
  background: #f4f7f8;
}

.login-brand-panel {
  display: flex;
  min-height: 100vh;
  flex-direction: column;
  justify-content: space-between;
  padding: 42px 52px 34px;
  background: #efeaf7;
  color: #102a43;
}

.brand-lockup { display: flex; align-items: center; gap: 14px; }
.brand-lockup img { width: 156px; height: 40px; object-fit: contain; mix-blend-mode: multiply; }
.brand-lockup div { display: flex; flex-direction: column; gap: 3px; }
.brand-lockup strong { color: #3a2a55; font-size: 17px; }
.brand-lockup span { color: #6f6285; font-size: 11px; }

.brand-message { max-width: 580px; padding: 80px 0; }
.brand-message h1 { max-width: 530px; margin: 13px 0 16px; color: #102a43; font-size: 44px; line-height: 1.18; letter-spacing: 0; }
.brand-message p { max-width: 470px; margin: 0; color: #5f4d77; font-size: 14px; line-height: 1.7; }

.login-form-panel { display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 40px; }
.login-form { width: min(440px, 100%); padding: 40px 38px; border: 1px solid #d9e2ec; border-radius: 8px; background: #fff; box-shadow: 0 12px 34px rgba(16, 42, 67, 0.08); }
.form-title { margin: 8px 0 7px; color: #102a43; font-size: 25px; letter-spacing: 0; }
.form-subtitle { margin: 0; color: #829ab1; font-size: 12px; }
.form-field { display: flex; flex-direction: column; gap: 7px; margin-top: 15px; }
.form-label { color: #486581; font-size: 12px; font-weight: 700; }
.form-input { width: 100%; height: 43px; padding: 0 12px; border: 1px solid #bcccdc; border-radius: 6px; outline: none; color: #243b53; font: inherit; font-size: 13px; transition: border-color 0.15s ease, box-shadow 0.15s ease; box-sizing: border-box; }
.form-input:focus { border-color: #6f329b; box-shadow: 0 0 0 3px rgba(111, 50, 155, 0.11); }
.form-input::placeholder { color: #9fb3c8; }
.password-wrap { position: relative; }
.password-wrap .form-input { padding-right: 52px; }
.toggle-password { position: absolute; top: 0; right: 0; height: 43px; padding: 0 14px 0 8px; border: 0; background: transparent; color: #7b3fb2; display: flex; align-items: center; cursor: pointer; }
.form-error { margin-top: 14px; padding: 9px 10px; border-left: 3px solid #d64545; background: #fff5f3; color: #9b2c2c; font-size: 11px; line-height: 1.45; }
.submit-btn { display: flex; width: 100%; height: 43px; align-items: center; justify-content: center; gap: 8px; margin-top: 20px; border: 0; border-radius: 6px; background: linear-gradient(180deg, #7b3fb2, #63308f); color: #fff; font: inherit; font-size: 13px; font-weight: 800; cursor: pointer; }
.submit-btn:hover:not(:disabled) { background: linear-gradient(180deg, #6f329b, #5a2d85); }
.submit-btn:disabled { cursor: not-allowed; opacity: 0.6; }
.spinner-small { width: 14px; height: 14px; border: 2px solid rgba(255, 255, 255, 0.4); border-top-color: #fff; border-radius: 50%; animation: spin 0.75s linear infinite; }

.brand-footer { display: flex; align-items: center; justify-content: space-between; padding-top: 18px; border-top: 1px solid rgba(111, 50, 155, 0.12); color: #6f6285; font-size: 11px; line-height: 1.4; }
.brand-footer span + span { text-align: right; }

@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 840px) {
  .login-page { grid-template-columns: 1fr; }
  .login-brand-panel { min-height: 250px; padding: 28px; }
  .brand-message { padding: 44px 0 20px; }
  .brand-message h1 { font-size: 30px; }
  .brand-footer { display: none; }
  .login-form-panel { min-height: auto; padding: 28px 18px 42px; }
  .login-form { padding: 28px 24px; }
}
</style>
