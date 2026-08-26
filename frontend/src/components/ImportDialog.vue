<template>
  <!--
    批量导入。分两步:先预演看判定结果,确认无误再落库。
    几百台设备盲导进去,出了错谁也说不清哪些进了哪些没进。
  -->
  <el-dialog
    :model-value="modelValue"
    title="批量导入设备"
    width="760px"
    @update:model-value="(v) => emit('update:modelValue', v)"
    @closed="reset"
  >
    <el-steps :active="step" simple style="margin-bottom: 16px">
      <el-step title="选择文件" />
      <el-step title="核对结果" />
      <el-step title="完成" />
    </el-steps>

    <!-- 第一步 -->
    <template v-if="step === 0">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
        <template #title>
          第一次用请先
          <el-link type="primary" :href="templateUrl" target="_blank" :underline="false">
            下载导入模板
          </el-link>
          。分类必须是系统里已有的分类名称。
        </template>
      </el-alert>

      <el-upload
        drag
        action="#"
        :auto-upload="false"
        :limit="1"
        accept=".xlsx"
        :on-change="onPick"
        :on-remove="() => (file = null)"
        :file-list="fileList"
      >
        <div class="drop">把 .xlsx 文件拖到这里,或<em>点击选择</em></div>
      </el-upload>

      <el-checkbox v-model="createMissingCompanies" style="margin-top: 12px">
        自动创建表格里没见过的采购公司
      </el-checkbox>
      <div class="muted hint">
        不勾的话,采购公司必须先在系统里建好,否则那几行会报错。分类无论如何都不会自动创建
        —— 分类需要编号前缀,打错字会造出垃圾分类。
      </div>
    </template>

    <!-- 第二步 -->
    <template v-else-if="step === 1 && preview">
      <div class="summary">
        <span>共 <b>{{ preview.total }}</b> 行</span>
        <el-tag type="success">可导入 {{ preview.ok_count }}</el-tag>
        <el-tag v-if="preview.error_count" type="danger">有问题 {{ preview.error_count }}</el-tag>
        <el-tag v-if="warningCount" type="warning">提醒 {{ warningCount }}</el-tag>
      </div>

      <el-alert
        v-if="preview.error_count"
        type="error"
        :closable="false"
        show-icon
        :title="`有 ${preview.error_count} 行有问题。导入是全有或全无的 —— 请在表格里改好后重新上传。`"
        style="margin: 12px 0"
      />

      <el-table :data="displayRows" max-height="340" size="small">
        <el-table-column label="行" width="60" prop="row" />
        <el-table-column label="设备名称" min-width="140" prop="name" />
        <el-table-column label="分类" width="90" prop="category" />
        <el-table-column label="编号" width="110">
          <template #default="{ row }">
            <span v-if="row.asset_tag" class="tag">{{ row.asset_tag }}</span>
            <span v-else class="muted">自动生成</span>
          </template>
        </el-table-column>
        <el-table-column label="判定" min-width="260">
          <template #default="{ row }">
            <div v-for="(e, i) in row.errors" :key="`e${i}`" class="err">{{ e }}</div>
            <div v-for="(w, i) in row.warnings" :key="`w${i}`" class="warn">{{ w }}</div>
            <span v-if="!row.errors.length && !row.warnings.length" class="muted">正常</span>
          </template>
        </el-table-column>
      </el-table>

      <el-checkbox v-if="preview.error_count" v-model="onlyProblems" style="margin-top: 8px">
        只看有问题的行
      </el-checkbox>
    </template>

    <!-- 第三步 -->
    <template v-else-if="step === 2 && preview">
      <el-result icon="success" :title="`已导入 ${preview.ok_count} 台设备`">
        <template #sub-title>
          <div>编号已自动分配。接下来可以勾选这批设备导出编号 CSV,拿去标签机打标签。</div>
        </template>
      </el-result>
      <el-table :data="preview.rows" max-height="260" size="small">
        <el-table-column label="编号" width="120">
          <template #default="{ row }"><span class="tag">{{ row.asset_tag }}</span></template>
        </el-table-column>
        <el-table-column label="设备名称" prop="name" />
        <el-table-column label="分类" prop="category" width="100" />
      </el-table>
    </template>

    <template #footer>
      <template v-if="step === 0">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" :disabled="!file" :loading="busy" @click="doPreview">
          下一步:核对
        </el-button>
      </template>
      <template v-else-if="step === 1">
        <el-button @click="step = 0">上一步</el-button>
        <el-button
          type="primary"
          :disabled="preview.error_count > 0 || preview.ok_count === 0"
          :loading="busy"
          @click="doImport"
        >
          确认导入 {{ preview.ok_count }} 台
        </el-button>
      </template>
      <el-button v-else type="primary" @click="emit('update:modelValue', false)">完成</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { api, toast } from '../api'

defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue', 'done'])

const templateUrl = api.importTemplateUrl()

const step = ref(0)
const file = ref(null)
const fileList = ref([])
const createMissingCompanies = ref(false)
const preview = ref(null)
const busy = ref(false)
const onlyProblems = ref(true)

const warningCount = computed(
  () => (preview.value ? preview.value.rows.filter((r) => r.warnings.length).length : 0),
)
const displayRows = computed(() => {
  if (!preview.value) return []
  if (onlyProblems.value && preview.value.error_count) {
    return preview.value.rows.filter((r) => !r.ok)
  }
  return preview.value.rows
})

function onPick(picked) {
  file.value = picked.raw
  fileList.value = [picked]
}

function reset() {
  step.value = 0
  file.value = null
  fileList.value = []
  preview.value = null
  onlyProblems.value = true
}

async function doPreview() {
  busy.value = true
  try {
    preview.value = await api.importAssets(file.value, {
      commit: false,
      createMissingCompanies: createMissingCompanies.value,
    })
    step.value = 1
  } catch (err) {
    toast(err)
  } finally {
    busy.value = false
  }
}

async function doImport() {
  busy.value = true
  try {
    // 重新上传同一个文件:预演不留服务端状态,导入时后端会再校验一遍
    preview.value = await api.importAssets(file.value, {
      commit: true,
      createMissingCompanies: createMissingCompanies.value,
    })
    ElMessage.success(`已导入 ${preview.value.ok_count} 台`)
    step.value = 2
    emit('done')
  } catch (err) {
    toast(err)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.drop { padding: 40px 20px; color: #606266; }
.drop em { color: var(--el-color-primary); font-style: normal; }
.hint { font-size: 12px; line-height: 1.7; margin-top: 8px; }
.summary { display: flex; align-items: center; gap: 10px; }
.tag { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.err { color: #f56c6c; line-height: 1.6; }
.warn { color: #e6a23c; line-height: 1.6; }
</style>
