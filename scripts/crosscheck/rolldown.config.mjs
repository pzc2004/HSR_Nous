// 对拍驱动打包配置（BACKLOG B22）。
// 用 external/hsr-optimizer 自带的 rolldown 把 crosscheck.mts 与其 TS 源码
// 打成一个无依赖的 ESM 文件；tsconfigFilename 让 `lib/...`、`types/...`
// 路径别名按 optimizer 自己的 tsconfig 解析（paths: { "*": ["./src/*"] }）。
//
// 跑法（仓库根目录）：
//   external/hsr-optimizer/node_modules/.bin/rolldown -c scripts/crosscheck/rolldown.config.mjs
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../..', import.meta.url))

export default {
  input: fileURLToPath(new URL('./crosscheck.mts', import.meta.url)),
  platform: 'node',
  resolve: {
    tsconfigFilename: `${root}/external/hsr-optimizer/tsconfig.json`,
  },
  output: {
    file: fileURLToPath(new URL('./dist/crosscheck.mjs', import.meta.url)),
    format: 'esm',
  },
}
