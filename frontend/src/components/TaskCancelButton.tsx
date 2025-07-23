import React from 'react';
import { Button } from './ui/button';
import { api } from '../services/api';
import { useToast } from './ui/use-toast';

interface TaskCancelButtonProps {
  taskId: string;
  onCancel?: () => void;
  disabled?: boolean;
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link';
  size?: 'default' | 'sm' | 'lg' | 'icon';
}

/**
 * 任务取消按钮组件
 * 用于取消队列中的任务
 */
export function TaskCancelButton({ 
  taskId, 
  onCancel, 
  disabled = false,
  variant = 'destructive',
  size = 'sm'
}: TaskCancelButtonProps) {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = React.useState(false);

  const handleCancel = async () => {
    try {
      setIsLoading(true);
      const response = await api.post(`/cancel-task/${taskId}`);
      
      if (response.data.message) {
        toast({
          title: "任务取消",
          description: response.data.message
        });
      }

      if (onCancel) {
        onCancel();
      }
    } catch (error: any) {
      console.error('取消任务失败:', error);
      toast({
        variant: "destructive",
        title: "取消失败",
        description: error.response?.data?.detail || "无法取消任务，请重试"
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleCancel}
      disabled={disabled || isLoading}
    >
      {isLoading ? "取消中..." : "取消"}
    </Button>
  );
} 