import React, { useState, useEffect, useRef } from 'react';
import ControlPanel from './ControlPanel';
import TextToImagePanel from './TextToImagePanel';
import ImageGallery from './ImageGallery';
// import Header from './Header';
import { toast } from "sonner";
import { Button } from './ui/button';
import { ImageIcon, History, MessageSquareText, Download, Trash2, X, Check, CheckSquare, Square, AlertTriangle, AlertCircle, Loader2, Clock, Wand2, RefreshCw, Upload, FileImage } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { GeneratedImage } from './ImageGallery'; // GeneratedImage type (now updated)
import HistoryGallery from './HistoryGallery'; // 导入 HistoryGallery
import { authenticatedRequest, normalizeImageUrl, api, COMFYUI_UNAVAILABLE_EVENT } from '../services/api';
import { GenerationProgressBar, GenerationProgress } from './GenerationProgressBar';

// ConfirmDialogProps and ConfirmDialog component are now in ConfirmDialog.tsx
// HistoryGalleryProps and HistoryGallery component are now in HistoryGallery.tsx

// 批量处理确认组件 (Remains in AIImageGenerator.tsx as it's specific to its batch logic)
const BatchConfirmationDialog = ({ 
  isOpen,
  title,
  message,
  icon,
  onConfirm, 
  onCancel 
}: { 
  isOpen: boolean; 
  title: string;
  message: string;
  icon: React.ReactNode;
  onConfirm: () => void; 
  onCancel: () => void; 
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed bottom-24 left-1/2 transform -translate-x-1/2 z-40 w-full max-w-2xl mx-auto px-4 transition-all duration-500 ease-in-out pointer-events-none">
      <div className="bg-slate-900/95 border border-purple-500/50 rounded-xl shadow-2xl p-5 backdrop-blur-xl pointer-events-auto">
        <div className="flex items-start space-x-4">
          <div className="p-2 bg-purple-500/10 rounded-full">
            {icon}
          </div>
          <div className="flex-1">
            <h3 className="text-xl font-semibold text-white mb-2">{title}</h3>
            <p className="text-slate-300 mb-4">
              {message}
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6">
          <Button
            variant="ghost"
            onClick={onCancel}
            className="text-slate-300 hover:text-white hover:bg-slate-800"
          >
            取消处理
          </Button>
          <Button
            onClick={onConfirm}
            className="bg-purple-600 hover:bg-purple-700 text-white"
          >
            继续处理
          </Button>
        </div>
      </div>
    </div>
  );
};

// 添加任务历史类型定义
interface UserTask {
  task_id: string;
  status: string;
  prompt: string;
  creation_time: number;
  completion_time: number | null;
  image_url: string | null;
  generation_type: string;
  queue_position?: number | null;
  estimated_wait_seconds?: number | null;
  progress?: number | null;
}

// 修改TaskHistoryPanel组件，简化刷新逻辑
const TaskHistoryPanel = () => {
  const [tasks, setTasks] = useState<UserTask[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshTime, setLastRefreshTime] = useState<number>(Date.now());
  const timerRef = useRef<number | null>(null);

  // 获取所有任务
  const fetchTasks = async () => {
    setIsLoading(true);
    setError(null);
    try {
      // 使用axios替代fetch
      const response = await api.get('/user-tasks');
      setTasks(response.data);
      setLastRefreshTime(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取任务历史时出错');
      console.error('获取任务历史时出错:', err);
    } finally {
      setIsLoading(false);
    }
  };
  
  // 智能刷新逻辑
  useEffect(() => {
    // 初始加载
    fetchTasks();
    
    // 清除之前的定时器
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    
    // 设置智能刷新间隔
    const refreshInterval = () => {
      // 检查是否有进行中的任务
      const hasPendingTasks = tasks.some(
        task => task.status === 'pending' || task.status === 'processing'
      );
      
      // 如果有进行中的任务，每15秒刷新一次
      // 如果没有进行中的任务，每60秒刷新一次
      return hasPendingTasks ? 15000 : 60000;
    };
    
    // 创建定时器
    const timer = window.setInterval(fetchTasks, refreshInterval());
    
    timerRef.current = timer as unknown as number;
    
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [tasks.length]); // 只在任务数量变化时重新设置定时器

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return <span className="px-2 py-1 text-xs rounded-full bg-blue-100 text-blue-800">等待中</span>;
      case 'processing':
        return <span className="px-2 py-1 text-xs rounded-full bg-yellow-100 text-yellow-800">处理中</span>;
      case 'completed':
        return <span className="px-2 py-1 text-xs rounded-full bg-green-100 text-green-800">已完成</span>;
      case 'failed':
        return <span className="px-2 py-1 text-xs rounded-full bg-red-100 text-red-800">失败</span>;
      default:
        return <span className="px-2 py-1 text-xs rounded-full bg-gray-100 text-gray-800">未知</span>;
    }
  };

  const formatTime = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString();
  };

  return (
    <div className="bg-white shadow-md rounded-lg p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold text-gray-800">任务历史</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">
            {lastRefreshTime ? `上次更新: ${new Date(lastRefreshTime).toLocaleTimeString()}` : ''}
          </span>
          <Button
            size="sm"
            onClick={fetchTasks}
            disabled={isLoading}
            className="flex items-center gap-1"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            刷新
          </Button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-md">
          {error}
        </div>
      )}

      {tasks.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          {isLoading ? '加载中...' : '暂无任务历史'}
        </div>
      ) :
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">任务ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">类型</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">提示词</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">状态</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">创建时间</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {tasks.map((task) => (
                <tr key={task.task_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">
                    {task.task_id}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                    {task.generation_type === 'image-to-image' ? '图生图' : '文生图'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500 max-w-xs truncate">
                    {task.prompt}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {getStatusBadge(task.status)}
                    {task.status === 'pending' && task.queue_position !== undefined && task.queue_position !== null && (
                      <div className="mt-1 text-xs text-gray-500">
                        队列位置: {task.queue_position}
                        {task.estimated_wait_seconds !== undefined && task.estimated_wait_seconds !== null && task.estimated_wait_seconds > 0 && (
                          <span className="ml-1">
                            (预计等待: {Math.floor(task.estimated_wait_seconds / 60)}分{task.estimated_wait_seconds % 60}秒)
                          </span>
                        )}
                      </div>
                    )}
                    {task.status === 'processing' && task.progress !== undefined && task.progress !== null && task.progress > 0 && (
                      <div className="mt-1 text-xs text-gray-500">
                        进度: {Math.round(task.progress * 100)}%
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                    {formatTime(task.creation_time)}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm font-medium">
                    {task.image_url && (
                      <button 
                        onClick={() => window.open(task.image_url!, '_blank')}
                        className="text-indigo-600 hover:text-indigo-900"
                      >
                        查看图片
                      </button>
                    )}
                    {task.status === 'pending' || task.status === 'processing' ? (
                      <button 
                        onClick={() => {
                          const statusUrl = `/api/task-status/${task.task_id}`;
                          window.open(statusUrl, '_blank');
                        }}
                        className="text-blue-600 hover:text-blue-900 ml-2"
                      >
                        查看状态
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      }
    </div>
  );
};

// 添加类型定义
interface ProgressUpdateType {
  taskId?: string;
  asyncStatus?: 'pending' | 'processing' | 'completed' | 'failed';
}

interface TextToImageResult {
  success: boolean;
  criticalError: boolean;
  image: GeneratedImage | null;
  errorDetail?: string;
  progressUpdate?: ProgressUpdateType;
}

// 添加ComfyUI状态类型
interface ComfyUIStatus {
  is_running: boolean;
  gpu_info: {
    utilization: number;
    memory_used_gb: number;
    memory_total_gb: number;
    memory_usage_percent: number;
  };
  resource_available: boolean;
  message: string;
}

const AIImageGenerator = () => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedImages, setGeneratedImages] = useState<GeneratedImage[]>([]);
  const [prompt, setPrompt] = useState('');
  const [uploadedFiles, setUploadedFiles] = useState<File[] | null>(null);
  const [modalImageSrc, setModalImageSrc] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'generate' | 'history' | 'tasks'>('generate');
  const [generationMode, setGenerationMode] = useState<'image-to-image' | 'text-to-image'>('image-to-image');
  
  // 批量处理相关状态
  const [batchFilesToProcess, setBatchFilesToProcess] = useState<File[]>([]);
  const [isAwaitingBatchConfirmation, setIsAwaitingBatchConfirmation] = useState(false);
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress | null>(null);
  const [batchInitialPrompt, setBatchInitialPrompt] = useState<string | null>(null);
  const [batchInitialOutputCount, setBatchInitialOutputCount] = useState<number | null>(null);
  const [batchInitialImageStrength, setBatchInitialImageStrength] = useState<string | null>(null);
  const [batchInitialFaceFiles, setBatchInitialFaceFiles] = useState<File[] | null>(null);
  
  // New state for Text-to-Image batch confirmation
  const [isAwaitingTextBatchConfirmation, setIsAwaitingTextBatchConfirmation] = useState(false);
  const [textBatchInitialPrompt, setTextBatchInitialPrompt] = useState<string | null>(null);
  const [textBatchInitialTotalCount, setTextBatchInitialTotalCount] = useState<number | null>(null);
  const [textBatchRemainingCount, setTextBatchRemainingCount] = useState<number | null>(null);
  const [textBatchInitialAspectRatio, setTextBatchInitialAspectRatio] = useState<string | null>(null);
  const [textBatchInitialReferenceImage, setTextBatchInitialReferenceImage] = useState<File | null>(null);
  const [textBatchInitialFaceImages, setTextBatchInitialFaceImages] = useState<File[] | null>(null);
  
  // ComfyUI状态
  const [comfyUIStatus, setComfyUIStatus] = useState<ComfyUIStatus | null>(null);
  const [isLoadingComfyUIStatus, setIsLoadingComfyUIStatus] = useState(false);
  
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  // 监听认证状态变化
  useEffect(() => {
    if (!isAuthenticated && location.pathname !== '/login' && location.pathname !== '/register') {
      navigate('/login');
    }
  }, [isAuthenticated, location.pathname, navigate]);

  // 获取ComfyUI状态
  const fetchComfyUIStatus = async () => {
    setIsLoadingComfyUIStatus(true);
    try {
      const response = await authenticatedRequest('/comfyui-status', {
        method: 'GET',
      });

      if (response.ok) {
        const statusData = await response.json();
        setComfyUIStatus(statusData);
      } else {
        console.error('获取ComfyUI状态失败');
        setComfyUIStatus(null);
      }
    } catch (error) {
      console.error('获取ComfyUI状态出错:', error);
      setComfyUIStatus(null);
    } finally {
      setIsLoadingComfyUIStatus(false);
    }
  };

  // 确保在页面加载时显示ComfyUI状态面板
  useEffect(() => {
    if (activeTab === 'generate') {
      // 初始加载时获取ComfyUI状态
      fetchComfyUIStatus();
    }
  }, [activeTab]);

  // 定期获取ComfyUI状态
  useEffect(() => {
    // 初始加载
    fetchComfyUIStatus();

    // 设置30秒刷新间隔
    const intervalId = setInterval(fetchComfyUIStatus, 30000);

    return () => clearInterval(intervalId);
  }, []);

  // ComfyUI状态显示组件
  const ComfyUIStatusPanel = () => {
    if (isLoadingComfyUIStatus && !comfyUIStatus) {
      return (
        <div className="bg-gray-50 p-4 rounded-lg shadow-sm mb-4 animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
          <div className="h-4 bg-gray-200 rounded w-1/2"></div>
        </div>
      );
    }

    if (!comfyUIStatus) {
      return (
        <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 rounded-lg shadow-sm mb-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-yellow-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm text-yellow-700">
                无法获取ComfyUI状态信息
              </p>
            </div>
          </div>
        </div>
      );
    }

    const statusColor = comfyUIStatus.is_running ? 'green' : 'red';
    const resourceAvailableColor = comfyUIStatus.resource_available ? 'green' : 'yellow';

    return (
      <div className="bg-white p-4 rounded-lg shadow-sm mb-4 border border-gray-200">
        <h3 className="text-lg font-medium text-gray-900 mb-2">系统状态</h3>
        
        <div className="flex items-center mb-2">
          <div className={`w-3 h-3 rounded-full bg-${statusColor}-500 mr-2`}></div>
          <span className="text-sm text-gray-700">ComfyUI: {comfyUIStatus.is_running ? '运行中' : '未运行'}</span>
        </div>
        
        <div className="flex items-center mb-2">
          <div className={`w-3 h-3 rounded-full bg-${resourceAvailableColor}-500 mr-2`}></div>
          <span className="text-sm text-gray-700">资源状态: {comfyUIStatus.resource_available ? '可用' : '繁忙'}</span>
        </div>
        
        <div className="mt-3 text-sm text-gray-600">
          <div className="mb-1">GPU使用率: {comfyUIStatus.gpu_info.utilization.toFixed(1)}%</div>
          <div className="w-full bg-gray-200 rounded-full h-2.5">
            <div 
              className={`h-2.5 rounded-full ${
                comfyUIStatus.gpu_info.utilization > 80 ? 'bg-red-500' : 
                comfyUIStatus.gpu_info.utilization > 50 ? 'bg-yellow-500' : 'bg-green-500'
              }`} 
              style={{ width: `${Math.min(100, comfyUIStatus.gpu_info.utilization)}%` }}
            ></div>
          </div>
        </div>
        
        <div className="mt-3 text-sm text-gray-600">
          <div className="mb-1">
            显存使用: {comfyUIStatus.gpu_info.memory_used_gb.toFixed(1)}GB / {comfyUIStatus.gpu_info.memory_total_gb.toFixed(1)}GB 
            ({comfyUIStatus.gpu_info.memory_usage_percent.toFixed(1)}%)
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2.5">
            <div 
              className={`h-2.5 rounded-full ${
                comfyUIStatus.gpu_info.memory_usage_percent > 80 ? 'bg-red-500' : 
                comfyUIStatus.gpu_info.memory_usage_percent > 50 ? 'bg-yellow-500' : 'bg-green-500'
              }`} 
              style={{ width: `${Math.min(100, comfyUIStatus.gpu_info.memory_usage_percent)}%` }}
            ></div>
          </div>
        </div>
        
        <div className="mt-3 text-xs text-gray-500">
          最后更新: {new Date().toLocaleTimeString()}
          <button 
            onClick={fetchComfyUIStatus} 
            className="ml-2 text-blue-500 hover:text-blue-700"
            disabled={isLoadingComfyUIStatus}
          >
            刷新
          </button>
        </div>
      </div>
    );
  };

  if (!isAuthenticated && location.pathname !== '/login' && location.pathname !== '/register') {
    return null; 
  }

  // 修改image_to_image_api函数，使用异步进度显示
  const image_to_image_api = async (prompt: string, image_file: File, strength: string, face_files?: File[] | null) => {
    const formData = new FormData();
    formData.append('prompt', prompt);
    formData.append('file', image_file);
    formData.append('image_strength', strength);

    // 添加人脸文件（最多2个）
    if (face_files && face_files.length > 0) {
      const maxFaceFiles = Math.min(face_files.length, 2);
      for (let i = 0; i < maxFaceFiles; i++) {
        formData.append(`face_file_${i}`, face_files[i]);
      }
    }

    const token = localStorage.getItem('token');
    if (!token) {
      toast.error("认证失败，请重新登录");
      setIsGenerating(false); 
      navigate('/login');
      return { success: false };
    }

    let operationSuccess = false;

    // 初始化为异步任务进度显示
    setGenerationProgress({
      currentBatch: 1,
      totalBatches: 1,
      currentImage: 0,
      totalImages: 1,
      isBatch: false,
      fileName: image_file.name,
      processType: 'image-to-image',
      isAsync: true,
      asyncStatus: 'pending'
    });

    try {
      // 提交任务
      const response = await authenticatedRequest('/image-to-image', {
        method: 'POST',
        body: formData,
        headers: {}, // FormData不需要Content-Type header，会自动设置为multipart/form-data
      });

      if (!response.ok) {
        // 处理503错误（服务不可用）
        if (response.status === 503) {
          const errorData = await response.json().catch(() => ({ message: "服务器资源不可用，请稍后再试" }));
          toast.error(errorData.message || "ComfyUI服务不可用，请稍后再试");
          
          // 自动获取ComfyUI状态
          fetchComfyUIStatus();
          
          return { 
            success: false, 
            criticalError: false, 
            errorDetail: errorData.message || "ComfyUI服务不可用，请稍后再试" 
          };
        }
        
        const errorData = await response.json().catch(() => ({ detail: `图像生成失败` }));
        toast.error(errorData.detail || `HTTP error! status: ${response.status}`);
        if (response.status === 401) {
          navigate('/login');
          return { success: false, criticalError: true }; 
        }
        return { success: false, criticalError: false };
      }

      // 获取任务状态
      const taskData = await response.json();
      const taskId = taskData.task_id;
      
      if (!taskId) {
        toast.error("服务器未返回有效的任务ID");
        return { success: false, criticalError: false };
      }
      
      // 更新进度显示，包含任务ID
      setGenerationProgress(prev => {
        if (!prev) return null;
        return {
          currentBatch: prev.currentBatch,
          totalBatches: prev.totalBatches,
          currentImage: prev.currentImage,
          totalImages: prev.totalImages,
          isBatch: prev.isBatch,
          processType: prev.processType,
          isAsync: prev.isAsync,
          ...(prev.fileName && { fileName: prev.fileName }),
          taskId: taskId,
          asyncStatus: 'processing'
        };
      });
      
      // 轮询任务状态
      let retryCount = 0;
      const maxRetries = 120; // 最多轮询2分钟 (每秒一次)
      
      while (retryCount < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000)); // 等待1秒
        
        try {
          const statusResponse = await authenticatedRequest(`/task-status/${taskId}`, {
            method: 'GET'
          });
          
          if (!statusResponse.ok) {
            retryCount++;
            continue;
          }
          
          const statusData = await statusResponse.json();
          
          // 根据任务状态处理
          if (statusData.status === 'completed' && statusData.result) {
            // 更新进度显示为完成
            setGenerationProgress(prev => {
              if (!prev) return null;
              return {
                currentBatch: prev.currentBatch,
                totalBatches: prev.totalBatches,
                currentImage: prev.currentImage,
                totalImages: prev.totalImages,
                isBatch: prev.isBatch,
                processType: prev.processType,
                isAsync: prev.isAsync,
                ...(prev.fileName && { fileName: prev.fileName }),
                ...(prev.taskId && { taskId: prev.taskId }),
                asyncStatus: 'completed'
              };
            });
            
            const result = statusData.result;
            const newImage: GeneratedImage = {
              id: `${new Date().toISOString()}-${image_file.name}-${Math.random()}`,
              image_url: result.image_url,
              prompt: prompt,
              timestamp: new Date().toISOString(),
              generationType: 'image-to-image',
              image_filename: result.image_url.substring(result.image_url.lastIndexOf('/') + 1)
            };
            setGeneratedImages((prevImages) => [newImage, ...prevImages]);
            operationSuccess = true; 
            toast.success(`图片生成成功!`);
            break;
          } else if (statusData.status === 'failed') {
            // 更新进度显示为失败
            setGenerationProgress(prev => {
              if (!prev) return null;
              return {
                currentBatch: prev.currentBatch,
                totalBatches: prev.totalBatches,
                currentImage: prev.currentImage,
                totalImages: prev.totalImages,
                isBatch: prev.isBatch,
                processType: prev.processType,
                isAsync: prev.isAsync,
                ...(prev.fileName && { fileName: prev.fileName }),
                ...(prev.taskId && { taskId: prev.taskId }),
                asyncStatus: 'failed'
              };
            });
            
            toast.error(statusData.message || "图像生成失败");
            break;
          } else if (statusData.status === 'processing' || statusData.status === 'pending') {
            // 继续轮询，更新状态
            setGenerationProgress(prev => {
              if (!prev) return null;
              return {
                currentBatch: prev.currentBatch,
                totalBatches: prev.totalBatches,
                currentImage: prev.currentImage,
                totalImages: prev.totalImages,
                isBatch: prev.isBatch,
                processType: prev.processType,
                isAsync: prev.isAsync,
                ...(prev.fileName && { fileName: prev.fileName }),
                ...(prev.taskId && { taskId: prev.taskId }),
                asyncStatus: statusData.status === 'processing' ? 'processing' : 'pending'
              };
            });
            retryCount++;
          } else {
            // 未知状态
            toast.error(`未知的任务状态: ${statusData.status}`);
            break;
          }
        } catch (error) {
          console.error("轮询任务状态时出错:", error);
          retryCount++;
        }
      }
      
      if (retryCount >= maxRetries) {
        toast.error("图像生成超时，请稍后查看历史记录");
        setGenerationProgress(prev => {
          if (!prev) return null;
          return {
            currentBatch: prev.currentBatch,
            totalBatches: prev.totalBatches,
            currentImage: prev.currentImage,
            totalImages: prev.totalImages,
            isBatch: prev.isBatch,
            processType: prev.processType,
            isAsync: prev.isAsync,
            ...(prev.fileName && { fileName: prev.fileName }),
            ...(prev.taskId && { taskId: prev.taskId }),
            asyncStatus: 'failed'
          };
        });
      }
        
    } catch (error) {
      console.error(`生成图像时出错:`, error);
      toast.error(error instanceof Error ? error.message : `生成图像时发生未知错误`);
      setGenerationProgress(prev => {
        if (!prev) return null;
        return {
          currentBatch: prev.currentBatch,
          totalBatches: prev.totalBatches,
          currentImage: prev.currentImage,
          totalImages: prev.totalImages,
          isBatch: prev.isBatch,
          processType: prev.processType,
          isAsync: prev.isAsync,
          ...(prev.fileName && { fileName: prev.fileName }),
          ...(prev.taskId && { taskId: prev.taskId }),
          asyncStatus: 'failed'
        };
      });
    } finally {
      // 延迟2秒后隐藏进度条，让用户有时间看到完成状态
      setTimeout(() => {
        setIsGenerating(false);
        setGenerationProgress(null);
      }, 2000);
    }
    return { success: operationSuccess }; 
  };

  // Refactored to generate a single text-to-image
  const performSingleTextToImageGeneration = async (promptStr: string, aspectRatioStr: string, refImage: File | null, faceImages?: File[] | null): Promise<TextToImageResult> => {
    const formData = new FormData();
    formData.append('prompt', promptStr);
    formData.append('aspect_ratio', aspectRatioStr);
    
    if (refImage) {
      formData.append('reference_image', refImage);
    }
    
    // 添加人脸图片（最多2个）
    if (faceImages && faceImages.length > 0) {
      const maxFaceFiles = Math.min(faceImages.length, 2);
      for (let i = 0; i < maxFaceFiles; i++) {
        formData.append(`face_image_${i}`, faceImages[i]);
      }
    }
    
    try {
      // 提交任务
      const response = await authenticatedRequest('/text-to-image', {
        method: 'POST',
        body: formData,
        headers: {}, // FormData不需要Content-Type header
      });
      
      if (!response.ok) {
        // 处理503错误（服务不可用）
        if (response.status === 503) {
          const errorData = await response.json().catch(() => ({ message: "服务器资源不可用，请稍后再试" }));
          toast.error(errorData.message || "ComfyUI服务不可用，请稍后再试");
          
          // 自动获取ComfyUI状态
          fetchComfyUIStatus();
          
          return { 
            success: false, 
            criticalError: false, 
            image: null,
            errorDetail: errorData.message || "ComfyUI服务不可用，请稍后再试" 
          };
        }
        
        const errorData = await response.json().catch(() => ({ detail: `文生图失败` }));
        toast.error(errorData.detail || `HTTP error! status: ${response.status}`);
        
        if (response.status === 401) {
          navigate('/login');
          return { success: false, criticalError: true, image: null }; 
        }
        
        return { success: false, criticalError: false, image: null };
      }

      // 获取任务状态
      const taskData = await response.json();
      const taskId = taskData.task_id;
      
      if (!taskId) {
        return { success: false, criticalError: false, image: null, errorDetail: "服务器未返回有效的任务ID" };
      }
      
      // 返回任务ID，让调用者更新进度状态
      const progressUpdate = {
        taskId: taskId,
        asyncStatus: 'processing' as const
      };
      
      // 轮询任务状态
      let retryCount = 0;
      const maxRetries = 180; // 最多轮询3分钟 (每秒一次)
      
      while (retryCount < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000)); // 等待1秒
        
        try {
          const statusResponse = await authenticatedRequest(`/task-status/${taskId}`, {
            method: 'GET'
          });
          
          if (!statusResponse.ok) {
            retryCount++;
            continue;
          }
          
          const statusData = await statusResponse.json();
          
          // 根据任务状态处理
          if (statusData.status === 'completed' && statusData.result) {
            // 返回完成状态，让调用者更新进度
            const result = statusData.result;
            // 使用normalizeImageUrl处理图片URL
            const normalizedImageUrl = normalizeImageUrl(result.image_url);
            
            const newImage: GeneratedImage = {
              id: `${new Date().toISOString()}-text-${Math.random()}`,
              image_url: normalizedImageUrl,
              prompt: promptStr,
              timestamp: new Date().toISOString(),
              generationType: 'text-to-image',
              image_filename: normalizedImageUrl.substring(normalizedImageUrl.lastIndexOf('/') + 1)
            };
            
            return { 
              success: true, 
              criticalError: false, 
              image: newImage,
              progressUpdate: { asyncStatus: 'completed' as const }
            };
          } else if (statusData.status === 'failed') {
            // 返回失败状态，让调用者更新进度
            return { 
              success: false, 
              criticalError: false, 
              image: null, 
              errorDetail: statusData.message || "图像生成失败",
              progressUpdate: { asyncStatus: 'failed' as const }
            };
          } else if (statusData.status === 'processing' || statusData.status === 'pending') {
            // 继续轮询，可以选择返回当前状态让调用者更新进度
            retryCount++;
          } else {
            // 未知状态
            return { 
              success: false, 
              criticalError: false, 
              image: null, 
              errorDetail: `未知的任务状态: ${statusData.status}`,
              progressUpdate: { asyncStatus: 'failed' as const }
            };
          }
        } catch (error) {
          console.error("轮询任务状态时出错:", error);
          retryCount++;
        }
      }
      
      if (retryCount >= maxRetries) {
        return { 
          success: false, 
          criticalError: false, 
          image: null, 
          errorDetail: "图像生成超时，请稍后查看历史记录",
          progressUpdate: { asyncStatus: 'failed' as const }
        };
      }
      
      // 如果执行到这里，说明任务状态轮询结束但没有明确结果
      return { 
        success: false, 
        criticalError: false, 
        image: null, 
        errorDetail: "无法获取任务结果",
        progressUpdate: { asyncStatus: 'failed' as const }
      };
    } catch (error) {
      console.error(`生成图像时出错:`, error);
      // toast.error(error instanceof Error ? error.message : `生成图像时发生未知错误`); // Handled by caller
      return { 
        success: false, 
        criticalError: false, 
        image: null, 
        errorDetail: error instanceof Error ? error.message : `生成图像时发生未知错误`,
        progressUpdate: { asyncStatus: 'failed' as const }
      };
    }
  };

  const handleImageToImageGenerate = async (currentPrompt: string, files: File[], count: number, imageStrength: string, faceFiles?: File[], needConfirmation: boolean = true) => {
    if (!isAuthenticated) {
      toast.error("请先登录");
      navigate('/login');
      return;
    }
    
    if (!files || files.length === 0) {
      toast.error("没有有效的上传文件。");
      return;
    }
    
    setIsGenerating(true);
    setIsAwaitingBatchConfirmation(false); // Reset any previous batch confirmation
    setBatchFilesToProcess([]); // Reset for new operation
    setGenerationProgress(null); // Reset progress
    // Reset initial batch parameters for a fresh start
    setBatchInitialPrompt(null); 
    setBatchInitialOutputCount(null); 
    setBatchInitialImageStrength(null);
    setBatchInitialFaceFiles(null);
    setUploadedFiles(null); // Clear previously stored single file if any

    const firstFile = files[0];

    if (files.length === 1 && count > 1) {
      // Scenario: Single file uploaded, but count > 1 requested
      const firstImageResult = await image_to_image_api(currentPrompt, firstFile, imageStrength, faceFiles);

      if (firstImageResult.success) {
        // 如果不需要确认，直接继续处理剩余图片
        if (!needConfirmation) {
          // 直接处理剩余图片
          for (let i = 1; i < count; i++) {
            await image_to_image_api(currentPrompt, firstFile, imageStrength, faceFiles);
          }
          setIsGenerating(false);
          return;
        }
        
        setUploadedFiles(files); // Store the single file
        setBatchFilesToProcess([]); // No *other* files to process in this mode
        setIsAwaitingBatchConfirmation(true);
        setBatchInitialPrompt(currentPrompt);
        setBatchInitialOutputCount(count); // Store original total count for this file
        setBatchInitialImageStrength(imageStrength);
        setBatchInitialFaceFiles(faceFiles || null);
        // Message in BatchConfirmationDialog will use batchInitialOutputCount and uploadedFiles
      } else {
        setIsGenerating(false); // Stop if first one fails
        if (!firstImageResult.criticalError) {
          toast.error("首张图片生成失败，批量处理已中止。");
        }
      }
    } else if (files.length > 1) {
      // Scenario: Multiple files uploaded (original batch logic)
      const firstImageOutputCount = 1; // Always generate 1 for the first file in a multi-file batch
      const remainingFiles = files.slice(1);

      const firstImageResult = await image_to_image_api(currentPrompt, firstFile, imageStrength, faceFiles);

      if (!firstImageResult.success && firstImageResult.criticalError) {
        setIsGenerating(false);
        return;
      }

      if (remainingFiles.length > 0 && firstImageResult.success) {
        // 如果不需要确认，直接继续处理剩余文件
        if (!needConfirmation) {
          // 处理剩余文件
          for (const file of remainingFiles) {
            for (let i = 0; i < count; i++) {
              await image_to_image_api(currentPrompt, file, imageStrength, faceFiles);
            }
          }
          
          // 如果第一个文件需要生成多张，继续处理
          if (count > 1) {
            for (let i = 1; i < count; i++) {
              await image_to_image_api(currentPrompt, firstFile, imageStrength, faceFiles);
            }
          }
          
          setIsGenerating(false);
          toast.success("所有图片处理完成！");
          return;
        }
        
        setBatchFilesToProcess(remainingFiles);
        setUploadedFiles(files); // Store all uploaded files
        setIsAwaitingBatchConfirmation(true);
        setBatchInitialPrompt(currentPrompt);
        // For multi-file, batchInitialOutputCount is count PER FILE
        setBatchInitialOutputCount(count);
        setBatchInitialImageStrength(imageStrength);
        setBatchInitialFaceFiles(faceFiles || null);
      } else {
        setIsGenerating(false);
        if (files.length > 1 && !firstImageResult.success) {
          toast.error("首张图片生成失败，批量处理已中止。");
        }
      }
    } else {
      // Scenario: Single file, single generation (count is 1 or not specified as > 1)
      await image_to_image_api(currentPrompt, firstFile, imageStrength, faceFiles);
      setIsGenerating(false); // Done generating
      setGenerationProgress(null); // Clear progress
    }
  };

  const handleTextToImageGenerate = async (prompt: string, count: number, aspectRatio: string, referenceImage: File | null, faceImages?: File[] | null, needConfirmation: boolean = true) => {
    if (!isAuthenticated) {
      toast.error("请先登录");
      navigate('/login');
      return;
    }

    setIsGenerating(true);
    
    // 初始化为异步任务进度显示
    setGenerationProgress({
      currentBatch: 1,
      totalBatches: 1,
      currentImage: 1,
      totalImages: count,
      isBatch: count > 1,
      processType: 'text-to-image',
      isAsync: true,
      asyncStatus: 'pending'
    });

    toast.info("正在提交文生图任务...");
    
    try {
      // 修改这里：如果count > 1，先生成第一张，然后询问是否继续生成剩余图片
      if (count > 1) {
        // 使用performSingleTextToImageGeneration生成第一张图片
        const result = await performSingleTextToImageGeneration(
          prompt,
          aspectRatio,
          referenceImage,
          faceImages
        );

        // 处理返回的progressUpdate
        if (result.progressUpdate) {
          setGenerationProgress(prev => {
            if (!prev) return null;
            return {
              currentBatch: prev.currentBatch,
              totalBatches: prev.totalBatches,
              currentImage: prev.currentImage,
              totalImages: prev.totalImages,
              isBatch: prev.isBatch,
              processType: prev.processType,
              isAsync: prev.isAsync,
              ...(prev.fileName && { fileName: prev.fileName }),
              ...(prev.taskId && { taskId: prev.taskId }),
              ...result.progressUpdate
            };
          });
        }

        if (result.success && result.image) {
          // 添加图片到生成列表
          setGeneratedImages((prevImages) => [result.image!, ...prevImages]);
          toast.success(`第1张图片生成成功!`);
          
          // 如果不需要确认，直接继续生成剩余图片
          if (!needConfirmation) {
            // 生成剩余图片
            let successCount = 1; // 已经成功生成了第一张
            for (let i = 1; i < count; i++) {
              const nextResult = await performSingleTextToImageGeneration(
                prompt,
                aspectRatio,
                referenceImage,
                faceImages
              );
              
              if (nextResult.progressUpdate) {
                setGenerationProgress(prev => {
                  if (!prev) return null;
                  return {
                    currentBatch: prev.currentBatch,
                    totalBatches: prev.totalBatches,
                    currentImage: i + 1,
                    totalImages: prev.totalImages,
                    isBatch: prev.isBatch,
                    processType: prev.processType,
                    isAsync: prev.isAsync,
                    ...(prev.fileName && { fileName: prev.fileName }),
                    ...(prev.taskId && { taskId: prev.taskId }),
                    ...nextResult.progressUpdate
                  };
                });
              }
              
              if (nextResult.success && nextResult.image) {
                setGeneratedImages((prevImages) => [nextResult.image!, ...prevImages]);
                successCount++;
              }
            }
            
            if (successCount === count) {
              toast.success(`所有 ${count} 张图片已成功生成!`);
            } else {
              toast.warning(`批量处理部分完成: ${successCount} / ${count} 张图片生成成功。`);
            }
            
            setTimeout(() => {
              setIsGenerating(false);
              setGenerationProgress(null);
            }, 2000);
            return;
          }
          
          // 设置批量处理参数
          setTextBatchInitialPrompt(prompt);
          setTextBatchInitialTotalCount(count);
          setTextBatchRemainingCount(count - 1); // 剩余的图片数量
          setTextBatchInitialAspectRatio(aspectRatio);
          setTextBatchInitialReferenceImage(referenceImage);
          setTextBatchInitialFaceImages(faceImages || null);
          
          // 显示确认对话框
          setIsAwaitingTextBatchConfirmation(true);
        } else {
          // 第一张图片生成失败，结束流程
          toast.error(result.errorDetail || "首张图片生成失败，批量处理已中止。");
          setIsGenerating(false);
          setGenerationProgress(null);
        }
      } else {
        // 如果只需要生成一张图片，使用performSingleTextToImageGeneration
        const result = await performSingleTextToImageGeneration(
          prompt,
          aspectRatio,
          referenceImage,
          faceImages
        );

        // 处理返回的progressUpdate
        if (result.progressUpdate) {
          setGenerationProgress(prev => {
            if (!prev) return null;
            return {
              currentBatch: prev.currentBatch,
              totalBatches: prev.totalBatches,
              currentImage: prev.currentImage,
              totalImages: prev.totalImages,
              isBatch: prev.isBatch,
              processType: prev.processType,
              isAsync: prev.isAsync,
              ...(prev.fileName && { fileName: prev.fileName }),
              ...(prev.taskId && { taskId: prev.taskId }),
              ...result.progressUpdate
            };
          });
        }

        if (result.success && result.image) {
          // 添加图片到生成列表
          setGeneratedImages((prevImages) => [result.image!, ...prevImages]);
          toast.success(`图片生成成功!`);
        } else {
          toast.error(result.errorDetail || "图像生成失败");
        }
        
        // 单张图片生成完成，重置状态
        setTimeout(() => {
          setIsGenerating(false);
          setGenerationProgress(null);
        }, 2000);
      }
    } catch (error) {
      console.error("文生图过程中出错:", error);
      toast.error(error instanceof Error ? error.message : "生成图像时发生未知错误");
      setGenerationProgress(prev => {
        if (!prev) return null;
        return {
          currentBatch: prev.currentBatch,
          totalBatches: prev.totalBatches,
          currentImage: prev.currentImage,
          totalImages: prev.totalImages,
          isBatch: prev.isBatch,
          processType: prev.processType,
          isAsync: prev.isAsync,
          ...(prev.fileName && { fileName: prev.fileName }),
          ...(prev.taskId && { taskId: prev.taskId }),
          asyncStatus: 'failed'
        };
      });
      setIsGenerating(false);
      setGenerationProgress(null);
    }
  };

  const handleContinueBatchProcessing = async () => {
    if (batchInitialPrompt === null || batchInitialOutputCount === null || batchInitialImageStrength === null || uploadedFiles === null) {
      setIsAwaitingBatchConfirmation(false);
      setIsGenerating(false);
      setBatchInitialPrompt(null);
      setBatchInitialOutputCount(null);
      setBatchInitialImageStrength(null);
      setUploadedFiles(null);
      setBatchFilesToProcess([]);
      toast.error("无法继续批量处理，缺少必要信息。");
      return;
    }

    setIsAwaitingBatchConfirmation(false);
    setIsGenerating(true); 
    
    const originalPrompt = batchInitialPrompt;
    const originalOutputCountPerFile = batchInitialOutputCount; // This is count PER file for multi-file, or TOTAL count for single-file-multi-gen
    const originalImageStrength = batchInitialImageStrength;
    const originalFaceFiles = batchInitialFaceFiles;
    let overallBatchSuccess = true;

    // Scenario 1: Multiple uploaded files (batchFilesToProcess has items)
    if (batchFilesToProcess.length > 0 && uploadedFiles.length > 1) {
      // The first file of the multi-file batch already had one image generated.
      // If originalOutputCountPerFile > 1, generate the rest for the first file.
      const firstFile = uploadedFiles[0];
      if (originalOutputCountPerFile > 1) {
        toast.info(`继续为首个文件 ${firstFile.name} 生成剩余 ${originalOutputCountPerFile - 1} 张图片...`);
        // 修改这里：循环生成剩余的图片，而不是只生成一张
        for (let i = 0; i < originalOutputCountPerFile - 1; i++) {
          const firstFileRemainingResult = await image_to_image_api(originalPrompt, firstFile, originalImageStrength, originalFaceFiles);
          if (!firstFileRemainingResult.success) {
            overallBatchSuccess = false;
            if (firstFileRemainingResult.criticalError) {
              setIsGenerating(false); setGenerationProgress(null); /* Reset states */ return;
            }
            toast.warning(`首个文件 ${firstFile.name} 的第 ${i+2} 张图片生成失败。`);
            break; // 如果生成失败，停止生成该文件的剩余图片
          }
        }
      }
      // Process remaining files from batchFilesToProcess
      for (let i = 0; i < batchFilesToProcess.length; i++) {
        const fileToProcess = batchFilesToProcess[i];
        // 修改这里：为每个文件生成指定数量的图片
        for (let j = 0; j < originalOutputCountPerFile; j++) {
          const result = await image_to_image_api(originalPrompt, fileToProcess, originalImageStrength, originalFaceFiles);
          if (!result.success) {
            overallBatchSuccess = false;
            if (result.criticalError) {
              setIsGenerating(false); setGenerationProgress(null); /* Reset states */ return;
            }
            toast.warning(`图片 ${fileToProcess.name} 的第 ${j+1} 张处理失败，跳过...`);
            break; // 如果生成失败，停止生成该文件的剩余图片
          }
        }
      }
    }
    // Scenario 2: Single uploaded file, but original total count > 1 (batchFilesToProcess is empty)
    else if (uploadedFiles.length === 1 && originalOutputCountPerFile > 1) {
      const singleFile = uploadedFiles[0];
      const remainingGenerationsForSingleFile = originalOutputCountPerFile - 1; // Since 1 was already done

      if (remainingGenerationsForSingleFile > 0) {
        toast.info(`继续为文件 ${singleFile.name} 生成剩余 ${remainingGenerationsForSingleFile} 张图片...`);
        // 修改这里：循环生成剩余的所有图片，而不是只生成一张
        for (let i = 0; i < remainingGenerationsForSingleFile; i++) {
          const result = await image_to_image_api(
            originalPrompt,
            singleFile,
            originalImageStrength,
            originalFaceFiles
          );
          if (!result.success) {
            overallBatchSuccess = false;
            if (result.criticalError) {
              setIsGenerating(false); setGenerationProgress(null); /* Reset states */ return;
            }
            toast.warning(`第 ${i+2} 张图片生成失败，跳过剩余图片...`);
            break; // 如果生成失败，停止生成剩余图片
          }
        }
      }
    }

    setBatchFilesToProcess([]);
    setGenerationProgress(null);
    setIsGenerating(false);
    setBatchInitialPrompt(null); 
    setBatchInitialOutputCount(null); 
    setBatchInitialImageStrength(null);
    setBatchInitialFaceFiles(null);
    setUploadedFiles(null);

    if (overallBatchSuccess) {
      toast.success("所有图片处理完成！");
    } else {
      toast.warning("部分图片处理失败或任务未完成。");
    }
  };
  
  const handleCancelBatch = () => {
    setBatchFilesToProcess([]);
    setIsAwaitingBatchConfirmation(false);
    setIsGenerating(false);
    setGenerationProgress(null);
    setBatchInitialPrompt(null);
    setBatchInitialOutputCount(null);
    setBatchInitialImageStrength(null);
    setBatchInitialFaceFiles(null);
    toast.info("批量处理已取消。");
  };

  const handleContinueTextBatchProcessing = async () => {
    if (
      textBatchInitialPrompt === null ||
      textBatchRemainingCount === null ||
      textBatchRemainingCount <= 0 ||
      textBatchInitialAspectRatio === null ||
      textBatchInitialTotalCount === null
    ) {
      // Should not happen if logic is correct, but as a safeguard
      setIsAwaitingTextBatchConfirmation(false);
      setIsGenerating(false);
      setGenerationProgress(null);
      toast.error("无法继续批量处理，缺少必要信息。");
      return;
    }

    setIsAwaitingTextBatchConfirmation(false);
    // isGenerating should already be true if we reached here from the first image generation
    // If not, set it: setIsGenerating(true);

    let successfulGenerations = 0;
    const totalRemaining = textBatchRemainingCount;

    for (let i = 0; i < totalRemaining; i++) {
      const currentOverallImageNumber = (textBatchInitialTotalCount - totalRemaining) + i + 1;
      setGenerationProgress(prev => ({
        ...(prev || { 
            currentBatch: 1, 
            totalBatches: 1, 
            isBatch: true, 
            processType: 'text-to-image',
            isAsync: true,
            asyncStatus: 'pending'
        }),
        currentImage: currentOverallImageNumber,
        totalImages: textBatchInitialTotalCount,
      }));
      
      toast.info(`正在生成第 ${currentOverallImageNumber}/${textBatchInitialTotalCount} 张图片...`);

      const result = await performSingleTextToImageGeneration(
        textBatchInitialPrompt,
        textBatchInitialAspectRatio,
        textBatchInitialReferenceImage,
        textBatchInitialFaceImages
      );

      // 处理返回的progressUpdate
      if (result.progressUpdate) {
        setGenerationProgress(prev => {
          if (!prev) return null;
          return {
            currentBatch: prev.currentBatch,
            totalBatches: prev.totalBatches,
            currentImage: prev.currentImage,
            totalImages: prev.totalImages,
            isBatch: prev.isBatch,
            processType: prev.processType,
            isAsync: prev.isAsync,
            ...(prev.fileName && { fileName: prev.fileName }),
            ...(prev.taskId && { taskId: prev.taskId }),
            ...result.progressUpdate
          };
        });
      }

      if (result.success && result.image) {
        setGeneratedImages((prevImages) => [result.image!, ...prevImages]);
        successfulGenerations++;
        // toast.success(`图片 ${currentOverallImageNumber}/${textBatchInitialTotalCount} 生成成功!`); // Optional: can be too many toasts
      } else if (result.criticalError) {
        // Navigation is handled in performSingleTextToImageGeneration
        // Stop batch processing
        setGenerationProgress(null); 
        setIsGenerating(false); 
        // Reset batch states
        setTextBatchInitialPrompt(null);
        setTextBatchInitialTotalCount(null);
        setTextBatchRemainingCount(null);
        setTextBatchInitialAspectRatio(null);
        setTextBatchInitialReferenceImage(null);
        setTextBatchInitialFaceImages(null);
        return; 
      } else {
        toast.error(result.errorDetail || `图片 ${currentOverallImageNumber}/${textBatchInitialTotalCount} 生成失败。`);
      }
    }

    if (successfulGenerations > 0 && successfulGenerations < totalRemaining) {
        toast.warning(`批量处理部分完成: ${successfulGenerations} / ${totalRemaining} 张后续图片生成成功。`);
    } else if (successfulGenerations === totalRemaining && totalRemaining > 0) {
        toast.success(`所有 ${textBatchInitialTotalCount} 张图片已成功生成!`);
    } else if (totalRemaining > 0) { // implies successfulGenerations is 0 for the remaining
        toast.error("批量处理中的后续图片均生成失败。");
    }
    // If totalRemaining was 0, the initial success toast for the first image already covered it.

    // Reset batch states
    setTextBatchInitialPrompt(null);
    setTextBatchInitialTotalCount(null);
    setTextBatchRemainingCount(null);
    setTextBatchInitialAspectRatio(null);
    setTextBatchInitialReferenceImage(null);
    setTextBatchInitialFaceImages(null);
    setGenerationProgress(null);
    setIsGenerating(false);
  };

  const handleCancelTextBatch = () => {
    setIsAwaitingTextBatchConfirmation(false);
    setIsGenerating(false);
    setGenerationProgress(null);
    setTextBatchInitialPrompt(null);
    setTextBatchInitialTotalCount(null);
    setTextBatchRemainingCount(null);
    setTextBatchInitialAspectRatio(null);
    setTextBatchInitialReferenceImage(null);
    setTextBatchInitialFaceImages(null);
    toast.info("文生图批量处理已取消。");
  };

  const isControlPanelDisabled = isGenerating || isAwaitingBatchConfirmation;

  const openImageModal = (imageUrl: string) => {
    setModalImageSrc(imageUrl);
    setIsModalOpen(true);
  };

  const closeImageModal = () => {
    setModalImageSrc(null);
    setIsModalOpen(false);
  };

  // 添加进度条状态更新处理函数
  const handleProgressStatusUpdate = (status: string) => {
    // 当进度条组件检测到状态变化时更新本地状态
    if (generationProgress) {
      setGenerationProgress(prev => {
        if (!prev) return null;
        // 创建一个完整的新对象，确保所有必需属性都存在
        return {
          currentBatch: prev.currentBatch,
          totalBatches: prev.totalBatches,
          currentImage: prev.currentImage,
          totalImages: prev.totalImages,
          isBatch: prev.isBatch,
          processType: prev.processType,
          isAsync: prev.isAsync,
          ...(prev.fileName && { fileName: prev.fileName }),
          ...(prev.taskId && { taskId: prev.taskId }),
          asyncStatus: status as 'pending' | 'processing' | 'completed' | 'failed'
        };
      });
      
      // 如果任务完成或失败，延迟隐藏进度条
      if (status === 'completed' || status === 'failed') {
        setTimeout(() => {
          setIsGenerating(false);
          setGenerationProgress(null);
        }, 2000);
      }
    }
  };

  // 找到处理异步任务结果的函数，添加normalizeImageUrl处理
  const handleAsyncTaskResult = (taskId: string, result: any) => {
    if (!result || !result.image_url) {
      return null;
    }
    
    // 使用normalizeImageUrl处理图片URL
    const normalizedImageUrl = normalizeImageUrl(result.image_url);
    
    const newImage: GeneratedImage = {
      id: result.history_id || Date.now(),
      image_url: normalizedImageUrl,
      prompt: result.prompt || prompt, // 使用result中的prompt或当前prompt状态
      timestamp: new Date().toISOString(),
      generationType: result.generation_type || 'text-to-image', // 使用result中的类型或默认为text-to-image
      image_filename: normalizedImageUrl.substring(normalizedImageUrl.lastIndexOf('/') + 1)
    };
    
    setGeneratedImages((prevImages) => [newImage, ...prevImages]);
    return newImage;
  };

  // 监听ComfyUI不可用事件
  useEffect(() => {
    const handleComfyUIUnavailable = () => {
      toast.error("ComfyUI服务不可用，请稍后再试。");
      setIsGenerating(false);
      setGenerationProgress(null);
      setComfyUIStatus(null); // 清除ComfyUI状态
      setIsLoadingComfyUIStatus(false);
    };

    window.addEventListener(COMFYUI_UNAVAILABLE_EVENT, handleComfyUIUnavailable);

    return () => {
      window.removeEventListener(COMFYUI_UNAVAILABLE_EVENT, handleComfyUIUnavailable);
    };
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* <Header /> */}
      <div className="flex flex-col md:flex-row h-[calc(100vh-64px)] p-2 md:p-4 gap-2 md:gap-4">
        <div className="w-full md:w-72 lg:w-80 flex flex-col bg-white rounded-lg shadow-sm max-h-[calc(100vh-80px)] md:max-h-[calc(100vh-96px)]">
          <div className="p-2 md:p-3">
            <div className="flex gap-1">
              <button
                onClick={() => setGenerationMode('image-to-image')}
                className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  generationMode === 'image-to-image'
                    ? 'bg-blue-50 text-blue-600 shadow-sm'
                    : 'text-gray-600 hover:text-blue-600 hover:bg-blue-50'
                }`}
              >
                <Wand2 className="w-4 h-4" />
                <span className="hidden sm:inline">图生图</span>
              </button>
              <button
                onClick={() => setGenerationMode('text-to-image')}
                className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  generationMode === 'text-to-image'
                    ? 'bg-blue-50 text-blue-600 shadow-sm'
                    : 'text-gray-600 hover:text-blue-600 hover:bg-blue-50'
                }`}
              >
                <MessageSquareText className="w-4 h-4" />
                <span className="hidden sm:inline">文生图</span>
              </button>
            </div>
          </div>
          
          <div className="flex-1 min-h-0">
            {generationMode === 'image-to-image' ? (
          <ControlPanel 
                onGenerate={handleImageToImageGenerate}
            isGenerating={isGenerating}
            isControlPanelDisabled={isControlPanelDisabled}
            prompt={prompt}
            setPrompt={setPrompt}
            uploadedFiles={uploadedFiles}
            setUploadedFiles={setUploadedFiles}
          />
            ) : (
              <TextToImagePanel
                onGenerate={handleTextToImageGenerate}
                isGenerating={isGenerating}
                isPanelDisabled={isControlPanelDisabled}
              />
            )}
          </div>
          </div>

        <div className="flex-1 flex flex-col min-h-0 bg-white rounded-lg shadow-sm">
          <div className="p-2 md:p-3">
            <div className="flex gap-2">
                <button 
                  onClick={() => setActiveTab('generate')}
                className={`flex gap-1.5 items-center px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  activeTab === 'generate' 
                  ? 'bg-blue-50 text-blue-600 shadow-sm' 
                  : 'text-gray-600 hover:text-blue-600 hover:bg-blue-50'
                }`}
              >
                <ImageIcon className="w-4 h-4" />
                <span className="hidden sm:inline">生成记录</span>
                </button>
                <button 
                  onClick={() => setActiveTab('history')}
                className={`flex gap-1.5 items-center px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  activeTab === 'history' 
                  ? 'bg-blue-50 text-blue-600 shadow-sm' 
                  : 'text-gray-600 hover:text-blue-600 hover:bg-blue-50'
                }`}
              >
                <History className="w-4 h-4" />
                <span className="hidden sm:inline">历史记录</span>
                </button>
                <button 
                  onClick={() => setActiveTab('tasks')}
                className={`flex gap-1.5 items-center px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  activeTab === 'tasks' 
                  ? 'bg-blue-50 text-blue-600 shadow-sm' 
                  : 'text-gray-600 hover:text-blue-600 hover:bg-blue-50'
                }`}
              >
                <Clock className="w-4 h-4" />
                <span className="hidden sm:inline">任务查询</span>
                </button>
              </div>
            </div>
            
          <div className="flex-1 overflow-y-auto p-3 md:p-4 custom-scrollbar">
            <BatchConfirmationDialog
              isOpen={isAwaitingBatchConfirmation && activeTab === 'generate'}
              title="图生图批量处理"
              // Updated message to handle both multi-file and single-file-multi-count scenarios
              message={(
                batchFilesToProcess.length > 0 
                ? `首张图片已成功生成！是否继续处理剩余的 ${batchFilesToProcess.length} 个文件（每个文件 ${batchInitialOutputCount} 张图）？` 
                : (uploadedFiles && uploadedFiles.length === 1 && batchInitialOutputCount && batchInitialOutputCount > 1)
                  ? `首张图片已成功生成！是否继续为该文件生成剩余的 ${batchInitialOutputCount - 1} 张图片？`
                  : "是否继续处理？" // Fallback, should ideally not be hit with correct logic
              )}
              icon={<ImageIcon className="w-8 h-8 text-purple-400" />}
              onConfirm={handleContinueBatchProcessing}
              onCancel={handleCancelBatch}
            />
            {/* Dialog for Text-to-Image batch confirmation */}
            <BatchConfirmationDialog
              isOpen={isAwaitingTextBatchConfirmation && activeTab === 'generate'}
              title="文生图批量处理"
              message={`首张图片已生成！是否继续生成剩余的 ${textBatchRemainingCount || 0} 张图片？`}
              icon={<MessageSquareText className="w-8 h-8 text-purple-400" />}
              onConfirm={handleContinueTextBatchProcessing}
              onCancel={handleCancelTextBatch}
            />
            <div className={`h-full w-full ${activeTab === 'generate' ? 'block' : 'hidden'}`}>
              <ImageGallery images={generatedImages} openImageModal={openImageModal} />
            </div>
            <div className={`h-full w-full ${activeTab === 'history' ? 'block' : 'hidden'}`}>
              <HistoryGallery openImageModal={openImageModal} isVisible={activeTab === 'history'} />
            </div>
            {activeTab === 'tasks' && (
              <TaskHistoryPanel />
            )}
          </div>
        </div>
      </div>
      
      {/* 进度条 */}
      <GenerationProgressBar
        isVisible={!!generationProgress}
        generationProgress={generationProgress}
        onStatusUpdate={handleProgressStatusUpdate}
      />
      
      {isModalOpen && modalImageSrc && (
        <div 
          className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4"
          onClick={closeImageModal}
        >
          <div 
            className="relative max-w-3xl lg:max-w-4xl max-h-[80vh] bg-slate-800 p-2 rounded-lg shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <img 
              src={modalImageSrc} 
              alt="Enlarged view" 
              className="block max-w-full max-h-[calc(80vh-1rem)] object-contain rounded"
            />
            <Button 
              variant="ghost"
              size="icon"
              className="absolute top-2 right-2 bg-slate-700/50 hover:bg-slate-600/80 text-white scale-90 lg:scale-100"
              onClick={closeImageModal}
            >
              <X className="w-5 h-5 lg:w-6 lg:h-6" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AIImageGenerator;
