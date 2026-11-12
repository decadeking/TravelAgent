# 旅智者 TravelAgent · 前端

交互式旅行规划智能体的 Vue 3 前端（Vue 3 + Vite + TypeScript + Pinia + Vue Router + Axios）。

## 环境要求

- Node.js ≥ 18（开发环境使用 Node v24）
- 后端服务运行在 `http://127.0.0.1:8000`

## 启动方式

```bash
npm install
npm run dev
```

开发服务器地址：`http://127.0.0.1:5173`

开发环境下 `/api` 已通过 Vite 代理转发到 `http://127.0.0.1:8000`，无需额外配置跨域。

## 构建

```bash
npm run build      # 类型检查 + 生产构建，产物输出到 dist/
npm run preview    # 本地预览构建产物
```

## 目录结构

```
src/
├── api/          # Axios 实例与各服务接口封装
├── components/   # 通用组件（布局、侧边栏、头像菜单、工具卡片、行程预览等）
├── router/       # 路由与登录守卫
├── stores/       # Pinia 状态（鉴权）
├── styles/       # 全局样式与设计变量
├── types/        # 与后端契约对应的 TypeScript 类型
├── utils/        # SSE 流式解析、格式化工具
└── views/        # 页面：登录 / 行程列表 / 规划对话 / 行程详情 / 个人中心
```

## 页面

- `/login` 登录与注册（Tab 切换）
- `/trips` 行程列表（默认首页）
- `/plan` 规划对话（左侧对话流 + 右侧行程实时预览）
- `/trips/:id` 行程详情
- `/profile` 个人中心（偏好管理 / Token 用量 / 历史会话）

## SSE 说明

`/api/agent/chat` 需要 POST + `Authorization` 头，原生 `EventSource` 不支持，
因此由 `src/utils/sse.ts` 使用原生 `fetch` + `ReadableStream` 手动解析 SSE 事件流。
