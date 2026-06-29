<template>
  <div ref="chartRef" class="kline-chart" :style="{ height: height }"></div>
</template>

<script setup>
import { ref, onMounted, watch, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
  markDate: { type: String, default: null },
  stockName: { type: String, default: '' },
  height: { type: String, default: '400px' },
})

const chartRef = ref(null)
let chart = null
let resizeObserver = null

function initChart() {
  if (!chartRef.value) return
  if (chart) {
    chart.dispose()
    chart = null
  }

  chart = echarts.init(chartRef.value)
  updateChart()
}

function updateChart() {
  if (!chart) return

  if (!props.data?.length) {
    chart.clear()
    chart.setOption({
      title: { text: '暂无K线数据', left: 'center', top: 'center', textStyle: { color: '#999', fontSize: 14 } },
    })
    return
  }

  const dates = props.data.map(d => d.date)
  const ohlc = props.data.map(d => [d.open, d.close, d.low, d.high])
  const volumes = props.data.map(d => d.volume)

  // 检查 markDate 是否在数据日期范围内
  let validMarkDate = null
  if (props.markDate) {
    const markDateStr = String(props.markDate)
    if (dates.includes(markDateStr)) {
      validMarkDate = markDateStr
    } else {
      // 找最接近的日期
      const markTs = new Date(markDateStr).getTime()
      let closest = dates[0]
      let minDiff = Infinity
      for (const d of dates) {
        const diff = Math.abs(new Date(d).getTime() - markTs)
        if (diff < minDiff) {
          minDiff = diff
          closest = d
        }
      }
      if (minDiff < 7 * 24 * 3600 * 1000) {
        validMarkDate = closest
      }
    }
  }

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    grid: [
      { left: '8%', right: '4%', top: '12%', height: '55%' },
      { left: '8%', right: '4%', top: '75%', height: '15%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        gridIndex: 0,
        axisLabel: { color: '#666', rotate: 30, fontSize: 10 },
        axisLine: { lineStyle: { color: '#ccc' } },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 1,
        axisLabel: { show: false },
        axisLine: { lineStyle: { color: '#ccc' } },
      },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        scale: true,
        axisLabel: { color: '#666' },
        splitLine: { lineStyle: { color: '#eee' } },
      },
      {
        type: 'value',
        gridIndex: 1,
        axisLabel: { color: '#999', fontSize: 10 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: ohlc,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: '#ef5350',
          color0: '#26a69a',
          borderColor: '#ef5350',
          borderColor0: '#26a69a',
        },
        markLine: validMarkDate ? {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#4caf50', type: 'dashed', width: 2 },
          data: [{
            xAxis: validMarkDate,
            label: {
              formatter: `大V集中提及\n${validMarkDate}`,
              position: 'start',
              color: '#4caf50',
              fontSize: 11,
            },
          }],
        } : undefined,
      },
      {
        name: '成交量',
        type: 'bar',
        data: volumes,
        xAxisIndex: 1,
        yAxisIndex: 1,
        itemStyle: {
          color: (params) => {
            const item = ohlc[params.dataIndex]
            return item ? (item[1] > item[0] ? '#ef5350' : '#26a69a') : '#999'
          },
        },
      },
    ],
  }

  chart.setOption(option, true)
}

function handleResize() {
  if (chart && chartRef.value) {
    chart.resize()
  }
}

watch(() => props.data, () => {
  nextTick(() => updateChart())
}, { deep: true })

watch(() => props.markDate, () => {
  nextTick(() => updateChart())
})

watch(() => props.stockName, () => {
  nextTick(() => updateChart())
})

onMounted(() => {
  nextTick(() => {
    initChart()
  })
  window.addEventListener('resize', handleResize)
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => {
      handleResize()
    })
    resizeObserver.observe(chartRef.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.kline-chart {
  width: 100%;
  min-height: 200px;
}
</style>
