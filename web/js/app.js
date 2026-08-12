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

const App = {
  components: { Overview },
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
        <Overview v-if="route === 'overview'" :status="status"/>
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
    return { route, status };
  },
};

const app = createApp(App);
for (const [name, comp] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, comp);
}
app.use(ElementPlus).mount('#app');
