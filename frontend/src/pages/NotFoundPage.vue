<template>
  <div class="not-found">
    <span>404</span>
    <h1>页面不存在</h1>
    <p>当前地址没有对应的工作台页面。</p>
    <RouterLink to="/">返回工作台</RouterLink>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  min-height: 100vh;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  padding: 24px;
  background: #f4f7f8;
  color: #334e68;
  text-align: center;
}

.not-found > span { color: #7b3fb2; font-size: 56px; font-weight: 900; }
h1 { margin: 8px 0 6px; color: #102a43; font-size: 24px; }
p { margin: 0 0 20px; color: #829ab1; font-size: 13px; }
a { padding: 9px 14px; border-radius: 6px; background: linear-gradient(180deg, #7b3fb2, #63308f); color: #fff; font-size: 12px; font-weight: 800; text-decoration: none; }
a:hover { background: linear-gradient(180deg, #6f329b, #5a2d85); text-decoration: none; }
</style>
