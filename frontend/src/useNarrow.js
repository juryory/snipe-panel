import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * 窄屏判断。
 *
 * 后台是按桌面设计的,但管理员会拿手机打开(移动端菜单里就有「后台管理」入口)。
 * el-table 在手机上基本没法用 —— 尤其 fixed 列会盖住整张表。所以窄屏时改渲染
 * 卡片列表,不是靠 CSS 硬压。
 */
export function useNarrow(maxWidth = 768) {
  const narrow = ref(false)
  let mq = null

  const update = (e) => {
    narrow.value = e.matches
  }

  onMounted(() => {
    mq = window.matchMedia(`(max-width: ${maxWidth}px)`)
    narrow.value = mq.matches
    // Safari 14 以下只有 addListener
    if (mq.addEventListener) mq.addEventListener('change', update)
    else mq.addListener(update)
  })

  onBeforeUnmount(() => {
    if (!mq) return
    if (mq.removeEventListener) mq.removeEventListener('change', update)
    else mq.removeListener(update)
  })

  return narrow
}
