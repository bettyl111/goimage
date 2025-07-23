from fastapi import FastAPI, HTTPException, Depends, status, Request, File, UploadFile, Form, BackgroundTasks, Header, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List, Any, Tuple
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
from task_queue import Task, get_task_queue  # 导入任务队列模块 2023.07.03 14
import aiohttp
from functools import wraps
from fastapi.responses import JSONResponse
from comfyui_manager import get_comfyui_manager  # 导入ComfyUI管理器 2023.07.04 15
from helper import get_user_directory_name, calculate_dimensions, modify_comfyui_workflow, modify_text_to_image_workflow 
# 配置日志
logging.basicConfig(
    filename=config.LOG_FILE,
    format=config.LOG_FORMAT,
    level=config.LOG_LEVEL
)
logger = logging.getLogger(__name__)

# 创建FastAPI应用，设置API前缀为空
app = FastAPI(docs_url="/docs", redoc_url="/redoc")

# 获取任务队列实例
task_queue = get_task_queue()  # 2023.07.03 14

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
    queue_position: Optional[int] = None  # 添加队列位置 2023.07.03 14
    estimated_wait_seconds: Optional[int] = None  # 添加预计等待时间 2023.07.03 14

# 添加用户任务模型
class UserTask(BaseModel):
    task_id: str
    status: str
    prompt: str
    creation_time: float
    completion_time: Optional[float] = None
    image_url: Optional[str] = None
    generation_type: str
    queue_position: Optional[int] = None  # 添加队列位置 2023.07.03 14
    estimated_wait_seconds: Optional[int] = None  # 添加预计等待时间 2023.07.03 14

# 添加任务记录到数据库
user_tasks = {}  # 用户ID -> 任务列表的映射

# 配置CORS 2023.07.03 15
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://192.168.0.241:8081",  # 测试环境前端
        "http://192.168.0.241:5173",  # Vite开发服务器
        "http://localhost:5173",      # 本地开发
        "http://localhost:8081",      # 本地测试
        "http://localhost:5001",      # 本地API服务
        "http://192.168.0.241:5001",  # 测试环境API服务
        "https://ai-image-test.3g.net.cn",  # 测试环境域名
        "https://ai-image-generation.3g.net.cn",  # 生产环境域名
        "*"                           # 允许所有源（开发环境使用）
    ],
    allow_credentials=True,  # 允许携带认证信息（cookies）
    allow_methods=["*"],  # 允许的HTTP方法
    allow_headers=["*"],  # 允许的HTTP头
    expose_headers=["*"]  # 允许浏览器访问的响应头
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
os.makedirs(config.TEMP_UPLOADS_DIR, exist_ok=True)
os.makedirs(config.USER_GENERATED_IMAGES_DIR, exist_ok=True)


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



async def queue_prompt_comfyui(workflow: dict):
    """将工作流提交到ComfyUI 2023.07.03 14"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{config.COMFYUI_API_BASE}/prompt",
                json={"prompt": workflow},
                timeout=config.COMFYUI_POLLING_TIMEOUT_SECONDS
            ) as response:
                if response.status == 404:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="ComfyUI服务未启动或地址错误"
                    )
                response.raise_for_status()
                return await response.json()
    except aiohttp.ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"无法连接到ComfyUI服务: {str(e)}"
        )

async def get_comfyui_history(prompt_id: str) -> Optional[Dict]:
    """获取ComfyUI历史记录 2023.07.03 14"""
    try:
        encoded_params = prompt_id.replace("/", "_")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{config.COMFYUI_API_BASE}/history/{encoded_params}",
                timeout=config.COMFYUI_POLLING_TIMEOUT_SECONDS
            ) as response:
                if response.status == 404:
                    return None
                response.raise_for_status()
                return await response.json()
    except aiohttp.ClientError:
        return None

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
        exp: int = payload.get("exp")
        
        # 检查token是否已过期
        if exp is None:
            raise credentials_exception
            
        # 检查当前时间是否超过了token的过期时间
        current_time = datetime.datetime.utcnow().timestamp()
        if current_time > exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌已过期",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
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

# 获取任务队列状态
@app.get("/api/queue-status")
async def get_queue_status(current_user: dict = Depends(get_current_user)):
    """获取队列状态 2023.07.03 12"""
    return task_queue.get_queue_status()

@app.post("/api/cancel-task/{task_id}")
async def cancel_task_api(task_id: str, current_user: Dict = Depends(get_current_user)):
    """取消任务 2023.07.03 14"""
    user_id = current_user["email"]
    
    success, message = task_queue.cancel_task(task_id, user_id)
    
    if success:
        return {"success": True, "message": "任务已取消"}
    else:
        raise HTTPException(status_code=400, detail=message)

# 获取任务状态
@app.get("/api/task-status/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """获取任务状态 2023.07.03 14"""
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
    
    # 如果任务不在队列中，回退到旧的任务状态管理
    if task_id in task_status:
        status_info = task_status[task_id]
        result = task_results.get(task_id)
        
        return TaskStatus(
            task_id=task_id,
            status=status_info["status"],
            progress=status_info.get("progress"),
            message=status_info.get("message", ""),
            result=result
        )
    else:
        raise HTTPException(status_code=404, detail="任务不存在")

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

# 获取用户任务API
@app.get("/api/user-tasks", response_model=list[UserTask])
async def get_user_tasks_api(current_user: Dict = Depends(get_current_user)):
    """获取用户任务列表 2023.07.03 14"""
    user_email = current_user["email"]
    
    # 获取用户的任务
    user_task_list = []
    
    # 从任务队列中获取用户任务
    for task in task_queue.queue:
        if task.user_id == user_email:
            position = task_queue.get_queue_position(task.id)
            estimated_wait = task_queue.estimate_wait_time(position) if position else None
            
            user_task_list.append(UserTask(
                task_id=task.id,
                status=task.status,
                prompt=task.params.get("prompt", ""),
                creation_time=task.created_at,
                generation_type=task.task_type,
                queue_position=position,
                estimated_wait_seconds=estimated_wait
            ))
    
    # 从处理中任务获取
    for task_info in task_queue.processing.values():
        task = task_info['task']
        if task.user_id == user_email:
            user_task_list.append(UserTask(
                task_id=task.id,
                status=task.status,
                prompt=task.params.get("prompt", ""),
                creation_time=task.created_at,
                generation_type=task.task_type,
                progress=task.progress
            ))
    
    # 从已完成任务获取（最近的10个）
    completed_tasks = [task for task_id, task in task_queue.completed.items() if task.user_id == user_email]
    completed_tasks.sort(key=lambda t: t.completed_at or 0, reverse=True)
    for task in completed_tasks[:10]:
        image_url = None
        if task.result and "image_url" in task.result:
            image_url = task.result["image_url"]
            
        user_task_list.append(UserTask(
            task_id=task.id,
            status=task.status,
            prompt=task.params.get("prompt", ""),
            creation_time=task.created_at,
            completion_time=task.completed_at,
            image_url=image_url,
            generation_type=task.task_type
        ))
    
    # 兼容旧系统的任务
    if user_email in user_tasks:
        for task in user_tasks[user_email]:
            # 检查是否已经添加
            if not any(t.task_id == task["task_id"] for t in user_task_list):
                user_task_list.append(UserTask(**task))
    
    # 按创建时间排序
    user_task_list.sort(key=lambda t: t.creation_time, reverse=True)
    
    return user_task_list

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
    return "http://192.168.0.241:5001"

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
    """处理图像到图像任务 2023.07.03 14"""
    try:
        # 创建任务数据
        task_data = {
            "prompt": prompt,
            "image_path": uploaded_image_path,
            "image_strength": image_strength,
            "face_file_paths": face_file_paths,
            "count": 1  # 默认生成1张图片
        }
        
        # 创建任务对象
        task = Task(
            task_id=task_id,
            user_id=current_user["email"],
            task_type="image2image",
            params=task_data,
            priority=1,  # 默认优先级
            estimated_duration=120  # 估计处理时间（秒）
        )
        
        # 添加到任务队列
        task_queue.add_task(task)
        
        # 记录用户任务
        record_user_task(current_user["email"], task_id, prompt, "image-to-image")
        
        # 更新旧的任务状态（兼容性）
        task_status[task_id] = {
            "status": "pending",
            "message": "任务已添加到队列"
        }
        task_timestamps[task_id] = time.time()
        
        # 返回任务ID
        return task_id
    except Exception as e:
        logger.error(f"处理图像到图像任务出错: {str(e)}")
        task_status[task_id] = {
            "status": "failed",
            "message": f"处理任务出错: {str(e)}"
        }
        return task_id

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
    """图生图API 2023.07.04 15"""
    # 检查ComfyUI状态和资源可用性
    comfyui_manager = get_comfyui_manager()
    available, message = comfyui_manager.check_resource_availability()
    
    if not available:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unavailable",
                "message": message,
                "task_id": None
            }
        )
    
    # 生成任务ID
    task_id = str(uuid.uuid4())
    
    # 保存上传的图片
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    uploaded_image_path = os.path.join(config.TEMP_UPLOADS_DIR, unique_filename)
    
    async with aiofiles.open(uploaded_image_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
    
    # 处理人脸图片
    face_file_paths = []
    face_files = [face_file_0, face_file_1]
    for i, face_file in enumerate(face_files):
        if face_file:
            # 确保ComfyUI输入目录存在
            os.makedirs(config.COMFYUI_INPUT_DIR, exist_ok=True)
            
            # 保存人脸图片
            file_extension = os.path.splitext(face_file.filename)[1]
            unique_face_filename = f"face_{i}_{uuid.uuid4()}{file_extension}"
            face_file_path = os.path.join(config.COMFYUI_INPUT_DIR, unique_face_filename)
            face_file_paths.append(face_file_path)
    
            async with aiofiles.open(face_file_path, 'wb') as out_file:
                content = await face_file.read()
                await out_file.write(content)
    
    # 创建任务
    task = Task(
        task_id=task_id,
        user_id=current_user["email"],
        task_type="image-to-image",
        params={
            "prompt": prompt,
            "image_strength": image_strength,
            "uploaded_image_path": uploaded_image_path,
            "face_file_paths": face_file_paths
        },
        priority=1,  # 默认优先级
        estimated_duration=180,  # 估计执行时间（秒）
        is_single_image=True  # 单图任务
    )
    
    # 添加任务到队列
    task_queue.add_task(task)
    
    # 记录用户任务
    record_user_task(current_user["email"], task_id, prompt, "image-to-image")
    
    # 启动后台任务处理
    background_tasks.add_task(
        process_image_to_image_task,
        task_id,
        prompt,
        uploaded_image_path,
        image_strength,
        face_file_paths,
        current_user,
        request
    )
    
    # 返回任务状态
    return TaskStatus(
        task_id=task_id,
        status="pending",
        message="任务已添加到队列"
    )

# 静态文件挂载逻辑 - 只保留一个版本
if os.path.exists(config.USER_GENERATED_IMAGES_DIR):
    app.mount(f"/{config.USER_GENERATED_IMAGES_DIR}", StaticFiles(directory=config.USER_GENERATED_IMAGES_DIR), name="user_images")
    logger.info(f"已挂载静态文件目录 /{config.USER_GENERATED_IMAGES_DIR} 指向 {config.USER_GENERATED_IMAGES_DIR}")
else:
    logger.error(f"用户图像基目录 {config.USER_GENERATED_IMAGES_DIR} 未找到，这是一个严重错误。")

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
    base_url = "http://192.168.0.241:5001"
    
    history_entries = []
    for record in history_records:
        # 使用统一的用户目录名生成逻辑，考虑历史记录兼容性
        user_specific_output_dir_name = get_user_directory_name(current_user, record["user_email"])
        image_url = f"{base_url}/{config.USER_GENERATED_IMAGES_DIR}/{user_specific_output_dir_name}/{record['image_filename']}"
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
        image_path = os.path.join(config.USER_GENERATED_IMAGES_DIR, owner_dir_name, image_filename)

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
    """处理文本到图像任务 2023.07.03 14"""
    try:
        # 创建任务数据
        task_data = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "reference_image_path": reference_image_path,
            "face_image_paths": face_image_paths,
            "count": 1  # 默认生成1张图片
        }
        
        # 创建任务对象
        task = Task(
            task_id=task_id,
            user_id=current_user["email"],
            task_type="text-to-image",
            params=task_data,
            priority=1,  # 默认优先级
            estimated_duration=180  # 估计处理时间（秒）
        )
        
        # 添加到任务队列
        task_queue.add_task(task)
        
        # 记录用户任务
        record_user_task(current_user["email"], task_id, prompt, "text-to-image")
        
        # 更新旧的任务状态（兼容性）
        task_status[task_id] = {
            "status": "pending",
            "message": "任务已添加到队列"
        }
        task_timestamps[task_id] = time.time()
        
        # 返回任务ID
        return task_id
    except Exception as e:
        logger.error(f"处理文本到图像任务出错: {str(e)}")
        task_status[task_id] = {
            "status": "failed",
            "message": f"处理任务出错: {str(e)}"
        }
        return task_id

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
    """文生图API 2023.07.04 15"""
    # 检查ComfyUI状态和资源可用性
    comfyui_manager = get_comfyui_manager()
    available, message = comfyui_manager.check_resource_availability()
    
    if not available:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unavailable",
                "message": message,
                "task_id": None
            }
        )
    
    # 生成任务ID
    task_id = str(uuid.uuid4())
    
    # 处理参考图片（如果有）
    reference_image_path = None
    if reference_image:
        # 确保ComfyUI输入目录存在
        os.makedirs(config.COMFYUI_INPUT_DIR, exist_ok=True)
        
        # 保存参考图片
        file_extension = os.path.splitext(reference_image.filename)[1]
        unique_ref_filename = f"ref_{uuid.uuid4()}{file_extension}"
        reference_image_path = os.path.join(config.COMFYUI_INPUT_DIR, unique_ref_filename)
        
        async with aiofiles.open(reference_image_path, 'wb') as out_file:
            content = await reference_image.read()
            await out_file.write(content)
    
    # 处理人脸图片
    face_image_paths = []
    face_files = [face_image_0, face_image_1]
    for i, face_file in enumerate(face_files):
        if face_file:
            # 确保ComfyUI输入目录存在
            os.makedirs(config.COMFYUI_INPUT_DIR, exist_ok=True)
            
            # 保存人脸图片
            file_extension = os.path.splitext(face_file.filename)[1]
            unique_face_filename = f"face_{i}_{uuid.uuid4()}{file_extension}"
            face_image_path = os.path.join(config.COMFYUI_INPUT_DIR, unique_face_filename)
            face_image_paths.append(face_image_path)
                
            async with aiofiles.open(face_image_path, 'wb') as out_file:
                content = await face_file.read()
                await out_file.write(content)
    
    # 创建任务
    task = Task(
        task_id=task_id,
        user_id=current_user["email"],
        task_type="text-to-image",
        params={
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "reference_image_path": reference_image_path,
            "face_image_paths": face_image_paths
        },
        priority=1,  # 默认优先级
        estimated_duration=180,  # 估计执行时间（秒）
        is_single_image=True  # 单图任务
    )
    
    # 添加任务到队列
    task_queue.add_task(task)
    
    # 记录用户任务
    record_user_task(current_user["email"], task_id, prompt, "text-to-image")
    
    # 启动后台任务处理
    background_tasks.add_task(
        process_text_to_image_task,
        task_id,
        prompt,
        aspect_ratio,
        reference_image_path,
        face_image_paths,
        current_user,
        request
    )
    
    # 返回任务状态
    return TaskStatus(
        task_id=task_id,
        status="pending",
        message="任务已添加到队列"
    )

# 添加批量任务状态查询模型
class BatchTaskStatusRequest(BaseModel):
    task_ids: List[str]

class BatchTaskStatusResponse(BaseModel):
    tasks: Dict[str, TaskStatus]

# 批量查询任务状态API
@app.post("/api/batch-task-status", response_model=BatchTaskStatusResponse)
async def get_batch_task_status(request: BatchTaskStatusRequest):
    """批量获取任务状态 2023.07.03 14"""
    tasks = {}
    
    for task_id in request.task_ids:
        try:
            task_status_response = await get_task_status(task_id)
            tasks[task_id] = task_status_response
        except HTTPException:
            # 如果任务不存在，返回404状态
            tasks[task_id] = TaskStatus(
                task_id=task_id,
                status="not_found",
                message="任务不存在"
            )
    
    return BatchTaskStatusResponse(tasks=tasks)

@app.post("/api/clean-tasks")
async def clean_tasks(current_user: dict = Depends(get_current_user)):
    """清理任务状态 2023.07.03 12"""
    # 检查用户权限（只允许管理员清理任务）
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
        
    success, message = task_queue.clean_tasks()
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)
        
    return {"message": message}

# Token验证端点 2023.07.03 14
@app.get("/api/validate-token")
async def validate_token(current_user: Dict = Depends(get_current_user)):
    """
    验证token是否有效
    如果token无效会抛出401异常
    如果有效则返回成功
    """
    return {"status": "valid", "user": current_user}

# 添加queue_prompt作为queue_prompt_comfyui的别名，用于兼容性
async def queue_prompt(workflow: dict):
    """queue_prompt_comfyui的别名 2023.07.03 14"""
    return await queue_prompt_comfyui(workflow)

# uvicorn app:app --reload --host 0.0.0.0 --port 5001
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)  # 测试环境使用5001端口 

@app.get("/api/comfyui-status")
async def get_comfyui_status(current_user: Dict = Depends(get_current_user)):
    """获取ComfyUI状态 2023.07.04 15"""
    comfyui_manager = get_comfyui_manager()
    is_running = comfyui_manager.is_comfyui_running()
    gpu_info = comfyui_manager.get_gpu_info()
    
    return {
        "is_running": is_running,
        "gpu_info": {
            "utilization": gpu_info['utilization'],
            "memory_used_gb": round(gpu_info['memory_used_gb'], 2),
            "memory_total_gb": round(gpu_info['memory_total_gb'], 2),
            "memory_usage_percent": round(gpu_info['memory_usage_percent'], 2)
        },
        "resource_available": is_running and gpu_info['utilization'] < comfyui_manager.max_gpu_utilization,
        "message": "ComfyUI正在运行" if is_running else "ComfyUI未运行"
    } 