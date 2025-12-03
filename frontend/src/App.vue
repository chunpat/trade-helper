<template>
  <el-container class="app-container">
    <el-aside width="200px">
      <el-menu
        :router="true"
        :default-active="$route.path"
        class="app-menu"
        background-color="#304156"
        text-color="#fff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon>
          <span>风控仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/accounts">
          <el-icon><Wallet /></el-icon>
          <span>账户管理</span>
        </el-menu-item>
        <el-menu-item index="/positions">
          <el-icon><TrendCharts /></el-icon>
          <span>持仓监控</span>
        </el-menu-item>
        <el-menu-item index="/risk-alerts">
          <el-icon><Warning /></el-icon>
          <span>风险预警</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>风控配置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header height="60px">
        <div class="header-title">数字货币合约交易风控系统</div>
        <div class="header-right">
          <el-dropdown>
            <span class="user-info">
              管理员 <el-icon><CaretBottom /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item>个人设置</el-dropdown-item>
                <el-dropdown-item divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      
      <el-main>
        <router-view></router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script>
import { DataLine, Wallet, TrendCharts, Warning, Setting, CaretBottom } from '@element-plus/icons-vue'

export default {
  name: 'App',
  components: {
    DataLine,
    Wallet,
    TrendCharts,
    Warning,
    Setting,
    CaretBottom
  }
}
</script>

<style lang="scss">
.app-container {
  height: 100vh;
  .app-menu {
    height: 100%;
    border-right: none;
  }
  .el-header {
    background: #fff;
    border-bottom: 1px solid #ddd;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    
    .header-title {
      font-size: 18px;
      font-weight: bold;
      color: #303133;
    }
    
    .header-right {
      .user-info {
        cursor: pointer;
        color: #606266;
        display: flex;
        align-items: center;
        
        .el-icon {
          margin-left: 5px;
        }
      }
    }
  }
  
  .el-aside {
    background-color: #304156;
  }
  
  .el-main {
    background-color: #f0f2f5;
    padding: 20px;
  }
}

// Global styles
body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
</style>
