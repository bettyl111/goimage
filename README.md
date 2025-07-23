# AI 图像生成器

这是一个利用 AI 模型生成图像的全栈项目。

## 技术栈

-   **前端**: React, Vite, TypeScript, Tailwind CSS
-   **后端**: FastAPI, Python
-   **数据库**: SQLite

## 项目结构

```
.
├── backend/                  # 后端代码
│   ├── app.py                # FastAPI 应用主文件
│   ├── auth.py               # 认证相关逻辑
│   ├── config.py             # 配置文件
│   ├── requirements.txt      # Python 依赖
│   ├── image_history.db      # SQLite 数据库文件
│   ├── users.json            # 用户数据
│   ├── workflows/             # 工作流
│   └── user_generated_images/ # 用户生成的图片
|       
├── frontend/                 # 前端代码
│   ├── src/                  # React 源代码
│   │   ├── components/       # UI 组件
│   │   ├── pages/            # 页面
│   │   └── ...
│   ├── package.json          # Node.js 依赖和脚本
│   └── ...
└── start.sh                  # 项目一键启动脚本
```

## 运行项目

推荐使用项目根目录下的 `start.sh` 脚本一键启动前后端服务。

### 先决条件

-   [Node.js](https://nodejs.org/) 和 [npm](https://www.npmjs.com/)
-   [Conda](https://docs.conda.io/en/latest/miniconda.html)
-   一个名为 `comfyui` 的 Conda 环境

### 启动方法

1.  **赋予脚本执行权限**
    ```bash
    chmod +x start.sh
    ```

2.  **运行脚本**
    ```bash
    ./start.sh
    ```
    该脚本会：
    -   在后台启动前端开发服务器 (默认 Vite 端口)。
    -   激活 `comfyui` Conda 环境。
    -   在前台启动后端 FastAPI 服务器 (`http://localhost:5000`)。

    同时要运行comfyui服务器，运行端口在`http://0.0.0.0:8188`(或修改配置文件)

    要停止所有服务，只需在终端按 `Ctrl+C`。
