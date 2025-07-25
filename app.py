"""
FastAPI 异步图像生成服务

注意：由于图像生成过程可能需要较长时间，建议在Nginx配置中增加以下设置：

```nginx
http {
    # 增加超时设置
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
    
    # 增加上传文件大小限制
    client_max_body_size 20M;
    
    # 其他配置...
}
```

这样可以避免在处理大文件或长时间运行的任务时出现504 Gateway Timeout错误。
"""

from fastapi import FastAPI, HTTPException, Depends, status, Request, File, UploadFile, Form, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import jwt
import datetime
import logging
import uvicorn # 用于本地运行
import uuid
import json
import requests # 用于调用 ComfyUI API
import time
import aiofiles # 用于异步文件操作
import os
import random # 用于 KSampler seed
import asyncio # 用于轮询时的 sleep
import shutil # 用于移动文件
import sqlite3
from auth import UserManager
import config # 导入配置文件
from fastapi.staticfiles import StaticFiles # 确保只导入一次
from collections import defaultdict
from backend.task_queue import Task, get_task_queue  # 导入任务队列模块

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 创建FastAPI应用，设置API前缀为空
app = FastAPI(docs_url="/docs", redoc_url="/redoc")

# 初始化任务队列
task_queue = get_task_queue()

# 添加全局任务状态管理
# 任务状态：pending, processing, completed, failed
task_status = {}
task_results = {}
task_timestamps = {}  # 添加时间戳记录
next_task_id = 1  # 添加简单数字ID计数器

# 添加任务状态模型
class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: Optional[float] = None
    message: Optional[str] = None
    result: Optional[Dict] = None
    queue_position: Optional[int] = None  # 队列位置
    estimated_wait_seconds: Optional[int] = None  # 预计等待时间

# 添加用户任务模型
class UserTask(BaseModel):
    task_id: str
    status: str
    prompt: str
    creation_time: float
    completion_time: Optional[float] = None
    image_url: Optional[str] = None
    generation_type: str
    queue_position: Optional[int] = None  # 队列位置
    estimated_wait_seconds: Optional[int] = None  # 预计等待时间
    progress: Optional[float] = None  # 任务进度

# 添加任务记录到数据库
user_tasks = {}  # 用户ID -> 任务列表的映射

# --- Helper 函数: 用户目录名生成 ---
def get_user_directory_name(current_user: Dict, record_user_email: Optional[str] = None) -> str:
    """
    统一的用户目录名生成逻辑
    
    规则：
    1. 域账号用户：直接使用域用户名（如 'aaa'）
    2. 邮箱用户：使用邮箱转换格式（如 'aaa@mail.com' -> 'aaa_at_mail_dot_com'）
    3. 历史记录兼容：如果记录中的user_email与当前用户不同类型，使用记录的格式
    
    Args:
        current_user: 当前登录用户信息
        record_user_email: 历史记录中的用户邮箱（用于兼容性处理）
    
    Returns:
        用户目录名字符串
    """
    user_email = current_user["email"]
    username = current_user.get("username", user_email)
    user_role = current_user.get("role", "user")
    
    # 如果提供了历史记录的用户邮箱，需要检查兼容性
    if record_user_email:
        # 如果当前用户是域账号，但历史记录是邮箱格式
        if user_role == "domain_user" and "@" in record_user_email:
            # 检查是否是同一个用户的不同登录方式
            domain_name = username
            email_prefix = record_user_email.split("@")[0]
            
            if domain_name == email_prefix:
                # 同一个用户，使用邮箱格式（向后兼容）
                return record_user_email.replace('@', '_at_').replace('.', '_dot_')
            else:
                # 不同用户，使用当前用户的格式
                return username if user_role == "domain_user" else record_user_email.replace('@', '_at_').replace('.', '_dot_')
        
        # 如果当前用户是邮箱，但历史记录是域账号格式
        elif user_role != "domain_user" and "@" not in record_user_email:
            # 检查是否是同一个用户的不同登录方式
            email_prefix = user_email.split("@")[0]
            
            if email_prefix == record_user_email:
                # 同一个用户，使用域账号格式（保持一致性）
                return record_user_email
            else:
                # 不同用户，使用当前用户的格式
                return user_email.replace('@', '_at_').replace('.', '_dot_')
    
    # 标准处理逻辑
    if user_role == "domain_user":
        # 域账号用户：直接使用域用户名
        return username
    else:
        # 邮箱用户：转换邮箱格式
        return user_email.replace('@', '_at_').replace('.', '_dot_')

# CORS 中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
       "http://ai-image-generation.3g.net.cn",
        "https://ai-image-generation.3g.net.cn",
        "http://localhost:5173",  # Vite开发服务器
        "http://127.0.0.1:5173",  # Vite开发服务器
        "http://192.168.0.241:5173",  # 局域网IP Vite
        "http://192.168.0.241:8080",  # 局域网IP 生产
        "http://localhost:8080",  # 本地生产
        "http://127.0.0.1:8080",  # 本地生产
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

user_manager = UserManager()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

class CompanyLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Dict # 包含用户信息，如 email 和 role

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

# 使用config中的值
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
os.makedirs(config.USER_IMAGES_BASE_DIR, exist_ok=True)


# --- 初始化数据库 ---
def init_db():
    conn = sqlite3.connect(config.DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS image_generations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL,
        prompt TEXT NOT NULL,
        image_filename TEXT NOT NULL, -- ComfyUI output 目录中的文件名
        generation_type TEXT, -- New column: 'text-to-image' or 'image-to-image'
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    # Add column if it doesn't exist, for existing databases
    try:
        cursor.execute("ALTER TABLE image_generations ADD COLUMN generation_type TEXT")
        conn.commit()
        logger.info("Column 'generation_type' added to 'image_generations' table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.info("Column 'generation_type' already exists in 'image_generations' table.")
        else:
            raise # Re-raise other operational errors
    conn.commit()
    conn.close()

init_db() # 应用启动时初始化数据库

# --- Pydantic 模型 ---
class ImageGenerationRequest(BaseModel):
    prompt: str
    image_strength: str

class TextToImageRequest(BaseModel):
    prompt: str
    size: str

class ImageGenerationResponse(BaseModel):
    message: str
    image_url: Optional[str] = None
    history_id: Optional[int] = None

class HistoryEntry(BaseModel):
    id: int
    user_email: str
    prompt: str
    image_filename: str
    generation_type: Optional[str] = None
    timestamp: str
    image_url: str

# --- Helper 函数: 与 ComfyUI 交互 ---
def modify_comfyui_workflow(workflow_json_path: str, input_image_path: str, prompt: str, image_strength: str, face_files: Optional[list] = None) -> dict:
    with open(workflow_json_path, 'r') as f:
        workflow = json.load(f)

    if config.I2I_NODE_ID_LOAD_IMAGE in workflow:
        workflow[config.I2I_NODE_ID_LOAD_IMAGE]["inputs"]["image"] = os.path.basename(input_image_path)
    else:
        logger.warning(f"图生图工作流 {workflow_json_path} 中未找到加载图像节点 '{config.I2I_NODE_ID_LOAD_IMAGE}'")

    if config.I2I_NODE_ID_PROMPT_TEXT in workflow:
        if prompt:
            workflow[config.I2I_NODE_ID_PROMPT_TEXT]["inputs"]["text"] = prompt # Assuming positive prompt
        else:
            workflow[config.I2I_NODE_ID_PROMPT_TEXT]["inputs"]["text"] = "" 
    else:
        logger.warning(f"图生图工作流 {workflow_json_path} 中未找到提示词节点 '{config.I2I_NODE_ID_PROMPT_TEXT}'")
    
    if config.I2I_NODE_ID_IMAGE_STRENGTH in workflow and \
       "inputs" in workflow[config.I2I_NODE_ID_IMAGE_STRENGTH] and \
       "image_strength" in workflow[config.I2I_NODE_ID_IMAGE_STRENGTH]["inputs"]:
        workflow[config.I2I_NODE_ID_IMAGE_STRENGTH]["inputs"]["image_strength"] = image_strength
    else:
        logger.warning(f"图生图工作流 {workflow_json_path} 中未找到图像强度节点 '{config.I2I_NODE_ID_IMAGE_STRENGTH}' 或其 'image_strength' 输入。")

    if config.I2I_NODE_ID_KSAMPLER_SEED in workflow:
        workflow[config.I2I_NODE_ID_KSAMPLER_SEED]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
    else:
        logger.warning(f"图生图工作流 {workflow_json_path} 中未找到种子节点 '{config.I2I_NODE_ID_KSAMPLER_SEED}'")
    
    # 处理人脸文件（如果提供了的话）
    if face_files and len(face_files) > 0:
        # 获取人脸相关节点ID（需要在config中配置）
        face_node_ids = getattr(config, 'I2I_FACE_NODE_IDS', {})
        
        if face_node_ids:
            for i, face_file in enumerate(face_files):
                if i < 5:  # 最多支持5个人脸
                    face_load_node_id = face_node_ids.get(f"load_face_{i}")
                    if face_load_node_id and face_load_node_id in workflow:
                        workflow[face_load_node_id]["inputs"]["image"] = os.path.basename(face_file)
                        logger.info(f"人脸文件 {i+1} '{os.path.basename(face_file)}' 已设置到加载节点 '{face_load_node_id}'")
                    elif face_load_node_id:
                        logger.warning(f"图生图工作流 {workflow_json_path} 中未找到人脸图像加载节点 '{face_load_node_id}'. 人脸文件 {i+1} 可能不会生效。")
                    else:
                        logger.warning(f"未配置人脸图像加载节点ID (I2I_FACE_NODE_IDS.load_face_{i})，人脸文件 {i+1} 将被忽略。")
                
            # 配置人脸替换/融合节点（如果配置了的话）
            face_swap_node_id = face_node_ids.get("face_swap")
            if face_swap_node_id and face_swap_node_id in workflow:
                workflow[face_swap_node_id]["inputs"]["enabled"] = True
                logger.info(f"人脸替换节点 '{face_swap_node_id}' 已启用")
                
            logger.info(f"为图生图工作流添加 {len(face_files)} 个人脸文件")
        else:
            # 向后兼容：使用旧的单个节点配置
            if config.I2I_FACE_NODE_ID_LOAD_FACE in workflow:
                workflow[config.I2I_FACE_NODE_ID_LOAD_FACE]["inputs"]["image"] = os.path.basename(face_files[0])
                logger.info(f"使用向后兼容模式：人脸文件 '{os.path.basename(face_files[0])}' 已设置到节点 '{config.I2I_FACE_NODE_ID_LOAD_FACE}'")
            
            if config.I2I_FACE_NODE_ID_FACE_SWAP in workflow:
                workflow[config.I2I_FACE_NODE_ID_FACE_SWAP]["inputs"]["enabled"] = True
                logger.info(f"使用向后兼容模式：人脸替换节点 '{config.I2I_FACE_NODE_ID_FACE_SWAP}' 已启用")
        
    return workflow

def calculate_dimensions(aspect_ratio_str: str, longest_edge: int = 1024) -> tuple[int, int]:
    try:
        ar_w, ar_h = map(int, aspect_ratio_str.split(':'))
        if ar_w <= 0 or ar_h <= 0:
            raise ValueError("Aspect ratio parts must be positive")
    except ValueError as e:
        logger.error(f"无法解析长宽比字符串: '{aspect_ratio_str}'. 错误: {e}. 使用默认 1:1.")
        ar_w, ar_h = 1, 1 # Default to 1:1 on error

    if ar_w == ar_h:
        width = longest_edge
        height = longest_edge
    elif ar_w > ar_h: # Landscape or square
        width = longest_edge
        height = int(round(longest_edge * (ar_h / ar_w)))
    else: # Portrait
        height = longest_edge
        width = int(round(longest_edge * (ar_w / ar_h)))

    # Ensure dimensions are multiples of 8 (common for diffusion models)
    # And not zero if original calculation was too small (e.g. very extreme aspect ratio and small longest_edge)
    width = max(64, int(round(width / 8.0) * 8))
    height = max(64, int(round(height / 8.0) * 8))
    
    logger.info(f"根据长宽比 '{aspect_ratio_str}' 和最长边 {longest_edge} 计算出尺寸: {width}x{height}")
    return width, height

def modify_text_to_image_workflow(
    workflow_json_path: str, 
    prompt: str, 
    aspect_ratio: str, # Changed from size
    reference_image_filename: Optional[str] = None,
    face_image_filenames: Optional[list[str]] = None
) -> dict:
    with open(workflow_json_path, 'r') as f:
        workflow = json.load(f)

    is_pose_workflow = reference_image_filename is not None
    has_face_images = face_image_filenames is not None and len(face_image_filenames) > 0
    actual_width, actual_height = calculate_dimensions(aspect_ratio_str=aspect_ratio, longest_edge=1024)

    prompt_node_id = config.T2I_NODE_ID_PROMPT_TEXT
    empty_latent_node_id = config.T2I_NODE_ID_EMPTY_LATENT
    flux_forward_model_node_id = config.T2I_NODE_ID_Flux_FORWARD_MODEL
    pulid1_node_id = config.T2I_NODE_ID_PULID_MODEL1
    pulid2_node_id = config.T2I_NODE_ID_PULID_MODEL2
    first_block_node_id = config.T2I_NODE_ID_FIRST_BLOCK_MODEL
    ksampler_seed_node_id = config.T2I_NODE_ID_KSAMPLER_SEED
    load_ref_image_node_id = config.T2I_NODE_ID_LOAD_REFERENCE_IMAGE
    resize_ref_image_node_id = config.T2I_NODE_ID_RESIZE_IMAGE
    # input_resize_node_id = config.T2I_NODE_ID_INPUT_RESIZE

    flux_clip_node_id = config.T2I_NODE_ID_FLUXGUIDANCE
    instruct_node_id = config.T2I_NODE_ID_INSTRUCT
    basic_guider_node_id = config.T2I_NODE_ID_BASIC_GUIDER

    if '<english>' in prompt: 
        workflow["23"]["inputs"]['text'][0] = "257"
        prompt = prompt.replace('<english>','')
    else:
        workflow["23"]["inputs"]['text'][0] = "256"

    logger.info(prompt)


    if prompt_node_id in workflow:
        workflow[prompt_node_id]["inputs"]["text"] = prompt
    else:
        logger.warning(f"文生图工作流 {workflow_json_path} 中未找到提示词节点 '{prompt_node_id}'")

    if ksampler_seed_node_id in workflow:
        workflow[ksampler_seed_node_id]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
    else:
        logger.warning(f"文生图工作流 {workflow_json_path} 中未找到种子节点 '{ksampler_seed_node_id}'")

    # 处理参考图片
    if is_pose_workflow:
        workflow[basic_guider_node_id]["inputs"]['conditioning'][0] = instruct_node_id # p2p controlnet
    else:
        workflow[basic_guider_node_id]["inputs"]['conditioning'][0] = flux_clip_node_id
        reference_image_filename = os.path.join(config.COMFYUI_INPUT_DIR, '00012.jpg') # init empty image


    if load_ref_image_node_id in workflow:
        workflow[load_ref_image_node_id]["inputs"]["image"] = reference_image_filename
        logger.info(f"参考图像 '{reference_image_filename}' 已设置到加载节点 '{load_ref_image_node_id}'")
        
        if resize_ref_image_node_id and resize_ref_image_node_id in workflow:
            try:
                workflow[resize_ref_image_node_id]["inputs"]["width"] = actual_width
                workflow[resize_ref_image_node_id]["inputs"]["height"] = actual_height
                logger.info(f"参考图像缩放节点 '{resize_ref_image_node_id}' 尺寸设置为: {actual_width}x{actual_height}")
            except KeyError as e:
                logger.warning(f"姿势参考工作流 {workflow_json_path} 中参考图像缩放节点 '{resize_ref_image_node_id}' 缺少 width/height 输入: {e}")
        elif resize_ref_image_node_id:
             logger.warning(f"姿势参考工作流 {workflow_json_path} 中未找到已配置的参考图像缩放节点 '{resize_ref_image_node_id}'.")
    else:
        logger.warning(f"姿势参考工作流 {workflow_json_path} 中未找到参考图像加载节点 '{load_ref_image_node_id}'. 参考图像可能不会生效。")


    if 'nsfw' in prompt[:10]: #set nsfw lora
        workflow["244"]["inputs"]['lora_03'] = "NSFW_master.safetensors"
        workflow["244"]["inputs"]['strength_03'] = 0.8
        workflow["244"]["inputs"]['lora_02'] = "feet_fetish_LoRA__for_Flux.safetensors"
        workflow["244"]["inputs"]['strength_02'] = 1.0
    else:
        workflow["244"]["inputs"]['lora_03'] = "None"

    if '<zilcova>' in prompt: #set id lora
        workflow["244"]["inputs"]['lora_04'] = "flux-zilcova.safetensors"
        workflow["244"]["inputs"]['strength_04'] = 1.2
    elif '<merry>' in prompt: #set id lora
        workflow["244"]["inputs"]['lora_04'] = "merry.safetensors"
        workflow["244"]["inputs"]['strength_04'] = 1.0
    else:
        workflow["244"]["inputs"]['lora_04'] = "None"

    

    

    # 处理人脸图片
    if has_face_images:
        # 获取人脸相关节点ID（需要在config中配置）
        face_node_ids = getattr(config, 'T2I_FACE_NODE_IDS', {})
        logger.info(f'face count {len(face_image_filenames)}')

        if len(face_image_filenames) == 0:
            workflow[first_block_node_id]["inputs"]['model'][0] = flux_forward_model_node_id
        elif len(face_image_filenames) == 1:
            workflow[first_block_node_id]["inputs"]['model'][0] = pulid1_node_id
        elif len(face_image_filenames) == 2:
            workflow[first_block_node_id]["inputs"]['model'][0] = pulid2_node_id

        
        
        if face_node_ids:
            for i, face_filename in enumerate(face_image_filenames):
                face_load_node_id = face_node_ids.get(f"load_face_{i}")
                if face_load_node_id and face_load_node_id in workflow:
                    workflow[face_load_node_id]["inputs"]["image"] = face_filename
                    logger.info(f"人脸图像 {i+1} '{face_filename}' 已设置到加载节点 '{face_load_node_id}'")
                elif face_load_node_id:
                    logger.warning(f"文生图工作流 {workflow_json_path} 中未找到人脸图像加载节点 '{face_load_node_id}'. 人脸图像 {i+1} 可能不会生效。")
                else:
                    logger.warning(f"未配置人脸图像加载节点ID (T2I_FACE_NODE_IDS.load_face_{i})，人脸图像 {i+1} 将被忽略。")
        else:
            logger.warning("未配置人脸节点ID字典 (T2I_FACE_NODE_IDS)，所有人脸图像将被忽略。")
    else:
        workflow[first_block_node_id]["inputs"]['model'][0] = flux_forward_model_node_id

    return workflow

async def queue_prompt_comfyui(workflow: dict):
    try:
        response = requests.post(f"{config.COMFYUI_URL}/prompt", json={"prompt": workflow})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"ComfyUI API /prompt 调用失败: {e}")
        raise HTTPException(status_code=503, detail=f"无法连接到 ComfyUI 服务: {e}")

async def get_comfyui_history(prompt_id: str):
    try:
        response = requests.get(f"{config.COMFYUI_URL}/history/{prompt_id}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"ComfyUI API /history 调用失败: {e}")
        raise HTTPException(status_code=503, detail=f"无法获取 ComfyUI 生成历史: {e}")

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise credentials_exception
        token_data = TokenData(email=username, role=role)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exception
    
    # 对于公司域用户，直接从token构建用户信息，不再查询本地用户数据库
    return {
        "email": username,
        "username": username,
        "role": role
    }

# 任务清理函数
async def cleanup_old_tasks():
    """定期清理旧任务数据，防止内存泄漏"""
    while True:
        try:
            current_time = time.time()
            tasks_to_remove = []
            
            for task_id, timestamp in task_timestamps.items():
                if current_time - timestamp > config.TASK_MAX_AGE:
                    tasks_to_remove.append(task_id)
            
            for task_id in tasks_to_remove:
                if task_id in task_status:
                    del task_status[task_id]
                if task_id in task_results:
                    del task_results[task_id]
                if task_id in task_timestamps:
                    del task_timestamps[task_id]
            
            if tasks_to_remove:
                logger.info(f"已清理 {len(tasks_to_remove)} 个过期任务")
                
        except Exception as e:
            logger.error(f"清理任务时出错: {e}")
        
        await asyncio.sleep(config.TASK_CLEANUP_INTERVAL)

# 启动任务清理
@app.on_event("startup")
async def start_task_cleanup():
    asyncio.create_task(cleanup_old_tasks())

# 修改任务状态API，集成任务队列系统
@app.get("/api/task-status/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    # 首先检查任务队列中的任务
    task = task_queue.get_task(task_id)
    
    if task:
        # 如果任务在队列中
        if task.status == 'pending':
            # 获取队列位置
            position = task_queue.get_queue_position(task_id)
            # 估计等待时间
            estimated_wait = task_queue.estimate_wait_time(position) if position else None
            
            return TaskStatus(
                task_id=task_id,
                status="pending",
                progress=0,
                message="任务在队列中等待处理",
                queue_position=position,
                estimated_wait_seconds=estimated_wait
            )
        elif task.status == 'processing':
            return TaskStatus(
                task_id=task_id,
                status="processing",
                progress=task.progress,
                message="任务正在处理中"
            )
        elif task.status == 'completed':
            return TaskStatus(
                task_id=task_id,
                status="completed",
                progress=100,
                message="任务已完成",
                result=task.result
            )
        elif task.status == 'failed':
            return TaskStatus(
                task_id=task_id,
                status="failed",
                message=task.error or "任务处理失败"
            )
        elif task.status == 'cancelled':
            return TaskStatus(
                task_id=task_id,
                status="cancelled",
                message="任务已取消"
            )
    
    # 如果任务队列中没有，检查旧的任务状态管理系统（向后兼容）
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    status_data = {
        "task_id": task_id,
        "status": task_status[task_id],
        "progress": None,
        "message": None
    }
    
    # 如果任务已完成，返回结果
    if task_status[task_id] == "completed" and task_id in task_results:
        status_data["result"] = task_results[task_id]
    
    return TaskStatus(**status_data)

# 记录任务信息的函数
def record_user_task(user_email: str, task_id: str, prompt: str, generation_type: str):
    if user_email not in user_tasks:
        user_tasks[user_email] = []
    
    user_tasks[user_email].append({
        "task_id": task_id,
        "status": task_status.get(task_id, "unknown"),
        "prompt": prompt,
        "creation_time": task_timestamps.get(task_id, time.time()),
        "completion_time": None,
        "image_url": None,
        "generation_type": generation_type
    })

# 更新任务信息的函数
def update_user_task(user_email: str, task_id: str, status: str, image_url: Optional[str] = None):
    if user_email not in user_tasks:
        return
    
    for task in user_tasks[user_email]:
        if task["task_id"] == task_id:
            task["status"] = status
            if status == "completed":
                task["completion_time"] = time.time()
            if image_url:
                task["image_url"] = image_url
            break

# 获取队列状态API
@app.get("/api/queue-status")
async def get_queue_status(current_user: dict = Depends(get_current_user)):
    """获取任务队列状态"""
    user_id = current_user["email"]
    return task_queue.get_queue_status(user_id)

# 取消任务API
@app.post("/api/cancel-task/{task_id}")
async def cancel_task_api(task_id: str, current_user: Dict = Depends(get_current_user)):
    """取消任务"""
    user_id = current_user["email"]
    
    success, message = task_queue.cancel_task(task_id, user_id)
    
    if success:
        return {"success": True, "message": "任务已取消"}
    else:
        raise HTTPException(status_code=400, detail=message)

# 获取用户任务API
@app.get("/api/user-tasks", response_model=list[UserTask])
async def get_user_tasks_api(current_user: Dict = Depends(get_current_user)):
    user_email = current_user["email"]
    result_tasks = []
    
    # 从任务队列获取用户任务
    # 1. 获取队列中的任务（pending状态）
    for task in task_queue.queue:
        if task.user_id == user_email:
            position = task_queue.get_queue_position(task.id)
            estimated_wait = task_queue.estimate_wait_time(position) if position else None
            
            result_tasks.append({
                "task_id": task.id,
                "status": task.status,
                "prompt": task.params.get("prompt", ""),
                "creation_time": task.created_at,
                "completion_time": task.completed_at,
                "image_url": None,
                "generation_type": task.task_type,
                "queue_position": position,
                "estimated_wait_seconds": estimated_wait,
                "progress": task.progress
            })
    
    # 2. 获取处理中的任务（processing状态）
    for task_info in task_queue.processing.values():
        task = task_info['task']
        if task.user_id == user_email:
            result_tasks.append({
                "task_id": task.id,
                "status": task.status,
                "prompt": task.params.get("prompt", ""),
                "creation_time": task.created_at,
                "completion_time": task.completed_at,
                "image_url": None,
                "generation_type": task.task_type,
                "queue_position": None,
                "estimated_wait_seconds": None,
                "progress": task.progress
            })
    
    # 3. 获取已完成的任务（从数据库查询）
    try:
        import sqlite3
        conn = sqlite3.connect(task_queue.db_path)
        cursor = conn.cursor()
        
        # 查询用户的已完成任务
        cursor.execute("""
            SELECT task_id, status, params, created_at, completed_at, result, error, task_type, progress
            FROM tasks 
            WHERE user_id = ? AND status IN ('completed', 'failed', 'cancelled')
            ORDER BY created_at DESC
            LIMIT 50
        """, (user_email,))
        
        rows = cursor.fetchall()
        for row in rows:
            task_id, status, params_json, created_at, completed_at, result_json, error, task_type, progress = row
            params = json.loads(params_json) if params_json else {}
            result = json.loads(result_json) if result_json else None
            
            # 构建图像URL
            image_url = None
            if result and "images" in result:
                # 从任务队列结果中获取图像URL
                images = result["images"]
                if images and len(images) > 0:
                    image_url = f"http://192.168.0.241:5000/api/user-image/{user_email.replace('@', '_at_').replace('.', '_dot_')}/{images[0]['filename']}"
            
            result_tasks.append({
                "task_id": task_id,
                "status": status,
                "prompt": params.get("prompt", ""),
                "creation_time": created_at,
                "completion_time": completed_at,
                "image_url": image_url,
                "generation_type": task_type,
                "queue_position": None,
                "estimated_wait_seconds": None,
                "progress": progress or 0
            })
        
        conn.close()
    except Exception as e:
        logger.error(f"获取用户任务历史失败: {str(e)}")
    
    # 4. 向后兼容：从旧的任务系统获取任务（如果有）
    if user_email in user_tasks:
    for task in user_tasks[user_email]:
            # 检查是否已经从任务队列获取到了这个任务
            if not any(t["task_id"] == task["task_id"] for t in result_tasks):
                # 更新任务状态
        task_id = task["task_id"]
        if task_id in task_status:
            current_status = task_status[task_id]
            if current_status != task["status"]:
                task["status"] = current_status
                if current_status == "completed" and task_id in task_results:
                    task["completion_time"] = time.time()
                    task["image_url"] = task_results[task_id].get("image_url")
                
                result_tasks.append({
                    "task_id": task["task_id"],
                    "status": task["status"],
                    "prompt": task["prompt"],
                    "creation_time": task["creation_time"],
                    "completion_time": task.get("completion_time"),
                    "image_url": task.get("image_url"),
                    "generation_type": task["generation_type"],
                    "queue_position": None,
                    "estimated_wait_seconds": None,
                    "progress": 0
                })
    
    # 按创建时间倒序排序
    sorted_tasks = sorted(result_tasks, key=lambda x: x["creation_time"], reverse=True)
    return sorted_tasks

# 添加一个辅助函数来获取一致的基础URL
def get_consistent_base_url(request: Request) -> str:
    """
    获取一致的基础URL，无论是通过域名还是IP访问
    
    规则：
    1. 如果是通过域名访问，使用域名
    2. 如果是通过IP访问，使用IP
    3. 确保图片URL与当前访问方式一致
    """
    # host = request.headers['host']
    # scheme = request.url.scheme
    
    # # 记录原始请求信息，便于调试
    # logger.info(f"请求头中的host: {host}, scheme: {scheme}")
    
    # # 检查是否为域名访问
    # if host == 'ai-image-generation.3g.net.cn':
    #     # 生产环境域名访问
    #     return f"{scheme}://{host}"
    # elif host.startswith('192.168.') or host.startswith('localhost:') or host.startswith('127.0.0.1:'):
    #     # 本地或局域网IP访问
    #     return f"{scheme}://{host}"
    # else:
    #     # 默认情况，直接使用请求中的信息
    #     return f"{scheme}://{host}"
    return "http://192.168.0.241:5000"
# 异步处理图像生成任务
async def process_image_to_image_task(
    task_id: str,
    prompt: str,
    uploaded_image_path: str,
    image_strength: str,
    face_file_paths: List[str],
    current_user: Dict,
    request: Request
):
    try:
        user_email = current_user["email"]
        # 记录任务信息
        record_user_task(user_email, task_id, prompt, "image-to-image")
        
        task_status[task_id] = "processing"
        update_user_task(user_email, task_id, "processing")
        
        username = current_user.get("username", user_email)
        logger.info(f"开始处理任务 {task_id} - 用户: {username}")
        
        # 使用统一的用户目录名生成逻辑
        user_specific_output_dir_name = get_user_directory_name(current_user)
        absolute_user_output_dir = os.path.join(config.BASE_DIR, config.USER_IMAGES_BASE_DIR, user_specific_output_dir_name)
        os.makedirs(absolute_user_output_dir, exist_ok=True)
        
        # 复制图像到ComfyUI输入目录
        unique_filename = os.path.basename(uploaded_image_path)
        comfyui_input_image_path = os.path.join(config.COMFYUI_INPUT_DIR, unique_filename)
        
        async with aiofiles.open(uploaded_image_path, 'rb') as f_read:
            async with aiofiles.open(comfyui_input_image_path, 'wb') as f_write:
                img_data = await f_read.read()
                await f_write.write(img_data)
        
        # 修改工作流
        modified_workflow = modify_comfyui_workflow(
            config.IMAGE_TO_IMAGE_WORKFLOW_FILE_PATH, 
            comfyui_input_image_path, 
            prompt, 
            image_strength, 
            face_file_paths
        )
        
        # 提交到ComfyUI
        comfy_response = await queue_prompt_comfyui(modified_workflow)
        prompt_id = comfy_response.get("prompt_id")
        if not prompt_id:
            task_status[task_id] = "failed"
            logger.error(f"任务 {task_id} 失败: ComfyUI未返回prompt_id")
            return
        
        # 轮询ComfyUI结果
        output_filename = None
        for _ in range(config.COMFYUI_POLLING_TIMEOUT_SECONDS):
            await asyncio.sleep(3)
            history = await get_comfyui_history(prompt_id)
            if prompt_id in history and history[prompt_id].get("outputs"):
                outputs = history[prompt_id]["outputs"]
                if config.I2I_NODE_ID_SAVE_IMAGE in outputs and outputs[config.I2I_NODE_ID_SAVE_IMAGE]["images"]:
                    output_image_info = outputs[config.I2I_NODE_ID_SAVE_IMAGE]["images"][0]
                    output_filename = output_image_info["filename"]
                    break
        
        if not output_filename:
            task_status[task_id] = "failed"
            logger.error(f"任务 {task_id} 失败: ComfyUI处理超时或未生成图像")
            return
        
        # 移动生成的图像到用户目录
        _, file_extension = os.path.splitext(output_filename)
        unique_filename_for_user = f"{uuid.uuid4().hex}{file_extension}"
        comfyui_image_path = os.path.join(config.COMFYUI_OUTPUT_DIR, output_filename)
        destination_path = os.path.join(absolute_user_output_dir, unique_filename_for_user)
        
        if os.path.exists(comfyui_image_path):
            shutil.move(comfyui_image_path, destination_path)
        else:
            task_status[task_id] = "failed"
            logger.error(f"任务 {task_id} 失败: ComfyUI输出的图像 {comfyui_image_path} 未找到")
            return
        
        # 保存到数据库
        conn = sqlite3.connect(config.DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO image_generations (user_email, prompt, image_filename, generation_type) VALUES (?, ?, ?, ?)",
            (user_email, prompt, unique_filename_for_user, "image-to-image")
        )
        conn.commit()
        history_id = cursor.lastrowid
        conn.close()
        
        # 构建图像URL - 使用一致的基础URL
        base_url = get_consistent_base_url(request)
        image_url = f"{base_url}/{config.USER_IMAGES_BASE_DIR}/{user_specific_output_dir_name}/{unique_filename_for_user}"
        
        # 更新任务状态和结果
        task_status[task_id] = "completed"
        task_results[task_id] = {
            "message": "图像生成成功!",
            "image_url": image_url,
            "history_id": history_id
        }
        update_user_task(user_email, task_id, "completed", image_url)
        logger.info(f"任务 {task_id} 完成")
        
    except Exception as e:
        task_status[task_id] = "failed"
        update_user_task(current_user["email"], task_id, "failed")
        logger.error(f"任务 {task_id} 处理过程中发生错误: {e}")

# 获取新任务ID的函数
def get_next_task_id():
    global next_task_id
    task_id = str(next_task_id)
    next_task_id += 1
    return task_id

# 修改图生图API，使用简单数字ID
@app.post("/api/image-to-image", response_model=TaskStatus)
async def image_to_image_api(
    request: Request,
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    file: UploadFile = File(...),
    image_strength: str = Form(...),
    current_user: Dict = Depends(get_current_user),
    face_file_0: Optional[UploadFile] = File(None),
    face_file_1: Optional[UploadFile] = File(None)
):
    user_email = current_user["email"]
    username = current_user.get("username", user_email)
    logger.info(f"用户 {username} 请求图生图，Prompt: {prompt}, Image Strength: {image_strength}")
    
    # 检查用户任务限制
    active_tasks_count = task_queue.count_user_active_tasks(user_email)
    max_tasks_per_user = config.TASK_QUEUE_CONFIG['max_tasks_per_user']
    
    if active_tasks_count >= max_tasks_per_user:
        raise HTTPException(
            status_code=429,
            detail=f"您已达到最大任务数限制（{max_tasks_per_user}个），请等待当前任务完成后再提交新任务。"
        )
    
    # 创建任务ID
    task_id = str(uuid.uuid4())
    
    # 收集所有有效的人脸文件
    face_files = []
    for i in range(2):
        face_file = locals().get(f"face_file_{i}")
        if face_file and face_file.filename:
            face_files.append(face_file)
    
    # 处理人脸文件上传
    face_file_paths = []
    try:
        for i, face_file in enumerate(face_files):
            face_file_extension = os.path.splitext(face_file.filename)[1]
            unique_face_filename = f"face_{i}_{uuid.uuid4()}{face_file_extension}"
            face_file_path = os.path.join(config.UPLOAD_DIR, unique_face_filename)
            
            async with aiofiles.open(face_file_path, 'wb') as out_file:
                face_content = await face_file.read()
                await out_file.write(face_content)
            
            # 复制到ComfyUI input目录
            comfyui_face_path = os.path.join(config.COMFYUI_INPUT_DIR, unique_face_filename)
            async with aiofiles.open(face_file_path, 'rb') as f_read:
                async with aiofiles.open(comfyui_face_path, 'wb') as f_write:
                    face_data = await f_read.read()
                    await f_write.write(face_data)
            
            face_file_paths.append(face_file_path)
    
    except Exception as e:
        logger.error(f"处理人脸文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理人脸文件失败: {str(e)}")
    
    # 处理上传的图像
    try:
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        uploaded_image_path = os.path.join(config.UPLOAD_DIR, unique_filename)
        
        async with aiofiles.open(uploaded_image_path, 'wb') as out_file:
            content = await file.read()
            await out_file.write(content)
    except Exception as e:
        logger.error(f"保存上传图像失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理上传图像失败: {str(e)}")
    
    # 创建任务对象并添加到队列
    task_params = {
        "prompt": prompt,
        "uploaded_image_path": uploaded_image_path,
        "image_strength": image_strength,
        "face_file_paths": face_file_paths
    }
    
    # 估算任务时长和优先级
    estimated_duration = 180  # 默认3分钟
    priority = 1  # 默认优先级
    
    # 创建任务对象
    task = Task(
        task_id=task_id,
        user_id=user_email,
        task_type="image-to-image",
        params=task_params,
        priority=priority,
        estimated_duration=estimated_duration,
        is_single_image=True
    )
    
    # 将任务添加到队列
    task_queue.add_task(task)
    
    # 记录到旧系统（向后兼容）
    record_user_task(user_email, task_id, prompt, "image-to-image")
    
    # 立即返回任务ID和状态
    return TaskStatus(
        task_id=task_id,
        status="pending",
        message="图生图任务已提交到队列，等待处理"
    )

# 静态文件挂载逻辑 - 只保留一个版本
if os.path.exists(config.USER_IMAGES_BASE_DIR):
    app.mount(f"/{config.USER_IMAGES_BASE_DIR}", StaticFiles(directory=config.USER_IMAGES_BASE_DIR), name="user_images")
    logger.info(f"已挂载静态文件目录 /{config.USER_IMAGES_BASE_DIR} 指向 {config.USER_IMAGES_BASE_DIR}")
else:
    logger.error(f"用户图像基目录 {config.USER_IMAGES_BASE_DIR} 未找到，这是一个严重错误。")

@app.get("/api/user-history", response_model=list[HistoryEntry])
async def get_user_history_api(request: Request, current_user: Dict = Depends(get_current_user)):
    user_email = current_user["email"]
    username = current_user.get("username", user_email)  # 兼容旧数据
    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_email, prompt, image_filename, generation_type, timestamp FROM image_generations WHERE user_email = ? ORDER BY timestamp DESC",
        (user_email,)
    )
    history_records = cursor.fetchall()
    conn.close()

    # 使用一致的基础URL
    # base_url = get_consistent_base_url(request)
    base_url = "http://192.168.0.241:5000"
    
    history_entries = []
    for record in history_records:
        # 使用统一的用户目录名生成逻辑，考虑历史记录兼容性
        user_specific_output_dir_name = get_user_directory_name(current_user, record["user_email"])
        image_url = f"{base_url}/{config.USER_IMAGES_BASE_DIR}/{user_specific_output_dir_name}/{record['image_filename']}"
        history_entries.append(HistoryEntry(
            id=record["id"],
            user_email=record["user_email"],
            prompt=record["prompt"],
            image_filename=record["image_filename"],
            generation_type=record["generation_type"],
            timestamp=record["timestamp"],
            image_url=image_url
        ))
    return history_entries



@app.get("/api/user/role")
async def get_user_role_api(current_user: Dict = Depends(get_current_user)):
    role = current_user.get("role")
    if role:
        return {"role": role}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

@app.delete("/api/user-history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_history_item(
    history_id: int,
    current_user: Dict = Depends(get_current_user)
):
    user_email = current_user["email"]
    logger.info(f"用户 {user_email} 请求删除历史记录 ID: {history_id}")

    import sqlite3
    conn = None
    try:
        conn = sqlite3.connect(config.DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT image_filename, user_email FROM image_generations WHERE id = ?", (history_id,))
        record = cursor.fetchone()

        if not record:
            logger.warning(f"尝试删除不存在的历史记录 ID: {history_id} (用户: {user_email})")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="历史记录未找到")

        if record["user_email"] != user_email:
            logger.error(f"用户 {user_email} 尝试删除不属于自己的历史记录 ID: {history_id} (所有者: {record['user_email']})")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除此历史记录")

        image_filename = record["image_filename"]
        # 使用统一的用户目录名生成逻辑，考虑历史记录兼容性
        owner_dir_name = get_user_directory_name(current_user, record["user_email"])
        image_path = os.path.join(config.USER_IMAGES_BASE_DIR, owner_dir_name, image_filename)

        if os.path.exists(image_path):
            os.remove(image_path)
            logger.info(f"已从文件系统删除图像: {image_path}")
        else:
            logger.warning(f"尝试删除历史记录时，文件系统中的图像未找到: {image_path} (历史ID: {history_id})。仍将删除数据库记录。")

        cursor.execute("DELETE FROM image_generations WHERE id = ?", (history_id,))
        conn.commit()
        logger.info(f"已从数据库删除历史记录 ID: {history_id} (用户: {user_email})")
        
        return

    except HTTPException as e:
        if conn: conn.rollback()
        raise e
    except sqlite3.Error as e:
        if conn: conn.rollback()
        logger.error(f"数据库操作失败，删除历史记录 ID {history_id} (用户: {user_email}) 时出错: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="删除历史记录时发生数据库错误")
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"删除历史记录 ID {history_id} (用户: {user_email}) 时发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="删除历史记录时发生未知错误")
    finally:
        if conn: conn.close()



@app.post("/api/login", response_model=Token)
async def unified_login(login_data: CompanyLogin):
    """
    统一登录接口 - 生产版本
    支持两种认证方式：
    1. 本地账号认证（users.json）
    2. 公司域用户认证（gomanager API）
    
    前端发送JSON格式: {"username": "用户名", "password": "密码"}
    """
    username = login_data.username
    password = login_data.password
    logger.info(f"[PROD] 收到登录请求，用户名: {username}")
    
    # 方式1：尝试本地账号认证
    logger.info("[PROD] 首先尝试本地账号认证...")
    local_user = user_manager.authenticate(username, password)
    if local_user:
        logger.info(f"[PROD] 本地账号认证成功: {username}")
        
        # 生成本地JWT令牌
        access_token_expires = datetime.timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": local_user["email"], "role": local_user["role"]},
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "email": local_user["email"],
                "username": local_user["email"],
                "role": local_user["role"]
            }
        }
    
    # 方式2：本地认证失败，尝试公司域认证
    logger.info("[PROD] 本地账号认证失败，尝试公司域认证...")
    try:
        # 公司认证接口配置
        company_auth_url = "http://gomanager.3g.net.cn/userManage/auth.do"
        
        # 注意：公司接口要求 application/x-www-form-urlencoded 格式
        # 参数名为 name, passwd, systemid（不是 username, password）
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # 构建表单数据，注意参数名的映射
        form_data = {
            "name": username,        # 公司接口使用 'name' 而不是 'username'
            "passwd": password,      # 公司接口使用 'passwd' 而不是 'password'
            "systemid": "337"        # 系统ID固定为123
        }
        
        logger.info(f"[PROD] 正在调用公司认证接口: {company_auth_url}")
        logger.info(f"[PROD] 发送的表单数据: name={username}, systemid=123")
        logger.info(f"[PROD] 请求头: {headers}")
        
        # 发送POST请求到公司认证接口
        # 使用 data= 参数发送表单数据，而不是 json= 参数
        resp = requests.post(
            company_auth_url, 
            headers=headers, 
            data=form_data,  # 使用 data= 发送表单数据
            timeout=10       # 增加超时时间到10秒
        )
        
        logger.info(f"[PROD] 公司认证接口响应状态码: {resp.status_code}")
        logger.info(f"[PROD] 公司认证接口响应内容: {resp.text}")
        
        # 检查HTTP状态码
        resp.raise_for_status()
        
        # 解析JSON响应
        try:
            result = resp.json()
            logger.info(f"[PROD] 解析后的JSON响应: {result}")
        except json.JSONDecodeError as e:
            logger.error(f"[PROD] 公司认证接口返回的不是有效JSON: {resp.text}")
            raise Exception(f"公司认证接口响应格式错误: {e}")
        
        # 提取用户信息
        user_info = result.get("user")
        logger.info(f"[PROD] 解析后的用户信息: {user_info}")
        
        # 验证用户信息的有效性
        if user_info and user_info.get("enable") and user_info.get("domain"):
            # 用户认证成功，生成本地JWT令牌
            access_token_expires = datetime.timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = create_access_token(
                data={"sub": user_info["loginName"], "role": "domain_user"},
                expires_delta=access_token_expires
            )
            
            logger.info(f"[PROD] 公司域用户登录成功: {user_info['loginName']} ({user_info.get('cname')})")
            
            # 返回登录成功响应
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user": {
                    "email": user_info["loginName"],
                    "username": user_info["loginName"],
                    "role": user_info.get("cname"),
                    "cname": user_info.get("cname"),      # 中文姓名
                    "address": user_info.get("address"),  # 地址信息
                    "id": user_info.get("id")             # 用户ID
                }
            }
        else:
            # 用户未启用或非域账号
            logger.warning(f"[PROD] 公司域认证失败：用户未启用或非域账号 - {user_info}")
            
    except requests.exceptions.Timeout as e:
        logger.error(f"[PROD] 公司认证接口调用超时: {e}")
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[PROD] 无法连接到公司认证接口: {e}")
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"[PROD] 公司认证接口返回HTTP错误: {e}")
        
    except requests.RequestException as e:
        logger.error(f"[PROD] 公司认证接口调用失败: {e}")
        
    except Exception as e:
        logger.error(f"[PROD] 公司域认证过程中发生未知错误: {e}")
    
    # 两种认证方式都失败，返回统一的认证失败错误
    logger.warning(f"[PROD] 用户 {username} 登录失败：本地和公司域认证都未通过")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="用户名或密码错误",
        headers={"WWW-Authenticate": "Bearer"},
    )

# 异步处理文生图任务
async def process_text_to_image_task(
    task_id: str,
    prompt: str,
    aspect_ratio: str,
    reference_image_path: Optional[str],
    face_image_paths: List[str],
    current_user: Dict,
    request: Request
):
    try:
        user_email = current_user["email"]
        # 记录任务信息
        record_user_task(user_email, task_id, prompt, "text-to-image")
        
        task_status[task_id] = "processing"
        update_user_task(user_email, task_id, "processing")
        
        username = current_user.get("username", user_email)
        logger.info(f"开始处理文生图任务 {task_id} - 用户: {username}")
        
        # 使用统一的用户目录名生成逻辑
        user_specific_output_dir_name = get_user_directory_name(current_user)
        absolute_user_output_dir = os.path.join(config.BASE_DIR, config.USER_IMAGES_BASE_DIR, user_specific_output_dir_name)
        os.makedirs(absolute_user_output_dir, exist_ok=True)
        
        # 确定使用哪个工作流和保存节点ID
        comfyui_input_reference_image_filename = None
        workflow_to_use = ""
        save_image_node_id_for_polling = ""
        
        if reference_image_path:
            if not config.TEXT_TO_IMAGE_POSE_WORKFLOW_FILE_PATH or not os.path.exists(config.TEXT_TO_IMAGE_POSE_WORKFLOW_FILE_PATH):
                task_status[task_id] = "failed"
                logger.error(f"任务 {task_id} 失败: 带参考图像的文生图工作流文件路径未设置或文件不存在")
                return
            
            workflow_to_use = config.TEXT_TO_IMAGE_POSE_WORKFLOW_FILE_PATH
            save_image_node_id_for_polling = config.T2I_POSE_NODE_ID_SAVE_IMAGE
            
            # 获取参考图像文件名
            comfyui_input_reference_image_filename = os.path.basename(reference_image_path)
        else:
            if not config.TEXT_TO_IMAGE_WORKFLOW_FILE_PATH or not os.path.exists(config.TEXT_TO_IMAGE_WORKFLOW_FILE_PATH):
                task_status[task_id] = "failed"
                logger.error(f"任务 {task_id} 失败: 标准文生图工作流文件路径未设置或文件不存在")
                return
            
            workflow_to_use = config.TEXT_TO_IMAGE_WORKFLOW_FILE_PATH
            save_image_node_id_for_polling = config.T2I_NODE_ID_SAVE_IMAGE
        
        # 修改工作流
        modified_workflow = modify_text_to_image_workflow(
            workflow_json_path=workflow_to_use,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            reference_image_filename=comfyui_input_reference_image_filename,
            face_image_filenames=[os.path.basename(path) for path in face_image_paths] if face_image_paths else None
        )
        
        # 提交到ComfyUI
        comfy_response = await queue_prompt_comfyui(modified_workflow)
        prompt_id = comfy_response.get("prompt_id")
        if not prompt_id:
            task_status[task_id] = "failed"
            logger.error(f"任务 {task_id} 失败: ComfyUI未返回prompt_id")
            return
        
        # 轮询ComfyUI结果
        output_filename = None
        for _ in range(config.COMFYUI_POLLING_TIMEOUT_SECONDS):
            await asyncio.sleep(1)
            history = await get_comfyui_history(prompt_id)
            if prompt_id in history and history[prompt_id].get("outputs"):
                outputs = history[prompt_id]["outputs"]
                if save_image_node_id_for_polling in outputs and outputs[save_image_node_id_for_polling].get("images"):
                    output_image_info = outputs[save_image_node_id_for_polling]["images"][0]
                    output_filename = output_image_info["filename"]
                    break
        
        if not output_filename:
            task_status[task_id] = "failed"
            logger.error(f"任务 {task_id} 失败: ComfyUI处理超时或未生成图像")
            return
        
        # 移动生成的图像到用户目录
        _, file_extension = os.path.splitext(output_filename)
        unique_filename_for_user = f"{uuid.uuid4().hex}{file_extension}"
        comfyui_image_path = os.path.join(config.COMFYUI_OUTPUT_DIR, output_filename)
        destination_path = os.path.join(absolute_user_output_dir, unique_filename_for_user)
        
        if os.path.exists(comfyui_image_path):
            shutil.move(comfyui_image_path, destination_path)
        else:
            task_status[task_id] = "failed"
            logger.error(f"任务 {task_id} 失败: ComfyUI输出的图像 {comfyui_image_path} 未找到")
            return
        
        # 保存到数据库
        conn = sqlite3.connect(config.DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO image_generations (user_email, prompt, image_filename, generation_type) VALUES (?, ?, ?, ?)",
            (user_email, prompt, unique_filename_for_user, "text-to-image")
        )
        conn.commit()
        history_id = cursor.lastrowid
        conn.close()
        
        # 构建图像URL - 使用一致的基础URL
        base_url = get_consistent_base_url(request)
        image_url = f"{base_url}/{config.USER_IMAGES_BASE_DIR}/{user_specific_output_dir_name}/{unique_filename_for_user}"
        
        # 更新任务状态和结果
        task_status[task_id] = "completed"
        task_results[task_id] = {
            "message": "图像生成成功!",
            "image_url": image_url,
            "history_id": history_id
        }
        update_user_task(user_email, task_id, "completed", image_url)
        logger.info(f"任务 {task_id} 完成")
        
    except Exception as e:
        task_status[task_id] = "failed"
        update_user_task(current_user["email"], task_id, "failed")
        logger.error(f"任务 {task_id} 处理过程中发生错误: {e}")

# 修改文生图API，使用简单数字ID
@app.post("/api/text-to-image", response_model=TaskStatus)
async def text_to_image_api(
    request: Request,
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    aspect_ratio: str = Form(...),
    reference_image: Optional[UploadFile] = File(None),
    face_image_0: Optional[UploadFile] = File(None),
    face_image_1: Optional[UploadFile] = File(None),
    current_user: Dict = Depends(get_current_user)
):
    user_email = current_user["email"]
    username = current_user.get("username", user_email)
    logger.info(f"用户 {username} 请求文生图。Prompt: {prompt}, AspectRatio: {aspect_ratio}, ReferenceImage: {reference_image.filename if reference_image else '无'}")
    
    # 检查用户任务限制
    active_tasks_count = task_queue.count_user_active_tasks(user_email)
    max_tasks_per_user = config.TASK_QUEUE_CONFIG['max_tasks_per_user']
    
    if active_tasks_count >= max_tasks_per_user:
        raise HTTPException(
            status_code=429,
            detail=f"您已达到最大任务数限制（{max_tasks_per_user}个），请等待当前任务完成后再提交新任务。"
        )
    
    # 创建任务ID
    task_id = str(uuid.uuid4())
    
    # 处理参考图像
    reference_image_path = None
    if reference_image and reference_image.filename:
        try:
            os.makedirs(config.COMFYUI_INPUT_DIR, exist_ok=True)
            file_extension = os.path.splitext(reference_image.filename)[1]
            unique_ref_filename = f"ref_{uuid.uuid4().hex}{file_extension}"
            reference_image_path = os.path.join(config.COMFYUI_INPUT_DIR, unique_ref_filename)
            
            async with aiofiles.open(reference_image_path, 'wb') as out_file:
                content = await reference_image.read()
                await out_file.write(content)
            logger.info(f"参考图像已保存: {reference_image_path}")
        except Exception as e:
            logger.error(f"保存参考图像失败: {e}")
            raise HTTPException(status_code=500, detail=f"处理参考图像失败: {str(e)}")
    
    # 处理人脸图像
    face_image_paths = []
    face_images = [face_image_0, face_image_1]
    for i, face_image in enumerate(face_images):
        if face_image and face_image.filename:
            try:
                os.makedirs(config.COMFYUI_INPUT_DIR, exist_ok=True)
                face_file_extension = os.path.splitext(face_image.filename)[1]
                unique_face_filename = f"face_{i}_{uuid.uuid4().hex}{face_file_extension}"
                face_image_path = os.path.join(config.COMFYUI_INPUT_DIR, unique_face_filename)
                
                async with aiofiles.open(face_image_path, 'wb') as out_file:
                    face_content = await face_image.read()
                    await out_file.write(face_content)
                face_image_paths.append(face_image_path)
                logger.info(f"人脸图像 {i+1} 已保存: {face_image_path}")
            except Exception as e:
                logger.error(f"保存人脸图像 {i+1} 失败: {e}")
                raise HTTPException(status_code=500, detail=f"处理人脸图像 {i+1} 失败: {str(e)}")
    
    # 创建任务对象并添加到队列
    task_params = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "reference_image_path": reference_image_path,
        "face_image_paths": face_image_paths
    }
    
    # 估算任务时长和优先级
    estimated_duration = 180  # 默认3分钟
    priority = 1  # 默认优先级
    
    # 创建任务对象
    task = Task(
        task_id=task_id,
        user_id=user_email,
        task_type="text-to-image",
        params=task_params,
        priority=priority,
        estimated_duration=estimated_duration,
        is_single_image=True
    )
    
    # 将任务添加到队列
    task_queue.add_task(task)
    
    # 记录到旧系统（向后兼容）
    record_user_task(user_email, task_id, prompt, "text-to-image")
    
    # 立即返回任务ID和状态
    return TaskStatus(
        task_id=task_id,
        status="pending",
        message="文生图任务已提交到队列，等待处理"
    )

# 添加批量任务状态查询模型
class BatchTaskStatusRequest(BaseModel):
    task_ids: List[str]

class BatchTaskStatusResponse(BaseModel):
    tasks: Dict[str, TaskStatus]

# 批量查询任务状态API
@app.post("/api/batch-task-status", response_model=BatchTaskStatusResponse)
async def get_batch_task_status(request: BatchTaskStatusRequest):
    result = {}
    for task_id in request.task_ids:
        # 首先检查任务队列中的任务
        task = task_queue.get_task(task_id)
        if task:
            status_data = {
                "task_id": task_id,
                "status": task.status,
                "progress": task.progress,
                "message": None
            }
            
            if task.status == 'completed':
                status_data["result"] = task.result
            elif task.status == 'failed':
                status_data["message"] = task.error
            
            result[task_id] = TaskStatus(**status_data)
        elif task_id in task_status:
            # 向后兼容旧的任务状态系统
            status_data = {
                "task_id": task_id,
                "status": task_status[task_id],
                "progress": None,
                "message": None
            }
            
            # 如果任务已完成，返回结果
            if task_status[task_id] == "completed" and task_id in task_results:
                status_data["result"] = task_results[task_id]
            
            result[task_id] = TaskStatus(**status_data)
    
    return BatchTaskStatusResponse(tasks=result)

# 清理任务状态API
@app.post("/api/clean-tasks")
async def clean_tasks(current_user: dict = Depends(get_current_user)):
    """清理任务状态 - 仅管理员可用"""
    # 检查用户权限（只允许管理员清理任务）
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
        
    success, message = task_queue.clean_tasks()
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)
        
    return {"message": message}

# uvicorn app:app --reload --host 0.0.0.0 --port 5000
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000) # 生产版本端口 5000 