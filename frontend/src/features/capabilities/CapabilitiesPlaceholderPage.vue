<script setup lang="ts">
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h2 class="page-title">能力目录</h2>
        <p class="page-desc">浏览平台已注册的分析工具、数据读取能力与章节写作 Agent 的分类目录</p>
      </div>
    </header>

    <section class="card empty-state">
      <div class="state-illus" aria-hidden="true">能力目录</div>
      <h3 class="state-title">功能待上线</h3>
      <p class="state-desc">
        工具目录 / Agent 注册表接口待后端抵达。
      </p>
      <p class="state-sub">
        目前可通过「分析」页面执行 Profile 和只读 SQL 查询；通过「报告生成」页面触发报告生成流程。
      </p>
    </section>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 18px; }

.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
.page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--color-text-dark); }
.page-desc { font-size: 13px; color: var(--color-text-medium); margin: 0; }

.card { background: #fff; border: 1px solid var(--color-border, #eae7f0); border-radius: 14px; padding: 18px 20px; }

.empty-state {
  padding: 56px 40px 52px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.state-illus {
  width: 88px;
  height: 88px;
  border-radius: 18px;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 700;
  font-size: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 1px;
}

.state-title {
  margin: 6px 0 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-dark);
}

.state-desc {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-medium);
  max-width: 50ch;
  line-height: 1.65;
}

.state-sub {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--color-text-light);
  max-width: 55ch;
  line-height: 1.6;
}
</style>
