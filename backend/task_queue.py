import time
import threading
import json
import logging
import os
import sqlite3
from typing import Dict, List, Any, Optional, Tuple
import subprocess
try:
    from config import TASK_QUEUE_CONFIG
except ImportError:
    # 如果无法导入config，使用默认配置
    TASK_QUEUE_CONFIG = {
        'max_concurrent_tasks': 2,
        'task_timeout': 600,
        'queue_check_interval': 5,
        'max_tasks_per_user': 3,
        'gpu_usage_high_threshold': 90,
        'gpu_memory_high_threshold': 85,
        'gpu_usage_normal_threshold': 50,
        'gpu_memory_normal_threshold': 60,
    }

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("task_queue.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TaskQueue")

class Task:
    """任务类 2023.07.03 14"""
    def __init__(self, task_id: str, user_id: str, task_type: str, params: Dict, priority: int = 1, estimated_duration: int = 180, is_single_image: bool = True):
        self.id = task_id
        self.user_id = user_id
        self.task_type = task_type
        self.params = params
        self.status = 'pending'
        self.progress = 0
        self.result = None
        self.error = None
        self.created_at = time.time()
        self.started_at = None
        self.completed_at = None
        self.in_comfyui = False  # 标记是否已进入ComfyUI处理
        self.priority = priority  # 任务优先级，默认为1
        self.estimated_duration = estimated_duration  # 估计执行时间（秒）
        self.is_single_image = is_single_image  # 是否为单图任务

class SimpleTaskQueue:
    """简单任务队列管理类 2023.07.01 10"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """单例模式实现 2023.07.01 10"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SimpleTaskQueue, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化任务队列 2023.07.01 10"""
        if self._initialized:
            return
            
        self.queue = []  # 存储待处理任务
        self.processing = {}  # 正在处理的任务 {task_id: {'start_time': time, 'task': task, 'process': process}}
        self.completed = {}  # 已完成的任务 {task_id: task}
        self.max_concurrent = TASK_QUEUE_CONFIG['max_concurrent_tasks']
        self.task_timeout = TASK_QUEUE_CONFIG['task_timeout']
        self.db_path = 'image_history.db'
        
        # 创建数据库表（如果不存在）
        self._init_db()
        
        # 从数据库恢复任务状态
        self._recover_tasks()
        
        # 启动任务处理线程
        self.running = True
        self.processor_thread = threading.Thread(target=self._task_processor_loop)
        self.processor_thread.daemon = True
        self.processor_thread.start()
        
        self._initialized = True
        logger.info("任务队列初始化完成")
    
    def _init_db(self):
        """初始化数据库 2023.07.03 14"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 检查tasks表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
            table_exists = cursor.fetchone() is not None
            
            if table_exists:
                # 检查表结构
                cursor.execute("PRAGMA table_info(tasks)")
                columns = {row[1] for row in cursor.fetchall()}
                
                # 检查是否需要重建表
                required_columns = {'task_id', 'user_id', 'task_type', 'params', 'status', 'result', 'error',
                                   'created_at', 'started_at', 'completed_at', 'priority', 'estimated_duration',
                                   'is_single_image', 'progress', 'in_comfyui'}
                
                missing_columns = required_columns - columns
                if missing_columns:
                    logger.warning(f"表结构不完整，缺少列: {missing_columns}。将尝试修复表结构。")
                    
                    # 备份旧表
                    cursor.execute("ALTER TABLE tasks RENAME TO tasks_old")
                    
                    # 创建新表
                    self._create_tasks_table(cursor)
                    
                    # 尝试迁移数据（仅复制存在的列）
                    existing_columns = required_columns.intersection(columns)
                    if existing_columns:
                        columns_str = ", ".join(existing_columns)
                        cursor.execute(f"INSERT INTO tasks ({columns_str}) SELECT {columns_str} FROM tasks_old")
                    
                    # 删除旧表
                    cursor.execute("DROP TABLE tasks_old")
                    logger.info("表结构已修复")
                else:
                    logger.info("表结构正确")
            else:
                # 创建新表
                self._create_tasks_table(cursor)
            
            conn.commit()
            conn.close()
            logger.info("数据库初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}")
        
    def _create_tasks_table(self, cursor):
        """创建tasks表 2023.07.03 14"""
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            params TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            error TEXT,
            created_at REAL NOT NULL,
            started_at REAL,
            completed_at REAL,
            priority INTEGER NOT NULL,
            estimated_duration INTEGER NOT NULL,
            is_single_image INTEGER NOT NULL,
            progress REAL DEFAULT 0,
            in_comfyui INTEGER DEFAULT 0
        )
        ''')
    
    def _recover_tasks(self):
        """从数据库恢复任务状态 2023.07.01 10"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 查询所有未完成的任务
            cursor.execute("SELECT * FROM tasks WHERE status IN ('pending', 'processing')")
            rows = cursor.fetchall()
            
            for row in rows:
                task_id = row[0]
                user_id = row[1]
                task_type = row[2]
                params_data = json.loads(row[3])
                status = row[4]
                result = json.loads(row[5]) if row[5] else None
                error = row[6]
                created_at = row[7]
                started_at = row[8]
                completed_at = row[9]
                priority = row[10]
                estimated_duration = row[11]
                is_single_image = bool(row[12])
                progress = row[13]
                in_comfyui = bool(row[14])
                
                # 创建任务对象
                task = Task(task_id, user_id, task_type, params_data, priority, estimated_duration, is_single_image)
                task.status = status
                task.result = result
                task.error = error
                task.created_at = created_at
                task.started_at = started_at
                task.completed_at = completed_at
                task.is_single_image = is_single_image
                task.progress = progress
                task.in_comfyui = in_comfyui
                
                # 将任务添加到队列或处理中列表
                if status == 'pending':
                    self.queue.append(task)
                elif status == 'processing':
                    # 对于处理中的任务，将其状态改为待处理，重新入队
                    task.status = 'pending'
                    self.queue.append(task)
            
            # 对队列进行排序
            self.sort_queue()
            
            conn.close()
            logger.info(f"从数据库恢复了 {len(rows)} 个任务")
        except Exception as e:
            logger.error(f"从数据库恢复任务失败: {str(e)}")
    
    def _save_task(self, task: Task):
        """将任务保存到数据库 2023.07.03 15"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT OR REPLACE INTO tasks 
            (task_id, user_id, task_type, params, status, result, error, 
             created_at, started_at, completed_at, priority, estimated_duration, 
             is_single_image, progress, in_comfyui)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task.id, 
                task.user_id,
                task.task_type,
                json.dumps(task.params),
                task.status,
                json.dumps(task.result) if task.result else None,
                task.error,
                task.created_at,
                task.started_at,
                task.completed_at,
                task.priority,
                task.estimated_duration,
                1 if task.is_single_image else 0,
                task.progress,
                1 if task.in_comfyui else 0
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"保存任务到数据库失败: {str(e)}")
    
    def add_task(self, task: Task):
        """添加任务到队列 2023.07.03 15"""
        try:
            self.queue.append(task)
            self.sort_queue()
            self._save_task(task)
            logger.info(f"添加任务: {task.id}, 用户: {task.user_id}, 类型: {task.task_type}")
            return task.id
        except Exception as e:
            logger.error(f"添加任务失败: {str(e)}")
            return None
    
    def sort_queue(self):
        """根据优先级排序队列 2023.07.01 10"""
        # 排序规则：
        # 1. 优先级高的先处理
        # 2. 单图任务优先于多图任务
        # 3. 短任务优先于长任务
        # 4. 等待时间长的任务优先级提高（任务老化）
        current_time = time.time()
        
        def sort_key(task):
            # 计算任务老化因子，每等待10分钟，优先级+0.1
            age_factor = (current_time - task.created_at) / 600 * 0.1
            return (
                -(task.priority + age_factor),  # 优先级越高越靠前
                -1 if task.is_single_image else 1,  # 单图优先
                task.estimated_duration  # 短任务优先
            )
        
        self.queue.sort(key=sort_key)
    
    def process_next_available(self):
        """处理下一个可用任务 2023.07.01 10"""
        if len(self.processing) < self.max_concurrent and self.queue:
            task = self.queue.pop(0)
            task.status = 'processing'
            task.started_at = time.time()
            self._save_task(task)
            
            # 启动任务处理
            self.processing[task.id] = {
                'start_time': task.started_at,
                'task': task,
                'process': None  # 将在process_task中设置
            }
            
            logger.info(f"开始处理任务: {task.id}, 用户: {task.user_id}")
            return task
        return None
    
    def complete_task(self, task_id: str, status: str = 'completed', result: Any = None, error: str = None):
        """完成任务 2023.07.01 10"""
        if task_id in self.processing:
            task = self.processing[task_id]['task']
            task.status = status
            task.completed_at = time.time()
            task.result = result
            task.error = error
            
            # 保存到已完成任务
            self.completed[task_id] = task
            
            # 从处理中任务移除
            del self.processing[task_id]
            
            # 更新数据库
            self._save_task(task)
            
            logger.info(f"完成任务: {task_id}, 状态: {status}")
            return True
        return False
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务 2023.07.01 10"""
        # 检查处理中的任务
        if task_id in self.processing:
            return self.processing[task_id]['task']
        
        # 检查队列中的任务
        for task in self.queue:
            if task.id == task_id:
                return task
        
        # 检查已完成的任务
        if task_id in self.completed:
            return self.completed[task_id]
        
        # 从数据库查询
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            
            if row:
                task_id = row[0]
                user_id = row[1]
                task_type = row[2]
                params_data = json.loads(row[3])
                status = row[4]
                result = json.loads(row[5]) if row[5] else None
                error = row[6]
                created_at = row[7]
                started_at = row[8]
                completed_at = row[9]
                priority = row[10]
                estimated_duration = row[11]
                is_single_image = bool(row[12])
                progress = row[13]
                in_comfyui = bool(row[14])
                
                # 创建任务对象
                task = Task(task_id, user_id, task_type, params_data, priority, estimated_duration, is_single_image)
                task.status = status
                task.result = result
                task.error = error
                task.created_at = created_at
                task.started_at = started_at
                task.completed_at = completed_at
                task.is_single_image = is_single_image
                task.progress = progress
                task.in_comfyui = in_comfyui
                
                conn.close()
                return task
            
            conn.close()
        except Exception as e:
            logger.error(f"从数据库获取任务失败: {str(e)}")
        
        return None
    
    def get_queue_position(self, task_id: str) -> Optional[int]:
        """获取任务在队列中的位置 2023.07.01 10"""
        for i, task in enumerate(self.queue):
            if task.id == task_id:
                return i + 1  # 位置从1开始
        return None
    
    def estimate_wait_time(self, position: int) -> int:
        """估计等待时间（秒） 2023.07.01 10"""
        if position <= 0:
            return 0
        
        # 简单估算：假设每个任务平均需要2分钟，考虑并发数
        avg_task_time = 120  # 秒
        concurrent = max(1, self.max_concurrent)
        
        # 计算前面有多少批次的任务
        batches = (position - 1) // concurrent + 1
        
        # 估计时间
        estimated_time = batches * avg_task_time
        
        return estimated_time
    
    def update_task_progress(self, task_id: str, progress: int):
        """更新任务进度 2023.07.01 10"""
        task = self.get_task(task_id)
        if task:
            task.progress = progress
            self._save_task(task)
            return True
        return False
    
    def count_user_active_tasks(self, user_id: str) -> int:
        """计算用户活跃任务数 2023.07.01 10"""
        count = 0
        
        # 检查处理中的任务
        for task_info in self.processing.values():
            if task_info['task'].user_id == user_id:
                count += 1
        
        # 检查队列中的任务
        for task in self.queue:
            if task.user_id == user_id:
                count += 1
        
        return count
    
    def cancel_task(self, task_id: str, user_id: str) -> Tuple[bool, str]:
        """取消任务 2023.07.03 12"""
        # 首先获取任务对象
        task = self.get_task(task_id)
        if not task:
            return False, "任务不存在"
            
        # 验证任务所有权
        if task.user_id != user_id:
            return False, "无权取消此任务"
            
        # 检查任务是否可以取消
        if task.status == 'completed':
            return False, "任务已完成，无法取消"
        elif task.status == 'failed':
            return False, "任务已失败，无法取消"
        elif task.status == 'cancelled':
            return False, "任务已被取消"
        elif task.in_comfyui:
            return False, "任务已进入生成阶段，无法取消"
            
        try:
            # 从队列中移除任务
            for i, queued_task in enumerate(self.queue):
                if queued_task.id == task_id:
                    self.queue.pop(i)
                    break
                
            # 如果任务正在处理中且未进入ComfyUI，尝试终止处理
            if task.status == 'processing' and not task.in_comfyui:
                # 更新任务状态
                self.update_task_status(task_id, 'cancelled', error="用户取消")
                
            return True, "任务已取消"
            
        except Exception as e:
            logger.error(f"取消任务失败: {str(e)}")
            return False, f"取消任务失败: {str(e)}"
    
    def _task_processor_loop(self):
        """任务处理主循环 2023.07.01 10"""
        while self.running:
            try:
                # 检查GPU资源
                resources = self._monitor_gpu_resources()
                
                # 如果资源可用，处理下一个任务
                if resources['available']:
                    task = self.process_next_available()
                    if task:
                        # 启动任务处理
                        self._process_task(task)
                
                # 检查任务超时
                self._check_task_timeouts()
                
                # 更新队列排序
                self.sort_queue()
                
                # 短暂休眠，避免过度轮询
                time.sleep(TASK_QUEUE_CONFIG['queue_check_interval'])
            except Exception as e:
                logger.error(f"任务处理循环异常: {str(e)}")
    
    def _monitor_gpu_resources(self) -> Dict[str, Any]:
        """监控GPU资源 2023.07.01 10"""
        try:
            # 检查nvidia-smi是否可用
            nvidia_smi_available = subprocess.run(
                ['which', 'nvidia-smi'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            ).returncode == 0
            
            if not nvidia_smi_available:
                logger.debug("nvidia-smi不可用，使用默认GPU状态")
                return {
                    'gpu_usage': 0,
                    'memory_usage': 0,
                    'available': True
                }
            
            # 使用nvidia-smi获取GPU使用情况
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.debug(f"nvidia-smi返回错误代码: {result.returncode}")
                return {
                    'gpu_usage': 0,
                    'memory_usage': 0,
                    'available': True
                }
            
            # 解析输出
            output = result.stdout.strip()
            if output:
                lines = output.split('\n')
                gpu_data = lines[0].split(',')
                
                gpu_usage = float(gpu_data[0].strip())
                memory_used = float(gpu_data[1].strip())
                memory_total = float(gpu_data[2].strip())
                memory_usage = (memory_used / memory_total) * 100
                
                # 根据GPU使用情况调整并发任务数
                if gpu_usage > TASK_QUEUE_CONFIG['gpu_usage_high_threshold'] or memory_usage > TASK_QUEUE_CONFIG['gpu_memory_high_threshold']:
                    self.max_concurrent = 1  # 降低并发数
                elif gpu_usage < TASK_QUEUE_CONFIG['gpu_usage_normal_threshold'] and memory_usage < TASK_QUEUE_CONFIG['gpu_memory_normal_threshold']:
                    self.max_concurrent = TASK_QUEUE_CONFIG['max_concurrent_tasks']  # 恢复并发数
                
                return {
                    'gpu_usage': gpu_usage,
                    'memory_usage': memory_usage,
                    'available': gpu_usage < 95 and memory_usage < 90
                }
        except subprocess.TimeoutExpired:
            logger.warning("nvidia-smi命令超时")
        except FileNotFoundError:
            logger.debug("nvidia-smi命令未找到")
        except Exception as e:
            logger.debug(f"监控GPU资源失败: {str(e)}")
        
        # 默认返回可用（适用于没有GPU或GPU监控不可用的情况）
        return {
            'gpu_usage': 0,
            'memory_usage': 0,
            'available': True
        }
    
    def _check_task_timeouts(self):
        """检查任务超时 2023.07.01 10"""
        current_time = time.time()
        for task_id, task_info in list(self.processing.items()):
            # 检查任务是否超时
            if current_time - task_info['start_time'] > self.task_timeout:
                logger.warning(f"任务超时: {task_id}")
                
                # 尝试终止任务
                process = task_info.get('process')
                if process:
                    try:
                        process.terminate()
                        logger.info(f"终止进程: {process.pid}")
                    except:
                        logger.warning(f"终止进程失败: {process.pid}")
                
                # 更新任务状态
                self.complete_task(task_id, 'failed', None, "任务超时")
    
    def _process_task(self, task: Task):
        """处理任务 2023.07.03 14"""
        logger.info(f"处理任务: {task.id}, 类型: {task.task_type}")
        
        try:
            # 导入需要的模块
            import asyncio
            import sys
            import os
            import uuid
            import json
            import time
            import shutil
            from pathlib import Path
            import sqlite3
            
            # 动态导入app模块中的函数
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            import config
            
            # 使用app中的函数
            try:
                from app import modify_text_to_image_workflow
                from app import queue_prompt_comfyui as queue_prompt
                from app import get_comfyui_history
            except ImportError as e:
                logger.error(f"导入app模块函数失败: {str(e)}")
                self.update_task_status(task.id, 'failed', error=f"导入app模块函数失败: {str(e)}")
                return
            
            # 创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if task.task_type == 'text-to-image':
                logger.info(f"开始处理文生图任务: {task.id}")
                logger.info(f"任务参数: {task.params}")
                
                try:
                    # 检查配置文件
                    logger.info("检查配置文件中的文生图工作流路径...")
                    if not hasattr(config, 'TEXT_TO_IMAGE_WORKFLOW_FILE_PATH'):
                        raise Exception("配置文件中缺少 TEXT_TO_IMAGE_WORKFLOW_FILE_PATH 配置项")
                    
                    workflow_path = config.TEXT_TO_IMAGE_WORKFLOW_FILE_PATH
                    logger.info(f"文生图工作流文件路径: {workflow_path}")
                    
                    if not os.path.exists(workflow_path):
                        raise Exception(f"文生图工作流文件不存在: {workflow_path}")
                    
                    logger.info("开始修改文生图工作流...")
                    # 修改工作流
                    try:
                        workflow = modify_text_to_image_workflow(task.params)
                        logger.info("文生图工作流修改成功")
                        logger.debug(f"修改后的工作流: {json.dumps(workflow, indent=2)}")
                    except Exception as e:
                        logger.error(f"修改文生图工作流失败: {str(e)}")
                        raise Exception(f"工作流修改失败: {str(e)}")
                    
                    # 提交到ComfyUI
                    logger.info("提交文生图工作流到ComfyUI...")
                    try:
                        prompt_result = loop.run_until_complete(queue_prompt(workflow))
                        logger.info(f"ComfyUI响应: {prompt_result}")
                        
                        if not prompt_result:
                            raise Exception("ComfyUI返回空响应")
                        
                        # 检查返回格式
                        if isinstance(prompt_result, dict) and 'prompt_id' in prompt_result:
                            prompt_id = prompt_result['prompt_id']
                        elif isinstance(prompt_result, str):
                            prompt_id = prompt_result
                        else:
                            raise Exception(f"ComfyUI返回的响应格式不正确: {type(prompt_result)} - {prompt_result}")
                        
                        if not prompt_id:
                            raise Exception("ComfyUI返回的prompt_id为空")
                            
                        logger.info(f"成功提交到ComfyUI，prompt_id: {prompt_id}")
                        
                    except Exception as e:
                        logger.error(f"提交到ComfyUI失败: {str(e)}")
                        raise Exception(f"提交到ComfyUI失败: {str(e)}")
                    
                    # 标记任务已进入ComfyUI处理
                    task.in_comfyui = True
                    self.update_task_status(task.id, 'processing', error=None)
                    logger.info(f"任务 {task.id} 已标记为进入ComfyUI处理阶段")
                    
                    # 轮询结果
                    logger.info("开始轮询ComfyUI处理结果...")
                    start_time = time.time()
                    result = None
                    poll_count = 0
                    
                    while time.time() - start_time < config.COMFYUI_POLLING_TIMEOUT_SECONDS:
                        poll_count += 1
                        logger.info(f"第 {poll_count} 次轮询ComfyUI历史记录...")
                        
                        try:
                            result = loop.run_until_complete(get_comfyui_history(prompt_id))
                            logger.debug(f"ComfyUI历史记录响应: {result}")
                            
                            if result is None:
                                logger.info("ComfyUI返回空结果，继续等待...")
                                time.sleep(5)  # 等待5秒后重试
                                continue
                            if "outputs" in result:
                                logger.info("检测到ComfyUI输出结果，处理完成")
                                break
                        except Exception as e:
                            logger.error(f"第 {poll_count} 次获取ComfyUI历史记录失败: {str(e)}")
                            time.sleep(5)
                            continue
                            
                        # 更新任务进度
                        progress = min(90, 20 + (poll_count * 3))  # 从20%开始，每次增加3%，最大90%
                        self.update_task_progress(task.id, progress)
                        logger.info(f"更新任务进度: {progress}%")
                        
                    if not result or "outputs" not in result:
                        logger.error("ComfyUI处理超时或失败")
                        logger.error(f"最终结果: {result}")
                        raise Exception("ComfyUI处理超时或失败")
                        
                    # 处理结果
                    output_images = []
                    for node_id, node_output in result["outputs"].items():
                        if "images" in node_output:
                            for img_data in node_output["images"]:
                                img_filename = img_data["filename"]
                                img_subfolder = img_data.get("subfolder", "")
                                
                                # 构建完整的图像路径
                                if img_subfolder:
                                    img_path = os.path.join(config.COMFYUI_OUTPUT_DIR, img_subfolder, img_filename)
                                else:
                                    img_path = os.path.join(config.COMFYUI_OUTPUT_DIR, img_filename)
                                
                                # 将图像复制到用户目录
                                user_dir = os.path.join(config.USER_IMAGES_BASE_DIR, task.user_id)
                                os.makedirs(user_dir, exist_ok=True)
                                
                                # 生成唯一文件名
                                unique_filename = f"{uuid.uuid4()}.png"
                                user_img_path = os.path.join(user_dir, unique_filename)
                                
                                # 复制文件
                                shutil.copy2(img_path, user_img_path)
                                
                                # 添加到输出列表
                                output_images.append({
                                    "filename": unique_filename,
                                    "path": user_img_path
                                })
                    
                    # 保存到数据库
                    conn = None
                    try:
                        conn = sqlite3.connect(config.DB_FILE)
                        cursor = conn.cursor()
                        
                        for img in output_images:
                            cursor.execute(
                                "INSERT INTO image_generations (user_email, prompt, image_filename, generation_type, timestamp) VALUES (?, ?, ?, ?, datetime('now'))",
                                (task.user_id, task.params["prompt"], img["filename"], "text-to-image")
                            )
                        
                        conn.commit()
                    except Exception as e:
                        logger.error(f"保存到数据库失败: {str(e)}")
                        if conn:
                            conn.rollback()
                    finally:
                        if conn:
                            conn.close()
                    
                    # 完成任务
                    logger.info(f"文生图任务 {task.id} 处理完成，生成了 {len(output_images)} 张图像")
                    self.complete_task(task.id, 'completed', {"images": output_images})
                    
                except Exception as e:
                    error_msg = f"处理文生图任务 {task.id} 失败: {str(e)}"
                    logger.error(error_msg)
                    logger.error(f"错误堆栈: ", exc_info=True)
                    self.update_task_status(task.id, 'failed', error=str(e))
                    return
                
            elif task.task_type == 'image-to-image':
                logger.info(f"开始处理图生图任务: {task.id}")
                logger.info(f"任务参数: {task.params}")
                
                try:
                    # 检查配置文件
                    logger.info("检查配置文件中的图生图工作流路径...")
                    if not hasattr(config, 'IMAGE_TO_IMAGE_WORKFLOW_FILE_PATH'):
                        raise Exception("配置文件中缺少 IMAGE_TO_IMAGE_WORKFLOW_FILE_PATH 配置项")
                    
                    workflow_path = config.IMAGE_TO_IMAGE_WORKFLOW_FILE_PATH
                    logger.info(f"工作流文件路径: {workflow_path}")
                    
                    if not os.path.exists(workflow_path):
                        raise Exception(f"工作流文件不存在: {workflow_path}")
                    
                    # 导入图像处理相关函数
                    logger.info("导入图像处理相关函数...")
                    try:
                        from app import modify_comfyui_workflow
                        logger.info("成功导入 modify_comfyui_workflow 函数")
                    except ImportError as e:
                        logger.error(f"导入 modify_comfyui_workflow 函数失败: {str(e)}")
                        raise Exception(f"无法导入图像处理函数: {str(e)}")
                    
                    # 获取和验证任务参数
                    logger.info("解析任务参数...")
                    uploaded_image_path = task.params.get("uploaded_image_path")
                    prompt = task.params.get("prompt", "")
                    image_strength = task.params.get("image_strength", "0.8")
                    face_file_paths = task.params.get("face_file_paths", [])
                    
                    logger.info(f"输入图像路径: {uploaded_image_path}")
                    logger.info(f"提示词: {prompt}")
                    logger.info(f"图像强度: {image_strength}")
                    logger.info(f"人脸文件: {face_file_paths}")
                    
                    # 验证输入图像文件是否存在
                    if not uploaded_image_path:
                        raise Exception("缺少输入图像路径")
                    
                    if not os.path.exists(uploaded_image_path):
                        raise Exception(f"输入图像文件不存在: {uploaded_image_path}")
                    
                    logger.info(f"输入图像文件验证通过: {uploaded_image_path}")
                    
                    # 修改工作流
                    logger.info("开始修改ComfyUI工作流...")
                    try:
                        workflow = modify_comfyui_workflow(
                            workflow_json_path=workflow_path,
                            input_image_path=uploaded_image_path,
                            prompt=prompt,
                            image_strength=image_strength,
                            face_files=face_file_paths
                        )
                        logger.info("工作流修改成功")
                        logger.debug(f"修改后的工作流: {json.dumps(workflow, indent=2)}")
                    except Exception as e:
                        logger.error(f"修改工作流失败: {str(e)}")
                        raise Exception(f"工作流修改失败: {str(e)}")
                    
                    # 提交到ComfyUI
                    logger.info("提交工作流到ComfyUI...")
                    try:
                        prompt_result = loop.run_until_complete(queue_prompt(workflow))
                        logger.info(f"ComfyUI响应: {prompt_result}")
                        
                        if not prompt_result:
                            raise Exception("ComfyUI返回空响应")
                        
                        # 检查返回格式
                        if isinstance(prompt_result, dict) and 'prompt_id' in prompt_result:
                            prompt_id = prompt_result['prompt_id']
                        elif isinstance(prompt_result, str):
                            prompt_id = prompt_result
                        else:
                            raise Exception(f"ComfyUI返回的响应格式不正确: {type(prompt_result)} - {prompt_result}")
                        
                        if not prompt_id:
                            raise Exception("ComfyUI返回的prompt_id为空")
                            
                        logger.info(f"成功提交到ComfyUI，prompt_id: {prompt_id}")
                        
                    except Exception as e:
                        logger.error(f"提交到ComfyUI失败: {str(e)}")
                        raise Exception(f"提交到ComfyUI失败: {str(e)}")
                    
                    # 标记任务已进入ComfyUI处理
                    task.in_comfyui = True
                    self.update_task_status(task.id, 'processing', error=None)
                    logger.info(f"任务 {task.id} 已标记为进入ComfyUI处理阶段")
                    
                    # 轮询结果
                    logger.info("开始轮询ComfyUI处理结果...")
                    start_time = time.time()
                    result = None
                    poll_count = 0
                    
                    while time.time() - start_time < 300:  # 5分钟超时
                        poll_count += 1
                        logger.info(f"第 {poll_count} 次轮询ComfyUI历史记录...")
                        
                        try:
                            result = loop.run_until_complete(get_comfyui_history(prompt_id))
                            logger.debug(f"ComfyUI历史记录响应: {result}")
                            
                            if result and "outputs" in result:
                                logger.info("检测到ComfyUI输出结果，处理完成")
                                break
                            else:
                                logger.info("ComfyUI还在处理中，继续等待...")
                                
                        except Exception as e:
                            logger.error(f"第 {poll_count} 次获取ComfyUI历史记录失败: {str(e)}")
                            time.sleep(5)
                            continue
                            
                        # 更新进度
                        progress = min(90, 20 + (poll_count * 5))  # 从20%开始，每次增加5%，最大90%
                        self.update_task_progress(task.id, progress)
                        logger.info(f"更新任务进度: {progress}%")
                        
                        time.sleep(5)
                        
                    if not result or "outputs" not in result:
                        logger.error("ComfyUI处理超时或失败")
                        logger.error(f"最终结果: {result}")
                        raise Exception("ComfyUI处理超时或失败")
                    
                    # 处理结果
                    logger.info("开始处理ComfyUI输出结果...")
                    output_images = []
                    
                    try:
                        # 解析输出图像
                        for node_id, node_output in result["outputs"].items():
                            logger.info(f"处理节点 {node_id} 的输出...")
                            if "images" in node_output:
                                for img_data in node_output["images"]:
                                    img_filename = img_data["filename"]
                                    img_subfolder = img_data.get("subfolder", "")
                                    
                                    logger.info(f"处理图像: {img_filename}, 子文件夹: {img_subfolder}")
                                    
                                    # 构建完整的图像路径
                                    if img_subfolder:
                                        img_path = os.path.join(config.COMFYUI_OUTPUT_DIR, img_subfolder, img_filename)
                                    else:
                                        img_path = os.path.join(config.COMFYUI_OUTPUT_DIR, img_filename)
                                    
                                    logger.info(f"图像源路径: {img_path}")
                                    
                                    if not os.path.exists(img_path):
                                        logger.warning(f"输出图像文件不存在: {img_path}")
                                        continue
                                    
                                    # 将图像复制到用户目录
                                    user_dir_name = task.user_id.replace('@', '_at_').replace('.', '_dot_')
                                    user_dir = os.path.join(config.USER_GENERATED_IMAGES_DIR, user_dir_name)
                                    os.makedirs(user_dir, exist_ok=True)
                                    
                                    # 生成唯一文件名
                                    import uuid
                                    unique_filename = f"{uuid.uuid4()}.png"
                                    user_img_path = os.path.join(user_dir, unique_filename)
                                    
                                    # 复制文件
                                    import shutil
                                    shutil.copy2(img_path, user_img_path)
                                    logger.info(f"图像已复制到用户目录: {user_img_path}")
                                    
                                    # 添加到输出列表
                                    output_images.append({
                                        "filename": unique_filename,
                                        "path": user_img_path
                                    })
                        
                        logger.info(f"共处理了 {len(output_images)} 张输出图像")
                        
                        if not output_images:
                            logger.warning("没有找到任何输出图像")
                        
                    except Exception as e:
                        logger.error(f"处理输出图像时发生错误: {str(e)}")
                        # 即使图像处理失败，也不要让整个任务失败
                        output_images = []
                    
                    # 保存到数据库
                    try:
                        logger.info("保存结果到数据库...")
                        import sqlite3
                        
                        # 检查数据库配置
                        if hasattr(config, 'DB_FILE'):
                            db_file = config.DB_FILE
                        else:
                            db_file = os.path.join(config.BASE_DIR, 'image_history.db')
                        
                        logger.info(f"数据库文件路径: {db_file}")
                        
                        conn = sqlite3.connect(db_file)
                        cursor = conn.cursor()
                        
                        for img in output_images:
                            cursor.execute(
                                "INSERT INTO image_generations (user_email, prompt, image_filename, generation_type, timestamp) VALUES (?, ?, ?, ?, datetime('now'))",
                                (task.user_id, prompt, img["filename"], "image-to-image")
                            )
                            logger.info(f"保存图像记录到数据库: {img['filename']}")
                        
                        conn.commit()
                        conn.close()
                        logger.info("数据库保存成功")
                        
                    except Exception as e:
                        logger.error(f"保存到数据库失败: {str(e)}")
                        # 数据库保存失败不影响任务完成
                    
                    # 完成任务
                    logger.info(f"图生图任务 {task.id} 处理完成")
                    self.complete_task(task.id, 'completed', {"images": output_images})
                    
                except Exception as e:
                    error_msg = f"处理图像到图像任务 {task.id} 失败: {str(e)}"
                    logger.error(error_msg)
                    logger.error(f"错误堆栈: ", exc_info=True)
                    self.update_task_status(task.id, 'failed', error=str(e))
                    return
                
        except Exception as e:
            logger.error(f"处理任务 {task.id} 失败: {str(e)}")
            self.update_task_status(task.id, 'failed', error=str(e))
            return

    def clean_tasks(self):
        """清理任务状态 2023.07.03 11"""
        try:
            # 清理内存中的任务
            self.queue = []
            self.processing = {}
            self.completed = {}
            
            # 清理数据库中的任务
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 将所有pending和processing状态的任务更新为failed
            cursor.execute("""
                UPDATE tasks 
                SET status = 'failed', 
                    error = '系统重启，任务已清理',
                    completed_at = ?
                WHERE status IN ('pending', 'processing')
            """, (time.time(),))
            
            conn.commit()
            conn.close()
            
            logger.info("任务状态已清理")
            return True, "任务状态已清理"
        except Exception as e:
            logger.error(f"清理任务状态失败: {str(e)}")
            return False, f"清理任务状态失败: {str(e)}"

    def get_queue_status(self, user_id: str = None) -> Dict[str, Any]:
        """获取队列状态 2023.07.03 11"""
        try:
            # 计算活跃任务数（队列中 + 处理中）
            total_active = len(self.queue) + len(self.processing)
            
            # 如果提供了用户ID，计算用户专属的任务数
            user_tasks_in_queue = 0
            user_tasks_processing = 0
            
            if user_id:
                # 计算用户队列中的任务数
                for task in self.queue:
                    if task.user_id == user_id:
                        user_tasks_in_queue += 1
                
                # 计算用户处理中的任务数
                for task_info in self.processing.values():
                    if task_info['task'].user_id == user_id:
                        user_tasks_processing += 1
            
            # 获取当前正在处理的任务信息
            processing_tasks = []
            for task_id, task_info in self.processing.items():
                task = task_info['task']
                processing_tasks.append({
                    'task_id': task.id,
                    'user_id': task.user_id,
                    'type': task.task_type,
                    'progress': task.progress,
                    'started_at': task.started_at
                })
            
            # 获取队列中的任务信息
            queued_tasks = []
            for task in self.queue:
                queued_tasks.append({
                    'task_id': task.id,
                    'user_id': task.user_id,
                    'type': task.task_type,
                    'created_at': task.created_at
                })
            
            return {
                # 保持向后兼容的字段名
                'total_active': total_active,
                'processing_count': len(self.processing),
                'queue_count': len(self.queue),
                'max_concurrent': self.max_concurrent,
                'processing_tasks': processing_tasks,
                'queued_tasks': queued_tasks,
                
                # 添加前端QueueStatusPanel期望的字段名
                'queue_length': len(self.queue),
                'user_tasks_in_queue': user_tasks_in_queue,
                'user_tasks_processing': user_tasks_processing,
                'concurrent_tasks': len(self.processing)
            }
        except Exception as e:
            logger.error(f"获取队列状态失败: {str(e)}")
            return {
                'total_active': 0,
                'processing_count': 0,
                'queue_count': 0,
                'max_concurrent': self.max_concurrent,
                'processing_tasks': [],
                'queued_tasks': [],
                'queue_length': 0,
                'user_tasks_in_queue': 0,
                'user_tasks_processing': 0,
                'concurrent_tasks': 0
            }

    def _process_comfyui_output(self, task: Task, output_data: Dict):
        """处理ComfyUI输出 2023.07.03 12"""
        try:
            # 获取图片文件名
            img_filename = None
            img_subfolder = None
            
            # 遍历输出节点找到保存的图片
            for node_id, node_output in output_data.get("output", {}).items():
                if "images" in node_output and node_output["images"]:
                    img_filename = node_output["images"][0]["filename"]
                    img_subfolder = node_output["images"][0].get("subfolder", "")
                    break
                
            if not img_filename:
                raise ValueError("未找到生成的图片文件名")
            
            # 构建完整的图片路径
            if img_subfolder:
                img_path = os.path.join(config.COMFYUI_OUTPUT_DIR, img_subfolder, img_filename)
            else:
                img_path = os.path.join(config.COMFYUI_OUTPUT_DIR, img_filename)
            
            # 创建用户目录
            user_dir = os.path.join(config.USER_GENERATED_IMAGES_DIR, task.user_id)
            os.makedirs(user_dir, exist_ok=True)
            
            # 移动图片到用户目录
            user_img_path = os.path.join(user_dir, img_filename)
            shutil.move(img_path, user_img_path)
            
            # 更新任务结果
            task.result = {
                "image_filename": img_filename,
                "image_path": user_img_path
            }
            
            return True
        except Exception as e:
            logger.error(f"处理ComfyUI输出时出错: {str(e)}")
            task.error = f"处理生成的图片时出错: {str(e)}"
            return False

    def update_task_status(self, task_id: str, status: str, result: Any = None, error: str = None):
        """更新任务状态 2023.07.03 14"""
        task = self.get_task(task_id)
        if not task:
            logger.warning(f"尝试更新不存在的任务状态: {task_id}")
            return False
        
        task.status = status
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        
        if status in ['completed', 'failed', 'cancelled']:
            task.completed_at = time.time()
        
        self._save_task(task)
        logger.info(f"更新任务状态: {task_id} -> {status}")
        return True

# 全局任务队列实例
task_queue = SimpleTaskQueue()

def get_task_queue() -> SimpleTaskQueue:
    """获取任务队列实例 2023.07.01 10"""
    return task_queue 