#!/bin/bash

# 当脚本退出时（包括被Ctrl+C中断），调用cleanup函数
cleanup() {
    echo "正在停止后台服务..."
    # 杀死由该脚本启动的所有子进程
    pkill -P $$
    echo "服务已停止。"
}
trap cleanup EXIT

# 如果任何命令失败，立即退出脚本
set -e

# --- 启动前端 ---
echo "正在启动前端开发服务器 (后台)..."
cd frontend
npm run dev &
cd ..
echo "前端服务已启动。"


# --- 启动后端 ---
echo "正在启动后端服务 (前台)..."
cd backend

echo "正在激活 Conda 环境 'comfyui'..."
# 使用 'eval' 和 'conda shell.bash hook' 是在脚本中激活conda环境的推荐方法
eval "$(conda shell.bash hook)"
conda activate comfyui

echo "Conda 环境已激活。正在启动 Uvicorn 服务器..."
# uvicorn 在前台运行，保持脚本活动。
# 当此命令被中断时，上面的trap会执行。
uvicorn app:app --reload --host 0.0.0.0 --port 5001

echo "脚本执行完毕。" 