import axios from 'axios';

// API 配置 2023.07.03 15
const getApiBaseUrl = () => {
  const hostname = window.location.hostname;
  const protocol = window.location.protocol;
  
  // 调试信息
  console.log('[API Config]', {
    hostname,
    protocol,
    fullLocation: window.location.href
  });

  // 生产环境判断（使用域名访问）
  if (hostname === 'ai-image-generation.3g.net.cn' || hostname === 'ai-image-test.3g.net.cn') {
    const url = `${protocol}//${hostname}/api`;
    console.log('[API] 使用生产环境URL:', url);
    return url;
  }
  
  // 局域网IP访问
  if (hostname === '192.168.0.241') {
    const port = window.location.port === '8081' ? '5001' : '5001';  // 测试环境使用5001端口
    const url = `${protocol}//${hostname}:${port}/api`;
    console.log('[API] 使用局域网IP URL:', url);
    return url;
  }
  
  // 开发环境（localhost）
  const url = `http://localhost:5001/api`;  // 测试环境使用5001端口
  console.log('[API] 使用开发环境URL:', url);
  return url;
};

export const API_BASE_URL = getApiBaseUrl();

// 添加一个函数来确保图片URL与当前页面域名一致 2023.07.03 15
export const normalizeImageUrl = (imageUrl: string): string => {
  try {
    // 如果是相对URL，直接返回
    if (imageUrl.startsWith('/')) {
      return imageUrl;
    }
    
    // 解析URL
    const parsedUrl = new URL(imageUrl);
    const currentHost = window.location.hostname;
    
    // 判断是否是域名访问
    const isDomainAccess = currentHost === 'ai-image-generation.3g.net.cn' || 
                          currentHost === 'ai-image-test.3g.net.cn';
    
    let newUrl;
    if (isDomainAccess) {
      // 域名访问时，使用相同的协议和域名，不需要端口
      newUrl = `${window.location.protocol}//${currentHost}${parsedUrl.pathname}${parsedUrl.search}${parsedUrl.hash}`;
    } else {
      // 本地或IP访问时，使用5001端口
      const apiPort = '5001';
      newUrl = `http://${currentHost}:${apiPort}${parsedUrl.pathname}${parsedUrl.search}${parsedUrl.hash}`;
    }
    
    // 添加日志，帮助调试
    console.log(`规范化图片URL: 从 ${imageUrl} 到 ${newUrl}`);
    
    return newUrl;
  } catch (error) {
    console.error('解析图片URL时出错:', error, imageUrl);
    return imageUrl; // 出错时返回原始URL
  }
};

// API 请求封装
export const apiRequest = async (endpoint: string, options: RequestInit = {}) => {
  const url = `${API_BASE_URL}${endpoint}`;
  
  // 创建一个可以被中止的请求
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 18000000); // 3分钟超时
  
  const defaultOptions: RequestInit = {
    credentials: "include",
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
    signal: controller.signal,
  };

  // 如果是FormData对象，移除Content-Type头，让浏览器自动设置
  if (options.body instanceof FormData) {
    if (defaultOptions.headers) {
      delete defaultOptions.headers['Content-Type'];
    }
  }

  // 安全地记录请求信息，避免FormData解析错误
  let logBody;
  if (options.body) {
    if (options.body instanceof FormData) {
      logBody = '[FormData对象]';
    } else if (typeof options.body === 'string') {
      try {
        if (options.body.trim().startsWith('{')) {
          logBody = JSON.parse(options.body);
        } else {
          logBody = options.body;
        }
      } catch (e) {
        logBody = `[无法解析的字符串: ${options.body.substring(0, 50)}...]`;
      }
    } else {
      logBody = options.body;
    }
  }

  console.log(`[API] 发起请求:`, {
    url,
    method: options.method || 'GET',
    headers: defaultOptions.headers,
    body: logBody
  });

  try {
    const response = await fetch(url, defaultOptions);
    clearTimeout(timeoutId);
    console.log(`[API] 响应:`, {
      status: response.status,
      statusText: response.statusText,
      url: response.url
    });

    // 如果是503错误，输出更多信息
    if (response.status === 503) {
      console.warn('[API] 服务不可用 (503) - 请求详情:', {
        完整URL: url,
        请求方法: options.method || 'GET',
        请求头: defaultOptions.headers,
        请求体: logBody,
        响应状态: response.status,
        当前位置: window.location.href
      });
      
      // 尝试解析错误消息
      try {
        const errorData = await response.clone().json();
        console.warn('[API] 503错误详情:', errorData);
      } catch (e) {
        console.warn('[API] 无法解析503错误详情');
      }
    }

    // 如果是404错误，输出更多信息
    if (response.status === 404) {
      console.error('[API] 404错误 - 请求详情:', {
        完整URL: url,
        请求方法: options.method || 'GET',
        请求头: defaultOptions.headers,
        请求体: logBody,
        响应状态: response.status,
        响应文本: response.statusText,
        当前位置: window.location.href
      });
    }

    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    console.error('[API] 请求失败:', {
      错误: error,
      URL: url,
      选项: defaultOptions
    });
    if (error.name === 'AbortError') {
      console.error('请求超时');
      // 可以考虑重试或通知用户
    }
    throw error;
  }
};

// 获取认证token
export const getAuthToken = () => {
  const token = localStorage.getItem('token');
  console.log('[API] 当前Token:', token ? '已设置' : '未设置');
  return token;
};

// 带认证的API请求
export const authenticatedRequest = async (endpoint: string, options: RequestInit = {}) => {
  const token = getAuthToken();
  
  const authOptions: RequestInit = {
    ...options,
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
      ...options.headers,
    },
  };

  console.log('[API] 发起认证请求:', {
    endpoint,
    hasToken: !!token,
    headers: authOptions.headers
  });

  return apiRequest(endpoint, authOptions);
};

// 批量查询任务状态
export interface TaskStatus {
  task_id: string;
  status: string;
  progress?: number | null;
  message?: string | null;
  result?: any;
}

export const batchQueryTaskStatus = async (taskIds: string[]): Promise<Record<string, TaskStatus>> => {
  if (!taskIds || taskIds.length === 0) {
    return {};
  }
  
  try {
    const response = await authenticatedRequest('/batch-task-status', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        task_ids: taskIds
      })
    });
    
    if (!response.ok) {
      console.error('[API] 批量查询任务状态失败:', response.status);
      return {};
    }
    
    const data = await response.json();
    return data.tasks || {};
  } catch (error) {
    console.error('[API] 批量查询任务状态出错:', error);
    return {};
  }
};

// 创建axios实例 2023.07.03 14
export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,  // 30秒超时
  headers: {
    'Content-Type': 'application/json'
  },
  withCredentials: true  // 支持跨域携带cookie
});

// 创建自定义事件 2023.07.03 14
export const AUTH_ERROR_EVENT = 'auth_error';
export const dispatchAuthError = () => {
  window.dispatchEvent(new CustomEvent(AUTH_ERROR_EVENT));
};

// 创建ComfyUI服务不可用事件 2023.07.04 16
export const COMFYUI_UNAVAILABLE_EVENT = 'comfyui_unavailable';
export const dispatchComfyUIUnavailable = (message: string) => {
  window.dispatchEvent(new CustomEvent(COMFYUI_UNAVAILABLE_EVENT, { 
    detail: { message } 
  }));
};

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = getAuthToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response) {
      // 处理401错误（未授权）
      if (error.response.status === 401) {
        console.error('[API] 认证失败:', error.response.data);
        dispatchAuthError();
      }
      
      // 处理503错误（服务不可用）
      if (error.response.status === 503) {
        console.warn('[API] ComfyUI服务不可用:', error.response.data);
        // 触发ComfyUI不可用事件
        const message = error.response.data?.message || "ComfyUI服务不可用，请稍后再试";
        dispatchComfyUIUnavailable(message);
      }
    }
    return Promise.reject(error);
  }
); 