import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from "sonner";
import { Button } from '@/components/ui/button';
import { History, CheckSquare, Square, Download, AlertTriangle, Trash2, Check, Sparkles, Maximize, ChevronLeft, ChevronRight, Search, Wand2, MessageSquareText, Clock } from 'lucide-react';
import ConfirmDialog, { ConfirmDialogProps } from './ConfirmDialog'; // 导入ConfirmDialog
import { GeneratedImage } from './ImageGallery'; // 导入 GeneratedImage 类型
import { useAuth } from '@/contexts/AuthContext';
import { authenticatedRequest, normalizeImageUrl } from '@/services/api';
import { TaskCancelButton } from './TaskCancelButton'; // 导入任务取消按钮组件 2023.07.01 12
import { GenerationProgressBar } from './GenerationProgressBar';

// Define and export HistoryEntry to match backend structure
export interface HistoryEntry {
  id: number;
  user_email: string;
  prompt: string;
  image_filename: string;
  generation_type?: string | null; // snake_case from backend
  timestamp: string;
  image_url: string;
}

// 定义用户任务接口 2023.07.01 12
export interface UserTask {
  task_id: string;
  status: string;
  prompt: string;
  creation_time: number;
  completion_time?: number;
  image_url?: string;
  generation_type: string;
  queue_position?: number;
  estimated_wait_seconds?: number;
}

interface TaskStatus {
  id: string;
  status: string;
  progress: number;
  result: any;
  error: string | null;
  in_comfyui: boolean;
}

export interface HistoryGalleryProps {
  openImageModal: (imageUrl: string) => void;
  isVisible: boolean;
}

const HistoryGallery = ({ openImageModal, isVisible }: HistoryGalleryProps) => {
  const [historyImages, setHistoryImages] = useState<HistoryEntry[]>([]);
  const [userTasks, setUserTasks] = useState<UserTask[]>([]); // 添加用户任务状态 2023.07.01 12
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isLoadingTasks, setIsLoadingTasks] = useState(false); // 添加任务加载状态 2023.07.01 12
  const [errorHistory, setErrorHistory] = useState<string | null>(null);
  const [selectedImages, setSelectedImages] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  const [confirmDialog, setConfirmDialog] = useState<Omit<ConfirmDialogProps, 'onClose' | 'isOpen'> & { isOpen: boolean; onConfirm: () => void; }> ({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: () => {},
    type: 'info'
  });
  const [tasks, setTasks] = useState<TaskStatus[]>([]);
  const navigate = useNavigate();

  // 格式化等待时间 2023.07.01 12
  const formatWaitTime = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds}秒`;
    } else {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      return `${minutes}分${remainingSeconds}秒`;
    }
  };

  // 获取用户任务 2023.07.01 12
  const fetchUserTasks = async () => {
    setIsLoadingTasks(true);
    try {
      const response = await authenticatedRequest('/user-tasks', {
        method: 'GET',
      });
      
      if (response.status === 401) {
        toast.error("会话已过期，请重新登录。");
        navigate('/login');
        return;
      }
      
      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: "获取任务列表失败" }));
        throw new Error(errData.detail || `HTTP error! Status: ${response.status}`);
      }
      
      const data: UserTask[] = await response.json();
      setUserTasks(data);
    } catch (err) {
      console.error("获取用户任务失败:", err);
      const errorMessageText = err instanceof Error ? err.message : "加载任务列表时发生未知错误";
      toast.error(errorMessageText);
    } finally {
      setIsLoadingTasks(false);
    }
  };

  // 任务取消成功后的回调 2023.07.01 12
  const handleTaskCancelled = (taskId: string) => {
    // 从任务列表中移除已取消的任务
    setUserTasks(prevTasks => prevTasks.filter(task => task.task_id !== taskId));
  };

  const handleDownloadHistoryImage = async (imageUrl: string, prompt: string) => {
    try {
      // 使用规范化的URL
      const normalizedUrl = normalizeImageUrl(imageUrl);
      const response = await fetch(normalizedUrl);
      if (!response.ok) throw new Error(`下载失败: ${response.status}`);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      const filename = normalizedUrl.split('/').pop() || 'history_image.png';
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      return true;
    } catch (error) {
      console.error("下载历史图片失败:", error);
      return false;
    }
  };

  const handleBatchDownload = async () => {
    if (selectedImages.size === 0) {
      toast.error("请先选择要下载的图片");
      return;
    }

    setConfirmDialog({
      isOpen: true,
      title: "批量下载确认",
      message: `是否下载选中的 ${selectedImages.size} 张图片？`,
      type: 'info',
      onConfirm: async () => {
        const selectedImagesList = historyImages.filter(img => selectedImages.has(img.id.toString()));
        toast.info(`开始下载 ${selectedImages.size} 张图片...`);

        let successCount = 0;
        let failCount = 0;

        for (const image of selectedImagesList) {
          const success = await handleDownloadHistoryImage(image.image_url, image.prompt);
          if (success) {
            successCount++;
          } else {
            failCount++;
          }
        }

        if (failCount === 0) {
          toast.success(`全部 ${successCount} 张图片下载成功！`);
        } else {
          toast.warning(`下载完成：${successCount} 张成功，${failCount} 张失败`);
        }
      }
    });
  };

  const handleBatchDelete = async () => {
    if (selectedImages.size === 0) {
      toast.error("请先选择要删除的图片");
      return;
    }

    setConfirmDialog({
      isOpen: true,
      title: "批量删除确认",
      message: `确定要删除选中的 ${selectedImages.size} 张图片吗？此操作不可撤销。`,
      type: 'warning',
      onConfirm: async () => {
        setIsDeleting(true);
        const selectedImagesList = historyImages.filter(img => selectedImages.has(img.id.toString()));
        toast.info(`开始删除 ${selectedImages.size} 张图片...`);

        let successCount = 0;
        let failCount = 0;

        try {
          for (const image of selectedImagesList) {
            try {


              const response = await authenticatedRequest(`/user-history/${image.id}`, {
                method: 'DELETE',
              });

              if (response.status === 204 || response.ok) {
                successCount++;
              } else if (response.status === 401) {
                toast.error("会话已过期，请重新登录。");
                navigate('/login');
                return;
              } else {
                const errorData = await response.json().catch(() => ({ detail: '删除失败' }));
                console.error(`删除图片 ${image.id} 失败:`, errorData.detail);
                failCount++;
              }
            } catch (error) {
              console.error(`删除图片 ${image.id} 时出错:`, error);
              failCount++;
            }
          }

          // 更新本地状态
          if (successCount > 0) {
            setHistoryImages(prevImages => 
              prevImages.filter(img => !selectedImages.has(img.id.toString()))
            );
            setSelectedImages(new Set()); // 清空选择
          }

          // 显示结果
          if (failCount === 0) {
            toast.success(`成功删除 ${successCount} 张图片！`);
          } else {
            toast.warning(`删除完成：${successCount} 张成功，${failCount} 张失败`);
          }
        } catch (error) {
          console.error("批量删除过程中发生错误:", error);
          toast.error("批量删除过程中发生错误");
        } finally {
          setIsDeleting(false);
        }
      }
    });
  };

  const handleDeleteHistoryItem = async (historyId: string | number) => {
    setConfirmDialog({
      isOpen: true,
      title: "删除确认",
      message: "确定要删除这条历史记录吗？此操作不可撤销。",
      type: 'warning',
      onConfirm: async () => {

        try {
          const response = await authenticatedRequest(`/user-history/${historyId}`, {
            method: 'DELETE',
          });
          if (response.status === 204 || response.ok) {
            toast.success("历史记录已删除");
            setHistoryImages(prevImages => prevImages.filter(img => img.id !== historyId));
          } else if (response.status === 401) {
            toast.error("会话已过期，请重新登录。");
            navigate('/login');
          } else {
            const errorData = await response.json().catch(() => ({ detail: '删除失败' }));
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
          }
        } catch (error) {
          console.error("删除历史记录时出错:", error);
          const delErrorMessage = error instanceof Error ? error.message : "删除时发生未知错误";
          toast.error(delErrorMessage);
          if (delErrorMessage.toLowerCase().includes("unauthorized") || delErrorMessage.includes("401")){
            navigate('/login');
          }
        }
      }
    });
  };

  const toggleImageSelection = (imageId: string) => {
    setSelectedImages(prev => {
      const newSet = new Set(prev);
      if (newSet.has(imageId)) {
        newSet.delete(imageId);
      } else {
        newSet.add(imageId);
      }
      return newSet;
    });
  };

  const toggleSelectAll = () => {
    if (selectedImages.size === historyImages.length) {
      setSelectedImages(new Set());
    } else {
      setSelectedImages(new Set(historyImages.map(img => img.id.toString())));
    }
  };

  const fetchTasks = async () => {
    try {
      const response = await authenticatedRequest('/user-tasks', {
        method: 'GET',
      });
      
      if (response.status === 401) {
        toast.error("会话已过期，请重新登录。");
        navigate('/login');
        return;
      }
      
      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: "获取任务列表失败" }));
        throw new Error(errData.detail || `HTTP error! Status: ${response.status}`);
      }
      
      const data: TaskStatus[] = await response.json();
      setTasks(data);
    } catch (error) {
      console.error('获取任务历史失败:', error);
    }
  };

  useEffect(() => {
    const fetchHistory = async () => {
      setIsLoadingHistory(true);
      setErrorHistory(null);

      try {
        const response = await authenticatedRequest('/user-history', {
          method: 'GET',
        });
        if (response.status === 401) {
          toast.error("会话已过期，请重新登录。");
          navigate('/login');
          return;
        }
        if (!response.ok) {
          const errData = await response.json().catch(() => ({ detail: "获取历史记录失败" }));
          throw new Error(errData.detail || `HTTP error! Status: ${response.status}`);
        }
        const data: HistoryEntry[] = await response.json();
        
        // 添加调试日志
        console.log('获取到的历史记录:', data);
        data.forEach(entry => {
          console.log(`历史记录图片URL: ${entry.image_url} -> ${normalizeImageUrl(entry.image_url)}`);
        });
        
        setHistoryImages(data);
      } catch (err) {
        console.error("获取历史记录失败:", err);
        const errorMessageText = err instanceof Error ? err.message : "加载历史记录时发生未知错误";
        setErrorHistory(errorMessageText);
        toast.error(errorMessageText);
        if (errorMessageText.toLowerCase().includes("unauthorized") || errorMessageText.includes("401")){
            navigate('/login');
        }
      } finally {
        setIsLoadingHistory(false);
      }
    };

    if (isVisible && historyImages.length === 0 && !errorHistory) {
      fetchHistory();
    }
    
    // 如果组件可见，获取用户任务 2023.07.01 12
    if (isVisible) {
      fetchUserTasks();
      fetchTasks();
      
      // 设置定时器，每10秒刷新一次任务状态
      const taskInterval = setInterval(() => {
        fetchUserTasks();
        fetchTasks();
      }, 10000);
      
      return () => clearInterval(taskInterval);
    }
  }, [isVisible, navigate, historyImages.length, errorHistory]);

  if (!isVisible) return null;

  if (isLoadingHistory && historyImages.length === 0) {
    return <div className="text-white text-center p-10">加载历史记录中...</div>;
  }

  if (errorHistory && historyImages.length === 0) {
    return <div className="text-red-400 text-center p-10">加载历史记录失败: {errorHistory}</div>;
  }

  // 过滤出待处理和处理中的任务 2023.07.01 12
  const pendingTasks = userTasks.filter(task => task.status === 'pending' || task.status === 'processing');

  return (
    <div className="h-full flex flex-col">
      {/* 添加任务队列状态显示 2023.07.01 12 */}
      {pendingTasks.length > 0 && (
        <div className="mb-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
            <h3 className="text-sm font-medium text-blue-700 mb-2 flex items-center">
              <Clock className="w-4 h-4 mr-1.5" />
              正在处理的任务 ({pendingTasks.length})
            </h3>
            <div className="space-y-2">
              {pendingTasks.map((task) => (
                <div key={task.task_id} className="bg-white p-2 rounded border border-blue-100 flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center">
                      {task.generation_type === 'text-to-image' ? (
                        <MessageSquareText className="w-3.5 h-3.5 text-blue-500 mr-1.5" />
                      ) : (
                        <Wand2 className="w-3.5 h-3.5 text-blue-500 mr-1.5" />
                      )}
                      <span className="text-sm font-medium text-blue-800 truncate">
                        {task.prompt || "无提示词"}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center text-xs text-blue-600">
                      <span className="mr-2">状态: {
                        task.status === 'pending' 
                          ? (task.queue_position 
                              ? `队列中 (位置: ${task.queue_position})` 
                              : '等待中')
                          : '处理中'
                      }</span>
                      {task.estimated_wait_seconds && task.status === 'pending' && (
                        <span>预计等待: {formatWaitTime(task.estimated_wait_seconds)}</span>
                      )}
                    </div>
                  </div>
                  <TaskCancelButton 
                    taskId={task.task_id} 
                    onCancel={() => handleTaskCancelled(task.task_id)}
                    size="sm"
                    variant="outline"
                    className="text-red-500 hover:text-red-600 hover:bg-red-50"
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="text-blue-900/70 hover:text-blue-900 hover:bg-blue-50"
            onClick={toggleSelectAll}
            disabled={isDeleting}
          >
            {selectedImages.size === historyImages.length ? (
              <CheckSquare className="w-4 h-4 mr-2" />
            ) : (
              <Square className="w-4 h-4 mr-2" />
            )}
            {selectedImages.size === historyImages.length ? "取消全选" : "全选"}
          </Button>
          <span className="text-blue-900/50 text-sm">
            已选择 {selectedImages.size} 张图片
          </span>
        </div>
        {selectedImages.size > 0 && (
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="text-blue-900/70 hover:text-blue-900 hover:bg-blue-50"
              onClick={handleBatchDownload}
              disabled={isDeleting}
            >
              <Download className="w-4 h-4 mr-2" />
              下载选中图片
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-red-500 hover:text-red-600 hover:bg-red-50"
              onClick={handleBatchDelete}
              disabled={isDeleting}
            >
              <AlertTriangle className="w-4 h-4 mr-2" />
              删除选中图片
            </Button>
          </div>
        )}
      </div>
      <div className="flex-1 overflow-hidden">
        <div className="h-full max-h-[calc(100vh-250px)] overflow-y-auto pr-2 custom-scrollbar">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {historyImages.map((item) => (
              <div key={item.id} className={`bg-white rounded-lg overflow-hidden border border-blue-100 hover:border-blue-200 transition-all ${isDeleting ? 'pointer-events-none opacity-50' : ''}`}>
                <div className="relative group aspect-square rounded-lg overflow-hidden shadow-lg cursor-pointer" onClick={() => openImageModal(normalizeImageUrl(item.image_url))}>
                  <img
                    src={normalizeImageUrl(item.image_url)}
                    alt={item.prompt || "Generated image"}
                    className="w-full h-full object-contain transition-transform duration-300 ease-in-out group-hover:scale-105"
                    loading="lazy"
                    onError={(e) => {
                      console.warn(`Failed to load image: ${normalizeImageUrl(item.image_url)}`);
                      // 尝试显示错误信息
                      const imgElement = e.currentTarget as HTMLImageElement;
                      imgElement.style.display = 'none';
                      const errorDiv = document.createElement('div');
                      errorDiv.className = 'w-full h-full flex items-center justify-center bg-gray-100 text-red-500';
                      errorDiv.innerHTML = `<div class="text-center p-2"><div>图片加载失败</div><div class="text-xs mt-1">${item.image_filename}</div></div>`;
                      imgElement.parentNode?.appendChild(errorDiv);
                    }}
                  />
                  {item.generation_type && (
                    <div className="absolute top-1.5 left-1.5 p-1 rounded-full flex items-center justify-center text-blue-600">
                      {item.generation_type === 'text-to-image' ? 
                        <MessageSquareText className="w-3 h-3 drop-shadow-md" /> :
                        <Wand2 className="w-3 h-3 drop-shadow-md" />
                      }
                    </div>
                  )}
                  <div className="absolute inset-0 bg-gradient-to-t from-blue-900/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                    <div className="absolute bottom-0 left-0 right-0 p-3 text-white">
                      <p className="text-sm font-medium line-clamp-2" title={item.prompt}>{item.prompt || "无提示词"}</p>
                      <p className="text-xs text-blue-100 mt-1">{
                        (() => {
                          const date = new Date(item.timestamp);
                          const year = date.getFullYear();
                          const month = date.getMonth() + 1;
                          const day = date.getDate();
                          return `${year}/${month}/${day}`;
                        })()
                      }</p>
                    </div>
                  </div>
                  <div className="absolute inset-0 bg-blue-900/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-4">
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="bg-white/90 hover:bg-white text-blue-600 hover:text-blue-700"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleImageSelection(item.id.toString());
                      }}
                      disabled={isDeleting}
                    >
                      {selectedImages.has(item.id.toString()) ? (
                        <CheckSquare className="w-5 h-5" />
                      ) : (
                        <Square className="w-5 h-5" />
                      )}
                    </Button>
                    <Button variant="ghost" size="icon" className="bg-white/90 hover:bg-white text-blue-600 hover:text-blue-700" onClick={(e) => { e.stopPropagation(); toast.success("重新生成功能即将上线"); }} disabled={isDeleting}>
                      <Sparkles className="w-5 h-5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="bg-white/90 hover:bg-white text-blue-600 hover:text-blue-700" onClick={(e) => { e.stopPropagation(); handleDownloadHistoryImage(item.image_url, item.prompt); }} disabled={isDeleting}>
                      <Download className="w-5 h-5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="bg-red-500/90 hover:bg-red-600 text-white" onClick={(e) => { e.stopPropagation(); handleDeleteHistoryItem(item.id); }} title="删除此记录" disabled={isDeleting}>
                      <Trash2 className="w-5 h-5" />
                    </Button>
                  </div>
                  {selectedImages.has(item.id.toString()) && (
                    <div className="absolute top-2 left-2 bg-blue-500 text-white p-1 rounded-full">
                      <Check className="w-4 h-4" />
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        onClose={() => setConfirmDialog(prev => ({ ...prev, isOpen: false }))}
        onConfirm={confirmDialog.onConfirm}
        title={confirmDialog.title}
        message={confirmDialog.message}
        type={confirmDialog.type}
      />
    </div>
  );
};

export default HistoryGallery; 