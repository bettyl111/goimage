import React, { useState, useEffect } from 'react';
import { Loader2, BarChart3, Clock, Users } from 'lucide-react';
import { authenticatedRequest } from '../services/api';

/**
 * 队列状态面板组件 2023.07.01 11
 * 显示任务队列的整体状态，包括队列长度、用户任务数、并发任务数等
 */
const QueueStatusPanel: React.FC = () => {
  const [queueStatus, setQueueStatus] = useState<{
    queue_length: number;
    user_tasks_in_queue: number;
    user_tasks_processing: number;
    concurrent_tasks: number;
    max_concurrent: number;
  } | null>(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // 轮询队列状态
  useEffect(() => {
    const fetchQueueStatus = async () => {
      try {
        setLoading(true);
        const response = await authenticatedRequest('/queue-status', {
          method: 'GET'
        });
        
        if (!response.ok) {
          throw new Error(`获取队列状态失败: ${response.status}`);
        }
        
        const data = await response.json();
        setQueueStatus(data);
        setError(null);
      } catch (err) {
        console.error('获取队列状态出错:', err);
        setError('获取队列状态失败，请刷新重试');
      } finally {
        setLoading(false);
      }
    };
    
    // 立即获取一次
    fetchQueueStatus();
    
    // 设置轮询
    const interval = setInterval(fetchQueueStatus, 5001); // 每5秒更新一次
    
    return () => clearInterval(interval);
  }, []);
  
  if (loading && !queueStatus) {
    return (
      <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700 flex items-center justify-center">
        <Loader2 className="w-5 h-5 text-purple-400 animate-spin mr-2" />
        <span className="text-sm text-slate-300">加载队列状态...</span>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="p-4 bg-red-900/20 rounded-lg border border-red-700 text-center">
        <span className="text-sm text-red-300">{error}</span>
      </div>
    );
  }
  
  if (!queueStatus) return null;
  
  const queueUtilization = queueStatus.concurrent_tasks / queueStatus.max_concurrent * 100;
  
  return (
    <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700">
      <h3 className="text-sm font-medium text-slate-200 mb-3 flex items-center">
        <BarChart3 className="w-4 h-4 mr-2 text-purple-400" />
        任务队列状态
      </h3>
      
      <div className="space-y-3">
        {/* 队列长度 */}
        <div>
          <div className="flex justify-between items-center mb-1">
            <span className="text-xs text-slate-400">队列长度</span>
            <span className="text-xs font-medium text-slate-300">{queueStatus.queue_length} 个任务</span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-1.5">
            <div 
              className="h-1.5 rounded-full bg-purple-500"
              style={{ width: `${Math.min(100, queueStatus.queue_length * 10)}%` }}
            />
          </div>
        </div>
        
        {/* 并发任务 */}
        <div>
          <div className="flex justify-between items-center mb-1">
            <span className="text-xs text-slate-400">并发任务</span>
            <span className="text-xs font-medium text-slate-300">
              {queueStatus.concurrent_tasks}/{queueStatus.max_concurrent}
            </span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-1.5">
            <div 
              className={`h-1.5 rounded-full ${queueUtilization > 80 ? 'bg-amber-500' : 'bg-emerald-500'}`}
              style={{ width: `${queueUtilization}%` }}
            />
          </div>
        </div>
        
        {/* 用户任务 */}
        <div className="flex items-center justify-between pt-2 border-t border-slate-700">
          <div className="flex items-center">
            <Users className="w-3.5 h-3.5 text-slate-400 mr-1.5" />
            <span className="text-xs text-slate-400">您的任务</span>
          </div>
          <div>
            <span className="text-xs font-medium text-slate-300">
              {queueStatus.user_tasks_in_queue} 个等待中
            </span>
            <span className="text-xs text-slate-500 mx-1">|</span>
            <span className="text-xs font-medium text-slate-300">
              {queueStatus.user_tasks_processing} 个处理中
            </span>
          </div>
        </div>
        
        {/* 刷新时间 */}
        <div className="flex items-center justify-end pt-1 text-xs text-slate-500">
          <Clock className="w-3 h-3 mr-1" />
          <span>每5秒自动刷新</span>
        </div>
      </div>
    </div>
  );
};

export default QueueStatusPanel; 