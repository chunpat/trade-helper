<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2>登录</h2>
      <el-form :model="form" @submit.prevent="doLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名"/>
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码"/>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="doLogin">登录</el-button>
          <el-button @click="doRegister">注册并登录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script>
export default {
  name: 'Login',
  data() {
    return {
      form: { username: '', password: '' }
    }
  },
  methods: {
    async doLogin() {
      try {
        await this.$store.dispatch('login', this.form)
        this.$message.success('登录成功')
        this.$router.push({ name: 'Positions' })
      } catch (e) {
        this.$message.error('登录失败')
        console.error(e)
      }
    },
    async doRegister() {
      try {
        await this.$store.dispatch('register', this.form)
        this.$message.success('注册并登录成功')
        this.$router.push({ name: 'Positions' })
      } catch (e) {
        this.$message.error('注册失败')
        console.error(e)
      }
    }
  }
}
</script>

<style scoped>
.login-page { padding: 20px; display:flex; justify-content:center; align-items:center }
.login-card { width: 420px; padding: 20px }
</style>
