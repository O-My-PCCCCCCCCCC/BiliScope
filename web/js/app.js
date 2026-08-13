const { createApp, ref, onMounted, onBeforeUnmount, nextTick } = Vue;

async function api(path, options = {}) {
  const res = await fetch('/api' + path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `请求失败(${res.status})`);
  return data;
}

// 共用环形图配置（confine 防止 tooltip 被裁剪）
const PIE_COLORS = ['#fb7299', '#f6c445', '#7ecbf2', '#9cd6a5', '#b9a6ff', '#f2918e', '#66c7b8', '#d9a0ff', '#8fc1e3', '#e3b0ff'];
function pieOption(title, data) {
  return {
    title: { text: title, textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item', confine: true, formatter: '{b}<br/>{c} 个（{d}%）' },
    legend: { orient: 'vertical', left: 'left', top: 'middle', textStyle: { color: '#999', fontSize: 11 } },
    color: PIE_COLORS,
    series: [{
      type: 'pie', radius: ['38%', '62%'], center: ['60%', '55%'],
      itemStyle: { borderRadius: 4, borderColor: '#1a1a1a', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 13, fontWeight: 'bold' } },
      data,
    }],
  };
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
    <el-row :gutter="16" class="cards">
      <el-col :span="4" v-for="s in profileCards" :key="s.label">
        <el-card><div class="card-num">{{ s.value }}</div><div class="card-label">{{ s.label }}</div></el-card>
      </el-col>
    </el-row>
    <el-row :gutter="16">
      <el-col :span="12"><el-card><div data-monthly class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card><div data-favTname class="chart"></div></el-card></el-col>
      <el-col :span="8"><el-card><div data-dur class="chart"></div></el-card></el-col>
      <el-col :span="8"><el-card><div data-week class="chart"></div></el-card></el-col>
      <el-col :span="8"><el-card><div data-up class="chart"></div></el-card></el-col>
    </el-row>
    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="6"><el-card><div data-completion class="chart"></div></el-card></el-col>
      <el-col :span="6"><el-card><div data-timebuckets class="chart"></div></el-card></el-col>
      <el-col :span="6"><el-card><div data-popularity class="chart"></div></el-card></el-col>
      <el-col :span="6"><el-card><div data-weekend class="chart"></div></el-card></el-col>
    </el-row>
    <el-card style="margin-top:16px">
      <template #header>UP主深度榜（观看时长 TOP）</template>
      <el-table :data="upDepth" size="small" max-height="300" style="width:100%">
        <el-table-column prop="up_name" label="UP主" width="140"/>
        <el-table-column prop="views" label="观看次数" width="90"/>
        <el-table-column label="总时长" width="100">
          <template #default="s">{{ (s.row.total_sec / 3600).toFixed(1) }} 小时</template>
        </el-table-column>
        <el-table-column label="最近观看" width="140">
          <template #default="s">{{ timeAgo(s.row.last_view) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-card style="margin-top:16px">
      <template #header>分区吃灰率（收藏了没看）</template>
      <el-table :data="graveyardByTname" size="small" max-height="300" style="width:100%">
        <el-table-column prop="tname" label="分区" width="120"/>
        <el-table-column label="吃灰率" min-width="220">
          <template #default="s">
            <el-progress :percentage="Math.round(s.row.graveyard / s.row.total * 100)"/>
          </template>
        </el-table-column>
        <el-table-column prop="graveyard" label="没看过" width="80"/>
        <el-table-column prop="total" label="总收藏" width="80"/>
      </el-table>
    </el-card>
    <el-card style="margin-top:16px">
      <template #header>最近90天观看热力图</template>
      <div data-calendar class="chart" style="height:170px"></div>
    </el-card>
    <el-card style="margin-top:16px">
      <template #header>吃灰收藏明细（{{ graveyardItems.length }} 个，收藏了从没看过）</template>
      <el-table :data="graveyardItems" size="small" max-height="400" style="width:100%">
        <el-table-column prop="title" label="标题" min-width="240"/>
        <el-table-column prop="up_name" label="UP主" width="120"/>
        <el-table-column prop="tname" label="分区" width="90"/>
        <el-table-column label="收藏时间" width="160">
          <template #default="s">{{ fmt(s.row.fav_time) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  `,
  setup() {
    const profile = ref({});
    const graveyardItems = ref([]);
    const upDepth = ref([]); const graveyardByTname = ref([]);
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleDateString('zh-CN') : '';
    function timeAgo(ts) {
      if (!ts) return '';
      const diff = (Date.now() / 1000 - ts);
      if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
      if (diff < 604800) return Math.floor(diff / 86400) + '天前';
      return new Date(ts * 1000).toLocaleDateString('zh-CN');
    }
    const profileCards = Vue.computed(() => {
      const p = profile.value;
      return [
        { label: '总观看数', value: p.total_views ?? '-' },
        { label: '总时长(小时)', value: p.total_duration_h ?? '-' },
        { label: '活跃天数', value: p.active_days ?? '-' },
        { label: '日均观看', value: p.avg_daily ?? '-' },
        { label: '黄金时段', value: p.peak_hour ?? '-' },
        { label: '最活跃周几', value: p.peak_weekday ?? '-' },
      ];
    });
    async function load() {
      const [profileData, monthly, favTnames, graveyard, detailed] = await Promise.all([
        api('/analysis/profile'), api('/analysis/monthly'),
        api('/analysis/fav-tnames'), api('/analysis/graveyard-list'),
        api('/analysis/detailed'),
      ]).catch(() => [null, [], [], [], null]);
      if (!profileData) return;
      profile.value = profileData;
      graveyardItems.value = graveyard;
      upDepth.value = detailed?.up_depth || [];
      graveyardByTname.value = detailed?.graveyard_by_tname || [];
      nextTick(() => {
        const mk = (sel, option) => {
          const el = document.querySelector(sel);
          if (el) echarts.init(el, 'dark').setOption(option);
        };
        mk('[data-monthly]', {
          title: { text: '月度观看趋势', textStyle: { fontSize: 14 } }, tooltip: { trigger: 'axis' },
          xAxis: { type: 'category', data: monthly.map(x => x.ym) }, yAxis: { type: 'value' },
          series: [{ type: 'line', smooth: true, areaStyle: {}, data: monthly.map(x => x.n) }],
        });
        mk('[data-favTname]', pieOption('收藏分区分布', favTnames.map(x => ({ name: x.tname, value: x.n }))));
        (async () => {
          const dd = await api('/analysis/deep').catch(() => null);
          if (dd) {
            mk('[data-dur]', {
              title: { text: '观看时长分布', textStyle: { fontSize: 14 } }, tooltip: { trigger: 'item' },
              series: [{ type: 'pie', data: dd.duration.map(x => ({ name: x.bucket, value: x.n })) }],
            });
            mk('[data-week]', {
              title: { text: '周几活跃度', textStyle: { fontSize: 14 } }, tooltip: {},
              xAxis: { type: 'category', data: dd.weekday.map(x => x.w) }, yAxis: { type: 'value' },
              series: [{ type: 'bar', data: dd.weekday.map(x => x.n) }],
            });
            mk('[data-up]', {
              title: { text: 'UP主观看时长 TOP', textStyle: { fontSize: 14 } }, tooltip: { trigger: 'axis' },
              xAxis: { type: 'category', data: dd.up_watch.map(u => u.up_name), axisLabel: { rotate: 30 } },
              yAxis: { type: 'value', name: '秒' },
              series: [{ type: 'bar', data: dd.up_watch.map(u => u.total_sec) }],
            });
          }
        })();
        // 详细分析
        if (detailed) {
          const pie = (data, sel, title) => mk(sel, pieOption(
            title, data.map(x => ({ name: x.bucket || x.kind, value: x.n }))
          ));
          pie(detailed.completion, '[data-completion]', '观看完整度');
          pie(detailed.time_buckets, '[data-timebuckets]', '观看时段');
          pie(detailed.popularity, '[data-popularity]', '热门 vs 小众');
          pie(detailed.weekday_weekend, '[data-weekend]', '工作日 vs 周末');
          mk('[data-calendar]', {
            tooltip: {},
            calendar: { range: 90, cellSize: ['auto', 14], left: 30, right: 20, top: 10 },
            visualMap: { min: 0, max: 5, inRange: { color: ['#2a2a2a', '#fb7299'] },
                         orient: 'horizontal', left: 'center', bottom: 0, text: ['多', '少'] },
            series: [{ type: 'heatmap', coordinateSystem: 'calendar',
                       data: detailed.calendar.map(d => [d.day, d.n]) }],
          });
        }
      });
    }
    onMounted(load);
    return { profile, profileCards, graveyardItems, upDepth, graveyardByTname, fmt, timeAgo };
  },
};

const Downloads = {
  template: `
    <h2>下载管理</h2>
    <el-card style="margin-bottom:16px">
      <template #header>保存位置与格式</template>
      <div>保存到：<code style="color:#7ecbf2;word-break:break-all">{{ status.out_dir || '加载中...' }}</code></div>
      <div style="color:#999;font-size:12px;margin-top:6px">
        视频 → MP4（需 ffmpeg 合并）；音频 → MP3 / M4A。可在「设置 → 下载」里改保存目录。
      </div>
    </el-card>
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
    <el-row :gutter="12" style="margin-top:16px">
      <el-col :span="7"><el-card><div data-category class="chart"></div></el-card></el-col>
      <el-col :span="17"><el-card>
        <template #header>
          <el-radio-group v-model="catTab" size="small">
            <el-radio-button value="useful">有用（学习/实用/资讯）</el-radio-button>
            <el-radio-button value="waste">娱乐消遣</el-radio-button>
          </el-radio-group>
        </template>
        <el-table :data="catTab === 'useful' ? catData.useful : catData.waste" size="small" max-height="300" style="width:100%">
          <el-table-column prop="title" label="标题" min-width="200"/>
          <el-table-column prop="category" label="类别" width="90"/>
          <el-table-column prop="summary" label="摘要" min-width="180"/>
        </el-table>
        <div v-if="!((catTab === 'useful' ? catData.useful : catData.waste).length)" class="empty-tip">还没有分类数据，先点「分析未分析视频」</div>
      </el-card></el-col>
    </el-row>
  `,
  setup() {
    const running = ref(false); const status = ref({ analyzed: 0, total: 0 });
    const catData = ref({ distribution: [], useful: [], waste: [] });
    const catTab = ref('useful');
    async function loadCategory() {
      catData.value = await api('/analysis/category').catch(() => ({ distribution: [], useful: [], waste: [] }));
      nextTick(() => {
        const el = document.querySelector('[data-category]');
        if (el) echarts.init(el, 'dark').setOption(pieOption(
          '用途占比', catData.value.distribution.map(x => ({ name: x.category, value: x.n }))
        ));
      });
    }
    async function run() {
      running.value = true;
      try {
        const r = await api('/analysis/run?limit=50', { method: 'POST' });
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
    onMounted(() => { loadStatus(); renderChart(); loadCategory(); });
    return { running, status, run, catData, catTab, loadCategory };
  },
};

const Insights = {
  template: `
    <h2>洞察</h2>
    <el-card style="margin-bottom:16px">
      <template #header>AI 观看画像</template>
      <el-button type="primary" @click="genPersona" :loading="personaLoading">生成我的观看画像</el-button>
      <div v-if="persona" class="weekly-report" style="margin-top:12px">{{ persona }}</div>
      <div v-else style="color:#999;font-size:12px;margin-top:8px">
        用 AI 根据你的全部观看数据，描绘你的 B 站观看人格（深夜党 / 碎片党 / 深度爱好者…）。需先在设置页配置 LLM。
      </div>
    </el-card>
    <el-card style="margin-bottom:16px">
      <template #header>兴趣漂移（近 12 个月主题标签）</template>
      <div v-if="!interest.series.length" class="empty-tip">还没有主题数据，请先到「内容分析」页点「分析未分析视频」</div>
      <div v-else data-interest class="chart"></div>
    </el-card>
    <el-card style="margin-bottom:16px">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>时段 × 内容</span>
          <el-radio-group v-model="crossDim" size="small" @change="loadCross">
            <el-radio-button value="tname">分区</el-radio-button>
            <el-radio-button value="category">用途</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <div data-cross class="chart"></div>
    </el-card>
    <el-card>
      <template #header>时间投资榜（实际观看时长 TOP）</template>
      <el-row :gutter="12">
        <el-col :span="8"><el-card shadow="never"><div data-invest-cat class="chart"></div></el-card></el-col>
        <el-col :span="8"><el-card shadow="never"><div data-invest-tag class="chart"></div></el-card></el-col>
        <el-col :span="8"><el-card shadow="never"><div data-invest-up class="chart"></div></el-card></el-col>
      </el-row>
    </el-card>
  `,
  setup() {
    const interest = ref({ months: [], series: [] });
    const crossDim = ref('tname');
    const persona = ref('');
    const personaLoading = ref(false);
    async function genPersona() {
      personaLoading.value = true;
      try {
        const r = await api('/insights/persona', { method: 'POST' });
        persona.value = r.persona;
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { personaLoading.value = false; }
    }
    function mk(sel, option) {
      const el = document.querySelector(sel);
      if (el) echarts.init(el, 'dark').setOption(option);
    }
    async function loadInterest() {
      interest.value = await api('/insights/interest?months=12').catch(() => ({ months: [], series: [] }));
      nextTick(() => {
        mk('[data-interest]', {
          title: { text: '兴趣漂移', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis', confine: true },
          legend: { type: 'scroll', textStyle: { color: '#999', fontSize: 10 }, top: 0 },
          xAxis: { type: 'category', data: interest.value.months },
          yAxis: { type: 'value' },
          series: interest.value.series.map(s => ({ name: s.tag, type: 'line', stack: 'all', smooth: true, areaStyle: {}, data: s.data })),
        });
      });
    }
    async function loadCross() {
      const d = await api(`/insights/cross?dim=${crossDim.value}`).catch(() => ({ buckets: [], categories: [], matrix: [] }));
      nextTick(() => {
        mk('[data-cross]', {
          title: { text: crossDim.value === 'tname' ? '时段 × 分区' : '时段 × 用途', textStyle: { fontSize: 14 } },
          tooltip: { position: 'top' },
          grid: { left: 90, right: 30, top: 40 },
          xAxis: { type: 'category', data: d.buckets, splitArea: { show: true } },
          yAxis: { type: 'category', data: d.categories, splitArea: { show: true } },
          visualMap: { min: 0, max: Math.max(1, ...d.matrix.flat()), inRange: { color: ['#2a2a2a', '#fb7299'] } },
          series: [{ type: 'heatmap',
                     data: d.buckets.flatMap((b, bi) => d.categories.map((c, ci) => [bi, ci, d.matrix[bi]?.[ci] || 0])) }],
        });
      });
    }
    async function loadInvest() {
      const d = await api('/insights/invest').catch(() => ({ by_category: [], by_tag: [], by_up: [] }));
      const barOpt = (title, list) => ({
        title: { text: title, textStyle: { fontSize: 13 } },
        tooltip: { trigger: 'axis', confine: true, formatter: p => `${p[0].name}<br/>${(p[0].value / 3600).toFixed(1)} 小时` },
        grid: { left: 90, right: 30, top: 30 },
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: list.slice(0, 10).map(x => x.name).reverse(), axisLabel: { fontSize: 10 } },
        series: [{ type: 'bar', data: list.slice(0, 10).map(x => x.seconds).reverse(),
                   itemStyle: { color: '#7ecbf2' }, barMaxWidth: 12 }],
      });
      nextTick(() => {
        mk('[data-invest-cat]', barOpt('按用途', d.by_category));
        mk('[data-invest-tag]', barOpt('按主题', d.by_tag));
        mk('[data-invest-up]', barOpt('按UP主', d.by_up));
      });
    }
    onMounted(() => { loadInterest(); loadCross(); loadInvest(); });
    return { interest, crossDim, loadCross, persona, personaLoading, genPersona };
  },
};

const Overview = {
  props: ['status'],
  template: `
    <h2>概览</h2>
    <div style="margin-bottom:16px">
      <el-button @click="genWeekly" :loading="weeklyLoading" type="primary" plain>生成 AI 周报评价</el-button>
    </div>
    <el-card v-if="weeklyReport" style="margin-bottom:16px">
      <template #header>📋 本周评价</template>
      <div class="weekly-report">{{ weeklyReport }}</div>
    </el-card>
    <el-row :gutter="12" class="cards" style="margin-bottom:16px">
      <el-col :span="3" v-for="k in kpis" :key="k.label">
        <el-card><div class="card-num">{{ k.value }}</div><div class="card-label">{{ k.label }}</div></el-card>
      </el-col>
    </el-row>
    <el-row :gutter="12" class="cards" style="margin-bottom:16px">
      <el-col :span="8"><el-card><div class="card-num">{{ compare.this?.views ?? '-' }}</div><div class="card-label">本月观看（上月 {{ compare.last?.views ?? '-' }}）</div></el-card></el-col>
      <el-col :span="8"><el-card><div class="card-num">{{ compare.this?.days ?? '-' }}</div><div class="card-label">本月活跃天数（上月 {{ compare.last?.days ?? '-' }}）</div></el-card></el-col>
      <el-col :span="8"><el-card><div class="card-num">{{ favGrowthLast }}</div><div class="card-label">本月新增收藏</div></el-card></el-col>
    </el-row>
    <el-row :gutter="12" class="charts">
      <el-col :span="12"><el-card><div data-favgrowth class="chart"></div></el-card></el-col>
      <el-col :span="12"><el-card>
        <template #header>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span>UP主粉丝数（快照）</span>
            <el-button size="small" type="primary" @click="collectFollowers" :loading="followerLoading">采集快照</el-button>
          </div>
        </template>
        <el-table :data="upFollowers" size="small" max-height="240" style="width:100%">
          <el-table-column prop="uname" label="UP主"/>
          <el-table-column label="粉丝数" width="100">
            <template #default="s">{{ fmtNum(s.row.points[s.row.points.length - 1]?.follower) }}</template>
          </el-table-column>
          <el-table-column label="快照" width="70">
            <template #default="s">{{ s.row.points.length }} 次</template>
          </el-table-column>
        </el-table>
      </el-card></el-col>
    </el-row>
    <el-row :gutter="12" class="charts">
      <el-col :span="10"><el-card><div data-monthly class="chart"></div></el-card></el-col>
      <el-col :span="7"><el-card><div data-timebuckets class="chart"></div></el-card></el-col>
      <el-col :span="7"><el-card><div data-topup class="chart"></div></el-card></el-col>
      <el-col :span="8"><el-card><div data-completion class="chart"></div></el-card></el-col>
      <el-col :span="8"><el-card><div data-popularity class="chart"></div></el-card></el-col>
      <el-col :span="8"><el-card><div data-weekend class="chart"></div></el-card></el-col>
    </el-row>
    <el-row :gutter="12" style="margin-top:16px">
      <el-col :span="7"><el-card><div data-catpie class="chart"></div></el-card></el-col>
      <el-col :span="17"><el-card>
        <template #header>视频用途（有用 vs 娱乐）</template>
        <el-tabs v-model="catTab">
          <el-tab-pane :label="'有用 ' + catData.useful.length" name="useful">
            <el-table :data="catData.useful" size="small" max-height="280" style="width:100%">
              <el-table-column prop="title" label="标题" min-width="220"/>
              <el-table-column prop="category" label="类别" width="90"/>
            </el-table>
          </el-tab-pane>
          <el-tab-pane :label="'娱乐 ' + catData.waste.length" name="waste">
            <el-table :data="catData.waste" size="small" max-height="280" style="width:100%">
              <el-table-column prop="title" label="标题" min-width="220"/>
              <el-table-column prop="category" label="类别" width="90"/>
            </el-table>
          </el-tab-pane>
        </el-tabs>
        <div v-if="!(catData.useful.length + catData.waste.length)" class="empty-tip">还没分类数据，去「内容分析」页点分析</div>
      </el-card></el-col>
    </el-row>
    <el-collapse style="margin-top:16px">
      <el-collapse-item title="UP主深度榜（观看时长 TOP）" name="up">
        <el-table :data="upDepth" size="small" style="width:100%">
          <el-table-column prop="up_name" label="UP主" width="160"/>
          <el-table-column prop="views" label="观看次数" width="100"/>
          <el-table-column label="总时长" width="120">
            <template #default="s">{{ (s.row.total_sec / 3600).toFixed(1) }} 小时</template>
          </el-table-column>
          <el-table-column label="最近观看" min-width="140">
            <template #default="s">{{ timeAgo(s.row.last_view) }}</template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
      <el-collapse-item :title="'吃灰收藏明细（' + (graveyardStats.value.total ? graveyardStats.value.graveyard : graveyardItems.length) + ' 个）'" name="gy">
        <el-table :data="graveyardItems" size="small" max-height="360" style="width:100%">
          <el-table-column prop="title" label="标题" min-width="240"/>
          <el-table-column prop="up_name" label="UP主" width="120"/>
          <el-table-column prop="tname" label="分区" width="90"/>
          <el-table-column label="收藏时间" width="150">
            <template #default="s">{{ fmt(s.row.fav_time) }}</template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>
  `,
  setup(props) {
    const profile = ref({});
    const monthly = ref([]);
    const topUps = ref([]);
    const upDepth = ref([]);
    const graveyardItems = ref([]);
    const graveyardStats = ref({ graveyard: 0, total: 0, pct: 0 });
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleDateString('zh-CN') : '';
    function timeAgo(ts) {
      if (!ts) return '';
      const diff = (Date.now() / 1000 - ts);
      if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
      if (diff < 604800) return Math.floor(diff / 86400) + '天前';
      return new Date(ts * 1000).toLocaleDateString('zh-CN');
    }
    const weeklyReport = ref('');
    const weeklyLoading = ref(false);
    async function genWeekly() {
      weeklyLoading.value = true;
      try {
        const r = await api('/report/weekly-ai', { method: 'POST' });
        weeklyReport.value = r.report;
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { weeklyLoading.value = false; }
    }
    const kpis = Vue.computed(() => {
      const p = profile.value;
      const c = props.status.counts || {};
      return [
        { label: '总观看数', value: p.total_views ?? '-' },
        { label: '总时长(小时)', value: p.total_duration_h ?? '-' },
        { label: '活跃天数', value: p.active_days ?? '-' },
        { label: '日均观看', value: p.avg_daily ?? '-' },
        { label: '黄金时段', value: p.peak_hour ?? '-' },
        { label: '最活跃周几', value: p.peak_weekday ?? '-' },
        { label: '收藏数', value: c.favorites ?? '-' },
        { label: '收藏吃灰率', value: graveyardStats.value.total ? graveyardStats.value.pct + '%' : '-' },
      ];
    });
    const catData = ref({ distribution: [], useful: [], waste: [] });
    const catTab = ref('useful');
    const compare = ref({ this: null, last: null, labels: {} });
    const favGrowth = ref([]);
    const upFollowers = ref([]);
    const followerLoading = ref(false);
    const favGrowthLast = Vue.computed(() => {
      const arr = favGrowth.value;
      return arr.length ? arr[arr.length - 1].n : '-';
    });
    function fmtNum(n) { n = n || 0; return n >= 10000 ? (n / 10000).toFixed(1).replace(/\.0$/, '') + '万' : String(n); }
    async function collectFollowers() {
      followerLoading.value = true;
      try {
        const r = await api('/analysis/up-followers', { method: 'POST' });
        upFollowers.value = r.trend;
        ElementPlus.ElMessage.success(`已采集 ${r.collected} 个UP主粉丝数`);
      } catch (e) { ElementPlus.ElMessage.error(e.message); }
      finally { followerLoading.value = false; }
    }
    async function load() {
      const [ov, prof, mo, det, gy, gs, cmp, uf, cat] = await Promise.all([
        api('/stats/overview'), api('/analysis/profile'), api('/analysis/monthly'),
        api('/analysis/detailed'), api('/analysis/graveyard-list'), api('/analysis/graveyard-stats'),
        api('/analysis/compare'), api('/analysis/up-followers'), api('/analysis/category'),
      ]).catch(() => [null, null, [], null, [], null, null, [], null]);
      if (cat) catData.value = cat;
      if (!prof) return;
      profile.value = prof;
      monthly.value = mo;
      topUps.value = ov?.top_ups || [];
      upDepth.value = det?.up_depth || [];
      graveyardItems.value = gy;
      if (gs) graveyardStats.value = gs;
      if (cmp) { compare.value = cmp.compare; favGrowth.value = cmp.fav_growth; }
      upFollowers.value = uf || [];
      nextTick(() => {
        const mk = (sel, option) => {
          const el = document.querySelector(sel);
          if (el) echarts.init(el, 'dark').setOption(option);
        };
        mk('[data-monthly]', {
          title: { text: '月度观看趋势', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis', confine: true },
          xAxis: { type: 'category', data: mo.map(x => x.ym) },
          yAxis: { type: 'value' },
          series: [{ type: 'line', smooth: true, areaStyle: {}, data: mo.map(x => x.n),
                     itemStyle: { color: '#fb7299' } }],
        });
        const pie = (data, sel, title) => mk(sel, pieOption(
          title, data.map(x => ({ name: x.bucket || x.kind, value: x.n }))
        ));
        pie(det?.time_buckets || [], '[data-timebuckets]', '观看时段');
        mk('[data-topup]', {
          title: { text: '常看UP主 TOP', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis', confine: true },
          xAxis: { type: 'value' },
          yAxis: { type: 'category', data: topUps.value.slice(0, 8).map(u => u.up_name), inverse: true },
          series: [{ type: 'bar', data: topUps.value.slice(0, 8).map(u => u.n),
                     itemStyle: { color: '#fb7299' }, barMaxWidth: 14 }],
        });
        pie(det?.completion || [], '[data-completion]', '观看完整度');
        pie(det?.popularity || [], '[data-popularity]', '热门 vs 小众');
        pie(det?.weekday_weekend || [], '[data-weekend]', '工作日 vs 周末');
        mk('[data-favgrowth]', {
          title: { text: '收藏增长趋势', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis', confine: true },
          xAxis: { type: 'category', data: favGrowth.value.map(x => x.ym) },
          yAxis: { type: 'value' },
          series: [{ type: 'line', smooth: true, data: favGrowth.value.map(x => x.n),
                     itemStyle: { color: '#f6c445' } }],
        });
        mk('[data-catpie]', pieOption(
          '视频用途占比', catData.value.distribution.map(x => ({ name: x.category, value: x.n }))
        ));
      });
    }
    onMounted(load);
    return { kpis, compare, favGrowthLast, upFollowers, fmtNum, followerLoading, collectFollowers,
             catData, catTab, upDepth, graveyardItems, graveyardStats, fmt, timeAgo, weeklyReport, weeklyLoading, genWeekly };
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
    <el-card style="max-width:520px;margin-top:16px">
      <template #header>下载</template>
      <el-form :model="dl" label-width="80px" label-position="left">
        <el-form-item label="保存目录">
          <el-input v-model="dl.download_dir" placeholder="留空 = 项目 data/downloads"/>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveDownloadDir">保存</el-button>
          <span style="color:#999;font-size:12px;margin-left:8px">当前：{{ dl.download_dir || '默认 data/downloads' }}</span>
        </el-form-item>
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
      dl.value.download_dir = c.download_dir || '';
    }
    async function saveDownloadDir() {
      await api('/config', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ download_dir: dl.value.download_dir }) });
      ElementPlus.ElMessage.success('下载目录已保存');
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
    const dl = ref({ download_dir: '' });
    const hwLoading = ref(false); const hwModel = ref('');
    const account = ref({ stats: null, coin_log: [] });
    async function loadAccount() {
      try { account.value = await api('/account'); } catch (e) {}
    }
    onMounted(() => { loadConfig().catch(() => {}); loadAccount(); });
    return { qrVisible, qrMsg, syncing, smtp, testing, llm, dl, hwLoading, hwModel, account,
             modelList, modelLoading, installing, ollamaOk, installState, ollamaInstalling,
             fmt, openQr, stopPoll, sync, saveSmtp, testEmail, saveLlm, saveDownloadDir,
             recommendLocal, recommendModels, installModel, installOllama };
  },
};

const ContentBrowser = {
  components: { History, Favorites, Dynamics },
  template: `
    <el-tabs v-model="tab">
      <el-tab-pane label="观看历史" name="history"><History/></el-tab-pane>
      <el-tab-pane label="收藏夹" name="favorites"><Favorites/></el-tab-pane>
      <el-tab-pane label="我的动态" name="dynamics"><Dynamics/></el-tab-pane>
    </el-tabs>
  `,
  setup() { const tab = ref('history'); return { tab }; },
};

const SearchResult = {
  props: ['q'],
  template: `
    <h2>搜索结果：{{ q }}</h2>
    <el-tabs v-model="tab">
      <el-tab-pane :label="'历史（' + counts.history + '）'" name="history">
        <div class="bili-grid">
          <div class="bili-card" v-for="it in history" :key="it.bvid" @click="play(it)">
            <div class="bili-cover">
              <img :src="imgUrl(it.pic)" loading="lazy" decoding="async" :alt="it.title"/>
              <span class="bili-duration">{{ fmtDur(it.duration) }}</span>
            </div>
            <div class="bili-title">{{ it.title }}</div>
            <div class="bili-meta"><span class="bili-up">{{ it.up_name }}</span></div>
          </div>
        </div>
        <div v-if="!history.length" class="empty-tip">无结果</div>
      </el-tab-pane>
      <el-tab-pane :label="'收藏（' + counts.favorites + '）'" name="favorites">
        <div class="bili-grid">
          <div class="bili-card" v-for="it in favorites" :key="it.bvid" @click="play(it)">
            <div class="bili-cover">
              <img :src="imgUrl(it.pic)" loading="lazy" decoding="async" :alt="it.title"/>
            </div>
            <div class="bili-title">{{ it.title }}</div>
            <div class="bili-meta"><span class="bili-up">{{ it.up_name }}</span></div>
          </div>
        </div>
        <div v-if="!favorites.length" class="empty-tip">无结果</div>
      </el-tab-pane>
      <el-tab-pane :label="'关注的UP主（' + counts.followings + '）'" name="followings">
        <el-table :data="followings" style="width:100%">
          <el-table-column prop="uname" label="UP主"/>
          <el-table-column prop="mid" label="UID" width="200"/>
        </el-table>
        <div v-if="!followings.length" class="empty-tip">无结果</div>
      </el-tab-pane>
    </el-tabs>
  `,
  setup(props) {
    const tab = ref('history');
    const history = ref([]); const favorites = ref([]); const followings = ref([]);
    const counts = Vue.computed(() => ({
      history: history.value.length, favorites: favorites.value.length, followings: followings.value.length,
    }));
    function play(it) { if (it.bvid) window.open(`https://www.bilibili.com/video/${it.bvid}`, '_blank'); }
    function fmtNum(n) { n = n || 0; return n >= 10000 ? (n / 10000).toFixed(1).replace(/\.0$/, '') + '万' : String(n); }
    function fmtDur(s) {
      s = s || 0; const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
      const mm = String(m).padStart(2, '0'), ss = String(sec).padStart(2, '0');
      return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
    }
    async function load() {
      const d = await api(`/search?q=${encodeURIComponent(props.q)}`).catch(() => ({ history: [], favorites: [], followings: [] }));
      history.value = d.history; favorites.value = d.favorites; followings.value = d.followings;
    }
    onMounted(load);
    return { tab, history, favorites, followings, counts, play, imgUrl, fmtNum, fmtDur };
  },
};

const App = {
  components: { Overview, ContentBrowser, Monitor, Analysis, Insights, Downloads, SearchResult, Chat, Settings },
  template: `
    <el-container class="layout">
      <el-aside width="220px" class="aside">
        <div class="logo">BiliScope</div>
        <div class="search-box">
          <el-input v-model="searchQ" placeholder="搜索视频 / UP主" clearable @keyup.enter="doSearch">
            <template #prefix><el-icon><Search/></el-icon></template>
          </el-input>
        </div>
        <el-menu :default-active="route" @select="route = $event" class="menu">
          <el-menu-item index="overview"><el-icon><DataLine/></el-icon>概览</el-menu-item>
          <el-menu-item index="insights"><el-icon><TrendCharts/></el-icon>洞察</el-menu-item>
          <el-menu-item index="content"><el-icon><FolderOpened/></el-icon>内容浏览</el-menu-item>
          <el-menu-item index="monitor"><el-icon><Bell/></el-icon>监测中心<el-badge :value="status.alerts_unread || 0" :hidden="!(status.alerts_unread)" class="menu-badge"/></el-menu-item>
          <el-menu-item index="analysis"><el-icon><DataAnalysis/></el-icon>内容分析</el-menu-item>
          <el-menu-item index="downloads"><el-icon><Download/></el-icon>下载管理</el-menu-item>
          <el-menu-item index="chat"><el-icon><ChatDotRound/></el-icon>AI 助手</el-menu-item>
          <el-menu-item index="settings"><el-icon><Setting/></el-icon>设置</el-menu-item>
        </el-menu>
        <div class="account-card" v-if="status.logged_in && accountInfo.stats">
          <img :src="imgUrl(accountInfo.stats.face)" class="account-avatar" alt="头像"/>
          <div class="account-info">
            <div class="account-name">{{ accountInfo.stats.uname }}</div>
            <div class="account-uid">UID {{ status.uid }}</div>
            <div class="account-lv">Lv.{{ accountInfo.stats.level }}
              <el-progress :percentage="lvPct" :show-text="false" :stroke-width="4" style="margin-top:3px"/>
            </div>
            <div class="account-lv-pred">{{ accountInfo.stats.lv_prediction?.text }}</div>
          </div>
        </div>
        <div class="sync-status" v-else>
          <el-tag :type="status.logged_in ? 'success' : 'danger'" size="small">
            {{ status.logged_in ? '已登录' : '未登录' }}
          </el-tag>
        </div>
      </el-aside>
      <el-main>
        <Overview v-if="route === 'overview'" :status="status" @refresh="loadStatus"/>
        <ContentBrowser v-else-if="route === 'content'"/>
        <Monitor v-else-if="route === 'monitor'" :status="status" @refresh="loadStatus"/>
        <Analysis v-else-if="route === 'analysis'"/>
        <Insights v-else-if="route === 'insights'"/>
        <Downloads v-else-if="route === 'downloads'"/>
        <SearchResult v-else-if="route === 'search'" :q="searchQ"/>
        <Chat v-else-if="route === 'chat'"/>
        <Settings v-else-if="route === 'settings'" :status="status" @refresh="loadStatus"/>
      </el-main>
    </el-container>
  `,
  setup() {
    const route = ref('overview');
    const status = ref({ logged_in: false, counts: {} });
    const accountInfo = ref({ stats: null, coin_log: [] });
    const searchQ = ref('');
    function doSearch() {
      const q = searchQ.value.trim();
      if (!q) { ElementPlus.ElMessage.warning('请输入搜索内容'); return; }
      route.value = 'search';
    }
    const lvPct = Vue.computed(() => {
      const s = accountInfo.value.stats;
      if (!s || !s.current_min || !s.next_exp || s.next_exp <= s.current_min) return 0;
      return Math.min(100, Math.round((s.current_exp - s.current_min) / (s.next_exp - s.current_min) * 100));
    });
    async function loadStatus() {
      try { status.value = await api('/status'); } catch (e) {}
      try { accountInfo.value = await api('/account'); } catch (e) {}
    }
    onMounted(loadStatus);
    return { route, status, accountInfo, lvPct, loadStatus, imgUrl, searchQ, doSearch };
  },
};

const app = createApp(App);
for (const [name, comp] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, comp);
}
app.use(ElementPlus).mount('#app');
