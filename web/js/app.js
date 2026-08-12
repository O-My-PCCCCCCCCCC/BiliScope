const { createApp, ref, onMounted, onBeforeUnmount, nextTick } = Vue;

async function api(path, options = {}) {
  const res = await fetch('/api' + path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `请求失败(${res.status})`);
  return data;
}

// B 站 CDN 防盗链，统一走后端图片代理；追加缩略图参数，4K 下大幅降低解码/缩放开销
const imgUrl = u => {
  if (!u) return '';
  const src = u.includes('@') ? u : u + '@320w_200h_1c.webp';
  return '/api/img?url=' + encodeURIComponent(src);
};

const Dynamics = {
  template: `
    <h2>我的动态</h2>
    <el-table :data="items" style="width:100%">
      <el-table-column label="时间" width="170">
        <template #default="s">{{ fmt(s.row.ctime) }}</template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="s"><el-tag size="small">{{ typeName(s.row.type) }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="content" label="内容" min-width="300"/>
      <el-table-column prop="like_count" label="点赞" width="70"/>
      <el-table-column prop="comment_count" label="评论" width="70"/>
      <el-table-column prop="repost_count" label="转发" width="70"/>
    </el-table>
  `,
  setup() {
    const items = ref([]);
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '';
    const typeName = t => ({ AV: '视频', FORWARD: '转发', DRAW: '图文', WORD: '文字', DYNAMIC_TYPE_AV: '视频' }[t] || t);
    onMounted(async () => { items.value = await api('/dynamics').catch(() => []); });
    return { items, fmt, typeName };
  },
};

const DeepAnalysis = {
  template: `
    <h2>深度分析</h2>
    <el-row :gutter="16">
      <el-col :span="8"><el-card><div class="card-num">{{ graveyard.count }}</div><div class="card-label">吃灰收藏（共 {{ graveyard.total }} 个，收藏了没看过）</div></el-card></el-col>
      <el-col :span="8"><el-card><div data-dur class="chart"></div></el-card></el-col>
      <el-col :span="8"><el-card><div data-week class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card><div data-up class="chart"></div></el-card></el-col>
    </el-row>
  `,
  setup() {
    const graveyard = ref({ count: 0, total: 0 });
    async function load() {
      const d = await api('/analysis/deep').catch(() => null);
      if (!d) return;
      graveyard.value = d.graveyard;
      nextTick(() => {
        const mk = (sel, option) => {
          const el = document.querySelector(sel);
          if (el) echarts.init(el, 'dark').setOption(option);
        };
        mk('[data-dur]', {
          title: { text: '观看时长分布', textStyle: { fontSize: 14 } }, tooltip: { trigger: 'item' },
          series: [{ type: 'pie', data: d.duration.map(x => ({ name: x.bucket, value: x.n })) }],
        });
        mk('[data-week]', {
          title: { text: '周几活跃度', textStyle: { fontSize: 14 } }, tooltip: {},
          xAxis: { type: 'category', data: d.weekday.map(x => x.w) }, yAxis: { type: 'value' },
          series: [{ type: 'bar', data: d.weekday.map(x => x.n) }],
        });
        mk('[data-up]', {
          title: { text: 'UP主观看时长 TOP', textStyle: { fontSize: 14 } }, tooltip: { trigger: 'axis' },
          xAxis: { type: 'category', data: d.up_watch.map(u => u.up_name), axisLabel: { rotate: 30 } },
          yAxis: { type: 'value', name: '秒' },
          series: [{ type: 'bar', data: d.up_watch.map(u => u.total_sec) }],
        });
      });
    }
    onMounted(load);
    return { graveyard };
  },
};

const Downloads = {
  template: `
    <h2>下载管理</h2>
    <el-card style="margin-bottom:16px">
      <template #header>当前任务</template>
      <div v-if="status.state === 'running'">
        <el-progress :percentage="status.progress"/>
        <div style="color:#999;font-size:12px;margin-top:4px">{{ status.message }}</div>
        <div style="color:#666;font-size:12px;margin-top:2px">共 {{ status.tasks.length }} 个，当前：{{ status.current }}</div>
      </div>
      <div v-else-if="status.state === 'done'"><el-tag type="success">全部下载完成</el-tag></div>
      <div v-else-if="status.state === 'error'"><el-tag type="danger">下载失败：{{ status.message }}</el-tag></div>
      <div v-else style="color:#999">暂无任务。可以到 AI 助手让它批量下载，或点下方手动下载</div>
      <div style="margin-top:10px">
        <el-input v-model="manualUrl" placeholder="粘贴一个 B 站视频链接" style="width:360px"/>
        <el-button type="primary" @click="manual('mp4')">下载视频</el-button>
        <el-button @click="manual('audio')">下载音频</el-button>
      </div>
    </el-card>
    <el-card>
      <template #header>已下载文件（{{ files.length }}）</template>
      <el-table :data="files" style="width:100%">
        <el-table-column prop="name" label="文件名" min-width="300"/>
      </el-table>
    </el-card>
  `,
  setup() {
    const status = ref({ state: 'idle', tasks: [], current: '', progress: 0, message: '' });
    const files = ref([]); const manualUrl = ref('');
    let timer = null;
    async function load() {
      status.value = await api('/downloads/status').catch(() => status.value);
      files.value = (await api('/downloads/list').catch(() => [])).map(name => ({ name }));
    }
    async function manual(fmt) {
      const url = manualUrl.value.trim();
      if (!url) { ElementPlus.ElMessage.warning('请先粘贴链接'); return; }
      manualUrl.value = '';
      try {
        await api('/downloads/run', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ urls: [url], fmt }) });
        ElementPlus.ElMessage.success('已开始下载');
        load();
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
    }
    onMounted(() => { load(); timer = setInterval(load, 2000); });
    onBeforeUnmount(() => { if (timer) clearInterval(timer); });
    return { status, files, manualUrl, manual };
  },
};

const Chat = {
  template: `
    <h2>AI 助手</h2>
    <div class="chat-box" ref="chatBox">
      <div v-for="(m, i) in display" :key="i" class="chat-msg" :class="m.role">
        <div class="chat-avatar" v-if="m.role === 'assistant'">🤖</div>
        <div class="chat-bubble" v-if="m.role === 'user'">{{ m.text }}</div>
        <div class="chat-bubble md" v-else-if="m.role === 'assistant'" v-html="m.html"></div>
        <div class="chat-bubble tool" v-else-if="m.role === 'tool'">{{ m.text }}</div>
      </div>
      <div v-if="thinking" class="chat-msg assistant">
        <div class="chat-avatar">🤖</div>
        <div class="chat-bubble thinking">正在思考<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></div>
      </div>
    </div>
    <div class="chat-input">
      <el-input v-model="input" placeholder="例如：把音乐收藏夹里的视频整理到新文件夹" @keyup.enter="send"/>
      <el-button type="primary" @click="send" :loading="loading">发送</el-button>
      <el-button @click="reset">清空</el-button>
    </div>
  `,
  setup() {
    const messages = ref([]); const display = ref([]);
    const input = ref(''); const loading = ref(false); const thinking = ref(false);
    async function loadHistory() {
      try {
        const d = await api('/chat/history');
        messages.value = d.messages;
        buildDisplay();
      } catch (e) {}
    }
    function renderMd(text) {
      try { return DOMPurify.sanitize(marked.parse(text || '')); }
      catch (e) { return text || ''; }
    }
    function buildDisplay() {
      const out = [];
      for (const m of messages.value) {
        if (m.role === 'user') out.push({ role: 'user', text: m.content });
        else if (m.role === 'assistant' && m.content) out.push({ role: 'assistant', html: renderMd(m.content) });
        else if (m.role === 'assistant' && m.tool_calls) {
          out.push({ role: 'tool', text: '🔧 调用：' + m.tool_calls.map(t => t.function.name).join('、') });
        } else if (m.role === 'tool') {
          let brief = m.content || '';
          if (brief.length > 120) brief = brief.slice(0, 120) + '…';
          out.push({ role: 'tool', text: '  ✅ ' + brief });
        }
      }
      display.value = out;
      nextTick(() => {
        const box = document.querySelector('.chat-box');
        if (box) box.scrollTop = box.scrollHeight;
      });
    }
    function scrollToBottom() {
      nextTick(() => {
        const box = document.querySelector('.chat-box');
        if (box) box.scrollTop = box.scrollHeight;
      });
    }
    async function send() {
      const text = input.value.trim();
      if (!text || loading.value) return;
      input.value = '';
      loading.value = true;
      thinking.value = true;
      display.value.push({ role: 'user', text });  // 乐观显示，立即可见
      scrollToBottom();
      try {
        await api('/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text }) });
        await loadHistory();
      } catch (e) {
        ElementPlus.ElMessage.error(e.message);
        display.value.push({ role: 'assistant', html: renderMd('⚠️ ' + e.message) });
      } finally {
        loading.value = false;
        thinking.value = false;
        scrollToBottom();
      }
    }
    async function reset() {
      await api('/chat/reset', { method: 'POST' });
      messages.value = []; display.value = [];
    }
    onMounted(() => loadHistory().catch(() => {}));
    return { messages, display, input, loading, thinking, send, reset };
  },
};

const Analysis = {
  template: `
    <h2>内容分析</h2>
    <div style="margin-bottom:12px">
      <el-button type="primary" @click="run" :loading="running">分析未分析视频</el-button>
      <el-tag style="margin-left:8px">已分析 {{ status.analyzed }} / {{ status.total }}</el-tag>
    </div>
    <div v-if="!status.total" style="color:#e6a23c;font-size:12px;margin-bottom:12px">
      ⚠️ 还没有可分析的视频：请先在设置页配置 LLM（Ollama/DeepSeek），再同步一次数据（同步时会补拉视频简介）
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
    <div style="margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <el-select v-model="selScope" style="width:240px" placeholder="选择检测范围">
        <el-option label="全部（历史+收藏）" value="all"/>
        <el-option label="观看历史" value="history"/>
        <el-option v-for="f in folders" :key="f.media_id" :label="f.name + '（' + f.count + '）'" :value="String(f.media_id)"/>
      </el-select>
      <el-button type="primary" @click="run" :loading="running">检测失效视频</el-button>
      <el-tag v-if="result" style="margin-left:8px">失效 {{ result.invalid }} · UP更新 {{ result.updates }}</el-tag>
    </div>
    <div style="color:#999;font-size:12px;margin-bottom:12px">
      按收藏夹检测更快；全部检测需逐条请求 B 站，可能耗时几分钟，请耐心等待
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
    const folders = ref([]); const selScope = ref('all');
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString('zh-CN') : '';
    async function loadAll() {
      const d = await api('/alerts');
      alerts.value = d.items;
      invalidList.value = await api('/monitor/invalid');
      updates.value = await api('/monitor/updates');
    }
    async function loadFolders() {
      folders.value = await api('/favorites').catch(() => []);
    }
    async function run() {
      running.value = true;
      try {
        result.value = await api(`/monitor/run?scope=${selScope.value}`, { method: 'POST' });
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
    onMounted(() => { loadAll().catch(() => {}); loadFolders(); });
    return { tab, alerts, invalidList, updates, running, result, folders, selScope,
             fmt, run, markRead };
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
          <img :src="imgUrl(it.pic)" loading="lazy" decoding="async" :alt="it.title"/>
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
    <el-tabs v-model="favTab">
      <el-tab-pane label="收藏夹" name="folders">
    <div style="margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <el-button size="small" @click="selecting = !selecting">{{ selecting ? '完成选择' : '选择' }}</el-button>
      <template v-if="selecting">
        <el-button size="small" @click="selectAll">全选</el-button>
        <el-button size="small" type="primary" :disabled="!selCount" @click="downloadSel('mp4')">下载所选视频 ({{ selCount }})</el-button>
        <el-button size="small" :disabled="!selCount" @click="downloadSel('audio')">下载所选音频 ({{ selCount }})</el-button>
        <el-button size="small" text @click="clearSel">清空</el-button>
      </template>
    </div>
    <div class="fav-layout">
      <div class="fav-side">
        <div v-for="f in folders" :key="f.media_id" class="fav-side-item"
             :class="{ active: activeId === f.media_id }" @click="select(f)">
          <span class="fav-side-name">{{ f.name }}</span>
          <span class="fav-side-count">{{ f.count }}</span>
        </div>
      </div>
      <div class="fav-main" v-loading="loading" @scroll="onFavScroll">
        <div class="bili-grid">
          <div class="bili-card" v-for="it in items" :key="it.bvid"
               :class="{ sel: selecting && sel[it.bvid] }"
               @click="selecting ? toggleSelect(it) : play(it)">
            <div class="bili-cover">
              <el-checkbox v-if="selecting" v-model="sel[it.bvid]" class="card-check" @click.stop/>
              <img v-if="it.title" :src="imgUrl(it.pic)" loading="lazy" decoding="async" :alt="it.title"/>
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
        <div v-if="loading" class="empty-tip">加载中...</div>
        <div v-else-if="!hasMore && items.length" class="empty-tip">已经到底啦，共 {{ items.length }} 条</div>
      </div>
    </div>
      </el-tab-pane>
      <el-tab-pane label="追的合集" name="collections">
        <div class="bili-grid">
          <div class="bili-card" v-for="c in collections" :key="c.collection_id + '-' + c.category" @click="openCollection(c)">
            <div class="bili-cover">
              <img :src="imgUrl(c.cover)" loading="lazy" decoding="async" :alt="c.title"/>
            </div>
            <div class="bili-title">{{ c.title }}</div>
            <div class="bili-meta">
              <span class="bili-up">{{ c.category === 'season' ? '合集' : '系列' }}</span>
              <span class="bili-stats">{{ c.total }} 集</span>
            </div>
          </div>
        </div>
        <div v-if="!collections.length" class="empty-tip">暂无追的合集</div>
      </el-tab-pane>
      <el-tab-pane label="收藏的收藏夹" name="collected">
        <div class="bili-grid">
          <div class="bili-card" v-for="cf in collectedFolders" :key="cf.media_id" @click="openCollected(cf)">
            <div class="bili-cover folder-cover">📁</div>
            <div class="bili-title">{{ cf.title }}</div>
            <div class="bili-meta">
              <span class="bili-up">{{ cf.up_name }}</span>
              <span class="bili-stats">{{ cf.media_count }} 个</span>
            </div>
          </div>
        </div>
        <div v-if="!collectedFolders.length" class="empty-tip">暂无收藏的收藏夹</div>
      </el-tab-pane>
    </el-tabs>
  `,
  setup() {
    const folders = ref([]); const items = ref([]);
    const activeId = ref(null); const loading = ref(false);
    const favTab = ref('folders');
    const collections = ref([]); const collectedFolders = ref([]);
    async function loadFolders() {
      folders.value = await api('/favorites');
      if (folders.value.length && activeId.value == null) {
        select(folders.value[0]);
      }
    }
    async function loadExtras() {
      collections.value = await api('/collections').catch(() => []);
      collectedFolders.value = await api('/favorites/collected').catch(() => []);
    }
    const page = ref(1); const hasMore = ref(true);
    async function select(f) {
      activeId.value = f.media_id;
      items.value = []; page.value = 1; hasMore.value = true;
      await loadPage();
    }
    async function loadPage() {
      if (loading.value || !activeId.value) return;
      loading.value = true;
      try {
        const d = await api(`/favorites/${activeId.value}?page=${page.value}&page_size=24`);
        items.value.push(...d.items);
        hasMore.value = items.value.length < d.total;
        if (hasMore.value) page.value += 1;
      } finally { loading.value = false; }
    }
    function onFavScroll() {
      const el = document.querySelector('.fav-main');
      if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 300
          && !loading.value && hasMore.value) loadPage();
    }
    const selecting = ref(false);
    const sel = Vue.reactive({});
    const selCount = Vue.computed(() => Object.values(sel).filter(Boolean).length);
    function toggleSelect(it) { if (it.bvid) sel[it.bvid] = !sel[it.bvid]; }
    function selectAll() { items.value.forEach(it => { if (it.bvid) sel[it.bvid] = true; }); }
    function clearSel() { Object.keys(sel).forEach(k => delete sel[k]); selecting.value = false; }
    async function downloadSel(fmt) {
      const bvids = Object.keys(sel).filter(k => sel[k]);
      if (!bvids.length) { ElementPlus.ElMessage.warning('未选择视频'); return; }
      const urls = bvids.map(b => `https://www.bilibili.com/video/${b}`);
      try {
        await api('/downloads/run', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ urls, fmt }) });
        ElementPlus.ElMessage.success(`已开始下载 ${bvids.length} 个${fmt === 'audio' ? '音频' : '视频'}`);
        clearSel();
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
    }
    function play(it) {
      if (it.title) window.open(`https://www.bilibili.com/video/${it.bvid}`, '_blank');
    }
    function openCollection(c) {
      window.open(`https://www.bilibili.com/medialist/play/${c.collection_id}`, '_blank');
    }
    function openCollected(cf) {
      window.open(`https://www.bilibili.com/medialist/detail/ml${cf.media_id}`, '_blank');
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
    onMounted(() => { loadFolders(); loadExtras(); });
    return { folders, items, activeId, loading, favTab, collections, collectedFolders, hasMore,
             selecting, sel, selCount, toggleSelect, selectAll, clearSel, downloadSel,
             select, play, openCollection, openCollected, onFavScroll, imgUrl, fmtNum, fmtDur };
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
        <el-divider/>
        <el-button @click="recommendModels" :loading="modelLoading">按资源占比选择模型（本地安装）</el-button>
        <div v-if="modelList.length" style="margin-top:8px">
          <div class="model-row" v-for="m in modelList" :key="m.name">
            <div class="model-info">
              <b>{{ m.name }}</b>
              <span style="color:#999;font-size:12px;margin-left:8px">占用 ~{{ m.est_ram_gb }}G 内存 · 磁盘 {{ m.disk_gb }}G</span>
            </div>
            <el-button size="small" type="primary" :loading="installing === m.name" @click="installModel(m.name)">后台安装</el-button>
          </div>
          <div v-if="!ollamaOk" style="color:#e6a23c;font-size:12px;margin-top:6px">
            ⚠️ 未检测到 Ollama
            <el-button size="small" :loading="ollamaInstalling" @click="installOllama">一键安装 Ollama</el-button>
          </div>
          <div v-if="installState.state === 'running'" style="margin-top:8px">
            <el-progress :percentage="installState.progress"/>
            <div style="color:#999;font-size:12px">{{ installState.message }}</div>
          </div>
        </div>
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
    const modelList = ref([]); const modelLoading = ref(false);
    const installing = ref(''); const ollamaOk = ref(true);
    const installState = ref({ state: 'idle', progress: 0, message: '' });
    const ollamaInstalling = ref(false);
    let installTimer = null;
    async function installOllama() {
      ollamaInstalling.value = true;
      try {
        const r = await api('/ollama/install', { method: 'POST' });
        if (r.error) { ElementPlus.ElMessage.error(r.error); ollamaInstalling.value = false; return; }
        ElementPlus.ElMessage.success('开始后台安装 Ollama（约 700MB）');
        pollInstall();
      } catch (e) { ElementPlus.ElMessage.error(e.message); ollamaInstalling.value = false; }
    }
    async function recommendModels() {
      modelLoading.value = true;
      try {
        const d = await api('/models/recommend');
        modelList.value = d.models;
        ollamaOk.value = d.ollama_installed;
      } finally { modelLoading.value = false; }
    }
    async function installModel(name) {
      installing.value = name;
      try {
        await api('/models/install', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: name }) });
        ElementPlus.ElMessage.success('开始后台安装 ' + name);
        pollInstall();
      } catch (e) { ElementPlus.ElMessage.error(e.message); installing.value = ''; }
    }
    function pollInstall() {
      if (installTimer) clearInterval(installTimer);
      installTimer = setInterval(async () => {
        try {
          const s = await api('/models/install-status');
          installState.value = s;
          if (s.state === 'done') {
            clearInterval(installTimer); installing.value = ''; ollamaInstalling.value = false;
            if (s.phase === 'ollama') {
              ollamaOk.value = true;
              ElementPlus.ElMessage.success('Ollama 安装完成，可以选模型了'); loadLlm();
            } else {
              ElementPlus.ElMessage.success('模型安装完成，可直接使用'); loadLlm();
            }
          } else if (s.state === 'error') {
            clearInterval(installTimer); installing.value = ''; ollamaInstalling.value = false;
            ElementPlus.ElMessage.error('安装失败：' + s.message);
          }
        } catch (e) {}
      }, 1500);
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
             modelList, modelLoading, installing, ollamaOk, installState, ollamaInstalling,
             fmt, openQr, stopPoll, sync, saveSmtp, testEmail, saveLlm, recommendLocal,
             recommendModels, installModel, installOllama };
  },
};

const App = {
  components: { Overview, History, Favorites, Monitor, Analysis, Dynamics, DeepAnalysis, Downloads, Chat, Settings },
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
          <el-menu-item index="deep"><el-icon><TrendCharts/></el-icon>深度分析</el-menu-item>
          <el-menu-item index="dynamics"><el-icon><Message/></el-icon>我的动态</el-menu-item>
          <el-menu-item index="downloads"><el-icon><Download/></el-icon>下载管理</el-menu-item>
          <el-menu-item index="chat"><el-icon><ChatDotRound/></el-icon>AI 助手</el-menu-item>
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
        <DeepAnalysis v-else-if="route === 'deep'"/>
        <Dynamics v-else-if="route === 'dynamics'"/>
        <Downloads v-else-if="route === 'downloads'"/>
        <Chat v-else-if="route === 'chat'"/>
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
