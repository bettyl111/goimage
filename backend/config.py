# backend/config.py
import os
from pathlib import Path

# --- 基础配置 ---
# 建议在生产环境中通过环境变量设置敏感信息
SECRET_KEY = os.getenv("GO_IMAGE_SECRET_KEY", "your-default-secret-key-for-dev")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # Token 有效期设置为 24 小时

# --- 文件路径配置 ---
BASE_DIR = Path(__file__).resolve().parent
TEMP_UPLOADS_DIR = BASE_DIR / "temp_uploads"
USER_GENERATED_IMAGES_DIR = BASE_DIR / "user_generated_images"
WORKFLOWS_DIR = BASE_DIR / "workflows"

# ComfyUI目录配置 2023.07.03 14
# 使用环境变量或默认值
COMFYUI_BASE_DIR = Path(os.getenv("COMFYUI_BASE_DIR", str(BASE_DIR / "comfyui")))
COMFYUI_INPUT_DIR = Path(os.getenv("COMFYUI_INPUT_DIR", str(COMFYUI_BASE_DIR / "input")))
COMFYUI_OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", str(COMFYUI_BASE_DIR / "output")))

# ComfyUI安装路径配置 2023.07.04 16
# 使用环境变量或默认值
COMFYUI_PATH = os.getenv("COMFYUI_PATH", "")
# 如果环境变量未设置，尝试常见的安装路径
if not COMFYUI_PATH:
    common_paths = [
        # "/home/user/ComfyUI",  # Linux常见路径
        os.path.expanduser("~/comfy/ComfyUI"),  # 用户主目录
    ]
    
    for path in common_paths:
        if os.path.exists(path) and os.path.exists(os.path.join(path, "main.py")):
            COMFYUI_PATH = path
            print(f"找到ComfyUI安装路径: {COMFYUI_PATH}")
            break

# 如果仍然没有找到，使用默认值
if not COMFYUI_PATH:
    COMFYUI_PATH = str(BASE_DIR.parent / "ComfyUI")
    print(f"未找到ComfyUI安装路径，使用默认值: {COMFYUI_PATH}")

# 确保必要的目录存在
TEMP_UPLOADS_DIR.mkdir(exist_ok=True)
USER_GENERATED_IMAGES_DIR.mkdir(exist_ok=True)
# 创建ComfyUI目录（如果不存在）
try:
    COMFYUI_BASE_DIR.mkdir(exist_ok=True)
    COMFYUI_INPUT_DIR.mkdir(exist_ok=True)
    COMFYUI_OUTPUT_DIR.mkdir(exist_ok=True)
except Exception as e:
    print(f"警告：无法创建ComfyUI目录: {str(e)}")
    # 使用备用目录
    COMFYUI_INPUT_DIR = TEMP_UPLOADS_DIR
    COMFYUI_OUTPUT_DIR = USER_GENERATED_IMAGES_DIR

# 数据库配置
DB_FILE = BASE_DIR / "image_history.db"
USERS_FILE = BASE_DIR / "users.json"

# --- ComfyUI 配置 ---
COMFYUI_API_BASE = os.getenv("COMFYUI_API_BASE", "http://127.0.0.1:8188")
COMFYUI_POLLING_TIMEOUT_SECONDS = 300  # 5分钟超时
COMFYUI_MAX_RETRIES = 3

# --- 任务清理配置  ---
TASK_CLEANUP_INTERVAL = 3600  # 任务清理间隔，默认1小时
TASK_MAX_AGE = 7 * 24 * 3600  # 任务最大保存时间，默认7天
TASK_CLEANUP_BATCH_SIZE = 100  # 每次清理的任务数量

# --- 图生图 (Image-to-Image) 工作流 ---
# flux-image2image.json
IMAGE_TO_IMAGE_WORKFLOW_FILE = WORKFLOWS_DIR / "flux-image2image.json"
I2I_NODE_ID_LOAD_IMAGE = "17"       # 加载输入图像节点
I2I_NODE_ID_PROMPT_TEXT = "256"      # text2
I2I_NODE_ID_IMAGE_STRENGTH = "26"   # FluxGuidance 节点 (用于控制图像强度)
I2I_NODE_ID_KSAMPLER_SEED = "228"   # 'easy seed' 节点
I2I_NODE_ID_SAVE_IMAGE = "255"      # 保存图像节点

# 人脸相关节点ID（根据你的ComfyUI工作流来配置）
# 支持最多2个人脸的节点配置
I2I_FACE_NODE_IDS = {
    "load_face_0": "18",    # 第1个人脸加载节点
    "load_face_1": "19",    # 第2个人脸加载节点
    "face_swap": "20",      # 人脸替换/融合节点
}

# 向后兼容的单个节点ID（保持现有代码正常工作）
I2I_FACE_NODE_ID_LOAD_FACE = I2I_FACE_NODE_IDS["load_face_0"]
I2I_FACE_NODE_ID_FACE_SWAP = I2I_FACE_NODE_IDS["face_swap"]

# --- 文生图 (Text-to-Image) 标准工作流 ---
# flux-text2image.json
TEXT_TO_IMAGE_WORKFLOW_FILE = WORKFLOWS_DIR / "flux-text2image.json"
# T2I_NODE_ID_PROMPT_TEXT = "256"      
# T2I_NODE_ID_EMPTY_LATENT = "258"    # EmptyLatentImage (用于设置图像尺寸)
# T2I_NODE_ID_KSAMPLER_SEED = "228"   # 'easy seed' 节点
# T2I_NODE_ID_SAVE_IMAGE = "255"      # 保存图像节点

# # 文生图人脸相关节点ID（根据你的ComfyUI工作流来配置）
# # 支持最多2个人脸的节点配置
# T2I_FACE_NODE_IDS = {
#     "load_face_0": "270",    # 第1个人脸加载节点
#     "load_face_1": "274",    # 第2个人脸加载节点
#     "face_swap": "23",      # 人脸替换/融合节点
# }

# --- 文生图 (Text-to-Image) 带姿势参考工作流 ---
# flux-text2image-pose.json
TEXT_TO_IMAGE_WITH_POSE_WORKFLOW_FILE = WORKFLOWS_DIR / "flux-text2image-pose.json"
T2I_NODE_ID_PROMPT_TEXT = "256"          
T2I_NODE_ID_EMPTY_LATENT = "258"       # EmptyLatentImage (用于设置图像尺寸)
T2I_NODE_ID_Flux_FORWARD_MODEL = "169"
T2I_NODE_ID_PULID_MODEL1 = "269"   
T2I_NODE_ID_PULID_MODEL2 = "272"   
T2I_NODE_ID_FIRST_BLOCK_MODEL = "195"   
T2I_NODE_ID_KSAMPLER_SEED = "228"        # 'easy seed' 节点
T2I_NODE_ID_LOAD_REFERENCE_IMAGE = "282"  # LoadImage (加载参考姿势图)
T2I_NODE_ID_RESIZE_IMAGE = "325"

T2I_NODE_ID_FLUXGUIDANCE = "26"
T2I_NODE_ID_INSTRUCT = "238"
T2I_NODE_ID_BASIC_GUIDER = "192"

# T2I_NODE_ID_INPUT_RESIZE = "325"
T2I_NODE_ID_SAVE_IMAGE = "255"           # 保存图像节点
T2I_POSE_NODE_ID_SAVE_IMAGE = "255"           # 保存图像节点

T2I_FACE_NODE_IDS = {
    "load_face_0": "270",    # 第1个人脸加载节点
    "load_face_1": "274",    # 第2个人脸加载节点
    "face_swap": "23",      # 人脸替换/融合节点
}

# 向后兼容的单个节点ID（保持现有代码正常工作）
T2I_FACE_NODE_ID_LOAD_IMAGE = T2I_FACE_NODE_IDS["load_face_0"]
T2I_FACE_NODE_ID_FACE_SWAP = T2I_FACE_NODE_IDS["face_swap"]

# # --- 文生图 (Text-to-Image) 标准工作流 ---
# # flux-text2image.json
# TEXT_TO_IMAGE_WORKFLOW_FILE_PATH = os.path.join(WORKFLOW_DIR, "flux-text2image.json")
# T2I_NODE_ID_PROMPT_TEXT = "256"      
# T2I_NODE_ID_EMPTY_LATENT = "258"    # EmptyLatentImage (用于设置图像尺寸)
# T2I_NODE_ID_KSAMPLER_SEED = "228"   # 'easy seed' 节点
# T2I_NODE_ID_SAVE_IMAGE = "255"      # 保存图像节点

# # 文生图人脸相关节点ID（根据你的ComfyUI工作流来配置）
# # 支持最多2个人脸的节点配置
# T2I_FACE_NODE_IDS = {
#     "load_face_0": "270",    # 第1个人脸加载节点
#     "load_face_1": "274",    # 第2个人脸加载节点
#     "face_swap": "23",      # 人脸替换/融合节点
# }

# # --- 文生图 (Text-to-Image) 带姿势参考工作流 ---
# # flux-text2image-pose.json
# TEXT_TO_IMAGE_POSE_WORKFLOW_FILE_PATH = os.path.join(WORKFLOW_DIR, "flux-text2image-pose.json")
# T2I_POSE_NODE_ID_PROMPT_TEXT = "256"          
# T2I_POSE_NODE_ID_EMPTY_LATENT = "258"       # EmptyLatentImage (用于设置图像尺寸)
# T2I_POSE_NODE_ID_KSAMPLER_SEED = "228"        # 'easy seed' 节点
# T2I_POSE_NODE_ID_LOAD_REFERENCE_IMAGE = "17"  # LoadImage (加载参考姿势图)
# T2I_POSE_NODE_ID_SAVE_IMAGE = "255"           # 保存图像节点

# 正式部署域名: ai-image-genneration.3g.net.cn

# 任务队列配置 2023.07.01 10
TASK_QUEUE_CONFIG = {
    'max_concurrent_tasks': 2,  # 最大并发任务数
    'task_timeout': 600,  # 任务超时时间（秒）
    'queue_check_interval': 5,  # 队列检查间隔（秒）
    'max_tasks_per_user': 3,  # 每个用户最大活跃任务数
    'gpu_usage_high_threshold': 90,  # GPU使用率高阈值（%）
    'gpu_memory_high_threshold': 85,  # GPU内存使用率高阈值（%）
    'gpu_usage_normal_threshold': 50,  # GPU使用率正常阈值（%）
    'gpu_memory_normal_threshold': 60,  # GPU内存使用率正常阈值（%）
}

# JWT配置
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-here")  # 在生产环境中必须更改
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24小时

# 任务队列配置
MAX_CONCURRENT_TASKS = 2
MAX_QUEUE_SIZE = 100
MAX_USER_TASKS = 3  # 每个用户的最大任务数

# 日志配置
LOG_FILE = BASE_DIR / "task_queue.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_LEVEL = "INFO"
