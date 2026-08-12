const { createApp, ref, onMounted, onBeforeUnmount, nextTick } = Vue;

async function api(path, options = {}) {
  const res = await fetch('/api' + path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `请求失败(${res.status})`);
  return data;
}

// B 站 CDN 防盗链，统一走后端图片代理
const imgUrl = u => u ? '/api/img?url=' + encodeURIComponent(u) : '';

const Analysis = {
  template: `
    <h2>内容分析</h2>
    <div style="margin-bottom:12px">
      <el-button type="primary" @click="run" :loading="running">分析未分析视频</el-button>
      <el-tag style="margin-left:8px">已分析 {{ status.analyzed }} / {{ status.total }}</el-tag>
    </div>
    <el-card>
      <template #header>观看内容主题分布</template>
      <div data-theme-chart class="chart"></div>
    </el-card>
  `,
  setup() {
    const running = ref(false); const status = ref({ analyzed: 0, total: 0 });
    async function run() {
      running.value = true;
      try {
        const r = await api('/analysis/run?limit=50');
        ElementPlus.ElMessage.success(`分析完成：${r.analyzed} 条`);
        await loadStatus();
        renderChart();
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { running.value = false; }
    }
    async function loadStatus() {
      try { status.value = await api('/analysis/status'); } catch (e) {}
    }
    async function renderChart() {
      const themes = await api('/analysis/themes').catch(() => []);
      nextTick(() => {
        const el = document.querySelector('[data-theme-chart]');
        if (!el) return;
        const chart = echarts.init(el, 'dark');
        chart.setOption({
          title: { text: '主题标签 TOP', textStyle: { fontSize: 14 } },
          tooltip: {},
          xAxis: { type: 'category', data: themes.map(t => t.tag), axisLabel: { rotate: 30 } },
          yAxis: { type: 'value' },
          series: [{ type: 'bar', data: themes.map(t => t.n) }],
        });
      });
    }
    onMounted(() => { loadStatus(); renderChart(); });
    return { running, status, run };
  },
};

const Overview = {
  props: ['status'],
  template: `
    <h2>概览</h2>
    <el-row :gutter="16" class="cards">
      <el-col :span="6" v-for="c in cards" :key="c.label">
        <el-card><div class="card-num">{{ c.value }}</div><div class="card-label">{{ c.label }}</div></el-card>
      </el-col>
    </el-row>
    <el-row :gutter="16" class="charts">
      <el-col :span="12"><el-card><div ref="trendChart" class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card><div ref="upChart" class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card><div ref="hourChart" class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card><div ref="tnameChart" class="chart"></div></el-card></el-col>
    </el-row>
  `,
  computed: {
    cards() {
      const c = this.status.counts || {};
      return [
        { label: '观看历史', value: c.history ?? '-' },
        { label: '收藏视频', value: c.favorites ?? '-' },
        { label: '收藏夹', value: c.folders ?? '-' },
        { label: '关注', value: c.followings ?? '-' },
      ];
    },
  },
  async mounted() {
    const s = await api('/stats/overview').catch(() => null);
    if (s) this.renderCharts(s);
  },
  methods: {
    renderCharts(s) {
      nextTick(() => {
        const specs = {
          trendChart: { type: 'line', title: '近30天观看趋势',
            x: s.trend.map(t => t.day), y: s.trend.map(t => t.n) },
          upChart: { type: 'bar', title: '常看UP主 TOP10',
            x: s.top_ups.map(u => u.up_name), y: s.top_ups.map(u => u.n) },
          hourChart: { type: 'bar', title: '观看时段分布',
            x: s.hours.map(h => h.hour + '时'), y: s.hours.map(h => h.n) },
          tnameChart: { type: 'pie', title: '视频分区分布',
            data: s.tnames.map(t => ({ name: t.tname, value: t.n })) },
        };
        for (const [refName, spec] of Object.entries(specs)) {
          const el = this.$refs[refName];
          if (!el) continue;
          const chart = echarts.init(el, 'dark');
          const axis = spec.type === 'pie'
            ? {}
            : {
                xAxis: { type: 'category', data: spec.x, axisLabel: { rotate: spec.x.length > 8 ? 30 : 0 } },
                yAxis: { type: 'value' },
              };
          chart.setOption({
            title: { text: spec.title, textStyle: { fontSize: 14 } },
            tooltip: { trigger: 'axis' },
            ...axis,
            series: [{ type: spec.type, data: spec.y || spec.data, smooth: true }],
          });
        }
      });
    },
  },
};

const Monitor = {
  props: ['status'],
  emits: ['refresh'],
  template: `
    <h2>监测中心</h2>
    <div style="margin-bottom:12px">
      <el-button type="primary" @click="run" :loading="running">立即检测</el-button>
      <el-tag v-if="result" style="margin-left:8px">失效 {{ result.invalid }} · UP更新 {{ result.updates }}</el-tag>
    </div>
    <el-tabs v-model="tab">
      <el-tab-pane label="提醒" name="alerts">
        <el-table :data="alerts" style="width:100%">
          <el-table-column prop="title" label="标题" min-width="160"/>
          <el-table-column prop="content" label="内容" min-width="260"/>
          <el-table-column label="时间" width="180">
            <template #default="s">{{ fmt(s.row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="s">
              <el-button v-if="!s.row.read" size="small" @click="markRead(s.row.id)">标为已读</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="失效视频" name="invalid">
        <el-table :data="invalidList" style="width:100%">
          <el-table-column prop="bvid" label="BV号" width="180"/>
          <el-table-column prop="source" label="来源" width="100"/>
          <el-table-column label="检测时间" width="180">
            <template #default="s">{{ fmt(s.row.checked_at) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="UP主更新" name="updates">
        <el-table :data="updates" style="width:100%">
          <el-table-column prop="uname" label="UP主" width="160"/>
          <el-table-column prop="last_bvid" label="最新投稿" width="180"/>
          <el-table-column label="发布时间" width="180">
            <template #default="s">{{ fmt(s.row.last_pubdate) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  `,
  emits: ['refresh'],
  setup(props, { emit }) {
    const tab = ref('alerts');
    const alerts = ref([]); const invalidList = ref([]); const updates = ref([]);
    const running = ref(false); const result = ref(null);
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '';
    async function loadAll() {
      const d = await api('/alerts');
      alerts.value = d.items;
      invalidList.value = await api('/monitor/invalid');
      updates.value = await api('/monitor/updates');
    }
    async function run() {
      running.value = true;
      try {
        result.value = await api('/monitor/run', { method: 'POST' });
        await loadAll();
        emit('refresh');
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { running.value = false; }
    }
    async function markRead(id) {
      await api(`/alerts/${id}/read`, { method: 'POST' });
      await loadAll();
      emit('refresh');
    }
    onMounted(() => loadAll().catch(() => {}));
    return { tab, alerts, invalidList, updates, running, result, fmt, run, markRead };
  },
};

const History = {
  template: `
    <h2>观看历史</h2>
    <div style="margin-bottom:16px">
      <el-input v-model="search" placeholder="搜索标题或UP主" clearable style="width:320px"
                @keyup.enter="doSearch"/>
      <el-button type="primary" @click="doSearch">搜索</el-button>
    </div>
    <div class="bili-grid">
      <div class="bili-card" v-for="it in items" :key="it.bvid" @click="open(it)">
        <div class="bili-cover">
          <img :src="imgUrl(it.pic)" loading="lazy" :alt="it.title"/>
          <span class="bili-duration">{{ fmtDur(it.duration) }}</span>
        </div>
        <div class="bili-title">{{ it.title }}</div>
        <div class="bili-meta">
          <span class="bili-up">{{ it.up_name }} · {{ timeAgo(it.view_at) }}</span>
          <span class="bili-stats">{{ fmtNum(it.view_count) }} 播放</span>
        </div>
      </div>
    </div>
    <div ref="sentinel" style="height:20px"></div>
    <div v-if="loading" style="text-align:center;color:#999;padding:12px">加载中...</div>
    <div v-else-if="!hasMore && items.length" style="text-align:center;color:#666;padding:12px">已经到底啦，共 {{ items.length }} 条</div>
  `,
  setup() {
    const search = ref(''); const items = ref([]);
    const page = ref(1); const pageSize = 24;
    const loading = ref(false); const hasMore = ref(true);
    let observer = null;
    async function fetchPage() {
      if (loading.value) return;
      loading.value = true;
      try {
        const d = await api(`/history?search=${encodeURIComponent(search.value)}&page=${page.value}&page_size=${pageSize}`);
        items.value.push(...d.items);
        hasMore.value = items.value.length < d.total;
        if (hasMore.value) page.value += 1;
      } finally { loading.value = false; }
    }
    async function reset() {
      items.value = []; page.value = 1; hasMore.value = true;
      await fetchPage();
    }
    function doSearch() { reset(); }
    function onScroll() {
      const scroller = document.querySelector('.el-main');
      if (!scroller) return;
      if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 400
          && !loading.value && hasMore.value) fetchPage();
    }
    function onSentinel(el) {
      if (observer) observer.disconnect();
      observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !loading.value && hasMore.value) fetchPage();
      }, { rootMargin: '300px' });
      if (el) observer.observe(el);
    }
    function open(it) { window.open(`https://www.bilibili.com/video/${it.bvid}`, '_blank'); }
    function fmtNum(n) {
      n = n || 0;
      return n >= 10000 ? (n / 10000).toFixed(1).replace(/\.0$/, '') + '万' : String(n);
    }
    function fmtDur(s) {
      s = s || 0;
      const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
      const mm = String(m).padStart(2, '0'), ss = String(sec).padStart(2, '0');
      return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
    }
    function timeAgo(ts) {
      if (!ts) return '';
      const diff = (Date.now() / 1000 - ts);
      if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
      if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
      if (diff < 604800) return Math.floor(diff / 86400) + '天前';
      return new Date(ts * 1000).toLocaleDateString('zh-CN');
    }
    onMounted(() => {
      reset();
      const scroller = document.querySelector('.el-main');
      if (scroller) scroller.addEventListener('scroll', onScroll);
    });
    onBeforeUnmount(() => {
      const scroller = document.querySelector('.el-main');
      if (scroller) scroller.removeEventListener('scroll', onScroll);
      if (observer) observer.disconnect();
    });
    return { search, items, loading, hasMore, onSentinel, doSearch, open, imgUrl, fmtNum, fmtDur, timeAgo };
  },
};

const Favorites = {
  template: `
    <h2>收藏夹</h2>
    <div class="fav-layout">
      <div class="fav-side">
        <div v-for="f in folders" :key="f.media_id" class="fav-side-item"
             :class="{ active: activeId === f.media_id }" @click="select(f)">
          <span class="fav-side-name">{{ f.name }}</span>
          <span class="fav-side-count">{{ f.count }}</span>
        </div>
      </div>
      <div class="fav-main" v-loading="loading">
        <div class="bili-grid">
          <div class="bili-card" v-for="it in items" :key="it.bvid" @click="play(it)">
            <div class="bili-cover">
              <img v-if="it.title" :src="imgUrl(it.pic)" loading="lazy" :alt="it.title"/>
              <el-tag v-else type="danger" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%)">已失效</el-tag>
              <span v-if="it.title" class="bili-duration">{{ fmtDur(it.duration) }}</span>
            </div>
            <div class="bili-title">{{ it.title || '已失效视频' }}</div>
            <div class="bili-meta">
              <span class="bili-up">{{ it.up_name }}</span>
              <span class="bili-stats">{{ fmtNum(it.view_count) }} 播放</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  setup() {
    const folders = ref([]); const items = ref([]);
    const activeId = ref(null); const loading = ref(false);
    async function loadFolders() {
      folders.value = await api('/favorites');
      if (folders.value.length && activeId.value == null) {
        select(folders.value[0]);
      }
    }
    async function select(f) {
      activeId.value = f.media_id; loading.value = true;
      try {
        const d = await api(`/favorites/${f.media_id}?page_size=200`);
        items.value = d.items;
      } finally { loading.value = false; }
    }
    function play(it) {
      if (it.title) window.open(`https://www.bilibili.com/video/${it.bvid}`, '_blank');
    }
    function fmtNum(n) {
      n = n || 0;
      return n >= 10000 ? (n / 10000).toFixed(1).replace(/\.0$/, '') + '万' : String(n);
    }
    function fmtDur(s) {
      s = s || 0;
      const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
      const mm = String(m).padStart(2, '0'), ss = String(sec).padStart(2, '0');
      return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
    }
    onMounted(loadFolders);
    return { folders, items, activeId, loading, select, play, imgUrl, fmtNum, fmtDur };
  },
};

const Settings = {
  props: ['status'],
  emits: ['refresh'],
  template: `
    <h2>设置</h2>
    <el-card style="max-width:520px">
      <template #header>账号</template>
      <div v-if="status.logged_in">
        <p>已登录 <el-tag type="success">UID {{ status.uid || '-' }}</el-tag></p>
        <p v-if="status.login_at" style="margin-top:8px">登录时间：{{ fmt(status.login_at) }}</p>
        <template v-if="account.stats">
          <el-divider/>
          <el-descriptions :column="2" size="small">
            <el-descriptions-item label="硬币">{{ account.stats.coins }}</el-descriptions-item>
            <el-descriptions-item label="等级">Lv.{{ account.stats.level }}</el-descriptions-item>
            <el-descriptions-item label="关注">{{ account.stats.following }}</el-descriptions-item>
            <el-descriptions-item label="粉丝">{{ account.stats.follower }}</el-descriptions-item>
            <el-descriptions-item label="追番">{{ account.stats.bangumi }}</el-descriptions-item>
            <el-descriptions-item label="追剧">{{ account.stats.drama }}</el-descriptions-item>
          </el-descriptions>
          <el-divider/>
          <div style="font-size:13px;color:#999;margin-bottom:8px">硬币明细（{{ account.coin_log.length }} 条）</div>
          <el-table :data="account.coin_log" size="small" max-height="240" style="width:100%">
            <el-table-column prop="time" label="时间" width="150"/>
            <el-table-column prop="delta" label="变动" width="70"/>
            <el-table-column prop="reason" label="原因" min-width="220"/>
          </el-table>
        </template>
      </div>
      <p v-else>尚未登录，点击下方按钮扫码登录 B 站账号。</p>
      <div style="margin-top:16px">
        <el-button type="primary" @click="openQr">扫码登录</el-button>
        <el-button type="success" :disabled="!status.logged_in" @click="sync" :loading="syncing">
          立即同步数据
        </el-button>
      </div>
    </el-card>
    <el-card style="max-width:520px;margin-top:16px">
      <template #header>邮件通知（SMTP）</template>
      <el-form :model="smtp" label-width="80px" label-position="left">
        <el-form-item label="SMTP 主机"><el-input v-model="smtp.host" placeholder="smtp.qq.com"/></el-form-item>
        <el-form-item label="端口"><el-input v-model.number="smtp.port" placeholder="465"/></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="smtp.user" placeholder="发件邮箱"/></el-form-item>
        <el-form-item label="授权码"><el-input v-model="smtp.password" type="password" placeholder="SMTP 授权码"/></el-form-item>
        <el-form-item label="收件人"><el-input v-model="smtp.to" placeholder="收件邮箱"/></el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveSmtp">保存配置</el-button>
          <el-button @click="testEmail" :loading="testing">发送测试邮件</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    <el-card style="max-width:520px;margin-top:16px">
      <template #header>内容分析（LLM）</template>
      <el-form :model="llm" label-width="80px" label-position="left">
        <el-form-item label="提供商">
          <el-select v-model="llm.provider" style="width:100%">
            <el-option label="Ollama（本地免费）" value="ollama"/>
            <el-option label="Claude" value="anthropic"/>
            <el-option label="OpenAI 兼容（DeepSeek等）" value="openai"/>
          </el-select>
        </el-form-item>
        <el-form-item label="API Key"><el-input v-model="llm.api_key" type="password"/></el-form-item>
        <el-form-item label="Base URL"><el-input v-model="llm.base_url" placeholder="OpenAI 兼容地址，如 https://api.deepseek.com/v1"/></el-form-item>
        <el-form-item label="模型"><el-input v-model="llm.model" placeholder="如 qwen2.5:7b / deepseek-chat"/></el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveLlm">保存</el-button>
          <el-button @click="recommendLocal" :loading="hwLoading">检测硬件推荐模型</el-button>
        </el-form-item>
        <el-form-item v-if="hwModel"><el-tag type="success">推荐：{{ hwModel }}</el-tag></el-form-item>
      </el-form>
    </el-card>
    <el-dialog v-model="qrVisible" title="扫码登录 B 站" width="340px" @closed="stopPoll">
      <div id="qrcode" style="display:flex;justify-content:center"></div>
      <p style="text-align:center;margin-top:12px">{{ qrMsg }}</p>
    </el-dialog>
  `,
  setup(props, { emit }) {
    const qrVisible = ref(false); const qrMsg = ref('等待扫码'); const syncing = ref(false);
    const smtp = ref({ host: '', port: 465, user: '', password: '', to: '' });
    const testing = ref(false);
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '';
    let timer = null; let qrKey = '';
    async function openQr() {
      qrVisible.value = true; qrMsg.value = '等待扫码';
      try {
        const d = await api('/login/qrcode');
        qrKey = d.qrcode_key;
        nextTick(() => {
          const el = document.getElementById('qrcode');
          el.innerHTML = '';
          new QRCode(el, { text: d.url, width: 220, height: 220 });
        });
        startPoll();
      } catch (e) { qrMsg.value = e.message; }
    }
    function startPoll() {
      stopPoll();
      timer = setInterval(async () => {
        try {
          const r = await api(`/login/poll?qrcode_key=${qrKey}`);
          qrMsg.value = r.message || '...';
          if (r.status === 'ok') { stopPoll(); qrVisible.value = false; ElementPlus.ElMessage.success('登录成功'); emit('refresh'); }
          else if (r.status === 'expired') { stopPoll(); ElementPlus.ElMessage.warning('二维码已失效'); }
        } catch (e) { /* 网络抖动忽略 */ }
      }, 2000);
    }
    function stopPoll() { if (timer) { clearInterval(timer); timer = null; } }
    async function sync() {
      syncing.value = true;
      try {
        const r = await api('/sync', { method: 'POST' });
        ElementPlus.ElMessage.success(`同步完成：历史+${r.history} 收藏+${r.favorites} 关注+${r.followings}`);
        emit('refresh');
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { syncing.value = false; }
    }
    async function loadConfig() {
      const c = await api('/config');
      smtp.value = { ...c.smtp };
      llm.value = { provider: 'ollama', api_key: '', base_url: '', model: '', ...c.llm };
    }
    async function saveLlm() {
      await api('/config', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llm.value }) });
      ElementPlus.ElMessage.success('LLM 配置已保存');
    }
    async function recommendLocal() {
      hwLoading.value = true;
      try {
        const h = await api('/hardware');
        hwModel.value = h.recommended_model;
        llm.value.provider = 'ollama';
        llm.value.model = h.recommended_model;
        ElementPlus.ElMessage.success(`推荐 ${h.recommended_model}（内存 ${h.ram_gb}G / 显存 ${(h.gpu[0]?.vram_gb || 0)}G）`);
      } finally { hwLoading.value = false; }
    }
    async function saveSmtp() {
      await api('/config', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ smtp: smtp.value }) });
      ElementPlus.ElMessage.success('配置已保存');
      emit('refresh');
    }
    async function testEmail() {
      testing.value = true;
      try {
        await api('/config/test-email', { method: 'POST' });
        ElementPlus.ElMessage.success('测试邮件已发送');
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { testing.value = false; }
    }
    const llm = ref({ provider: 'ollama', api_key: '', base_url: '', model: '' });
    const hwLoading = ref(false); const hwModel = ref('');
    const account = ref({ stats: null, coin_log: [] });
    async function loadAccount() {
      try { account.value = await api('/account'); } catch (e) {}
    }
    onMounted(() => { loadConfig().catch(() => {}); loadAccount(); });
    return { qrVisible, qrMsg, syncing, smtp, testing, llm, hwLoading, hwModel, account,
             fmt, openQr, stopPoll, sync, saveSmtp, testEmail, saveLlm, recommendLocal };
  },
};

const App = {
  components: { Overview, History, Favorites, Monitor, Analysis, Settings },
  template: `
    <el-container class="layout">
      <el-aside width="220px" class="aside">
        <div class="logo">BiliScope</div>
        <el-menu :default-active="route" @select="route = $event" class="menu">
          <el-menu-item index="overview"><el-icon><DataLine/></el-icon>概览</el-menu-item>
          <el-menu-item index="history"><el-icon><Clock/></el-icon>观看历史</el-menu-item>
          <el-menu-item index="favorites"><el-icon><Star/></el-icon>收藏夹</el-menu-item>
          <el-menu-item index="monitor"><el-icon><Bell/></el-icon>监测中心<el-badge :value="status.alerts_unread || 0" :hidden="!(status.alerts_unread)" class="menu-badge"/></el-menu-item>
          <el-menu-item index="analysis"><el-icon><DataAnalysis/></el-icon>内容分析</el-menu-item>
          <el-menu-item index="settings"><el-icon><Setting/></el-icon>设置</el-menu-item>
        </el-menu>
        <div class="sync-status">
          <el-tag :type="status.logged_in ? 'success' : 'danger'" size="small">
            {{ status.logged_in ? '已登录' : '未登录' }}
          </el-tag>
        </div>
      </el-aside>
      <el-main>
        <Overview v-if="route === 'overview'" :status="status" @refresh="loadStatus"/>
        <History v-else-if="route === 'history'"/>
        <Favorites v-else-if="route === 'favorites'"/>
        <Monitor v-else-if="route === 'monitor'" :status="status" @refresh="loadStatus"/>
        <Analysis v-else-if="route === 'analysis'"/>
        <Settings v-else-if="route === 'settings'" :status="status" @refresh="loadStatus"/>
      </el-main>
    </el-container>
  `,
  setup() {
    const route = ref('overview');
    const status = ref({ logged_in: false, counts: {} });
    async function loadStatus() {
      try { status.value = await api('/status'); } catch (e) {}
    }
    onMounted(loadStatus);
    return { route, status, loadStatus };
  },
};

const app = createApp(App);
for (const [name, comp] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, comp);
}
app.use(ElementPlus).mount('#app');
