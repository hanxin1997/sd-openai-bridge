```markdown
# 🌉 SD-OpenAI Bridge

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-green.svg)](docker-compose.yml)

**SD-OpenAI Bridge** 是一个轻量级的 API 转换中间件。它将标准的 **Stable Diffusion API** (SD WebUI 格式) 请求拦截并转换为 **OpenAI Chat Completions API** 格式。

这个项目的主要目的是让仅支持 SD 协议的前端应用（如 **SillyTavern / 酒馆**）能够使用支持 OpenAI 格式的图像生成服务（如 DALL-E 3、`img-router` 或其他兼容 OpenAI 接口的生图服务）。

## ✨ 核心功能

- **🔄 协议转换**：将 SD 的 `txt2img` 和 `img2img` 请求转换为 OpenAI `/v1/chat/completions` 请求。
- **⚖️ 负载均衡与轮询**：支持配置多个上游 API 端点，支持按请求次数轮询切换。
- **🛡️ 故障自动熔断**：自动检测上游 API 失败情况，连续失败达到阈值后暂时封禁该节点，自动切换到下一个可用节点。
- **🖥️ 可视化管理界面**：提供直观的 Web UI，用于添加/删除 API、查看实时日志、监控额度及状态。
- **📝 提示词优化**：自动处理 Negative Prompt（负面提示词），将其转换为自然语言描述（如 `--no ...`）发送给上游。
- **🐳 Docker 部署**：开箱即用，一键部署。

## 🛠️ 安装与部署

### 前置要求

- [Docker](https://www.docker.com/)
- [Docker Compose](https://docs.docker.com/compose/)

### 1. 克隆项目

```bash
git clone https://github.com/hanxin1997/sd-openai-bridge.git
cd sd-openai-bridge
```

### 2. 启动服务

```bash
docker-compose up -d --build
```

启动完成后，服务将监听以下端口：
- **前端管理 UI**: `http://localhost:3000`
- **SD 兼容 API**: `http://localhost:7860`

## ⚙️ 配置指南

### 1. 添加上游 API

1. 浏览器访问 `http://localhost:3000`。
2. 点击右上角的 **"➕ 添加"** 按钮。
3. 填写上游服务信息：
   - **名称**: 给 API 起个名字（如 `Img-Router`）。
   - **API地址**: 填写 OpenAI 兼容的接口地址（例如：`http://your-upstream-service/v1/chat/completions`）。
   - **API Key**: 上游服务的鉴权密钥（Bearer Token）。
   - **模型**: 上游服务支持的模型名称（如 `z-image-turbo`, `dall-e-3`）。
4. 点击 **"保存"**。

### 2. 全局设置

在 **"⚙️ 设置"** 标签页中，您可以配置：
- **轮询策略**：每个 API 成功多少次后切换。
- **熔断机制**：连续失败多少次后封禁该 API。
- **超时设置**：请求的最大等待时间。

## 🔌 对接酒馆 (SillyTavern)

1. 打开 SillyTavern。
2. 进入 **扩展 (Extensions)** -> **图像生成 (Image Generation)**。
3. **来源 (Source)** 选择 `Stable Diffusion WebUI (Automatic1111)`。
4. **API URL** 填写本服务的地址：
   ```
   http://127.0.0.1:7860
   ```
   *(如果部署在服务器上，请将 127.0.0.1 替换为服务器 IP)*
5. 点击 **Connect**。
6. 连接成功后，您就可以像使用本地 SD 一样使用 OpenAI 格式的生图服务了。

## 📂 项目结构

```
.
├── app/
│   ├── main.py          # FastAPI 主程序
│   ├── config.py        # 配置管理与数据模型
│   ├── converter.py     # 核心协议转换逻辑
│   └── logger.py        # 日志系统
├── frontend/            # Web 管理界面源码
│   └── index.html
├── data/                # 持久化数据 (配置与日志)
├── docker-compose.yml   # Docker 编排文件
├── Dockerfile           # 构建文件
└── requirements.txt     # Python 依赖
```

## ⚠️ 注意事项

- 本项目本身不提供图像生成功能，它只是一个**代理/网关**，你需要拥有可用的上游 OpenAI 格式生图 API（例如搭建了 `img-router` 或拥有 DALL-E API 权限）。
- `img2img` 功能会将图片转换为 Base64 格式并通过 Vision 协议发送给上游，请确保上游模型支持图片输入。

## 🤝 贡献

欢迎分支，不用找作者和提问题，作者不会编程，全程ai写的，反正能跑。原本就是因为酒馆的文生图不支持这个格式，只好大力出奇迹了。
