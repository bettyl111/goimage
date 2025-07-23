
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import AIImageGenerator from '@/components/AIImageGenerator';

const Index = () => {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login');
    }
  }, [isAuthenticated, navigate]);

  // 如果未认证，不渲染任何内容（避免闪烁）
  if (!isAuthenticated) {
    return null;
  }

  return <AIImageGenerator />;
};

export default Index;
