import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import Header from "@/components/Header";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/services/api";
import { LogIn, User, Lock } from "lucide-react";

const Login = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { login, isAuthenticated } = useAuth();

  // 如果已经登录，重定向到首页
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
    }
  }, [isAuthenticated, navigate]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    
    try {
      const response = await api.post('/login', {
        username: username,
        password: password
      });

      const data = response.data;
      
      console.log('Login successful:', data);
      login(data.user.username || data.user.email, data.access_token);
      toast.success(`欢迎 ${data.user.cname || data.user.username}！`);
      window.location.href = '/';
      
    } catch (error) {
      console.error('Login error:', error);
      if (error.response && error.response.data) {
        toast.error(error.response.data.detail || "用户名或密码错误");
      } else {
        toast.error("网络错误，请稍后重试");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <div className="flex justify-center items-center h-[calc(100vh-64px)] p-4">
        <div className="w-full max-w-md bg-white rounded-lg shadow-sm border border-gray-200">
          {/* 登录头部 */}
          <div className="p-6 border-b border-gray-100">
            <div className="flex items-center justify-center mb-4">
              <div className="p-3 bg-blue-50 rounded-full">
                <LogIn className="w-8 h-8 text-blue-600" />
              </div>
            </div>
            <div className="text-center">
              <h2 className="text-2xl font-semibold text-gray-900">用户登录</h2>
              <p className="mt-2 text-sm text-gray-600">公司域账号登录</p>
            </div>
          </div>
          
          {/* 登录表单 */}
          <div className="p-6">
            <form onSubmit={handleLogin} className="space-y-5">
              <div className="space-y-4">
                <div>
                  <Label htmlFor="username" className="text-sm font-medium text-gray-700 mb-2 block">
                  域账号
                  </Label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <User className="h-4 w-4 text-gray-400" />
                    </div>
                    <Input
                      id="username"
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="请输入域账号"
                      className="pl-10 border-gray-300 focus:border-blue-500 focus:ring-blue-500"
                      required
                    />
                  </div>
                  {/* <p className="mt-1 text-xs text-gray-500">
                    公司域账号
                  </p> */}
                </div>
                
                <div>
                  <Label htmlFor="password" className="text-sm font-medium text-gray-700 mb-2 block">
                    密码
                  </Label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Lock className="h-4 w-4 text-gray-400" />
                    </div>
                    <Input
                      id="password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="请输入您的密码"
                      className="pl-10 border-gray-300 focus:border-blue-500 focus:ring-blue-500"
                      required
                    />
                  </div>
                </div>
              </div>
              
              <div className="pt-2">
                <Button
                  type="submit"
                  className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-4 rounded-lg transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <div className="flex items-center justify-center">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      登录中...
                    </div>
                  ) : (
                    "登录"
                  )}
                </Button>
              </div>
            </form>
          </div>
          
          {/* 底部提示 */}
          {/* <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 rounded-b-lg"> */}
            {/* <p className="text-xs text-gray-500 text-center">
              登录即表示您同意我们的服务条款和隐私政策
            </p> */}
          {/* </div> */}
        </div>
      </div>
    </div>
  );
};

export default Login;
