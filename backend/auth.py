import json
import os
from typing import Dict, Optional
import hashlib
import logging
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

class UserManager:
    def __init__(self, users_file: str = "users.json"):
        self.users_file = users_file
        self._ensure_users_file()
        
    def _ensure_users_file(self):
        """确保用户文件存在"""
        if not os.path.exists(self.users_file):
            with open(self.users_file, 'w') as f:
                json.dump({"users": []}, f)
    
    def _load_users(self) -> Dict:
        """加载用户数据"""
        with open(self.users_file, 'r') as f:
            return json.load(f)
    
    def _save_users(self, data: Dict):
        """保存用户数据"""
        with open(self.users_file, 'w') as f:
            json.dump(data, f, indent=4)
    
    def _hash_password(self, password: str) -> str:
        """对密码进行哈希处理"""
        hashed = hashlib.sha256(password.encode()).hexdigest()
        logger.debug(f"Password hashed: {hashed}")
        return hashed
    
    def authenticate(self, identifier: str, password: str) -> Optional[Dict]:
        """验证用户登录，支持邮箱或用户名"""
        data = self._load_users()
        hashed_password = self._hash_password(password)
        
        logger.debug(f"Authenticating user: {identifier}")
        logger.debug(f"Stored users: {[user['email'] for user in data['users']]}")
        
        for user in data["users"]:
            # 支持邮箱或用户名登录
            if (user["email"] == identifier or user["email"].split('@')[0] == identifier) and \
               (user["hashed_password"] == hashed_password):
                logger.info(f"Authentication successful for user: {identifier} -> {user['email']}")
                return {
                    "email": user["email"],
                    "role": user["role"]
                }
        
        logger.warning(f"Authentication failed for user: {identifier}")
        return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """根据邮箱获取用户信息"""
        data = self._load_users()
        for user in data["users"]:
            if user["email"] == email:
                # 返回不含密码的用户信息
                return {"email": user["email"], "role": user["role"]}
        return None
    
    def register(self, email: str, password: str, role: str = "user") -> bool:
        """注册新用户"""
        data = self._load_users()
        
        # 检查邮箱是否已存在
        if any(user["email"] == email for user in data["users"]):
            return False
        
        # 添加新用户
        data["users"].append({
            "email": email,
            "hashed_password": self._hash_password(password),
            "password": password,
            "role": role
        })
        
        self._save_users(data)
        return True
    
    def get_user_role(self, email: str) -> Optional[str]:
        """获取用户角色"""
        data = self._load_users()
        for user in data["users"]:
            if user["email"] == email:
                return user["role"]
        return None

async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)):
    """
    获取当前用户信息
    验证本地JWT token
    """
    try:
        from config import SECRET_KEY, ALGORITHM
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if username:
            logger.debug(f"JWT token验证成功: {username}")
            return {"email": username, "username": username, "role": role}
    except jwt.PyJWTError as e:
        logger.debug(f"JWT token验证失败: {e}")

    # JWT验证失败，返回未授权
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, 
        detail="无效token或会话已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"}
    ) 