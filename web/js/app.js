const { createApp, ref, onMounted, nextTick } = Vue;

async function api(path, options = {}) {
  const res = await fetch('/api' + path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `请求失败(${res.status})`);
  return data;
}

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

const History = {
  template: `
    <h2>观看历史</h2>
    <div style="margin-bottom:12px">
      <el-input v-model="search" placeholder="搜索标题或UP主" clearable style="width:320px"
                @keyup.enter="load(1)"/>
      <el-button type="primary" @click="load(1)">搜索</el-button>
    </div>
    <el-table :data="items" v-loading="loading" style="width:100%">
      <el-table-column label="观看时间" width="180">
        <template #default="s">{{ fmt(s.row.view_at) }}</template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="260"/>
      <el-table-column prop="up_name" label="UP主" width="140"/>
      <el-table-column prop="tname" label="分区" width="100"/>
      <el-table-column label="进度" width="100">
        <template #default="s">{{ pct(s.row.progress, s.row.duration) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination layout="prev, pager, next" :total="total" :page-size="pageSize"
                   :current-page="page" @current-change="load" style="margin-top:12px"/>
  `,
  setup() {
    const search = ref(''); const items = ref([]); const total = ref(0);
    const page = ref(1); const pageSize = 20; const loading = ref(false);
    async function load(p) {
      page.value = p || 1; loading.value = true;
      try {
        const d = await api(`/history?search=${encodeURIComponent(search.value)}&page=${page.value}&page_size=${pageSize}`);
        items.value = d.items; total.value = d.total;
      } finally { loading.value = false; }
    }
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '';
    const pct = (prog, dur) => dur ? Math.round(prog / dur * 100) + '%' : (prog || '-');
    onMounted(() => load(1));
    return { search, items, total, page, pageSize, loading, load, fmt, pct };
  },
};

const Favorites = {
  template: `
    <h2>收藏夹</h2>
    <el-row :gutter="12">
      <el-col :span="8" v-for="f in folders" :key="f.media_id">
        <el-card @click="open(f)" style="margin-bottom:12px;cursor:pointer">
          <div class="fav-name">{{ f.name }}</div>
          <div class="fav-count">{{ f.count }} 个视频 · {{ fmt(f.created_at) }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-dialog v-model="dialog" :title="current?.name" width="70%">
      <el-table :data="items" v-loading="loading">
        <el-table-column label="标题" min-width="260">
          <template #default="s">
            <span v-if="s.row.title">{{ s.row.title }}</span>
            <el-tag v-else type="danger">已失效</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="up_name" label="UP主" width="140"/>
        <el-table-column label="收藏时间" width="180">
          <template #default="s">{{ fmt(s.row.fav_time) }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  `,
  setup() {
    const folders = ref([]); const items = ref([]); const current = ref(null);
    const dialog = ref(false); const loading = ref(false);
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '';
    async function loadFolders() {
      folders.value = await api('/favorites');
    }
    async function open(f) {
      current.value = f; dialog.value = true; loading.value = true;
      try {
        const d = await api(`/favorites/${f.media_id}?page_size=200`);
        items.value = d.items;
      } finally { loading.value = false; }
    }
    onMounted(loadFolders);
    return { folders, items, current, dialog, loading, fmt, open };
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
      </div>
      <p v-else>尚未登录，点击下方按钮扫码登录 B 站账号。</p>
      <div style="margin-top:16px">
        <el-button type="primary" @click="openQr">扫码登录</el-button>
        <el-button type="success" :disabled="!status.logged_in" @click="sync" :loading="syncing">
          立即同步数据
        </el-button>
      </div>
    </el-card>
    <el-dialog v-model="qrVisible" title="扫码登录 B 站" width="340px" @closed="stopPoll">
      <div id="qrcode" style="display:flex;justify-content:center"></div>
      <p style="text-align:center;margin-top:12px">{{ qrMsg }}</p>
    </el-dialog>
  `,
  setup(props, { emit }) {
    const qrVisible = ref(false); const qrMsg = ref('等待扫码'); const syncing = ref(false);
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
    return { qrVisible, qrMsg, syncing, fmt, openQr, stopPoll, sync };
  },
};

const App = {
  components: { Overview, History, Favorites, Settings },
  template: `
    <el-container class="layout">
      <el-aside width="220px" class="aside">
        <div class="logo">BiliScope</div>
        <el-menu :default-active="route" @select="route = $event" class="menu">
          <el-menu-item index="overview"><el-icon><DataLine/></el-icon>概览</el-menu-item>
          <el-menu-item index="history"><el-icon><Clock/></el-icon>观看历史</el-menu-item>
          <el-menu-item index="favorites"><el-icon><Star/></el-icon>收藏夹</el-menu-item>
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
