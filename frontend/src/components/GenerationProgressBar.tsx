import React, { useEffect, useRef, useState } from 'react';
import { Loader2, BarChart3, Users } from 'lucide-react';
import { authenticatedRequest } from '../services/api';
import { Progress } from './ui/progress';
import { api } from '../services/api';

// 进度显示接口
export interface GenerationProgress {
  currentBatch: number;
  totalBatches: number;
  currentImage: number;
  totalImages: number;
  isBatch: boolean;
  fileName?: string;
  processType: 'image-to-image' | 'text-to-image';
  taskId?: string;  // 任务ID
  isAsync: boolean; // 是否为异步任务
  asyncStatus?: 'pending' | 'processing' | 'completed' | 'failed'; // 异步任务状态
  queuePosition?: number; // 队列位置 2023.07.01 11
  estimatedWaitSeconds?: number; // 预计等待时间（秒） 2023.07.01 11
}

// 队列状态接口
interface QueueStatus {
  total_active: number;
  processing_count: number;
  queue_count: number;
  max_concurrent: number;
  processing_tasks: Array<{
    task_id: string;
    user_id: string;
    type: string;
    progress: number;
    start_time: number;
  }>;
  queued_tasks: Array<{
    task_id: string;
    user_id: string;
    type: string;
    create_time: number;
  }>;
}

interface GenerationProgressBarProps {
  taskId?: string;
  generationProgress?: GenerationProgress | null;
  isVisible?: boolean;
  onComplete?: () => void;
  onStatusUpdate?: (status: string) => void;
}

// 进度条组件 2023.07.04 15
export function GenerationProgressBar({ 
  taskId, 
  generationProgress, 
  isVisible = true, 
  onComplete, 
  onStatusUpdate 
}: GenerationProgressBarProps) {
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<string>('pending');
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    // 重置状态
    if (taskId !== undefined) {
      setIsInitialized(true);
      setError(null);
      setStatus('pending');
      setProgress(0);
    }
  }, [taskId]);

  // 处理从外部传入的进度信息
  useEffect(() => {
    if (generationProgress) {
      if (generationProgress.isAsync && generationProgress.taskId) {
        // 如果是异步任务，使用taskId查询状态
        setIsInitialized(true);
      } else {
        // 如果是同步任务，直接更新进度
        const calculatedProgress = generationProgress.isBatch
          ? ((generationProgress.currentBatch - 1) / generationProgress.totalBatches) * 100 +
            (generationProgress.currentImage / generationProgress.totalImages) * (100 / generationProgress.totalBatches)
          : (generationProgress.currentImage / generationProgress.totalImages) * 100;
        
        setProgress(calculatedProgress);
        setStatus(generationProgress.asyncStatus || 'processing');
      }
    }
  }, [generationProgress]);

  useEffect(() => {
    // 如果组件未初始化或taskId未定义，不执行检查
    if (!isInitialized || (!taskId && (!generationProgress || !generationProgress.taskId))) {
      return;
    }

    // 使用传入的taskId或generationProgress中的taskId
    const currentTaskId = taskId || (generationProgress?.taskId);
    if (!currentTaskId) return;

    const checkStatus = async () => {
      try {
        // 获取任务状态
        const response = await api.get(`/task-status/${currentTaskId}`);
        const taskStatus = response.data;

        // 获取队列状态
        try {
          const queueResponse = await api.get('/queue-status');
          setQueueStatus(queueResponse.data);
        } catch (queueError) {
          console.error('获取队列状态失败:', queueError);
          // 队列状态获取失败不影响任务状态显示
        }

        if (taskStatus.status === 'completed') {
          setProgress(100);
          setStatus('completed');
          if (onStatusUpdate) onStatusUpdate('completed');
          if (onComplete) onComplete();
        } else if (taskStatus.status === 'failed') {
          setStatus('failed');
          setError(taskStatus.error || '生成失败');
          if (onStatusUpdate) onStatusUpdate('failed');
        } else if (taskStatus.status === 'cancelled') {
          setStatus('cancelled');
          setError('任务已取消');
          if (onStatusUpdate) onStatusUpdate('cancelled');
        } else {
          setProgress(taskStatus.progress || 0);
          setStatus(taskStatus.status);
          if (onStatusUpdate) onStatusUpdate(taskStatus.status);
        }
      } catch (error: any) {
        console.error('获取任务状态失败:', error);
        
        // 处理404错误（任务不存在）
        if (error.response?.status === 404) {
          setError('任务不存在或已被删除');
          setStatus('failed');
          if (onStatusUpdate) onStatusUpdate('failed');
          return; // 停止轮询
        }
        
        // 处理其他错误
        setError(error.response?.data?.detail || '获取任务状态失败');
      }
    };

    // 启动轮询
    const interval = setInterval(checkStatus, 2000);
    
    // 立即执行一次检查
    checkStatus();

    // 清理函数
    return () => {
      clearInterval(interval);
    };
  }, [taskId, generationProgress, onComplete, onStatusUpdate, isInitialized]);

  const getStatusText = () => {
    const currentTaskId = taskId || (generationProgress?.taskId);
    
    if (!currentTaskId && !generationProgress) {
      return '等待任务...';
    }

    if (error) {
      return error;
    }

    // 如果有generationProgress且包含队列位置信息
    if (generationProgress?.isAsync && generationProgress?.asyncStatus === 'pending' && generationProgress?.queuePosition !== undefined) {
      return `队列中 - 位置: ${generationProgress.queuePosition}${
        generationProgress.estimatedWaitSeconds 
          ? ` (预计等待: ${Math.floor(generationProgress.estimatedWaitSeconds / 60)}分${generationProgress.estimatedWaitSeconds % 60}秒)`
          : ''
      }`;
    }

    // 使用队列状态API返回的信息
    if (status === 'pending' && queueStatus && currentTaskId) {
      const position = queueStatus.queued_tasks.findIndex(task => task.task_id === currentTaskId);
      if (position !== -1) {
        return `队列中 - 位置: ${position + 1} (当前处理中: ${queueStatus.processing_count}/${queueStatus.max_concurrent})`;
      }
    }

    if (status === 'processing') {
      if (currentTaskId && queueStatus) {
        const processingTask = queueStatus.processing_tasks.find(task => task.task_id === currentTaskId);
        if (processingTask) {
          const duration = Math.floor((Date.now() - processingTask.start_time * 1000) / 1000);
          return `处理中 - 已用时间: ${Math.floor(duration / 60)}分${duration % 60}秒 (${queueStatus.processing_count}/${queueStatus.max_concurrent})`;
        }
      }
      
      // 如果是批处理，显示批处理进度
      if (generationProgress?.isBatch) {
        return `处理中 - 批次 ${generationProgress.currentBatch}/${generationProgress.totalBatches}, 图片 ${generationProgress.currentImage}/${generationProgress.totalImages}`;
      }
      
      return '处理中...';
    }

    if (status === 'completed') {
      return '生成完成';
    }

    if (status === 'cancelled') {
      return '已取消';
    }

    if (status === 'failed') {
      return `生成失败: ${error || '未知错误'}`;
    }

    return '等待中...';
  };

  if (!isVisible) {
    return null;
  }

  return (
    <div className="w-full bg-white p-4 rounded-lg shadow-md mb-6">
      <h3 className="text-lg font-medium text-gray-900 mb-2">任务进度</h3>
      <Progress value={progress} className="w-full" />
      <div className="text-sm text-gray-500 dark:text-gray-400 mt-2">
        {getStatusText()}
      </div>
      {queueStatus && (
        <div className="text-xs text-gray-400 dark:text-gray-500 mt-1">
          队列总数: {queueStatus.total_active} | 处理中: {queueStatus.processing_count}/{queueStatus.max_concurrent} | 等待中: {queueStatus.queue_count}
        </div>
      )}
    </div>
  );
} 