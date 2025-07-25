import subprocess
import requests
import time
import os
import logging
import threading
import psutil
import signal
from typing import Dict, Any, Optional, Tuple
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("comfyui_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ComfyUIManager")

class ComfyUIManager:
    """ComfyUI管理器类 2023.07.04 15"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """单例模式实现 2023.07.04 15"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ComfyUIManager, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化ComfyUI管理器 2023.07.04 16"""
        if self._initialized:
            return
            
        # 尝试从配置文件获取ComfyUI路径
        try:
            import config
            self.comfyui_path = getattr(config, 'COMFYUI_PATH', os.environ.get("COMFYUI_PATH", ""))
            logger.info(f"从配置文件获取ComfyUI路径: {self.comfyui_path}")
        except ImportError:
            self.comfyui_path = os.environ.get("COMFYUI_PATH", "")
            logger.warning(f"无法导入配置文件，使用环境变量中的ComfyUI路径: {self.comfyui_path}")
        
        # 如果路径为空，尝试常见的安装路径
        if not self.comfyui_path or not os.path.exists(self.comfyui_path):
            common_paths = [
                # os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ComfyUI"),  # 相对于当前文件的上级目录
                # os.path.join(os.path.dirname(os.path.abspath(__file__)), "ComfyUI"),  # 相对于当前文件的同级目录
                "C:\\ComfyUI",  # Windows常见路径
                "/home/huangjunjie/comfy/ComfyUI",  # Linux常见路径
                os.path.expanduser("~/ComfyUI"),  # 用户主目录
            ]
            
            for path in common_paths:
                if os.path.exists(path) and os.path.exists(os.path.join(path, "main.py")):
                    self.comfyui_path = path
                    logger.info(f"找到ComfyUI安装路径: {self.comfyui_path}")
                    break
        
        # 检测conda环境
        self.conda_path, self.conda_env_path = self._detect_conda_env()
        
        # 记录最终使用的路径
        logger.info(f"使用ComfyUI路径: {self.comfyui_path}")
        logger.info(f"检测到conda路径: {self.conda_path}")
        logger.info(f"检测到conda环境路径: {self.conda_env_path}")
            
        self.comfyui_url = "http://127.0.0.1:8188"
        self.comfyui_process = None
        self.max_memory_usage_gb = 20  # 最大显存使用阈值（GB）
        self.max_gpu_utilization = 50  # 最大GPU使用率阈值（%）
        self.check_interval = 30  # 检查间隔（秒）
        self._initialized = True
        
        # 启动监控线程
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        
        logger.info("ComfyUI管理器初始化完成")
    
    def _detect_conda_env(self) -> Tuple[Optional[str], Optional[str]]:
        """检测conda环境路径"""
        try:
            # 常见的conda安装路径
            conda_paths = [
                "/home/huangjunjie/miniconda3/bin/conda",
                "/home/huangjunjie/anaconda3/bin/conda",
                "/opt/conda/bin/conda",
                "/usr/local/bin/conda",
                os.path.expanduser("~/miniconda3/bin/conda"),
                os.path.expanduser("~/anaconda3/bin/conda"),
            ]
            
            conda_path = None
            for path in conda_paths:
                if os.path.exists(path):
                    conda_path = path
                    logger.info(f"找到conda路径: {conda_path}")
                    break
            
            # 检测comfyui环境路径
            conda_env_path = None
            if conda_path:
                env_paths = [
                    "/home/huangjunjie/miniconda3/envs/comfyui/bin/python",
                    "/home/huangjunjie/anaconda3/envs/comfyui/bin/python",
                    os.path.expanduser("~/miniconda3/envs/comfyui/bin/python"),
                    os.path.expanduser("~/anaconda3/envs/comfyui/bin/python"),
                ]
                
                for path in env_paths:
                    if os.path.exists(path):
                        conda_env_path = path
                        logger.info(f"找到comfyui环境Python路径: {conda_env_path}")
                        break
            
            return conda_path, conda_env_path
            
        except Exception as e:
            logger.warning(f"检测conda环境失败: {str(e)}")
            return None, None
    
    def _monitoring_loop(self):
        """监控循环 2023.07.04 15"""
        while True:
            try:
                # 检查ComfyUI状态
                is_running = self.is_comfyui_running()
                logger.info(f"ComfyUI运行状态: {'运行中' if is_running else '未运行'}")
                
                # 检查GPU资源
                gpu_info = self.get_gpu_info()
                logger.info(f"GPU状态: 使用率={gpu_info['utilization']}%, 显存使用={gpu_info['memory_used_gb']:.2f}GB/{gpu_info['memory_total_gb']:.2f}GB")
                
                # 如果ComfyUI进程意外终止，更新状态
                if self.comfyui_process and not self.comfyui_process.poll() is None:
                    logger.warning("检测到ComfyUI进程已终止")
                    self.comfyui_process = None
                
            except Exception as e:
                logger.error(f"监控循环异常: {str(e)}")
                
            time.sleep(self.check_interval)
    
    def is_comfyui_running(self) -> bool:
        """检查ComfyUI是否正在运行 2023.07.04 15"""
        try:
            response = requests.get(f"{self.comfyui_url}/system_stats", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_gpu_info(self) -> Dict[str, Any]:
        """获取GPU信息 2023.07.04 15"""
        try:
            # 使用nvidia-smi获取GPU使用情况
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            
            # 解析输出
            output = result.stdout.strip()
            if output:
                lines = output.split('\n')
                gpu_data = lines[0].split(',')
                
                utilization = float(gpu_data[0].strip())
                memory_used = float(gpu_data[1].strip())
                memory_total = float(gpu_data[2].strip())
                
                # 转换为GB
                memory_used_gb = memory_used / 1024
                memory_total_gb = memory_total / 1024
                
                return {
                    'utilization': utilization,
                    'memory_used': memory_used,
                    'memory_total': memory_total,
                    'memory_used_gb': memory_used_gb,
                    'memory_total_gb': memory_total_gb,
                    'memory_usage_percent': (memory_used / memory_total) * 100 if memory_total > 0 else 0
                }
        except Exception as e:
            logger.error(f"获取GPU信息失败: {str(e)}")
        
        # 默认返回
        return {
            'utilization': 0,
            'memory_used': 0,
            'memory_total': 1,
            'memory_used_gb': 0,
            'memory_total_gb': 1,
            'memory_usage_percent': 0
        }
    
    def start_comfyui(self) -> Tuple[bool, str]:
        """启动ComfyUI 2023.07.04 16"""
        if self.is_comfyui_running():
            return True, "ComfyUI已经在运行"
        
        # 检查GPU显存
        gpu_info = self.get_gpu_info()
        if gpu_info['memory_used_gb'] >= self.max_memory_usage_gb:
            return False, f"GPU显存使用过高 ({gpu_info['memory_used_gb']:.2f}GB/{gpu_info['memory_total_gb']:.2f}GB)，无法启动ComfyUI"
        
        # 检查ComfyUI路径是否存在
        if not os.path.exists(self.comfyui_path):
            logger.error(f"ComfyUI路径不存在: {self.comfyui_path}")
            return False, f"ComfyUI路径不存在: {self.comfyui_path}"
        
        # 检查main.py是否存在
        main_py_path = os.path.join(self.comfyui_path, "main.py")
        if not os.path.exists(main_py_path):
            logger.error(f"ComfyUI main.py不存在: {main_py_path}")
            return False, f"ComfyUI main.py不存在: {main_py_path}"
        
        try:
            # 获取Python解释器路径
            python_path = sys.executable
            logger.info(f"使用Python解释器: {python_path}")
            
            # 构建启动命令列表
            start_commands = []
            
            # 优先使用检测到的conda环境Python路径
            if self.conda_env_path:
                start_commands.append(f"cd {self.comfyui_path} && {self.conda_env_path} main.py")
            
            # 使用conda run命令
            if self.conda_path:
                start_commands.append(f"cd {self.comfyui_path} && {self.conda_path} run -n comfyui python main.py")
            
            # 尝试bash初始化的方式
            start_commands.extend([
                f"bash -c 'source ~/.bashrc && cd {self.comfyui_path} && conda activate comfyui && python main.py'",
                f"bash -l -c 'cd {self.comfyui_path} && conda activate comfyui && python main.py'",
                f"cd {self.comfyui_path} && source ~/.bashrc && conda activate comfyui && python main.py",
                f"cd {self.comfyui_path} && source /etc/profile && conda activate comfyui && python main.py",
            ])
            
            # 备用方案：直接使用系统Python
            start_commands.append(f"cd {self.comfyui_path} && python main.py")
            
            # 尝试每个启动命令
            for i, cmd in enumerate(start_commands):
                try:
                    logger.info(f"尝试启动命令 {i+1}/{len(start_commands)}: {cmd}")
                    
                    # 启动ComfyUI进程
                    self.comfyui_process = subprocess.Popen(
                        cmd, 
                        shell=True, 
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    # 等待ComfyUI启动
                    start_time = time.time()
                    while time.time() - start_time < 45:  # 每个命令最多等待45秒
                        # 检查进程是否还在运行
                        if self.comfyui_process.poll() is not None:
                            # 进程已终止，获取输出信息
                            stdout, stderr = self.comfyui_process.communicate()
                            logger.error(f"ComfyUI进程已终止，命令 {i+1} 失败")
                            logger.error(f"标准输出: {stdout}")
                            logger.error(f"错误输出: {stderr}")
                            break
                        
                        if self.is_comfyui_running():
                            logger.info(f"ComfyUI已成功启动 (使用命令 {i+1})")
                            return True, f"ComfyUI已成功启动 (使用命令 {i+1})"
                        
                        # 检查进程是否已终止
                        if self.comfyui_process.poll() is not None:
                            # 获取输出和错误
                            stdout, stderr = self.comfyui_process.communicate()
                            logger.error(f"ComfyUI进程已终止，命令 {i+1} 失败")
                            logger.error(f"标准输出: {stdout[:500]}")
                            logger.error(f"错误输出: {stderr[:500]}")
                            break
                        
                        time.sleep(2)
                    
                    # 如果这个命令失败，终止进程并尝试下一个
                    if self.comfyui_process and self.comfyui_process.poll() is None:
                        self.comfyui_process.terminate()
                        try:
                            self.comfyui_process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            self.comfyui_process.kill()
                    
                    self.comfyui_process = None
                    
                except Exception as e:
                    logger.error(f"启动命令 {i+1} 执行失败: {str(e)}")
            
            # 所有命令都失败
            logger.error("所有启动命令都失败")
            return False, "无法启动ComfyUI，所有启动命令都失败"
            
        except Exception as e:
            logger.error(f"启动ComfyUI失败: {str(e)}")
            if self.comfyui_process:
                self.comfyui_process.terminate()
                self.comfyui_process = None
            return False, f"启动ComfyUI失败: {str(e)}"
    
    def stop_comfyui(self) -> Tuple[bool, str]:
        """停止ComfyUI 2023.07.04 15"""
        if not self.is_comfyui_running():
            return True, "ComfyUI未在运行"
        
        try:
            # 如果有进程引用，使用它终止
            if self.comfyui_process:
                self.comfyui_process.terminate()
                try:
                    self.comfyui_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.comfyui_process.kill()
                self.comfyui_process = None
            else:
                # 尝试通过端口查找进程
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline and 'python' in cmdline[0] and 'main.py' in ' '.join(cmdline):
                            os.kill(proc.info['pid'], signal.SIGTERM)
                            logger.info(f"已发送终止信号到进程 {proc.info['pid']}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
            
            # 等待ComfyUI停止
            start_time = time.time()
            while time.time() - start_time < 30:  # 最多等待30秒
                if not self.is_comfyui_running():
                    logger.info("ComfyUI已成功停止")
                    return True, "ComfyUI已成功停止"
                time.sleep(2)
            
            return False, "ComfyUI停止超时"
        except Exception as e:
            logger.error(f"停止ComfyUI失败: {str(e)}")
            return False, f"停止ComfyUI失败: {str(e)}"
    
    def check_resource_availability(self) -> Tuple[bool, str]:
        """检查资源可用性 2023.07.04 16"""
        # 检查ComfyUI是否运行
        is_running = self.is_comfyui_running()
        
        if is_running:
            # 检查GPU使用率
            gpu_info = self.get_gpu_info()
            if gpu_info['utilization'] >= self.max_gpu_utilization:
                return False, f"GPU使用率过高 ({gpu_info['utilization']}%)，请稍后再试"
            return True, "资源可用"
        else:
            # ComfyUI未运行，检查是否可以启动
            gpu_info = self.get_gpu_info()
            if gpu_info['memory_used_gb'] >= self.max_memory_usage_gb:
                return False, f"服务器繁忙，GPU显存使用过高 ({gpu_info['memory_used_gb']:.2f}GB/{gpu_info['memory_total_gb']:.2f}GB)，无法生成图片"
            
            # 检查ComfyUI路径是否存在
            if not os.path.exists(self.comfyui_path):
                return False, f"ComfyUI路径不存在: {self.comfyui_path}，请联系管理员配置正确的路径"
            
            # 检查main.py是否存在
            main_py_path = os.path.join(self.comfyui_path, "main.py")
            if not os.path.exists(main_py_path):
                return False, f"ComfyUI主程序不存在: {main_py_path}，请联系管理员安装ComfyUI"
            
            # 尝试启动ComfyUI
            logger.info("尝试自动启动ComfyUI...")
            success, message = self.start_comfyui()
            if success:
                return True, "已自动启动ComfyUI，资源可用"
            else:
                logger.error(f"自动启动ComfyUI失败: {message}")
                return False, f"ComfyUI启动失败: {message}，请联系管理员手动启动ComfyUI服务"

# 获取ComfyUI管理器实例
def get_comfyui_manager() -> ComfyUIManager:
    """获取ComfyUI管理器实例 2023.07.04 15"""
    return ComfyUIManager() 