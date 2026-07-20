<template>
  <div class="polymarket-workspace">
    <el-tabs v-model="activeTab" class="polymarket-tabs">
      <el-tab-pane label="交易员池" name="traders" lazy>
        <PolymarketTraders />
      </el-tab-pane>
      <el-tab-pane label="跟单策略" name="strategies" lazy>
        <PolymarketCopyStrategies />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import PolymarketCopyStrategies from './PolymarketCopyStrategies.vue'
import PolymarketTraders from './PolymarketTraders.vue'

export default {
  name: 'PolymarketWorkspace',
  components: {
    PolymarketCopyStrategies,
    PolymarketTraders
  },
  computed: {
    activeTab: {
      get() {
        return this.$route.query.tab === 'strategies' ? 'strategies' : 'traders'
      },
      set(tab) {
        const nextTab = tab === 'strategies' ? 'strategies' : 'traders'
        if (this.$route.query.tab === nextTab) return

        this.$router.replace({
          name: 'Polymarket',
          query: {
            ...this.$route.query,
            tab: nextTab
          }
        })
      }
    }
  }
}
</script>

<style scoped>
.polymarket-workspace {
  width: 100%;
}

.polymarket-tabs :deep(.el-tabs__header) {
  margin: 0 0 16px;
  padding: 0 24px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}

.polymarket-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background-color: #e2e8f0;
}

.polymarket-tabs :deep(.el-tabs__item) {
  height: 52px;
  padding: 0 24px;
  font-size: 15px;
  font-weight: 600;
}

.polymarket-tabs :deep(.el-tabs__content) {
  overflow: visible;
}

@media (max-width: 640px) {
  .polymarket-tabs :deep(.el-tabs__header) {
    padding: 0 12px;
  }

  .polymarket-tabs :deep(.el-tabs__item) {
    padding: 0 16px;
  }
}
</style>
