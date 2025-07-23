import React, { createContext, useContext, useState, useEffect } from 'react';
import { AUTH_ERROR_EVENT, api } from '../services/api';

export interface AuthContextType {
  user: string | null;
  token: string | null;
  login: (email: string, token: string) => void;
  logout: () => void;
  clearAuth: () => void;
  isAuthenticated: boolean;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<string | null>(localStorage.getItem('user'));
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));

  const validateToken = async (token: string) => {
    try {
      const response = await api.get('/validate-token', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      return response.status === 200;
    } catch (error) {
      console.error('Token验证失败:', error);
      return false;
    }
  };

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    if (storedToken) {
      validateToken(storedToken).then(isValid => {
        if (!isValid) {
          clearAuth();
        }
      });
    }
  }, []);

  useEffect(() => {
    const handleAuthError = () => {
      clearAuth();
      window.location.href = '/login';
    };

    window.addEventListener(AUTH_ERROR_EVENT, handleAuthError);
    return () => {
      window.removeEventListener(AUTH_ERROR_EVENT, handleAuthError);
    };
  }, []);

  const login = (email: string, newToken: string) => {
    setUser(email);
    setToken(newToken);
    localStorage.setItem('user', email);
    localStorage.setItem('token', newToken);
  };
  
  const logout = () => {
    clearAuth();
    window.location.href = '/login';
  };
  
  const clearAuth = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('user');
    localStorage.removeItem('token');
  };
  
  const isAuthenticated = !!user && !!token;

  return (
    <AuthContext.Provider value={{ user, token, login, logout, clearAuth, isAuthenticated }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
