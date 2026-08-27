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
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/datasets'
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
        <img src="/logo.png" alt="AI Report" />
        <div>
          <strong>AI Report</strong>
          <span>智能报告工作台</span>
        </div>
      </div>

      <div class="brand-message">
        <h1>让每一份报告，都能看见数据与过程。</h1>
        <p>任务计划、执行进度、章节结果和数据来源统一呈现。</p>
      </div>

      <div class="brand-footer">
        <span>© 2026 中国光大银行 版权所有</span>
        <span>仅供内部使用，请勿外传</span>
      </div>
    </section>

    <section class="login-form-panel">
      <div class="login-form">
        <h2 class="form-title">欢迎回来</h2>
        <p class="form-subtitle">登录以使用智能报告工作台</p>

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
              {{ showPassword ? '隐藏' : '显示' }}
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

        <p class="form-tip">
          <strong>说明：</strong>当前为开发环境假登录模式，输入任意账号密码即可。正式认证接口由后端后续提供。
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  overflow: hidden;
  background: #fff;
}

.login-brand-panel {
  width: 52%;
  background: #efeaf7;
  padding: 48px 64px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  position: relative;
  overflow: hidden;
}

.login-brand-panel::before {
  content: '';
  position: absolute;
  inset: -20% -10% auto auto;
  width: 480px;
  height: 480px;
  background: radial-gradient(closest-side, rgba(123, 63, 178, 0.18), transparent 70%);
  border-radius: 50%;
  pointer-events: none;
}

.login-brand-panel::after {
  content: '';
  position: absolute;
  inset: auto auto -25% -10%;
  width: 520px;
  height: 520px;
  background: radial-gradient(closest-side, rgba(123, 63, 178, 0.12), transparent 70%);
  border-radius: 50%;
  pointer-events: none;
}

.brand-lockup {
  display: flex;
  align-items: center;
  gap: 14px;
  position: relative;
  z-index: 1;
}

.brand-lockup img {
  height: 40px;
  width: auto;
}

.brand-lockup > div {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  gap: 2px;
}

.brand-lockup strong {
  font-size: 18px;
  font-weight: 700;
  color: #4b2f6a;
  letter-spacing: 0.3px;
}

.brand-lockup span {
  font-size: 13px;
  color: #6a4f8a;
  opacity: 0.9;
}

.brand-message {
  max-width: 480px;
  position: relative;
  z-index: 1;
}

.brand-message h1 {
  font-size: 34px;
  font-weight: 700;
  line-height: 1.3;
  color: #3a2452;
  margin: 0 0 18px;
  letter-spacing: 0.4px;
}

.brand-message p {
  font-size: 15.5px;
  line-height: 1.7;
  color: #5d4978;
  margin: 0;
  opacity: 0.92;
}

.brand-footer {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #7a6596;
  position: relative;
  z-index: 1;
}

.login-form-panel {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 32px;
  background: #fff;
}

.login-form {
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.form-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text-dark, #1a2a43);
  margin: 0 0 2px;
  letter-spacing: 0.3px;
}

.form-subtitle {
  font-size: 14px;
  color: var(--color-text-medium, #5a6376);
  margin: 0;
}

.form-error {
  padding: 10px 14px;
  border-radius: 10px;
  background: #fde8e8;
  color: #b91c1c;
  font-size: 13px;
  line-height: 1.5;
  border: 1px solid #f5c2c2;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-dark);
}

.form-input {
  padding: 11px 14px;
  border: 1px solid var(--color-primary-border, rgba(111, 50, 155, 0.14));
  border-radius: 10px;
  font-size: 14px;
  font-family: inherit;
  color: var(--color-text-dark);
  background: #fff;
  transition: border-color 0.15s, box-shadow 0.15s;
  outline: none;
}

.form-input::placeholder {
  color: var(--color-text-light, #9ca3af);
}

.form-input:focus {
  border-color: var(--color-primary, #7b3fb2);
  box-shadow: 0 0 0 3px rgba(123, 63, 178, 0.12);
}

.password-wrap {
  position: relative;
}

.password-wrap .form-input {
  width: 100%;
  padding-right: 44px;
}

.toggle-password {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  border: 0;
  background: transparent;
  font-size: 16px;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.toggle-password:hover {
  background: var(--color-primary-light, rgba(111, 50, 155, 0.08));
}

.submit-btn {
  margin-top: 4px;
  padding: 12px 18px;
  border: 0;
  border-radius: 10px;
  background: var(--gradient-primary, linear-gradient(180deg, #7b3fb2, #63308f));
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  box-shadow: 0 3px 8px rgba(123, 63, 178, 0.22);
  transition: transform 0.12s, box-shadow 0.18s, opacity 0.15s;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 12px rgba(123, 63, 178, 0.26);
}

.submit-btn:active:not(:disabled) {
  transform: translateY(0);
}

.submit-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  box-shadow: none;
}

.spinner-small {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.34);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.form-tip {
  margin: 4px 0 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f6f3fb;
  color: #5d4978;
  font-size: 12px;
  line-height: 1.55;
  border: 1px dashed var(--color-primary-border, rgba(111, 50, 155, 0.2));
}

.form-tip strong {
  color: #3a2452;
  font-weight: 600;
}

@media (max-width: 1024px) {
  .login-page { flex-direction: column; }
  .login-brand-panel {
    width: 100%;
    min-height: 260px;
    padding: 32px 28px;
    gap: 24px;
  }
  .login-form-panel { padding: 40px 24px 56px; }
  .brand-message h1 { font-size: 26px; }
}
</style>
